# -*- coding: utf-8 -*-
"""
    ItemCF 协同过滤 - Job3: 生成推荐
    功能: 用 Job2 的相似度表 + 用户评分, 为每个用户生成 Top-N 推荐 (过滤已看过的动漫)
    输入: itemcf_sim.txt (Job2 输出) + user_ratings.csv
    输出: 推荐:{user_id} \t {anime_id}:{score}|{anime_id}:{score}|...

    推荐分公式: pred(u,j) = Σ sim(i,j) * r(u,i)   (用户评过的 i 的邻居 j)

    算法流程 (本地模拟, 两次 sort):
    阶段A (mapper -> sort -> reduce_a):
        mapper 输出两种行 (key 都是 "动漫:{anime}", 让同一部动漫聚到一起):
          动漫:328609\t325585:0.62|325285:0.59|...   (相似行)
          动漫:328609\t评分:1:9                       (评分行, value 带 评分: 前缀)
        reduce_a 按动漫聚合: 收齐邻居 + 所有用户评分后,
        算出每个候选动漫对用户的贡献 + 记录用户已看, 输出:
          用户:1\t候选:325585:5.62|325285:5.35|...
          用户:1\t已看:100|200|300
    阶段B (sort -> reducer_b):
        相同用户的行聚到一起 (候选 + 已看), 过滤已看过的动漫, 按分数降序取 Top-N

    注意: 之前版本的 key 用 "相似:"/"评分:" 前缀,
         sort 后所有相似行在前、评分行在后, 同一部动漫根本不聚在一起,
         导致所有用户的贡献都用最后一部动漫的邻居表算, 结果全错。
         新版统一用 "动漫:{anime}" 前缀, 利用 sort 让同一部动漫聚在一起。
"""

# -- 头部导入 --
import sys
import logging

# -- 日志配置 --
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("itemcf_job3")

TOP_N = 10      # 每个用户推荐 10 部

# -- 阶段A: Mapper 1 (读相似度表 + 评分) --
# map 输出: 相似:{动漫}\t邻居串     /     评分:{用户}-{动漫}\t评分
def mapper():
    """
    生成推荐 Mapper。
    输入 stdin: itemcf_sim.txt (相似度表) + user_ratings.csv (评分), 文件头由外部处理
    输出: key 都是 "动漫:{anime}" 的两种行, 靠 sort 让同一部动漫聚到一起
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        # 相似度表的行: 相似Top:328609\t325585:0.62|...
        if line.startswith("相似Top:"):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            anime = parts[0].replace("相似Top:", "")
            neighbors = parts[1]
            print(f"动漫:{anime}\t{neighbors}")
            continue

        # 评分表的行: 用户ID, 动漫ID,评分
        if line.lstrip("\ufeff").startswith("user_id"):
            continue
        parts = line.split(",")
        if len(parts) < 3:
            continue
        try:
            user_id  = int(parts[0])
            anime_id = int(parts[1])
            rate     = int(parts[2])
        except (ValueError, TypeError):
            continue
        # value 带 "评分:" 前缀, 方便 reduce_a 区分相似行和评分行
        print(f"动漫:{anime_id}\t评分:{user_id}:{rate}")

# -- 阶段A: Reducer (按动漫聚合, 算贡献 + 记录已看) --
def settle_anime(anime_id, neighbors, ratings, user_contrib, user_seen):
    """
    结算一部动漫: 用它的邻居表, 给每个评分用户累加贡献 + 记录已看。
    """
    if not ratings:
        return      # 没有评分的动漫不处理
    for uid_str, rate in ratings:
        # 记录用户看过这部动漫 (过滤推荐用)
        user_seen.setdefault(uid_str, set()).add(anime_id)
        # 用户对这部动漫的评分, 贡献给它的所有邻居
        d = user_contrib.setdefault(uid_str, {})
        for nid, sim in neighbors.items():
            d[nid] = d.get(nid, 0.0) + sim * rate

def reduce_a():
    """
    阶段A Reducer: 按动漫聚合, 算每个用户的候选分数。
    输入 (已排序): 
        动漫:328609\t325585:0.62|325285:0.59|...        (相似行)
        动漫:328609\t评分:1:9                           (评分行)
        动漫:328609\t评分:2:8
    输出: 
        用户:1\t候选:325585:5.62|325285:5.35|...
        用户:1\t已看:100|200|300
    """
    user_contrib = {}       # 用户ID -> {候选动漫ID: 累加分}
    user_seen = {}          # 用户ID -> 已看过的动漫ID集合

    current_key = None
    current_anime = None    # 当前动漫 ID
    neighbors = {}          # 当前动漫的邻居表
    ratings = []            # 当前动漫收到的评分 [(user_id, rate), ...]

    for line in sys.stdin:
        line = line.strip("\t")
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]
        value = parts[1]

        if key != current_key:      # 换了一部动漫
            if current_key is not None:
                settle_anime(current_anime, neighbors, ratings, 
                             user_contrib, user_seen)
            current_key = key
            current_anime = key.replace("动漫:", "")
            neighbors = {}
            ratings = []

        if value.startswith("评分:"):
            # "评分:1:9" -> user_id=1, rate=9
            rest = value.replace("评分:", "")
            uid_str, rate_str = rest.rsplit(":", 1)
            ratings.append((uid_str, int(rate_str)))
        else:
            # 相似行的 value 是邻居串: "325585:0.62|325285:0.59|..."
            for item in value.split("|"):
                nid, sim = item.split(":")
                neighbors[nid] = float(sim)

    # 最后一部动漫别忘了结算
    if current_key is not None:
        settle_anime(current_anime, neighbors, ratings,
                     user_contrib, user_seen)

    # 输出两种行: 候选分数 + 已看列表 (key 都是 "用户:{uid}", 阶段B 聚合)
    for user_id, cand in user_contrib.items():
        items = [(nid, score) for nid, score in cand.items()]
        items.sort(key = lambda x: -x[1])       # 分数降序
        cand_str = "|".join(f"{nid}:{score:.2f}" for nid, score in items)
        print(f"用户:{user_id}\t候选:{cand_str}")
        seen = user_seen.get(user_id, set())
        seen_str = "|".join(sorted(seen))
        print(f"用户:{user_id}\t已看:{seen_str}")

# -- 阶段B: Reducer (按用户聚合, 过滤已看, 取 Top-N) --
def emit_rec(user_key, candidates, seen):
    """
    过滤已看 + 按分数降序 + 取 Top-N + 输出。
    """
    # 改进1: 过滤掉用户已经看过的动漫
    cand = [(nid, score) for nid, score in candidates if nid not in seen]
    cand.sort(key = lambda x: -x[1])
    top = cand[:TOP_N]
    rec_str = "|".join(f"{nid}:{score}" for nid, score in top)
    user_id = user_key.replace("用户:", "")
    print(f"推荐:{user_id}\t{rec_str}")

def reducer_b():
    """
    阶段B Reducer: 按用户聚合, 过滤已看, 取 Top-N。
    输入 (已排序): 
        用户:1\t候选:325585:5.62|325285:5.35|...
        用户:1\t已看:100|200|300
    输出: 推荐:{user_id} \t 前10部动漫
    """
    current_key = None
    candidates = []      # 候选 (动漫ID, 分数)
    seen = set()         # 已看动漫ID集合

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0]
        value = parts[1]

        if key != current_key:      # 换了一个用户
            if current_key is not None:
                emit_rec(current_key, candidates, seen)
            current_key = key
            candidates = []
            seen = set()

        if value.startswith("候选:"):
            cand_str = value.replace("候选:", "")
            for item in cand_str.split("|"):
                nid, score = item.split(":")
                candidates.append((nid, float(score)))
        elif value.startswith("已看:"):
            seen_str = value.replace("已看:", "")
            for aid in seen_str.split("|"):
                if aid:
                    seen.add(aid)

    # 最后一个用户
    if current_key is not None:
        emit_rec(current_key, candidates, seen)

# -- 主程序入口 --
if __name__ == "__main__":
    """
    本地模拟流程:
        cat itemcf_sim.txt user_ratings.csv | python itemcf_job3.py mapper \
            | sort | python itemcf_job3.py reduce_a \
            | sort | python itemcf_job3.py reducer_b
    Hadoop 版:
        阶段A: -mapper mapper -reducer reduce_a
        阶段B: -mapper "cat" -reducer reducer_b
    """
    if len(sys.argv) < 2:
        logger.error("请指定运行模式: mapper / reduce_a / reducer_b")
        sys.exit()

    mode = sys.argv[1]
    logger.info(f"启动模式: {mode}")

    if mode == "mapper":
        mapper()
    elif mode == "reduce_a":
        reduce_a()
    elif mode == "reducer_b":
        reducer_b()
    else:
        logger.error(f"未知模式: {mode}")
        sys.exit(1)

    logger.info(f"完成: {mode}")

# 一、Job3 干什么
# 用"动漫相似度表" + "用户评分"，给每个用户算 Top10 推荐 (排除看过的)。

# 二、推荐分公式 (核心)

# 翻译: "用户给i打了高分，而j和i很像 -> j就该被推荐"。分数 = 相似度 * 评分的累加

# 三、两阶段管道 (为什么要两次 sort)
# 阶段A: 按"动漫"分组
#     输入: 相似表(相似Top:动漫\t邻居串) + 评分表(user_id,anime_id,rate)
#     mapper: 统一输出 "动漫:{anime}\t..." 前缀
#     sort:   同一部动漫的 【邻居表】和【评分】聚到一起
#     reduce_a: 用邻居表 x 评分 -> 累加出每个用户的候选分
#               同时记录"用户看过哪些动漫"（推荐时要过滤）
#     输出:   "用户:{uid}\t候选:..." 和 "用户:{uid}\t已看:..."

# 阶段B: 按"用户"分组
#     sort:   同一用户的【候选】和【已看】聚到一起
#     reduce_b: 过滤已看 -> 按分降序 -> 取 Top10
#     输出:   "推荐:{uid}\t动漫:分数|动漫:分数|..."

# 为什么两次 sort? 
# 因为阶段 A 是按"动漫"聚的，算完吐出的数据却是按"用户"组织的————顺序乱了，得重新 sort 一次。两次 sort = 两种分组需求（先按动漫，再按用户）。

# 四、命令（含编码保险丝）
# $OutputEncoding = [System.Text.Encoding]::UTF8

# # 阶段A
# Get-Content itemcf_sim_train.txt, train_ratings.csv | python -X utf8 itemcf_job3.py mapper | Sort-Object | python -X utf8 itemcf_job3.py reduce_a | Out-File -Encoding utf8 itemcf_job3_mid.txt

# # 阶段B
# Get-Content itemcf_job3_mid.txt | Sort-Object | python -X utf8 itemcf_job3.py reducer_b | Out-File -Encoding utf8 itemcf_rec_train.txt

# 五、验证标准
# itemcf_rec_train.txt ≈ 100 万行级（10,303 用户 × 2 行候选/已看？不对——阶段B 输出是 1 行/用户，应该是 ~10,303 行）
# 抽查：推荐:{uid}\t{动漫}:{分数}|...（10 部，降序）
# 质量：推荐的动漫不该在用户的已看列表里

# 六、操作
