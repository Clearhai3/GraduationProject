"""
推荐引擎 —— 基于 ItemCF 相似度扩散

公式(甲·不除分母): score(C) = Σ sim(C,A) × (r(A) - 5.5)
    依据: formula_compare_report.json —— 留一法 Recall@10 = 15.10% (乙只有 2.35%)
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIM_FILE = os.path.join(BASE_DIR, "../../Spider/algorithms/itemcf/data/itemcf_sim_train.txt")

CENTER = 5.5        # 中心点: 8分 -> +2.5, 3分 -> -2.5

# 1. 相似度表: 懒加载 + 常驻
_SIM = None     # 模块级变量: 全进程共用一份

def get_sim():
    """第一次调用时读文件，之后一只用内存里这份 (534ms / 8.3MB)"""
    global _SIM
    if _SIM is None:
        sim = {}
        with open(SIM_FILE, encoding="utf-8") as f:
            for line in f:
                if not line.startswith("相似Top:"):
                    continue
                head, rest = line.rstrip("\n").split("\t", 1)
                anime_id = int(head.split(":")[1])
                sim[anime_id] = {
                    int(p.split(":")[0]): float(p.split(":")[1])
                    for p in rest.split("|")
                }
        _SIM = sim
    return _SIM


# 2. 打分: 纯函数，不碰数据库
def score_candidates(ratings, sim):
    """ratings = {动漫id: 评分}  ->  返回 {候选动漫id: 分数}"""
    scores = {}
    for anime_id, rate in ratings.items():
        weight = rate - CENTER
        for cand, similarity in sim.get(anime_id, {}).items():
            if cand in ratings:         # 已经打过分的，不再推荐
                continue
            scores[cand] = scores.get(cand, 0.0) + similarity * weight
    return scores

def rank(scores, limit):
    """分数降序; 同分按 id 升序 -> 结果稳定，刷两次不会变"""
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]

# 3. 主入口: 给个站内用户，还他一串推荐
def _by_ratings(user, limit):
    """路 1: 有评分 -> 相似度扩散"""
    from .models import UserRating

    ratings = dict(
        UserRating.objects.filter(user=user).values_list("anime_id", "rate")
    )
    if not ratings:
        return []
    return rank(score_candidates(ratings, get_sim()), limit)

def _by_tags(user, limit):
    """路 2: 没评分时 -> 用他选的标签召回
    排序 = 命中数降序 -> 热度降序 -> id 升序"""
    from .models import UserTag, AnimeTag, Anime, UserRating

    tag_ids = list(UserTag.objects.filter(user=user, source__in=["self", "algorithm"])
                   .distinct()
                   .values_list("tag_id", flat=True))

    if not tag_ids:
        return []

    # 已经打过分的别再推 (路 1 失败时可能走到这儿)
    rated = set(UserRating.objects.filter(user=user)
                .values_list("anime_id", flat=True))

    hits = {}
    for aid in AnimeTag.objects.filter(tag_id__in=tag_ids).values_list("anime_id", flat=True):
        if aid not in rated:
            hits[aid] = hits.get(aid, 0) + 1
    if not hits:
        return []

    # 热度做第二把尺子 (rating_count 可空, 兜 0)
    heat = dict(Anime.objects.filter(subject_id__in=hits)
                .values_list("subject_id", "rating_count"))

    ranked = sorted(hits, key=lambda aid: (-hits[aid], -(heat.get(aid) or 0), aid))
    return [(aid, float(hits[aid])) for aid in ranked[:limit]]


def recommend_for_user(user, limit=20):
    """多路召回
    返回 [(动漫id, 分数), ...]
    ⚠️ 分数只在同一路内有意义(①是证据量 0~15, ②是命中数 1~3), 调用方只该用 id
    """
    if not user.is_authenticated:
        return []

    recs = _by_ratings(user, limit)
    if recs:
        return recs

    recs = _by_tags(user, limit)
    if recs:
        return recs

    return []

def pick_by_tags(user, limit, exclude=()):
    """『按标签分组』召回 —— 每个自选标签轮流拿一部，保证都有份
    
    与 _by_tags 的区别:
       _by_tags      : 命中标签数多的排前面  (适合"猜你喜欢"要精度)
       pick_by_tags  : 每个标签轮到一次     (适合首页要覆盖) <- 首页用这个
    """
    if not user.is_authenticated:       # 游客直接退，别拿 AnonymousUser 去查库
        return []

    from .models import UserTag, AnimeTag, UserRating

    tag_ids = list(UserTag.objects.filter(user=user, source__in=["self", "algorithm"])
                   .order_by("tag_id")
                   .distinct()
                   .values_list("tag_id", flat=True))

    if not tag_ids:
        return []

    rated = UserRating.objects.filter(user=user).values("anime_id")     # 打过分的别再推
    excl = set(exclude)                                                 # 猜你喜欢池先让开

    # 每个标签一摞候选: 站内热度降序 (取前 200 就够，别把几千条全拖回来)
    buckets = []
    for tid in tag_ids:
        ids = [i for i in AnimeTag.objects.filter(tag_id=tid)
               .exclude(anime_id__in=rated)
               .order_by("-anime__rating_count", "anime_id")
               .values_list("anime_id", flat=True)[:200]
               if i not in excl]
        if ids:
            buckets.append(ids)
    if not buckets:
        return []

    # 轮流取: 一轮一个标签拿一部
    picked, seen, round_no = [], set(), 0
    while len(picked) < limit:
        got = False
        for ids in buckets:
            if round_no >= len(ids):
                continue
            aid = ids[round_no]
            if aid in seen:
                continue
            seen.add(aid)
            picked.append(aid)
            got = True
            if len(picked) >= limit:
                break
        if not got:     # 所有标签都取空了
            break
        round_no += 1

    return picked
