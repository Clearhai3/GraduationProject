# -*- coding: utf-8 -*-
"""
结果落库脚本
功能: 在本地运行 8 个 MapReduce 分析管道，把结果写入 anime_db 的各统计表
用法: python import_to_mysql.py
"""

import subprocess       # 在 Python 里执行系统命令(管道)
import datetime         # 生成"今天"的日期
import pymysql          # MySQL 连接库
import os               # 顶部加上
# subprocess 是本脚本的引擎——Python 本身不能直接跑 shell 管道，靠它把命令交给系统执行。

# 1. 配置区(按需修改)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "anime_cleaned.csv")                  # 清洗后的数据文件
MAPREDUCE = os.path.join(SCRIPT_DIR, "anime_data_mapreduce.py")           # 你的分析脚本
PYTHON_CMD = "python"                           # Linux 上若是 python3 就改成

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",         # 改成自己的密码
    "database": "anime_db",
    "charset": "utf8mb4",           # 必须 utf8mb4，否则中文乱码
}
# DB_CONFIG 是数据库连接的字典。
# 把可变信息集中放在顶部，是脚本的通用习惯————改配置不用动下面逻辑。

# 2. 工具函数
# 拼命令并执行
def run_pipeline(mapper, reducer):
    """执行 cat文件 | mapper | sort | reducer 管道，返回输出行列表"""
    cmd = (f"cat {CSV_FILE} | {PYTHON_CMD} {MAPREDUCE} {mapper} "
           f"| sort | {PYTHON_CMD} {MAPREDUCE} {reducer}")
    # 这条命令是本地测试的管道
    # 注意 sort 很关键: Hadoop 的 Reducer 依赖"相同 key 连续出现"，本地模拟就必须手动 sort。
    result = subprocess.run(cmd, shell = True, capture_output = True, text = True)
    # shell = True: 允许执行带 | 的完整命令
    # capture_output = True: 把命令的输出抓进内存，而不是打印到屏幕
    # text = True: 以文本形式返回 (否则是字节)
    if result.returncode != 0:
    # returncode -> 0: 正常结束，一切顺利
    # returncode -> 非 0 (1、2、127...): 异常结束，出事了
        print(f"[错误] 管道运行失败 ({mapper}/{reducer}):")
        print(result.stderr)
        # stderr -> 错误信息/日志输出到哪 (报错、警告走这里)

        # 标准输入 stdin -> 数据从哪进来 (你的管道里 cat 输出的数据就是从 stdin 流进来的)
        # 标准输出 stdout -> 正常结果输出到哪 (mapreduce 的统计结果，就是走 stdout)
        # stdout 只传"正经结果", stderr 只传"发生了什么"。
        # 命令失败了，失败原因 (比如"找不到文件""权限不够") 全部写在 stderr 里，而不是 stdout。
        return []
        # 返回空列表，让上层跳过这一维度
    return result.stdout.strip().splitlines()
    # splitlines() 负责"按行切开"

# cursor: 执行 SQL 的"手"       例子: 来自 conn.cursor()
# table: 目标表名 (字符串)      例子: "anime_type_stats"
# columns: 列名列表             例子: ["anime_type", "anime_count", ...]
# rows: 数据列表，每个元素是一行元组    例子: [("TV", 120, 7.6, 12500, date), ...] 
def insert_rows(cursor, table, columns, rows):
    """把解析好的 rows 批量插入指定表"""
    if not rows:
        return
    placeholders = ", ".join(["%s"] * len(columns))
    # 比如 5 列 → "%s, %s, %s, %s, %s" 。
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    cursor.executemany(sql, rows)       # executemany = 一次批量插多行，比逐条快很多
    print(f"  -> {table}: 插入 {len(rows)} 行")

# 3. 8个装载函数
# 输出格式(由 mapreduce 脚本决定): 维度值\t数量\t平均评分\t总评分人数
# 共同套路: 跑管道 -> 按制表符拆行 -> 存成元组 -> 批量插入

# 把 mapreduce 输出的每行文本，转成 MySQL 能接收的 "元组"，攒够一批后批量插入。
# 类型分布  ->  anime_type_stats
def load_type_stats(cursor):
# 接收一个 cursor (执行 SQL 的"手")，函数本身不返回值，数据直接写进数据库。
    lines = run_pipeline("mapper_type", "reducer_type")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rows.append((parts[0], int(parts[1]), float(parts[2]), int(parts[3]), today))
    insert_rows(cursor, "anime_type_stats",
                ["anime_type", "anime_count", "avg_score", "total_score_count", "stat_date"], rows)

# 年份趋势  ->  anime_year_stats
def load_year_stats(cursor):
    lines = run_pipeline("mapper_year", "reducer_year")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rows.append((parts[0], int(parts[1]), float(parts[2]), int(parts[3]), today))
    insert_rows(cursor, "anime_year_stats",
                ["year_value", "anime_count", "avg_score", "total_score_count", "stat_date"], rows)

# 季度趋势  ->  season_stats
def load_season_stats(cursor):
    lines = run_pipeline("mapper_season", "reducer_season")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rows.append((parts[0], int(parts[1]), float(parts[2]), int(parts[3]), today))
    insert_rows(cursor, "season_stats",
                ["season", "anime_count", "avg_score", "total_score_count", "stat_date"], rows)

# 评分区间  ->  score_distribution
def load_score_dist(cursor):
    lines = run_pipeline("mapper_score", "reducer_score")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append((parts[0], int(parts[1]), today))
    insert_rows(cursor, "score_distribution",
                ["score_range", "anime_count", "stat_date"], rows)

# 导演统计  ->  director_stats
def load_director_stats(cursor):
    lines = run_pipeline("mapper_director", "reducer_director")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append((parts[0], int(parts[1]), today))
    insert_rows(cursor, "director_stats",
                ["director", "work_count", "stat_date"], rows)

# 声优统计  ->  seiyuu_stats
def load_seiyuu_stats(cursor):
    lines = run_pipeline("mapper_seiyuu", "reducer_seiyuu")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append((parts[0], int(parts[1]), today))
    insert_rows(cursor, "seiyuu_stats",
                ["seiyuu", "work_count", "stat_date"], rows)

# 话数分布  ->  episodes_distribution
def load_episodes_dist(cursor):
    lines = run_pipeline("mapper_episodes", "reducer_episodes")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append((parts[0], int(parts[1]), today))
    insert_rows(cursor, "episodes_distribution", 
                ["episodes_range", "anime_count", "stat_date"], rows)

# TOP20榜  ->  top_anime
def load_top_anime(cursor):
    lines = run_pipeline("mapper_top", "reducer_top")
    today = datetime.date.today()
    rows = []
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rows.append((int(parts[0]), parts[1], float(parts[2]), int(parts[3]), today))
    insert_rows(cursor, "top_anime",
                ["rank_num", "anime_name", "score", "score_count", "stat_date"], rows)

# 主程序
def main():
    conn = pymysql.connect(**DB_CONFIG)     # 打开数据库连接
    try:
        with conn.cursor() as cursor:       # cursor = 执行 SQL 的"手"，在连接上开一个"游标"
            load_type_stats(cursor)
            load_year_stats(cursor)
            load_season_stats(cursor)
            load_score_dist(cursor)
            load_director_stats(cursor)
            load_seiyuu_stats(cursor)
            load_episodes_dist(cursor)
            load_top_anime(cursor)
        conn.commit()               # 统一提交，数据才真正生效
        print("全部写入完成!")
    except Exception as e:          # 出错则全部撤销，不留半截数据
        conn.rollback()
        print(f"[错误] {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
