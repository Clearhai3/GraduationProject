# -*- coding: utf-8 -*-
"""
大屏数据预计算脚本
功能: 把散落在 paper_summary.json / MySQL / 算法报告里的统计结果，统一算成 ECharts 能直接吃的 JSON
输出: Spider/webdata/ 下的 8 个 JSON
用法: python build_dashboard.py
"""

import json
import os
import pymysql

# 1. 配置区域
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))     # -> Spider/webdata
SPIDER_DIR = os.path.dirname(SCRIPT_DIR)                    # -> Spider
SUMMARY_JSON = os.path.join(SPIDER_DIR, "summary", "paper_summary.json")
ITEMCF_REPORT = os.path.join(SPIDER_DIR, "algorithms", "itemcf", "data", "evaluation_report.json")
ALS_REPORT = os.path.join(SPIDER_DIR, "algorithms", "als", "data", "als_report.json")

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
    """读 JSON 文件，返回字典"""
    with open(path, "r", encoding = "utf-8") as f:
        return json.load(f)

def query_rows(sql):
    """连库执行 SELECT, 返回字典列表(每行是 {列名: 值})"""
    conn = pymysql.connect(**DB_CONFIG, cursorclass = pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        conn.close()        # 无论成功失败都关连接

def save_json(subdir, filename, data):
    """把 data 写成 webdata/<subdir>/<filename>"""
    out_dir = os.path.join(SCRIPT_DIR, subdir)
    os.makedirs(out_dir, exist_ok = True)
    out_path = os.path.join(out_dir, filename)      # 输出到的地址位置: webdata/ratings/score_distribution.json
    with open(out_path, "w", encoding = "utf-8") as f:
        json.dump(data, f, ensure_ascii = False, indent = 2)
    print(f"已生成: {out_path}")

def build_score_distribution():
    """图1: 评分分布(1~10分各有多少条) —— 数据源 paper_summary.json"""
    summary = load_json(SUMMARY_JSON)
    dist = summary["评分分布"]

    labels = []
    values = []
    for score in range(1, 11):      # 1~10, 数字顺序
        key = f"{score}分"          # 拼出 "1分" "2分" ...
        labels.append(key)
        values.append(dist.get(key, 0))     # get 兜底: 万一某档没数据给 0, 别崩

    save_json("ratings", "score_distribution.json", {"labels": labels, "values": values})
    return sum(values)              # 返回总和，主流程拿去验收

def build_user_activity():
    """图2: 用户活跃度分层 —— 数据源 paper_summary.json"""
    summary = load_json(SUMMARY_JSON)
    activity = summary["用户活跃度分层"]

    order = ["1-10条", "11-50条", "51-100条", "100条以上"]

    # 防御性: 先查键全不全，缺了就当场炸，别让错别字溜进去
    missing = [k for k in order if k not in activity]
    if missing:
        raise KeyError(f"paper_summary.json 里缺少这些键: {missing}")

    labels = order                                  # 清单本身就是 labels, 不用再 append 一遍
    values = [activity[k] for k in order]           # 键已经验过了，放心用 []

    save_json("users", "user_activity.json", {"labels": labels, "values": values})
    return sum(values)

def build_type_distribution():
    """图3: 动漫类型分布 —— 数据源 MySQL anime_anime"""
    sql = """
        SELECT anime_type, COUNT(*) AS cnt
        FROM anime_anime
        GROUP BY anime_type
        ORDER BY cnt DESC
    """
    rows = query_rows(sql)

    labels = [row["anime_type"] for row in rows]
    values = [row["cnt"] for row in rows]

    save_json("anime", "type_distribution.json", {"labels": labels, "values": values})
    return sum(values)

def build_rating_top10():
    """图6: 评分 Top10 —— 数据源 MySQL anime_anime"""
    sql = """
        SELECT name, rating
        FROM anime_anime
        ORDER BY rating DESC, subject_id
        LIMIT 10
    """
    rows = query_rows(sql)

    labels = [row["name"] for row in rows]       # 第1列 = 动漫名
    values = [row["rating"] for row in rows]       # 第2列 = 评分

    save_json("anime", "rating_top10.json", {"labels": labels, "values": values})
    return len(labels)              # 验证长度

def build_active_users_top10():
    """图7: 活跃用户 Top10 —— 数据源 MySQL user_activity_top"""
    sql = """
        SELECT user_id, rating_count
        FROM user_activity_top
        ORDER BY rank_num
        LIMIT 10
    """
    rows = query_rows(sql)

    labels = [f"用户 #{row['user_id']}" for row in rows]    # 没有名字，拼个编号
    values = [row["rating_count"] for row in rows]

    save_json("users", "active_users_top10.json", {"labels": labels, "values": values})
    return len(labels)

def build_hot_anime_top20():
    """图6: 热门动漫 Top20(按评分人数) —— 数据源 MySQL hot_anime JOIN anime_anime"""
    sql = """
        SELECT h.rank_num, a.name, h.rating_count
        FROM hot_anime  AS h
        JOIN anime_anime AS a
            ON h.anime_id = a.subject_id
        ORDER BY h.rank_num
        LIMIT 20
    """

    rows = query_rows(sql)

    labels = [row["name"] for row in rows]
    values = [row["rating_count"] for row in rows]

    save_json("anime", "hot_anime_top20.json", {"labels": labels, "values": values})
    return len(labels)

def build_yearly_trend():
    """图7: 年度放送趋势 —— 数据源 MySQL anime_anime"""
    sql = """
        SELECT YEAR(air_date) AS yr, COUNT(*) AS cnt
        FROM anime_anime
        GROUP BY YEAR(air_date)
        ORDER BY yr IS NULL, yr
    """

    rows = query_rows(sql)

    labels = ["未知" if row["yr"] is None else str(row["yr"]) for row in rows]
    values = [row["cnt"] for row in rows]

    save_json("anime", "yearly_trend.json", {"labels": labels, "values": values})
    return sum(values)

def build_algorithm_compare():
    """图8: 算法效果对比 —— 数据源两份算法报告"""
    itemcf = load_json(ITEMCF_REPORT)
    als = load_json(ALS_REPORT)

    itemcf_labels = ["随机猜测", "精确率 @10", "召回率 @10"]
    itemcf_values = [0.20,
                     round(itemcf["精确率 Precision@10"] * 100, 2),
                     round(itemcf["召回率 Recall@10"] * 100, 2)]

    als_labels = ["基准(全猜平均分)", "ALS 模型"]
    als_values = [als["基准RMSE_全猜平均分"], als["RMSE"]]

    data = {
        "itemcf": {"labels": itemcf_labels, "values": itemcf_values},
        "als": {"labels": als_labels, "values": als_values},
    }

    save_json("algorithms", "algorithm_compare.json", data)
    return len(itemcf_values) + len(als_values)

if __name__ == "__main__":
    print("=== 大屏数据预计算 ===")

    total_score = build_score_distribution()
    print(f"验收: 评分分布求和 = {total_score} (应为 2253532)")

    total_user = build_user_activity()
    print(f"验收: 活跃度求和 = {total_user} (应为 10303)")

    total_type = build_type_distribution()
    print(f"验收: 类型分布求和 = {total_type} (应为 5009)")

    rating_top = build_rating_top10()
    print(f"验收: 评分Top10条数 = {rating_top} (应为 10)")

    users_top = build_active_users_top10()
    print(f"验收: 活跃用户Top10条数 = {users_top} (应为 10)")

    hot_top = build_hot_anime_top20()
    print(f"验收: 热门动漫Top20条数 = {hot_top} (应为 20)")

    year_trend = build_yearly_trend()
    print(f"验收: 年度趋势求和 = {year_trend} (应为 5009)")

    algo_cmp = build_algorithm_compare()
    print(f"验收: 算法对比条款 = {algo_cmp} (应为 5)")