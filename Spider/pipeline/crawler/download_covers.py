# -*- coding: utf-8 -*-
"""
封面图片本地化脚本
功能: 把 anime_anime 表的 cover_url 下载到 WebCode/static/images/anime/
输出: 4841 张 {subject_id}.jpg + 1 张 no_icon_subject.png(官方占位图)
特点: 断点续爬(已有文件跳过) + 走代理 + 结束报告失败清单
用法: python download_covers.py
"""

import os
import time
import requests
import pymysql

# 1. 路径锚点(全套用绝对路径，不依赖你站在哪个目录)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))     # Spider/pipeline/crawler
SPIDER_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))   # Spider
PROJECT_DIR = os.path.dirname(SPIDER_DIR)                   # 仓库根
OUT_DIR = os.path.join(PROJECT_DIR, "WebCode", "static", "images", "anime")

PLACEHOLDER_URL = "https://lain.bgm.tv/img/no_icon_subject.png"

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",
    "database": "anime_db",
    "charset": "utf8mb4",
}

# lain.bgm.tv 直连超时(实测 12 秒无响应)，必须走代理
PROXIES = {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

# UA 规范: 带上项目地址，让对面知道是谁在请求(借人家的图，要报上名号)
HEADERS = {"User-Agent": "mriya-graduation-project/1.0 (https://github.com/Clearhai3/GraduationProject)"}

def query_rows(sql):
    """连库执行 SELECT，返回字典列表(每行 {列名: 值})"""
    conn = pymysql.connect(**DB_CONFIG, cursorclass = pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        conn.close()

def download(url, out_path):
    """下载单个文件，成功返回 True"""
    r = requests.get(url, headers = HEADERS, proxies = PROXIES, timeout = 20)
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}")
        return False
    with open(out_path, "wb") as f:     # wb = 二进制写，图片不能用文本模式
        f.write(r.content)
    return True

def main():
    os.makedirs(OUT_DIR, exist_ok = True)

    # 先下官方占位图(那 168 部没有真图的动漫共用这一张)
    placeholder_path = os.path.join(OUT_DIR, "no_icon_subject.png")
    if not os.path.exists(placeholder_path):
        print("下载官方占位图...")
        download(PLACEHOLDER_URL, placeholder_path)

    rows = query_rows("SELECT subject_id, cover_url FROM anime_anime ORDER BY subject_id")
    total = len(rows)
    print(f"共 {total} 部动漫待处理")

    done = skip = fail = 0
    failed_ids = []

    for i, row in enumerate(rows, 1):
        sid = row["subject_id"]
        url = row["cover_url"]
        out_path = os.path.join(OUT_DIR, f"{sid}.jpg")

        if os.path.exists(out_path):
            skip += 1       # 断点续爬: 下过的直接跳过
            continue

        if not url or "lain.bgm.tv" not in url:
            fail += 1       # 占为图(地址坏的), 交给模板兜底
            failed_ids.append(sid)
            continue

        try: 
            if download(url, out_path):
                done += 1
            else:
                fail += 1
                failed_ids.append(sid)
        except Exception as e:
            fail += 1
            failed_ids.append(sid)
            print(f"[{i}/{total}] {sid} 异常: {e}")

        if i % 100 == 0:
            print(f"进度 {i}/{total} | 下载 {done} | 跳过 {skip} | 失败 {fail}")

        time.sleep(0.1)         # 增加停顿时长

    print(f"\n== 完成: 下载 {done} / 跳过 {skip} / 失败 {fail} ===")
    if failed_ids:
        print(f"失败的 subject_id{len(failed_ids)} 个，重跑本脚本会自动重试): {failed_ids}")

if __name__ == "__main__":
    main()
