# -*- coding: utf-8 -*-
"""
论文数据支撑统计 (收官脚本)
功能: 汇总全项目的关键数字, 生成 paper_summary.json 供论文引用
输入: cleaning_report.json / anime_cleaned.csv / evaluation_report.json / MySQL 统计表
输出: paper_summary.json
用法: python paper_summary.py
"""

import csv
import json
import os
import pymysql

# 1. 配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CLEAN_REPORT = os.path.join(SCRIPT_DIR, "cleaning_report.json")     # 清洗报告
ANIME_CSV = os.path.join(SCRIPT_DIR, "anime_cleaned.csv")           # 动漫表
EVAL_REPORT = os.path.join(SCRIPT_DIR, "evaluation_report.json")    # 评估报告

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",
    "database": "anime_db",
    "charset": "utf8mb4",
}

# 2. 工具函数
def load_json(path):
    """读 JSON 文件, 返回字典"""
    with open(path, "r", encoding = "utf-8") as f:
        return json.load(f)

def count_csv_lines(path):
    """数 CSV 数据行数 (跳过表头)"""
    count = 0
    with open(path, "r", encoding = "utf-8-sig") as f:
        next(f)     # 跳过表头
        for line in f:
            count += 1
    return count

def query_rows(sql):
    """连库执行 SELECT, 返回行列表"""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        conn.close()

# 3. 主程序
def main():
    # 1. 数据规模
    clean = load_json(CLEAN_REPORT)
    anime_count = count_csv_lines(ANIME_CSV)
    user_count = clean["清洗后用户数"]
    rating_count = clean["清洗后评分"]
    density = round(rating_count / (user_count * anime_count), 4)
    # 密度 = 评分总数 / (用户数 x 动漫数): 打分矩阵里"有评分"的比例

    # 2. 评分分布 (MySQL)
    score_dist = {}
    for rate, cnt in query_rows("SELECT rate, rating_count FROM user_score_distribution"):
        score_dist[f"{rate}分"] = cnt

    # 3. 活跃度分层 (MySQL)
    activity = {}
    for level, cnt in query_rows("SELECT activity_level, user_count FROM user_activity_stats"):
        activity[level] = cnt

    # 4. 推荐评估
    eval_date = load_json(EVAL_REPORT)
    hit = eval_date["命中数"]
    users = eval_date["用户数"]

    # 汇总
    summary = {
        "数据规模": {
            "动漫数": anime_count,
            "用户数": user_count,
            "评分总数": rating_count,
            "评分密度": density,
        }, 
        "评分分布": score_dist,
        "用户活跃度分层": activity,
        "推荐评估": {
            "命中数": hit,
            "参与评估用户数": users,
            "命中率(用户占比)": round(hit / users, 4),
            "Precision@10": eval_date["精确率 Precision@10"],
            "Recall@10": eval_date["召回率 Recall@10"],
            "F1值": eval_date["F1值"],
        },
    } 

    # 输出
    out_path = os.path.join(SCRIPT_DIR, "paper_summary.json")
    with open(out_path, "w", encoding = "utf-8") as f:
        json.dump(summary, f, ensure_ascii = False, indent = 2)
    print(json.dumps(summary, ensure_ascii = False, indent = 2))
    print(f"\n已保存: {out_path}")

if __name__ == "__main__":
    main()