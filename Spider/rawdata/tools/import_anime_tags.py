"""
导入题材标签 -> Tag 词库 + AnimeTag 关联表

数据来源: bangumi 归档筛选出来的 our_5009.jsonl
两条纪律:
    1. 绝不 delete —— Tag 可能已被 UserTag 引用，删了就丢用户的选择
    2. 幂等 —— 反复跑结果一样 (get_or_create + ignore_conflicts)
    
用法: cd Spider/rawdata/tools && python import_anime_tags.py
"""

import os
import sys
import json
import django

# 1. 加载 Django 环境
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "..", "..", "..", "WebCode"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "anime_web.settings")
django.setup()

from django.utils.text import slugify
from anime.models import Tag, AnimeTag
from tag_whitelist import GENRES

# 2. 配置
#    用"脚本自己所在的位置"当锚点找文件 —— 换机器/换系统都不用改代码
#      BASE_DIR             = Spider/rawdata/tools/
#      ".."                 = 退一级回到 Spider/rawdata/
#      再拼 "raw/xxx"       = Spider/rawdata/raw/xxx
JSONL = os.path.join(BASE_DIR, "..", "raw", "our_5009.jsonl")
JSONL = os.path.normpath(JSONL)        # 把 a/b/../c 这种走法"拍平"成干净路径

def main():
    # 2.1 开跑前先确认源文件在 —— 找不到就给一句人话，别让它报一堆栈
    if not os.path.exists(JSONL):
        print(f"[×] 找不到数据文件: {JSONL}")
        print("    这个文件在 git 里(Spider/rawdata/raw/our_5009.jsonl)")
        print("    如果你刚 clone 下来, 先确认它存在; 没有就重跑:")
        print("      git pull server main")
        sys.exit(1)
    print(f"[✓] 数据文件: {JSONL}")

    # 3.1 建词库 (49 个词) —— sort_order 按白名单顺序，热门的排在前面
    tag_map = {}
    created_n = 0
    for i, name in enumerate(GENRES, start=1):
        tag, created = Tag.objects.get_or_create(
            name=name,
            defaults={
                "slug": slugify(name, allow_unicode=True),
                "source": "bangumi",
                "sort_order": i,
            },
        )
        if created:
            created_n += 1
        tag_map[name] = tag
    print(f"词库: 新建 {created_n} 个，已有 {len(GENRES) - created_n} 个")

    # 3.2 挂线 (动漫 <-> 标签)
    with open(JSONL, "r", encoding="utf-8") as f:
        lines = [json.loads(ln) for ln in f if ln.strip()]

    rows = []
    for d in lines:
        # meta_tags 和 tags 都看，取交集里落在白名单的词
        names = set(d.get("meta_tags") or [])
        names |= {t["name"] for t in (d.get("tags") or [])}
        for n in names:
            if n in tag_map:
                # anime_id 直接给数字: 不用先查 Anime 对象(省 5009 次查询)
                rows.append(AnimeTag(anime_id=d["id"], tag_id=tag_map[n].id))

    # ignore_conflicts=True -> 撞了唯一约束就跳过，不报错(幂等的关键)
    AnimeTag.objects.bulk_create(rows, ignore_conflicts=True)

    print(f"关联: 扫描 {len(lines)} 部，写入 {len(rows)} 行(含已存在的)")
    print(f"入库核对: Tag={Tag.objects.count()} AnimeTag={AnimeTag.objects.count()}")

if __name__ == "__main__":
    main()

