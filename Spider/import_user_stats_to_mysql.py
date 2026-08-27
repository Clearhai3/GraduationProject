# -*- coding: utf-8 -*-
"""
用户评分统计落库脚本
功能: 在本地运行 3 个用户分析 MapReduce 管道, 把结果写入 anime_db 的 4 张统计表
用法: python import_user_stats_to_mysql.py
"""

import subprocess   # 在 Python 里执行系统命令 (管道)
import datetime     # 生成"今天"的日期
import pymysql      # MySQL 连接库
import os

# 1. 配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "user_ratings.csv")
MAPREDUCE = os.path.join(SCRIPT_DIR, "user_ratings_mapreduce.py")
PYTHON_CMD = "python"

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",
    "database": "anime_db",
    "charset": "utf8mb4",
}

# 2. 工具函数
def run_pipeline(mapper, reducer):
    """执行 cat文件 | mapper | sort | reducer 管道, 返回输出行列表"""
    cmd = (f"cat {CSV_FILE} | {PYTHON_CMD} {MAPREDUCE} {mapper} "
           f"| sort | {PYTHON_CMD} {MAPREDUCE} {reducer}")
    # 本地模拟必须手动 sort: Hadoop 的 Reducer 依赖"相同 key 连续出现"
    result = subprocess.run(cmd, shell = True, capture_output = True, text = True)
    if result.returncode != 0:
        print(f"[错误] 管道运行失败 ({mapper}/{reducer}):")
        print(result.stderr)
        return []
    return result.stdout.strip().splitlines()

def insert_rows(cursor, table, columns, rows):
    """把解析好的 rows 批量插入指定表"""
    if not rows:
        return
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    cursor.executemany(sql, rows)
    print(f"  -> {table}: 插入 {len(rows)} 行")

# 3. 建表 (表不存在才建, 避免重复运行报错)
def create_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_score_distribution (
            rate            INT NOT NULL,   -- 评分值 1~10
            rating_count    INT NOT NULL,   -- 该分值有多少条评分
            stat_date       DATE NOT NULL,  -- 统计日期
            PRIMARY KEY (rate, stat_date)
        ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_stats (
            activity_level VARCHAR(20) NOT NULL,    -- 活跃层级: 1-10条 / 11-50条 / ...
            user_count     INT NOT NULL,            -- 该层级的用户数
            stat_date      DATE NOT NULL,
            PRIMARY KEY (activity_level, stat_date)
        ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activity_top (
            rank_num        INT NOT NULL,       -- 排名 1~10
            user_id         INT NOT NULL,       -- 用户 ID
            rating_count    INT NOT NULL,       -- 该用户的评分条数
            stat_date       DATE NOT NULL, 
            PRIMARY KEY (rank_num, stat_date)
        ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
    """) 

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hot_anime (
            rank_num        INT NOT NULL,       -- 排名 1~20
            anime_id        INT NOT NULL,       -- 动漫 ID
            rating_count    INT NOT NULL,       -- 被多少用户评分
            stat_date       DATE NOT NULL,
            PRIMARY KEY (rank_num, stat_date)
        ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
    """)

# 4. 装载函数 (共同套路: 跑管道 -> 按制表符拆行 -> 存成元组 -> 批量插入)

# 评分分布 -> user_score_distribution
def load_score_dist(cursor):
    lines = run_pipeline("mapper_score", "reducer_score")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append((int(parts[0]), int(parts[1]), today))
    insert_rows(cursor, "user_score_distribution", 
                ["rate", "rating_count", "stat_date"], rows)

# 用户活跃度 (分层 + Top)  ->  user_activity_stats / user_activity_top
def load_user_activity(cursor):
    lines = run_pipeline("mapper_user", "reducer_user")
    today = datetime.date.today()
    stats_rows = []     # 分层
    top_rows = []       # Top 榜
    for line in lines:
        # reducer_user 输出两种行, 必须按前缀区分:
        # "活跃分层: 11-50条\t2558"     -> 分层
        # "活跃Top:1\t9861\t980"       -> Top 榜
        if line.startswith("活跃分层:"):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            level = parts[0].replace("活跃分层:", "")
            stats_rows.append((level, int(parts[1]), today))
        elif line.startswith("活跃Top:"):
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            rank = int(parts[0].replace("活跃Top:", ""))
            top_rows.append((rank, int(parts[1]), int(parts[2]), today))
    insert_rows(cursor, "user_activity_stats",
                ["activity_level", "user_count", "stat_date"], stats_rows)
    insert_rows(cursor, "user_activity_top",
                ["rank_num", "user_id", "rating_count", "stat_date"], top_rows)

# 热门动漫  ->  hot_anime
def load_hot_anime(cursor):
    lines = run_pipeline("mapper_anime", "reducer_anime")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rank = int(parts[0].replace("热门:", ""))
        rows.append((rank, int(parts[1]), int(parts[2]), today))
    insert_rows(cursor, "hot_anime",
                ["rank_num", "anime_id", "rating_count", "stat_date"], rows)

# 主程序
def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            create_tables(cursor)       # 先建表
            load_score_dist(cursor)     # 评分分布
            load_user_activity(cursor)  # 用户活跃度 (分层 + Top)
            load_hot_anime(cursor)      # 热门动漫
        conn.commit()       # 统一提交, 数据才真正生效
        print("用户统计全部写入完成!")
    except Exception as e:
        conn.rollback()     # 出错则全部撤销, 不留半截数据
        print(f"[错误] {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
