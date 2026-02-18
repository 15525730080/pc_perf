#coding=utf-8
from setuptools import setup, Extension
from Cython.Build import cythonize
from pathlib import Path
import re
import shutil  # 用于删除整个文件夹

# ====================== 配置区 ======================
PROJECT_ROOT = Path(__file__).parent

# 1. 临时存放区（放 .c, .obj 等中间文件，编译完就删）
TEMP_DIR = PROJECT_ROOT / "build_temp_trash"

# 2. 最终产物区（只放编译好的 .pyd/.so 文件）
DIST_DIR = PROJECT_ROOT / "cython_build"

EXCLUDE_FILES = [
    "cython_setup.py",
    "main.py",
    "test_*.py",
    "pc_perf.py"
]
# 排除目录中加入临时目录和产物目录，防止死循环扫描
EXCLUDE_DIRS = ["venv", "__pycache__", ".git", "cython_build", "build_temp_trash", ".fenv"]
# ======================================================
STATIC_RESOURCES = [
    "test_result",      # 静态资源文件夹
]

def is_valid_filename(file_path: Path) -> bool:
    """检查文件名是否合法"""
    file_path = Path(file_path)
    filename = file_path.name
    if filename.count(".") > 1: return False
    module_name = file_path.stem
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", module_name): return False
    return True

def collect_py_files():
    """收集所有合法的 .py 文件并生成 Extension"""
    py_files = []
    extensions = []
    skipped_files = []
    
    for file_path in PROJECT_ROOT.rglob("*.py"):
        if any(exclude_dir in file_path.parts for exclude_dir in EXCLUDE_DIRS): continue
        if any(file_path.match(pattern) for pattern in EXCLUDE_FILES): continue
        if not is_valid_filename(file_path):
            skipped_files.append(str(file_path))
            continue
        
        # 生成模块名 (例如: utils/helper.py -> utils.helper)
        relative_path = file_path.relative_to(PROJECT_ROOT)
        module_name = relative_path.with_suffix("").as_posix().replace("/", ".")
        
        extensions.append(Extension(name=module_name, sources=[str(file_path)]))
        py_files.append(str(file_path))
    
    if skipped_files:
        print(f"\n⚠️  跳过了 {len(skipped_files)} 个非法文件名的文件。")
    
    return py_files, extensions

def sync_static_resources():
    """将静态资源拷贝到编译后的目录"""
    print("\n📦 正在迁移静态资源...")
    for item_name in STATIC_RESOURCES:
        src = PROJECT_ROOT / item_name
        dst = DIST_DIR / item_name
        
        if not src.exists():
            print(f"  ⚠️  跳过：找不到资源 {item_name}")
            continue

        # 如果是目录，递归拷贝；如果是文件，直接拷贝
        if src.is_dir():
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  ✅ 已同步目录: {item_name}")
        else:
            shutil.copy2(src, dst)
            print(f"  ✅ 已同步文件: {item_name}")

def cleanup_temp_dir():
    """彻底删除临时文件夹"""
    if TEMP_DIR.exists():
        print(f"\n🧹 正在清理临时构建文件...")
        try:
            shutil.rmtree(TEMP_DIR)
            print("✅ 临时文件夹已彻底删除 (包含所有 .c 和 .obj 文件)")
        except Exception as e:
            print(f"❌ 清理失败: {e}")

if __name__ == "__main__":
    # 0. 准备工作
    if TEMP_DIR.exists(): shutil.rmtree(TEMP_DIR) # 先清理旧的垃圾
    if DIST_DIR.exists(): shutil.rmtree(DIST_DIR) # 先清理旧的产物（可选，看需求）
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    py_files, extensions = collect_py_files()
    
    if not py_files:
        print("❌ 没有找到合法的 .py 文件可以编译")
        exit(1)
    
    print(f"✅ 准备编译 {len(py_files)} 个文件...")
    
    try:
        # 1. 编译 (将 .py 转为 .c)
        # 重点：build_dir 指定为临时目录，这样 .c 文件全都会生成在这个文件夹里
        print("🔨 正在生成 C 代码...")
        cythonized_extensions = cythonize(
            extensions,
            compiler_directives={
                "language_level": "3",
                "embedsignature": True,
                "boundscheck": False,
                "wraparound": False
            },
            build_dir=str(TEMP_DIR), # .c 文件生成在这里
            quiet=True,
            force=True
        )
        
        # 2. 构建 (将 .c 编译为 .pyd/.so)
        print("🚀 正在编译二进制模块...")
        setup(
            ext_modules=cythonized_extensions,
            script_args=[
                "build_ext",
                "--build-lib", str(DIST_DIR), # 最终 .pyd 放这里
                "--build-temp", str(TEMP_DIR) # 编译产生的中间 .obj 放这里
            ]
        )
        sync_static_resources()
        print(f"\n🎉 编译成功！最终文件在：{DIST_DIR}")
        
    except Exception as e:
        print(f"\n❌ 编译过程中发生错误: {e}")
        
    finally:
        # 3. 最后清理 (无论成功失败，都尝试清理垃圾)
        cleanup_temp_dir()