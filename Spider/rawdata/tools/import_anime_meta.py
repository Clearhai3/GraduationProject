"""
补动漫元数据 -> name_cn / summary / score_detail / fav_detail

数据来源: bangumi 归档筛选出来的 our_5009.jsonl (官方归档里白捡起的四样)
纪律:
    1. 只 update，绝不 delete —— 不碰已有字段，也不碰任何用户数据
    2. 幂等 —— 反复跑结果一样
    3. 找不到文件就说人话，别甩一堆栈

用法: cd Spider/rawdata/tools && python import_anime_meta.py
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

from anime.models import Anime

# 2. 源文件 (用脚本自己所在位置当锚点)
JSONL = os.path.normpath(os.path.join(BASE_DIR, "..", "raw", "our_5009.jsonl"))

def main():
    if not os.path.exists(JSONL):
        print(f"[×] 找不到数据文件: {JSONL}")
        print("     它应该在 git 里 (Spider/rawdata/raw/our_5009.jsonl)，没有就:")
        print("     git pull server main")
        sys.exit(1)
    print(f"[✓] 数据文件: {JSONL}")

    with open(JSONL, "r", encoding="utf-8") as f:
        lines = [json.loads(ln) for ln in f if ln.strip()]

    db_ids = set(Anime.objects.values_list("subject_id", flat=True))

    updated, skipped = 0, 0
    for d in lines:
        if d["id"] not in db_ids:
            skipped += 1
            continue
        # summary 原文件带全角空格缩进，先 strip；换行留给模板处理
        Anime.objects.filter(subject_id=d["id"]).update(
            name_cn=(d.get("name_cn") or "").strip(),
            name_orig=(d.get("name") or "").strip(),
            summary=(d.get("summary") or "").strip(),
            score_detail=d.get("score_details") or {},
            fav_detail=d.get("favorite") or {},
        )
        updated += 1

    print(f"更新 {updated} 部 (跳过 {skipped} 部: 库里没这个 id) ")

    # 3. 入库核对 (查数据库，不看变量)
    a = Anime.objects.get(subject_id=8)
    print(f"核对 #8: {a.name} | {a.name_cn}")
    print(f"        简介 {len(a.summary or '')} 字 | 分数段 {len(a.score_detail or {})} 档 | 收藏 {len(a.fav_detail or {})} 项")
    print(f"有中文名: {Anime.objects.exclude(name_cn='').count()} / "
          f"有简介: {Anime.objects.exclude(summary='').count()} / 总 {Anime.objects.count()}")

if __name__ == "__main__":
    main()