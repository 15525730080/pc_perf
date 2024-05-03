import asyncio
import datetime
import os
import platform
from sqlalchemy import Column, String, Integer, DateTime, select, or_
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager
from sqlalchemy_serializer import SerializerMixin
from sqlalchemy.orm import declarative_base
from log import log as logger

logger.info("工作空间{0}".format(os.getcwd()))
db_path = os.path.join(os.getcwd(), "task.sqlite")
logger.info("db path {0}".format(db_path))
async_engine = create_async_engine('sqlite+aiosqlite:///{0}'.format(db_path), echo=False)
logger.info("current path {0}".format(os.getcwd()))
AsyncSessionLocal = sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


@asynccontextmanager
async def async_connect():
    session = AsyncSessionLocal()
    try:
        logger.info("sql begin")
        yield session
        await session.commit()
        logger.info("sql success")
    except Exception as e:
        await session.rollback()
        raise e
    finally:
        logger.info("sql end")
        await session.close()


async def update_table_structure():
    async with async_engine.begin() as conn:
        # 反射现有的数据库结构
        await conn.run_sync(Base.metadata.create_all)


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
    async def create_task(cls, pid, pid_name, file_dir, name):
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
                                target_pid=pid, platform=platform.system(), name=name, target_pid_name=pid_name)
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


async def create_table():
    await update_table_structure()


asyncio.run(create_table())
