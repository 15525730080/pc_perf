import asyncio
import datetime
import os
import platform
import json
from sqlalchemy import Column, String, Integer, DateTime, inspect, select, or_, Boolean, text, Text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy.orm import declarative_base
from app.log import log as logger

logger.info("工作空间{0}".format(os.getcwd()))
db_path = os.path.join(os.getcwd(), "task.sqlite")
logger.info("db path {0}".format(db_path))
async_engine = create_async_engine('sqlite+aiosqlite:///{0}'.format(db_path), echo=False,
                                   pool_pre_ping=True, connect_args={'check_same_thread': False}, pool_recycle=1800)
logger.info("current path {0}".format(os.getcwd()))
AsyncSessionLocal = sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=True,
                                 autocommit=False, autoflush=False)
Base = declarative_base()


@asynccontextmanager
async def async_connect():
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except BaseException as e:
        await session.rollback()
        logger.error("SQL EXEC ERROR".format(e))
        raise e
    finally:
        await session.close()


class Task(Base, SerializerMixin):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime, default=None)
    end_time = Column(DateTime, default=None)
    serialno = Column(String(255), default=None)
    status = Column(Integer)  # 0未开始, 1 执行中 , 2 执行完成 3.暂停
    file_dir = Column(String(255), default=None)  # 存储csv文件的路径
    target_pid = Column(Integer)  # 被测进程pid
    target_pid_name = Column(String(255), default=None)  # 被测进程pid 名称
    monitor_pid = Column(Integer, default=None)  # 当前任务运行的进程pid，任务执行的进程，里面有各个性能指标的线程
    platform = Column(String(50), default="win")  # win | mac | linux 任务
    name = Column(String(255), default=None)  # 任务名称
    include_child = Column(Boolean, default=False)  # 当前性能测试任务是否包含子进程性能
    version = Column(String(50), default=None)  # 应用版本信息
    is_baseline = Column(Boolean, default=False)  # 是否为基线版本


class ComparisonReport(Base, SerializerMixin):
    """对比报告表"""
    __tablename__ = 'comparison_reports'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), default=None)  # 报告名称
    create_time = Column(DateTime, default=datetime.datetime.now)  # 创建时间
    task_ids = Column(Text, default=None)  # 存储JSON格式的任务ID列表
    base_task_id = Column(Integer, default=None)  # 基准任务ID
    report_path = Column(String(255), default=None)  # 报告文件路径
    description = Column(Text, default=None)  # 报告描述


class TaskLabel(Base, SerializerMixin):
    __tablename__ = 'task_label'
    id = Column(Integer, primary_key=True, autoincrement=True)
    start_time = Column(DateTime, default=None)  # 标签开始
    end_time = Column(DateTime, default=None)  # 标签结束
    label_name = Column(String(255), default=None)  # 标签名称


class TaskCollection(object):

    @classmethod
    async def set_task_running(cls, task_id, monitor_pid):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.id == task_id))
                task = result.scalars().first()
                assert task, "NOT FIND TASK"
                assert task.status == 0, "TASK RUNNING FAIL, TASK STATUS IS {0}".format(task.status)
                task.status = 1
                task.monitor_pid = monitor_pid
                return task.to_dict()

    @classmethod
    async def get_all_task(cls):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task))
                task = result.scalars().fetchall()
                result_list = [t.to_dict() for t in task]
                result_list.sort(key=lambda x: x.get("start_time"), reverse=True)
                return result_list

    @classmethod
    async def get_item_task(cls, task_id):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.id == task_id))
                task = result.scalars().first()
                assert task, "NOT FIND TASK"
                return task.to_dict()

    @classmethod
    async def get_all_stop_task_monitor_pid(cls):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.status == 2))
                tasks = result.scalars().fetchall()
                return [task.monitor_pid for task in tasks]

    @classmethod
    async def create_task(cls, pid, pid_name, file_dir, name, include_child):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(
                    select(Task).filter(Task.target_pid == pid).filter(or_(
                        Task.status == 0,
                        Task.status == 1,
                    )))
                task = result.scalars().first()
                assert not task, "MONITOR PID {0} TASK {1} IS RUN".format(pid, task.name)
                new_task = Task(start_time=datetime.datetime.now(), serialno=platform.node(), status=0,
                                target_pid=pid, platform=platform.system(), name=name, target_pid_name=pid_name,
                                include_child=include_child)
                session.add(new_task)
                await session.flush()
                file_dir = os.path.join(file_dir, str(new_task.id))
                new_task.file_dir = file_dir
                await session.flush()
                return new_task.id, file_dir

    @classmethod
    async def stop_task(cls, task_id):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.id == task_id))
                task = result.scalars().first()
                assert task, "NOT FIND TASK"
                assert task.status != 0, "TASK NOT RUNNING, TASK STATUS IS {0}".format(task.status)
                task.status = 2
                task.end_time = datetime.datetime.now()
                return task.to_dict()

    @classmethod
    async def delete_task(cls, task_id):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.id == task_id))
                task = result.scalars().first()
                assert task, "NOT FIND TASK"
                assert task.status != 1, "TASK RUNNING NOT DELETE, TASK STATUS IS {0}".format(task.status)
                res = task.to_dict()
                await session.delete(task)
                return res

    @classmethod
    async def change_task_name(cls, task_id, new_name):
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.id == task_id))
                task = result.scalars().first()
                assert task, "NOT FIND TASK"
                task.name = new_name
                return task.to_dict()

    @classmethod
    async def set_task_version(cls, task_id, version):
        """设置任务的版本信息"""
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.id == task_id))
                task = result.scalars().first()
                assert task, "未找到任务"
                task.version = version
                return task.to_dict()
    
    @classmethod
    async def set_task_baseline(cls, task_id, is_baseline=True):
        """设置任务为基线版本"""
        async with async_connect() as session:
            async with session.begin():
                # 如果需要设置为基线，先将所有其他任务的基线标记清除
                if is_baseline:
                    result = await session.execute(select(Task).filter(Task.is_baseline == True))
                    baseline_tasks = result.scalars().fetchall()
                    for baseline_task in baseline_tasks:
                        baseline_task.is_baseline = False
                
                # 设置当前任务的基线标记
                result = await session.execute(select(Task).filter(Task.id == task_id))
                task = result.scalars().first()
                assert task, "未找到任务"
                task.is_baseline = is_baseline
                return task.to_dict()
    
    @classmethod
    async def get_baseline_task(cls):
        """获取基线任务"""
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(Task).filter(Task.is_baseline == True))
                task = result.scalars().first()
                return task.to_dict() if task else None


class ComparisonReportCollection:
    """对比报告集合类"""
    
    @classmethod
    async def create_report(cls, name, task_ids, base_task_id=None, description=None):
        """创建对比报告"""
        async with async_connect() as session:
            async with session.begin():
                # 将任务ID列表序列化为JSON字符串
                task_ids_json = json.dumps(task_ids)
                
                # 创建新的对比报告
                report = ComparisonReport(
                    name=name,
                    create_time=datetime.datetime.now(),
                    task_ids=task_ids_json,
                    base_task_id=base_task_id,
                    description=description
                )
                session.add(report)
                await session.flush()
                return report.to_dict()
    
    @classmethod
    async def get_report(cls, report_id):
        """获取对比报告"""
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(ComparisonReport).filter(ComparisonReport.id == report_id))
                report = result.scalars().first()
                assert report, "未找到对比报告"
                return report.to_dict()
    
    @classmethod
    async def get_all_reports(cls):
        """获取所有对比报告"""
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(ComparisonReport))
                reports = result.scalars().fetchall()
                report_list = [r.to_dict() for r in reports]
                report_list.sort(key=lambda x: x.get("create_time"), reverse=True)
                return report_list
    
    @classmethod
    async def update_report(cls, report_id, **kwargs):
        """更新对比报告"""
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(ComparisonReport).filter(ComparisonReport.id == report_id))
                report = result.scalars().first()
                assert report, "未找到对比报告"
                
                # 更新报告属性
                for key, value in kwargs.items():
                    if hasattr(report, key):
                        setattr(report, key, value)
                
                return report.to_dict()
    
    @classmethod
    async def delete_report(cls, report_id):
        """删除对比报告"""
        async with async_connect() as session:
            async with session.begin():
                result = await session.execute(select(ComparisonReport).filter(ComparisonReport.id == report_id))
                report = result.scalars().first()
                assert report, "未找到对比报告"
                
                # 保存报告数据用于返回
                report_data = report.to_dict()
                
                # 删除报告
                await session.delete(report)
                
                return report_data


async def update_table_structure():
    async with async_engine.begin() as conn:
        # 反射现有的数据库结构
        await conn.run_sync(Base.metadata.create_all)


async def upgrade_tasks_table():
    """检查并升级 tasks 表，添加所有缺失的列"""
    db_path = os.path.join(os.getcwd(), "task.sqlite")

    # 如果数据库文件不存在，无需升级
    if not os.path.exists(db_path):
        return

    async with async_engine.begin() as conn:
        table_name = Task.__tablename__

        try:
            # 获取数据库中实际的列名
            result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
            db_columns = [row[1] for row in result.fetchall()]

            # 获取模型中定义的列名
            model_columns = [column.name for column in Task.__table__.columns]

            # 找出缺失的列
            missing_columns = set(model_columns) - set(db_columns)

            # 为每个缺失的列生成并执行 ALTER TABLE 语句
            for column_name in missing_columns:
                column = getattr(Task, column_name)
                column_type = str(column.type)

                # SQLite 对 BOOLEAN 类型的特殊处理
                if "BOOLEAN" in column_type.upper():
                    column_type = "INTEGER"  # SQLite 使用 INTEGER 存储布尔值

                # 获取默认值（如果有）
                default = None
                if column.default is not None:
                    default = column.default.arg
                    if isinstance(default, str):
                        default = f"'{default}'"
                    elif isinstance(default, bool):
                        default = 1 if default else 0  # 将布尔值转换为整数

                # 构建 ALTER TABLE 语句
                alter_stmt = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                if default is not None:
                    alter_stmt += f" DEFAULT {default}"

                # 执行语句
                await conn.execute(text(alter_stmt))
                logger.info(f"已为表 {table_name} 添加列: {column_name}")

        except Exception as e:
            logger.error(f"升级表 {table_name} 时出错: {e}")


async def create_table():
    """创建数据库表"""
    # 检查数据库是否存在，不存在则创建
    if not os.path.exists(db_path):
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表创建完成")
    else:
        # 如果数据库已存在，检查是否需要更新表结构
        await update_table_structure()
        logger.info("数据库表结构更新完成")
    
    # 检查并升级tasks表的结构
    await upgrade_tasks_table()


# 移除这里的asyncio.run调用，避免事件循环冲突
# 数据库表将在应用启动时创建
