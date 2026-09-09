# -*- coding: utf-8 -*-
"""
    ItemCF 协同过滤 - Job1: 共现矩阵
    功能: 从用户评分数据计算动漫之间的共现矩阵
    输入: HDFS 上 /user/data/user_ratings.csv  (user_id, anime_id, rate)
    输出: 两类中间结果
        1. 共现: {动漫A}|{动漫B} \t 1  (两部动漫被同一用户评过 -> 共现一次)
        2. 单品: {动漫A} \t 1          (这部动漫被一个用户评过 -> 单品计数加一)
    后续: Job2 用这两张计算动漫相似度
"""

# -- 头部导入 --
import sys
import logging

# -- 日志配置 --
# stdout 是数据通道, 日志必须走 stderr
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("itemcf_job1")

# -- 工具函数 --
def parse_rating_line(line):
    """
    解析一行评分 CSV, 返回 (user_id, anime_id, rate)。
    解析失败返回 None。
    """
    line = line.strip()
    if not line:
        return None
    if line.lstrip("\ufeff").startswith("user_id"):
        return None     # 跳过表头
    parts = line.split(",")
    if len(parts) < 3:
        return None     # 防御: 字段不齐跳过

    try:
        user_id  = int(parts[0])
        anime_id = int(parts[1])
        rate     = int(parts[2])
    except (ValueError, TypeError):
        return None
    return (user_id, anime_id, rate)

# -- Mapper: 按用户分组 --
# map 输出: 用户:{user_id}\t{anime_id}
def mapper():
    """
    共现矩阵 Mapper。
    把每行评分转成 "用户:{user_id}\t{anime_id}"。
    目的: 让 reducer 能按用户分组, 拿到"这个用户评过的全部动漫"。
    """
    for line in sys.stdin:
        record = parse_rating_line(line)
        if not record:
            continue
        user_id, anime_id, rate = record
        print(f"用户:{user_id}\t{anime_id}")
        # key   = "用户:112345"    按用户分组
        # value = "79227"          动漫 ID (评分用不到, 共现只看"评没评过")

# -- Reducer: 组内两两组合 --
def emit_pairs(items):
    """
    给定一个用户评过的动漫列表, 输出两类行:
    1. 单点: 每部动漫输出一条, 用于统计被多少用户评过
    2. 共现: 动漫两两组合, 每对输出一条
    """
    items = sorted(set(items))      # 去重 + 排序 (保证 A < B, 一对只输出一次)
    # set: 去重 (同一个用户可能对同一部动漫有多条记录, 只算一次)
    # sorted: 排序 (保证小 ID 在前, 这样 共现:100|200 不会变成 共现:200|100)

    # 1. 单品计数: 用户评过这部动漫 -> 这部动漫被评次数 +1
    for a in items:
        print(f"单品:{a}\t1")

    # 2. 共现对: 用户评过的动漫两两组合
    n = len(items)
    for i in range(n):
        for j in range(i + 1, n):
            # 双重循环, 每个用户内部生成 C(n,2) 对
            print(f"共现:{items[i]}|{items[j]}\t1")

def reducer():
    """
    共现矩阵 Reducer。
    输入 (已按键排序): 用户:12345\t79227 ...
    同一个用户的所有动漫连续到达, 全部收齐后两两组合输出。
    """
    current_key = None      # 当前正在处理的用户
    items = []              # 攒当前用户评过的所有动漫

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]      # "用户:12345"
        anime_id = parts[1] # "79227"

        if key != current_key:      # 换了一个用户
            if current_key is not None:
                emit_pairs(items)   # 上一个用户收齐了, 生成他的共现对 
            current_key = key
            items = []              # 翻开新一页
        items.append(anime_id)

    # 最后一个用户别忘了结算
    if current_key is not None:
        emit_pairs(items)

# -- 主程序入口 --
if __name__ == "__main__":
    """
    运行方式: 由 Hadoop Streaming 指定运行哪个阶段
    例如:
        hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \\
            -input /user/data/user_ratings.csv \\
            -output /user/itemcf/cooccur \\
            -mapper "python itemcf_job1.py mapper" \\
            -reducer "python itemcf_job1.py reducer" \\ 
            -file itemcf_job1.py
    """
    if len(sys.argv) < 2:
        logger.error("请指定运行模式: mapper / reducer")
        sys.exit()

    mode = sys.argv[1]
    logger.info(f"启动模式: {mode}")

    if mode == "mapper":
        mapper()
    elif mode == "reducer":
        reducer()
    else:
        logger.error(f"未知模式: {mode}")
        sys.exit(1)

    logger.info(f"完成: {mode}")
    