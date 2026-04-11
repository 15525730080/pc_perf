"""通用 Cython 构建脚本。

用途：
1. 将 Python 项目中的 .py 编译为 .so/.pyd。
2. 中间 .c 文件只放到临时目录，不污染源码目录。
3. 输出目录只保留编译产物、静态资源和最小启动器 `__main__.py`。
4. 默认直接输出到 `out/`，避免多包一层导致静态资源相对路径失效。
5. 通过 `python -m <输出目录名>` 直接运行编译后的项目。
6. 默认使用更安全的 Cython 指令，优先保证运行时稳定性，避免因关闭边界检查导致段错误。

常见用法：
- 直接按默认配置构建：
    python cython_builder.py

- 指定源码目录、入口模块、入口函数：
    python cython_builder.py --src app --main main --callable main

- 构建后立刻运行，并把后续参数透传给项目入口：
    python cython_builder.py --run -- --host 0.0.0.0 --port 8080

可选配置文件：
- 在项目根目录放一个 `build_config.json`
- 未配置时会使用 DEFAULT_CONFIG
- 示例字段：
    {
      "src_dir": "app",
      "entry_module": "main",
      "entry_callable": "main",
      "out_dir": "out",
      "resources": ["*.json", "*.yaml"],
      "project_resource_paths": ["static", "test_result"],
      "exclude_patterns": ["**/tests/**", "**/__pycache__/**"],
      "compiler_directives": {"boundscheck": true, "wraparound": true}
    }
"""

import argparse
import fnmatch
import importlib.machinery
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from Cython.Build import cythonize
from Cython.Compiler import Options
from setuptools import Distribution
from setuptools.command.build_ext import build_ext

DEFAULT_CONFIG = {
    "src_dir": "app",
    "entry_module": "main",
    "entry_callable": "main",
    "out_dir": "out",
    "resources": ["*.json", "*.yaml", "*.yml", "*.txt", "*.sql", "*.ini"],
    "project_resource_paths": ["static", "test_result"],
    "exclude_patterns": [
        "**/__pycache__/**",
        "**/.DS_Store",
        "**/.git/**",
        "**/.venv/**",
        "**/.fenv/**",
        "**/build/**",
        "**/dist/**",
        "**/out/**",
    ],
    "compiler_directives": {
        # 通用构建器默认保持 Python 语义安全，避免编译后点击功能时触发段错误。
        "boundscheck": True,
        "wraparound": True,
        "language_level": "3",
        "binding": True,
    },
}


def load_config():
    """加载可选配置文件；不存在时直接返回默认配置。"""
    config_path = Path("build_config.json")
    if not config_path.exists():
        return DEFAULT_CONFIG.copy()

    with config_path.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)

    merged = DEFAULT_CONFIG.copy()
    merged.update(loaded)
    merged["compiler_directives"] = {
        **DEFAULT_CONFIG["compiler_directives"],
        **loaded.get("compiler_directives", {}),
    }
    merged["resources"] = loaded.get("resources", DEFAULT_CONFIG["resources"])
    merged["project_resource_paths"] = loaded.get(
        "project_resource_paths", DEFAULT_CONFIG["project_resource_paths"]
    )
    merged["exclude_patterns"] = loaded.get(
        "exclude_patterns", DEFAULT_CONFIG["exclude_patterns"]
    )
    return merged


def parse_args():
    parser = argparse.ArgumentParser(
        description="通用 Python -> Cython 二进制构建器",
        epilog=(
            "示例:\n"
            "  python cython_builder.py\n"
            "  python cython_builder.py --src app --main main --callable main\n"
            "  python cython_builder.py --run -- --host 0.0.0.0 --port 8080\n"
            "  python cython_builder.py --unsafe  # 仅在确认代码无越界风险时再开启"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--src", help="源码根目录，可以是 app，也可以是 src")
    parser.add_argument("--main", help="入口模块，例如 main、app.main、myproj.main")
    parser.add_argument("--callable", dest="entry_callable", help="入口函数名，默认 main")
    parser.add_argument("--out", help="输出目录，默认 out")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="额外排除规则，可重复传入，例如 --exclude '**/tests/**'",
    )
    parser.add_argument(
        "--resource",
        action="append",
        default=[],
        help="额外资源匹配规则，可重复传入，例如 --resource '*.toml'",
    )
    parser.add_argument("--run", action="store_true", help="构建完成后直接运行")
    parser.add_argument(
        "--unsafe",
        action="store_true",
        help="关闭 boundscheck/wraparound 以换取更激进优化，可能引入段错误",
    )
    parser.add_argument(
        "entry_args",
        nargs=argparse.REMAINDER,
        help="透传给入口函数的参数，放在 -- 之后",
    )
    return parser.parse_args()


def normalize_path(path_str: str):
    return Path(path_str).resolve()


def matches_any(path: Path, patterns: list[str], project_root: Path, src_root: Path):
    """同时用项目相对路径和源码相对路径做排除匹配。"""
    candidates = []
    try:
        candidates.append(path.relative_to(project_root).as_posix())
    except ValueError:
        pass
    try:
        candidates.append(path.relative_to(src_root).as_posix())
    except ValueError:
        pass
    candidates.append(path.as_posix())

    for candidate in candidates:
        for pattern in patterns:
            if fnmatch.fnmatch(candidate, pattern):
                return True
    return False


def resolve_entry_source(entry_module: str, src_root: Path, project_root: Path):
    """按模块名解析实际入口文件，兼容 app 布局和 src 布局。"""
    module_path = Path(*entry_module.split("."))
    candidates = [
        project_root / module_path.with_suffix(".py"),
        project_root / module_path / "__init__.py",
        src_root / module_path.with_suffix(".py"),
        src_root / module_path / "__init__.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def collect_source_files(src_root: Path, project_root: Path, exclude_patterns: list[str]):
    """收集所有要参与编译的 .py 文件。"""
    source_files = []
    for path in src_root.rglob("*.py"):
        if not path.is_file():
            continue
        if matches_any(path, exclude_patterns, project_root, src_root):
            continue
        source_files.append(str(path.resolve()))

    if not source_files:
        raise FileNotFoundError(f"未在 {src_root} 下找到可编译的 .py 文件")
    return sorted(source_files)


def is_binary_file(path: Path):
    return any(path.name.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)


def relative_to_root(path: Path, root: Path):
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def copy_compiled_outputs(cmd: build_ext, out_path: Path):
    """只从 build_ext 输出中拷贝真正的二进制模块。"""
    copied = []
    build_root = Path(cmd.build_lib).resolve()
    for output in cmd.get_outputs():
        output_path = Path(output).resolve()
        if not output_path.exists() or not is_binary_file(output_path):
            continue
        rel_path = relative_to_root(output_path, build_root)
        dest = out_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, dest)
        copied.append(dest)
        print(f"  复制二进制: {rel_path}")
    return copied


def copy_resources(
    src_root: Path,
    project_root: Path,
    out_path: Path,
    resource_patterns: list[str],
    exclude_patterns: list[str],
):
    """复制源码树中的静态资源，保持原有目录结构。"""
    for path in src_root.rglob("*"):
        if not path.is_file() or path.suffix == ".py":
            continue
        if matches_any(path, exclude_patterns, project_root, src_root):
            continue
        if not any(fnmatch.fnmatch(path.name, pattern) for pattern in resource_patterns):
            continue
        rel_path = relative_to_root(path.resolve(), project_root)
        dest = out_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        print(f"  复制资源: {rel_path}")


def copy_project_resource_paths(project_root: Path, out_path: Path, resource_paths: list[str]):
    """复制项目根目录下的整目录资源，解决 static/test_result 这类相对路径依赖。"""
    for resource_path in resource_paths:
        source = (project_root / resource_path).resolve()
        if not source.exists() or source == out_path:
            continue

        dest = out_path / source.relative_to(project_root)
        if source.is_dir():
            shutil.copytree(source, dest, dirs_exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
        print(f"  复制项目资源: {source.relative_to(project_root)}")


def build_runtime_paths(src_root: Path, project_root: Path):
    """生成运行时需要插入到 sys.path 的目录列表。"""
    runtime_paths = ["."]
    src_rel = relative_to_root(src_root.resolve(), project_root)
    if str(src_rel) not in {"", "."}:
        runtime_paths.append(src_rel.as_posix())
    return runtime_paths


def write_launcher(out_path: Path, entry_module: str, entry_callable: str, runtime_paths: list[str]):
    """生成最小启动器：保留一个 __main__.py，业务代码仍然全是二进制。"""
    runtime_paths_literal = repr(runtime_paths)
    launcher = f'''import importlib
import sys
from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parent
for rel in {runtime_paths_literal}:
    candidate = (RUNTIME_ROOT / rel).resolve()
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

entry_module = importlib.import_module("{entry_module}")
entry_callable = getattr(entry_module, "{entry_callable}")

if __name__ == "__main__":
    entry_callable()
'''
    (out_path / "__main__.py").write_text(launcher, encoding="utf-8")


def run_compiled_package(out_path: Path, passthrough_args: list[str]):
    command = [sys.executable, "-m", out_path.name, *passthrough_args]
    print(f"🏃 直接运行: {' '.join(command)}")
    subprocess.run(command, cwd=out_path.parent, check=True)


def build():
    args = parse_args()
    conf = load_config()

    project_root = Path.cwd().resolve()
    src_dir = args.src or conf.get("src_dir", DEFAULT_CONFIG["src_dir"])
    entry_module = args.main or conf.get("entry_module", DEFAULT_CONFIG["entry_module"])
    entry_callable = args.entry_callable or conf.get(
        "entry_callable", DEFAULT_CONFIG["entry_callable"]
    )
    out_dir = args.out or conf.get("out_dir", DEFAULT_CONFIG["out_dir"])
    resources = conf.get("resources", DEFAULT_CONFIG["resources"]) + args.resource
    project_resource_paths = conf.get(
        "project_resource_paths", DEFAULT_CONFIG["project_resource_paths"]
    )
    exclude_patterns = conf.get("exclude_patterns", DEFAULT_CONFIG["exclude_patterns"]) + args.exclude
    directives = dict(conf.get("compiler_directives", DEFAULT_CONFIG["compiler_directives"]))
    if args.unsafe:
        directives["boundscheck"] = False
        directives["wraparound"] = False

    src_root = normalize_path(src_dir)
    out_path = Path(out_dir).resolve()

    if not src_root.exists():
        raise FileNotFoundError(f"源码目录不存在: {src_root}")

    entry_source = resolve_entry_source(entry_module, src_root, project_root)
    if entry_source is None:
        raise FileNotFoundError(f"无法解析入口模块 {entry_module} 对应的源码文件")

    print(f"🧹 清理目录: {out_path}")
    if out_path.exists():
        shutil.rmtree(out_path)
    out_path.mkdir(parents=True, exist_ok=True)

    source_files = collect_source_files(src_root, project_root, exclude_patterns)
    if str(entry_source) not in source_files:
        source_files.append(str(entry_source))
        source_files.sort()

    print(f"🚀 [Cython] 编译 {len(source_files)} 个 Python 文件...")
    Options.annotate = False

    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        ext_modules = cythonize(
            source_files,
            compiler_directives=directives,
            build_dir=str(temp_dir),
            quiet=True,
        )

        dist = Distribution(
            {
                "ext_modules": ext_modules,
                "script_name": "setup.py",
                "script_args": ["build_ext"],
            }
        )
        dist.parse_config_files()

        cmd = build_ext(dist)
        cmd.build_lib = str(temp_dir)
        cmd.build_temp = str(temp_dir / "_build")
        cmd.inplace = False
        cmd.ensure_finalized()
        cmd.run()

        print("📦 收集二进制产物...")
        copied = copy_compiled_outputs(cmd, out_path)
        if not copied:
            raise RuntimeError("没有找到任何编译产物，请检查 Cython 配置")

    print("📦 复制静态资源...")
    copy_resources(src_root, project_root, out_path, resources, exclude_patterns)
    copy_project_resource_paths(project_root, out_path, project_resource_paths)

    print("🚪 暴露运行入口...")
    runtime_paths = build_runtime_paths(src_root, project_root)
    write_launcher(out_path, entry_module, entry_callable, runtime_paths)

    print("\n✅ 编译成功！")
    print(f"📍 产物路径: {out_path}")
    print(f"🚀 运行命令: cd {out_path.parent} && python -m {out_path.name}")

    if args.run:
        passthrough_args = list(args.entry_args)
        if passthrough_args[:1] == ["--"]:
            passthrough_args = passthrough_args[1:]
        run_compiled_package(out_path, passthrough_args)


if __name__ == "__main__":
    build()
