"""
Bangumi 绑定 —— 把"别人家的收藏"变成"我们的算法标签"

链路: 用户名 -> API(走代理) -> subject_id 集合
     -> n 我们库(5009 部)  -> 数标签频次 -> Top N -> UserTag(source="algorithm")

    两档燃料: 
    打分型用户 (rate 1~10)  -> 相似度扩散(精度高，以后再做)
    只收藏型用户 (rate=0)   -> 只能算标签  <- 本文件干的就是这个，也是多数人
"""

import requests

from django.conf import settings

from .models import Anime, AnimeTag, UserTag

API = "https://api.bgm.tv/v0/users/{username}/collections"

COLLECT_TYPE = 2    # 1=想看 2=看过* 3=在看 4=搁置 5=抛弃 (只要"看过")
PAGE_SIZE = 100     # 一页拉多少 (API 上限)
MAX_ITEMS = 300     # 一个人最多拉多少部 (封顶，防重度用户把代理拖垮)
TIMEOUT = 15        # 单个请求超时(秒)

class BangumiError(Exception):
    """拉取失败 —— 由调用方翻成人话，别把 requests 的报错直接甩给用户"""
    pass

def fetch_subject_ids(username, max_items=MAX_ITEMS):
    """拉一个用户的"看过", 返回 (subject_id 列表，API 报的总数)
    
    从最近看的开始拉 —— API 按更新时间排序，最近的口味更准
    """
    proxies = {"http": settings.BANGUMI_PROXY, "https": settings.BANGUMI_PROXY}
    headers = {"User-Agent": settings.BANGUMI_UA}

    ids, offset, total = [], 0, 0
    while len(ids) < max_items:
        try:
            resp = requests.get(
                API.format(username=username),
                params={
                    "subject_type": 2,          # 只关心动画
                    "type": COLLECT_TYPE,       # 只看"看过"
                    "limit": PAGE_SIZE,
                    "offset": offset,
                },
                headers=headers,
                proxies=proxies,
                timeout=TIMEOUT,
            )

        except requests.RequestException as e:
            raise BangumiError("连不上 Bangumi —— 代理大概没开") from e

        if resp.status_code == 404:
            raise BangumiError(f"Bangumi 上没有『{username}』这个用户")
        if resp.status_code != 200:
            raise BangumiError(f"Bangumi 返回了 {resp.status_code}")

        data = resp.json()
        if offset == 0:
            total = data.get("total", 0)        # 首次请求才带总数

        page = data.get("data") or []
        if not page:                            # 拉空了，收工
            break

        ids.extend(item["subject_id"] for item in page)
        offset += len(page)                     # 按实际拿到的加，别按 PAGE_SIZE 加

        if offset >= total:                     # 没有更多了
            break

    return ids[:max_items], total

def guess_tags(subject_ids, top=10, min_hits=2):
    """把"他看过的番"换成"他大概喜欢沈标签"
    
    返回 [(tag_id, 标签名, 命中次数), ...], 按次数降序
    min_hits=2: 只出现过一次的多半是偶然，不算数
    """
    if not subject_ids:
        return []

    # 跨表取名字: tag__name —— 双下划线穿两层
    rows = (AnimeTag.objects
            .filter(anime_id__in=subject_ids)
            .values_list("tag_id", "tag__name"))

    count, names = {}, {}
    for tid, name in rows:
        count[tid] = count.get(tid, 0) + 1
        names[tid] = name

    ranked = sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))      # 次数降序，同分按 id
    return [(tid, names[tid], c) for tid, c in ranked if c >= min_hits][:top]

def sync_user_tags(user, username):
    """主入口: 拉 -> 筛 -> 数 -> 写。返回一份报告，让视图能跟用户交代"""
    ids, total = fetch_subject_ids(username)

    # n 我们库 —— 只有库里有的番才查得到标签(命中率约 16%)
    matched = set(
        Anime.objects.filter(subject_id__in=ids)
        .values_list("subject_id", flat=True)
    )

    ranked = guess_tags(list(matched))

    # 只删"算法那一档", 自选的一个字都不碰 (两档共存的约定)
    UserTag.objects.filter(user=user, source="algorithm").delete()
    UserTag.objects.bulk_create([
        UserTag(user=user, tag_id=tid, source="algorithm")
        for tid, _, _ in ranked
    ])

    return {
        "total": total,             # Bangumi 说他看过多少部
        "fetched": len(ids),        # 我们实际拉回来多少
        "matched": len(matched),    # 其中在我们库里的有多少
        "tags": ranked,             # 算出来的标签
    }