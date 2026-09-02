"""
导入 anime 基础表 (Django ORM 版)
功能: 读取 anime_cleaned.csv, 把 5009 条记录写入 MySQL 的 anime_anime 表
用法: cd Spider && python import_anime.py
"""

import csv          # 读 csv 文件
import os           # 拼文件路径
import sys
import datetime
import django

# 1.加载 Django 环境
BASE_DIR = os.path.dirname(os.path.abspath(__file__))       # 本脚本所在目录 = Spider/
sys.path.insert(0, os.path.join(BASE_DIR, "..", "WebCode")) # 让 Python 找得到 anime_web 和 anime
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "anime_web.settings")   # 指定 Django 用哪份配置
django.setup()                                              # Django 点火

from anime.models import Anime

# 2.配置
CSV_FILE = os.path.join(BASE_DIR, "anime_cleaned.csv")

# 3.主程序
def main():
    rows = []       # 攒一批 Anime 对象
    skipped = 0     # 异常跳过计数

    with open(CSV_FILE, "r", encoding = "utf-8-sig") as f:
        reader = csv.reader(f)      # 逐行读取
        next(reader)

        for record in reader:
            if len(record) < 12:
                skipped += 1
                continue

            # 3.1 从详情页 URL 抽 subject_id (主键)
            #       https://bangumi.tv/subject/326  ->  326
            try:
                subject_id = int(record[11].rstrip("/").rsplit("/", 1)[1])
            except (ValueError, IndexError):
                skipped += 1
                continue

            # 3.2 日期: 字符串 -> 日期对象 (空或坏格式给 None)
            air_date = None
            if record[4]:
                try:
                    air_date = datetime.date.fromisoformat(record[4])
                except ValueError:
                    air_date = None

            # 3.3 数字兜底 (空值给 None: 0 是"有", None 是"不知道")
            episodes = int(record[3]) if record[3].isdigit() else None
            score    = float(record[8]) if record[8] else None
            rank_num = int(record[0]) if record[0].isdigit() else 0
            s_count  = int(record[9]) if record[9].isdigit() else 0

            rows.append(Anime(
                subject_id       = subject_id,
                rank             = rank_num,
                name             = record[1],
                anime_type       = record[2],
                episodes         = episodes,
                air_date         = air_date,
                director         = record[5],
                script_writer    = record[6],
                voice_actors     = record[7],
                rating           = score,
                rating_count     = s_count,
                cover_url        = record[10],
                detail_url       = record[11],
            ))

    # 3.4 幂等: 先清空再灌入, 跑两遍结果一样
    Anime.objects.all().delete()
    Anime.objects.bulk_create(rows)

    print(f"导入完成: {len(rows)} 行, 跳过 {skipped} 行")

if __name__ == "__main__":
    main()