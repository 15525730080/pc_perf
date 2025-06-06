import asyncio
import datetime
import importlib
import os
import platform
from sqlalchemy import Column, String, Integer, DateTime, inspect, select, or_, Boolean, text
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
        logger.info("sql begin")
        yield session
        await session.commit()
        logger.info("sql success")
    except BaseException as e:
        await session.rollback()
        logger.error(e)
        raise e
    finally:
        logger.info("sql end")
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
    include_child = Column(Boolean, default=False) #当前性能测试任务是否包含子进程性能  


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
                print(f"已为表 {table_name} 添加列: {column_name}")
                
        except Exception as e:
            print(f"升级表 {table_name} 时出错: {e}")


async def create_table():
    await upgrade_tasks_table()
    await update_table_structure()


asyncio.run(create_table())
