# -*- coding: utf-8 -*-
"""
    ItemCF 协同过滤 - Job2: 相似度计算
    功能: 把 Job1 的共现矩阵 + 单品计数, 计算成动漫相似度表
    输入: itemcf_cooccur.txt (Job1 的输出)
        单品: {动漫A} \t 1
        共现: {动漫A}|{动漫B} \t 1
    输出: 两类结果
        1. 计数: {动漫A} \t 被评次数        (每部动漫)
        2. 相似Top: {动漫A} \t {B}:{sim}|{C}:{sim}...   (每部动漫最相似的 20 部)
    相似度公式: sim(i,j) = 共现次数  / sqrt(被评次数(i) * 被评次数(j))
    后续: Job3 用相似度表 + 用户评分, 生成推荐
    
    设计要点:
    - Mapper 把 单品: 改名为 C:, 共现: 改名为 P:
      ASCII 码 C < P, 所以 sort 后所有计数行排在配对行前面
    - Reducer 先收齐全部计数 (只有约1200个, 内存装得下),
      再遇到配对行时直接查表算相似度 (in-memory join)
    - 此任务必须用 1 个 reducer, 否则计数和配对被分到不同节点
"""

# -- 头部导入 --
import sys
import logging
import math     # 开根号 sqrt

# -- 日志配置 -- 
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s", 
    handlers = [logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("itemcf_job2")

TOP_K = 20      # 每部动漫保留最相似的 20 部

# -- Mapper: 改前缀 --
# map 输出: C:{动漫A}\t1  /  P:{动漫A}|{动漫B}\t1
def mapper():
    """
    相似度计算 Mapper。
    把 单品: 前缀改成 C:, 共现: 前缀改成 P:。
    目的: 利用 ASCII 排序让 C 行全部排在 P 行前面。
    """
    for line in sys.stdin:
        line = line.strip()
        line = line.lstrip('\ufeff')        # 去掉第一行的 BOM
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]
        value = parts[1]

        if key.startswith("单品:"):
            anime_id = key.replace("单品:", "")
            print(f"C:{anime_id}\t{value}")
        elif key.startswith("共现:"):
            pair = key.replace("共现:", "")
            print(f"P:{pair}\t{value}")

# -- Reducer: 先收计数, 再算相似度 --
def settle(current_key, current_content, agg, item_counts, top_neighbors):
    """
    结算一个 key 的统计结果。
    C 行: 把累加值存进 item_counts (被评次数)
    P 行: 查表算相似度, 存入 top_neighbors (每部动漫的邻居列表)
    """
    if current_key.startswith("C:"):
        item_counts[current_content] = agg
    else:
        a, b = current_content.split("|")
        # 两部动漫各自的被评次数 (防御: 取不到就用 1)
        ca = item_counts.get(a, 1)
        cb = item_counts.get(b, 1)
        # 核心公式: 共现次数 / 开根号(两边的被评次数乘积)
        sim = agg / math.sqrt(ca * cb)
        # 双向记录: A 的邻居里有 B, B 的邻居里也有 A
        top_neighbors.setdefault(a, []).append((b, sim))
        top_neighbors.setdefault(b, []).append((a, sim))

def reducer():
    """
    相似度计算 Reducer。
    输入 (已排序): C:100\t1 / C:100\t1 / ... / P:100|200\t1 ...
    处理顺序: 所有 C 行先到 (收齐计数) -> 然后 P 行逐个算相似度
    """
    item_counts = {}        # 动漫ID -> 被评次数 (来自 C 行)
    top_neighbors = {}      # 动漫ID -> [(邻居ID, 相似度), ...] (来自 P 行)

    current_key = None
    current_content = None  # key 去掉前缀后的内容
    agg = 0                 # 当前 key 的累加值

    for line in sys.stdin:
        line = line.strip()
        line = line.lstrip('\ufeff')
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]
        value = int(parts[1])

        if key == current_key:      # 同一个 key 继续累加
            agg += value
            continue

        # 换 key: 先结算上一个
        if current_key is not None:
            settle(current_key, current_content, agg, item_counts, top_neighbors)

        # 切换新 key
        current_key = key
        current_content = key[2:]       # 去掉 "C:" 或 "P:" 前缀
        agg = value

    # 最后一个 key 别忘了结算
    if current_key is not None:
        settle(current_key, current_content, agg, item_counts, top_neighbors)

    # 输出 1: 每部动漫的被评次数
    for a in sorted(item_counts):
        print(f"计数:{a}\t{item_counts[a]}")

    # 输出 2: 每部动漫的 Top-K 相似动漫
    for a, neighbors in top_neighbors.items():
        neighbors.sort(key = lambda x: -x[1])   # 按相似度降序
        top = neighbors[:TOP_K]                 # 只留前 20 个
        # 拼成 "100:1.0000|300:0.7071" 格式
        sim_str = "|".join(f"{b}:{sim:.4f}" for b, sim in top)
        print(f"相似Top:{a}\t{sim_str}")

# -- 主程序入口 --
if __name__ == "__main__":
    """
    运行方式: 由 Hadoop Streaming 指定运行哪个阶段
    例如:
        hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \\
            -input /user/itemcf/cooccur \\
            -output /user/itemcf/sim \\
            -mapper "python itemcf_job2.py mapper" \\
            -reducer "python itemcf_job2.py reducer" \\
            -file itemcf_job2.py
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

