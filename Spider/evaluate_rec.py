# -*- coding: utf-8 -*-
"""
推荐系统评估脚本 (留一法)
功能: 对照测试集, 计算 ItemCF 推荐的精确率、召回率
输入:
    test_ratings.csv        每个用户藏起的 1 条评分 (正确答案)
    itemcf_rec_train.txt    每个用户的推荐 Top-N
输出: evaluation_report.json (精确率/召回率, 供论文使用)
用法: python evaluate_rec.py
"""

import json
import os

# 1. 配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_FILE = os.path.join(SCRIPT_DIR, "test_ratings.csv")        # 测试集
REC_FILE = os.path.join(SCRIPT_DIR, "itemcf_rec_train.txt")       # 推荐结果
REPORT_FILE = os.path.join(SCRIPT_DIR, "evaluation_report.json")

# 2. 读测试集: 每个用户藏起的正确答案
def load_test_answers(test_file):
    """
    返回: {user_id: anime_id}   (用户ID -> 他藏起的那部动漫)
    """
    answers = {}
    with open(test_file, "r", encoding = "utf-8-sig") as f:
        next(f)     # 跳过表头
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue
            user_id  = int(parts[0])
            anime_id = int(parts[1])
            answers[user_id] = anime_id
    return answers

# 3. 读推荐结果: 每个用户的 Top-N 推荐列表
def load_recommendation(rec_file):
    """
    返回: {user_id: [anime_id, ...]}    (用户ID -> 推荐的动漫列表)
    """
    recs = {}
    with open(rec_file, "r", encoding = "utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            # "推荐:1" -> 1, "793:10.73|841:10.5|..." -> [793, 841, ...]
            user_id = int(parts[0].replace("推荐:", ""))
            anime_list = []
            for item in parts[1].split("|"):
                anime_id = item.split(":")[0]   # 取冒号前的动漫ID
                anime_list.append(int(anime_id))
            recs[user_id] = anime_list
    return recs

# 4. 主程序
def main():
    answers = load_test_answers(TEST_FILE)
    recs = load_recommendation(REC_FILE)

    # 遍历所有用户, 统计命中
    hits = 0        # 命中的用户数
    users = 0       # 参与评估的用户数
    for user_id, answers in answers.items():
        rec_list = recs.get(user_id, [])
        users += 1
        if answers in rec_list:
            hits += 1       # 藏起多的动漫在推荐列表里 -> 命中

    # 计算指标 (N = 10, 每个用户推荐 10 部)
    n = 10
    precision = hits / (users * n) if users else 0.0
    recall    = hits / users if users else 0.0
    # 精确率: 推荐出来的动漫里, 命中的比例
    #   分子是命中数, 分母是"推荐总数" (用户数 x 每人的推荐条数)
    # 召回率: 藏起来的答案里, 被找回的比例
    #   分子是命中数, 分母是"藏起总数" (就是用户数)

    report = {
        "方法": "ItemCF (共现矩阵 + 余弦相似度 + 过滤已看)",
        "评估方式": "留一法 (Leave-One-Out)",
        "用户数": users,
        "推荐条数每人": n,
        "命中数": hits,
        "精确率 Precision@10": round(precision, 4),
        "召回率 Recall@10": round(recall, 4),
        "F1值": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0,
        # F1: 精确率和召回率的调和平均, 两个指标一起看时用
    }

    # 打印 + 存 JSON (写论文用)
    print(json.dumps(report, ensure_ascii = False, indent = 2))
    with open(REPORT_FILE, "w", encoding = "utf-8") as f:
        json.dump(report, f, ensure_ascii = False, indent = 2)
    print(f"评估报告已保存: {REPORT_FILE}")

if __name__ == "__main__":
    main()


