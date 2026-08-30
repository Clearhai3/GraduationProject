# -*- coding: utf-8 -*-
"""
留一法数据切分脚本
功能: 把 user_ratings.csv 按用户随机藏起 1 条评分, 切成训练集 + 测试集
输入: user_ratings.csv (user_id, anime_id, rate)
输出:
    train_ratings.csv  训练集 (每个人剩下 N-1 条)
    test_ratings.csv   测试集 (每个人藏起的那 1 条)
用法: python split_train_test.py
"""

import csv
import os
import random

# 1.配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RATINGS_FILE = os.path.join(SCRIPT_DIR, "user_ratings.csv")     # 输入
TRAIN_FILE = os.path.join(SCRIPT_DIR, "train_ratings.csv")      # 输出: 训练集
TEST_FILE = os.path.join(SCRIPT_DIR, "test_ratings.csv")        # 输出: 测试集
RANDOM_SEED = 42        # 固定随机种子, 保证实验可复现 (论文里要写这个数字)

# 2.主程序
def main():
    random.seed(RANDOM_SEED)    # 固定种子, 每次跑切分结果都一样

    # 第一次遍历: 按用户分组, 攒每个人的所有评分
    user_ratings = {}       # 用户ID -> [(anime_id, rate), ...]
    with open(RATINGS_FILE, "r", encoding = "utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)        # 跳过表头
        for row in reader:
            if len(row) < 3:
                continue    # 防御
            user_id  = int(row[0])
            anime_id = int(row[1])
            rate     = int(row[2])
            user_ratings.setdefault(user_id, []).append((anime_id, rate))

    print(f"共 {len(user_ratings)} 个用户")

    # 第二次遍历: 每个用户随机藏 1 条
    train_rows = []     # (user_id, anime_id, rate)
    test_rows = []
    for user_id, ratings in user_ratings.items():
        # 每个用户只藏 1 条, 随机选
        test_idx = random.randrange(len(ratings))
        # random.randrange(n): 从 0 到 n-1 随机取一个整数
        for i, (anime_id, rate) in enumerate(ratings):
            row = (user_id, anime_id, rate)
            if i == test_idx:
                test_rows.append(row)       # 这一条进测试集
            else:
                train_rows.append(row)      # 其余进训练集

    # 写训练集
    with open(TRAIN_FILE, "w", encoding = "utf-8", newline = "") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "anime_id", "rate"])
        writer.writerows(train_rows)

    # 写测试集
    with open(TEST_FILE, "w", encoding = "utf-8", newline = "") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "anime_id", "rate"])
        writer.writerows(test_rows)

    # 打印统计 (写论文用)
    print(f"训练集: {len(train_rows)} 条")
    print(f"测试集: {len(test_rows)} 条")
    print(f"测试集条数 = 用户数 = {len(test_rows)} (每人藏 1 条)")

if __name__ == "__main__":
    main()
