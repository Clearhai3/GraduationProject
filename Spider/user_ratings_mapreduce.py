# -*- coding: utf-8 -*-
"""
    Hadoop MapReduce 分析 - 用户评分数据离线统计
    功能: 从 HDFS 读取清洗后的用户评分数据，进行多维度统计分析
    输入: HDFS 上 /user/data/user_ratings.csv
    输出: 各维度统计结果，最终存入 MySQL
    
    数据格式: user_ratings.csv 三列
        user_id, anime_id, rate
    注意: 评分数据在 HDFS 上时，文件头那行 user_id,anime_id,rate 也要跳过
"""

# -- 头部导入 --
import sys
import logging

# -- 日志配置 --
# 流式任务的标准输入 (stdout) 被 Hadoop 用来传输数据,
# 日志只能写到 stderr, 否则会干扰 MapReduce 数据传输。
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("user_ratings_analysis")

# -- 工具函数 --
def parse_rating_line(line):
    """
    解析一行评分 CSV, 返回 (user_id, anime_id, rate)。
    解析失败返回 None。
    """
    line = line.strip()
    if not line:
        return None
    # 跳过表头 (带不带 BOM 都处理, lstrip 去掉文件开头的隐藏字符)
    if line.lstrip("\ufeff").startswith("user_id"):
        return None
    parts = line.split(",")     # 评分行没有内嵌逗号, 直接按逗号拆
    if len(parts) < 3:
        return None             # 防御: 字段不齐跳过
    try:
        user_id  = int(parts[0])
        anime_id = int(parts[1])
        rate     = int(parts[2])
    except (ValueError, TypeError):
        return None
    return (user_id, anime_id, rate)

# -- 分析1: 评分分布 (1~10 分各多少条) --
# map 输出: 评分:9\t1
def mapper_score():
    """
    评分分布统计 Mapper。
    输出格式: 评分:9\t1
    """
    for line in sys.stdin:
        record = parse_rating_line(line)
        if not record:
            continue
        user_id, anime_id, rate = record
        print(f"评分:{rate}\t1")

# reduce 输出: 9\t256789
def reducer_score():
    """
    评分分布统计 Reducer。
    统计 1~10 分各有多少条评分。
    输出格式: 评分值\t条数
    """
    current_key = None
    count = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]

        if key != current_key:      # 换了一个评分值
            if current_key is not None: # 先结算上一个
                rate = current_key.replace("评分:", "")
                print(f"{rate}\t{count}")
            current_key = key
            count = 0
        count += 1

    # 最后一个评分值别忘了结算
    if current_key is not None:
        rate = current_key.replace("评分:", "")
        print(f"{rate}\t{count}")

# -- 分析2: 用户活跃度 --
# map 输出: 用户:12345\t1   (每一行评分 = 该用户贡献 1 条)
def mapper_user():
    """
    用户活跃度统计 Mapper。
    每一行评分 = 该用户贡献 1 条评分。
    输出格式: 用户:{user_id}\t1
    """
    for line in sys.stdin:
        record = parse_rating_line(line)
        if not record:
            continue
        user_id, anime_id, rate = record
        print(f"用户:{user_id}\t1")

def activity_level(count):
    """
    把用户的评分条数映射到活跃度分层。
    比如 35 条 -> "11-50条"
    """
    if count <= 10:
        return "1-10条"
    if count <= 50:
        return "11-50条"
    if count <= 100:
        return "51-100条"
    return "100条以上"

# reduce 输出: 活跃分层:11-50条\t3254   和  活跃Top:1\t12345\t856
def reducer_user():
    """
    用户活跃度统计 Reducer。
    统计每个用户的评分条数，再汇总两件事:
    1. 活跃度分层: 每个层级的用户数
    2. 活跃用户 Top N: 评分最多的前 N 个用户
    注意: Top 榜必须用 1 个 reducer, 否则拿不到全局排名。
    """
    top_n = 10
    user_counts = []        # 收集 (user_id, 评分条数), 最后统一排序

    current_key = None
    count = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]

        if key != current_key:
            if current_key is not None:
                # 上一个用户的条数已经数完, 存起来
                user_id = current_key.replace("用户:", "")
                user_counts.append((user_id, count))
            current_key = key
            count = 0
        count += 1

    # 最后一个用户别忘了
    if current_key is not None:
        user_id = current_key.replace("用户:", "")
        user_counts.append((user_id, count))

    # 1. 活跃度分层: 数每个层级各有多少用户
    levels = {}
    for user_id, cnt in user_counts:
        level = activity_level(cnt)
        levels[level] = levels.get(level, 0) + 1
    for level in ["1-10条", "11-50条", "51-100条", "100条以上"]:
        if level in levels:     # 没有用户的层级就不输出
            print(f"活跃分层:{level}\t{levels[level]}")

    # 2. 活跃用户 Top N: 按条数降序，取前 top_n 名
    user_counts.sort(key = lambda x: -x[1])     # -x[1]: 条数多的排前面
    for i, (user_id, cnt) in enumerate(user_counts[:top_n], 1):
        print(f"活跃Top:{i}\t{user_id}\t{cnt}")

# -- 分析3: 热门动漫 (被评分最多的动漫) --
# map 输出: 动漫:79227\t1   (每一行评分 = 该动漫被 1 个用户评分)
def mapper_anime():
    """
    热门动漫统计 Mapper。
    每一行评分 = 该动漫被 1 个用户评分。
    输出格式: 动漫:{anime_id}\t1
    """
    for line in sys.stdin:
        record = parse_rating_line(line)
        if not record:
            continue
        user_id, anime_id, rate = record
        print(f"动漫:{anime_id}\t1")

# reduce 输出: 热门:1\t79227\t8563
def reducer_anime():
    """
    热门动漫统计 Reducer。
    统计每部动漫被多少用户评分, 输出评分人数最多的前 N 部。
    输出格式: 热门:{排名}\t{anime_id}\t{评分人数}
    """
    top_n = 20
    anime_counts = []       # 收集 (anime_id, 评分人数), 最后统一排序

    current_key = None
    count = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]

        if key != current_key:
            if current_key is not None:
                anime_id = current_key.replace("动漫:", "")
                anime_counts.append((anime_id, count))
            current_key = key
            count = 0
        count += 1

    if current_key is not None:
        anime_id = current_key.replace("动漫:", "")
        anime_counts.append((anime_id, count))

    # 按评分人数降序, 取前 N 名
    anime_counts.sort(key = lambda x: -x[1])
    for i, (anime_id, cnt) in enumerate(anime_counts[:top_n], 1):
        print(f"热门:{i}\t{anime_id}\t{cnt}")

# -- 主程序入口 --
if __name__ == "__main__":
    """
    运行方式: 由 Hadoop Streaming 指定以运行哪个 mapper/reducer
    例如:
        hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \\
            -input /user/data/user_ratings.csv \\
            -output /user/analysis/score \\
            -mapper "python user_ratings_mapreduce.py mapper_score" \\
            -reducer "python user_ratings_mapreduce.py reducer_score" \\
            -file user_ratings_mapreduce.py
    """
    if len(sys.argv) < 2:
        logger.error("请指定运行模式: mapper_score/reducer_score/...")
        sys.exit()

    mode = sys.argv[1]
    logger.info(f"启动分析模式: {mode}")

    # 根据命令行参数选择对应的 mapper 或 reducer
    mode_map = {
        "mapper_score":  mapper_score,
        "reducer_score": reducer_score,
        "mapper_user":   mapper_user,
        "reducer_user":  reducer_user,
        "mapper_anime":  mapper_anime,
        "reducer_anime": reducer_anime,
    }

    func = mode_map.get(mode)
    if func is None:
        logger.error(f"未知模式: {mode}")
        logger.error(f"可用的模式: {list(mode_map.keys())}")
        sys.exit(1)

    func()
    logger.info(f"分析完成: {mode}")

