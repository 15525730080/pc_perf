import sqlite3
import os

# 数据库路径
db_path = "task.sqlite"

# 确认数据库文件存在
if not os.path.exists(db_path):
    print(f"错误: 找不到数据库文件 {db_path}")
    exit(1)

# 连接到SQLite数据库
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # 首先查询数据库中包含旧路径的记录
    cursor.execute(
        "SELECT id, file_dir FROM tasks WHERE file_dir LIKE '%pc_perf - 副本%'"
    )
    records = cursor.fetchall()

    if not records:
        print("没有找到包含旧路径 'pc_perf - 副本' 的记录!")
    else:
        print(f"找到 {len(records)} 条记录包含旧路径:")
        for record in records:
            print(f"ID: {record[0]}, 路径: {record[1]}")

        # 执行更新
        cursor.execute(
            """
            UPDATE tasks 
            SET file_dir = REPLACE(file_dir, 'E:\\WorkArea\\pc_perf - 副本', 'E:\\WorkArea\\pc_perf') 
            WHERE file_dir LIKE '%pc_perf - 副本%'
        """
        )
        conn.commit()

        print(f"\n成功更新了 {cursor.rowcount} 条记录!")

        # 再次查询确认更新结果
        cursor.execute(
            "SELECT id, file_dir FROM tasks WHERE id IN ({})".format(
                ",".join([str(record[0]) for record in records])
            )
        )
        updated_records = cursor.fetchall()
        print("\n更新后的路径:")
        for record in updated_records:
            print(f"ID: {record[0]}, 新路径: {record[1]}")

except sqlite3.Error as e:
    print(f"数据库错误: {e}")
    conn.rollback()

finally:
    # 关闭连接
    cursor.close()
    conn.close()

print("\n路径更新完成!")

# BUG記錄
# 高级对比分析失败: Object of type bool_ is not JSON serializable
