# -*- coding: utf-8 -*-
"""
推荐结果落库脚本
功能: 把 ItemCF 生成的推荐结果 itemcf_rec.txt 写入 user_recommendations 表
输入: itemcf_rec.txt (格式: 推荐:{user_id}\t{anime_id}:{score}|{anime_id}:{score}|...)
输出: MySQL 的 user_recommendations 表
用法: python import_rec_to_mysql.py
"""

import os
import datetime
import pymysql

# 1. 配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REC_FILE = os.path.join(SCRIPT_DIR, "itemcf_rec.txt")       # 推荐结果 (全量数据那版)

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",
    "database": "anime_db",
    "charset": "utf8mb4",
}

# 2. 主程序
def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 建表 + 清空 (防止重复导入)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_recommendations (
                    user_id INT NOT NULL,       -- 用户 ID
                    rank_num INT NOT NULL,      -- 推荐排名 1~10
                    anime_id INT NOT NULL,      -- 推荐的动漫 ID
                    score    FLOAT NOT NULL,    -- 推荐分数
                    stat_date DATE NOT NULL,    -- 生成日期
                    PRIMARY KEY (user_id, rank_num, stat_date)
                ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
            """)
            cursor.execute("DELETE FROM user_recommendations")
            print("已清空 user_recommendations 表")

            rows = []
            with open(REC_FILE, "r", encoding = "utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) < 2:
                        continue
                    user_id = int(parts[0].replace("推荐:", ""))
                    # 解析推荐列表: "793:10.73|841:10.5|..."
                    rank = 1
                    for item in parts[1].split("|"):
                        anime_id, score = item.split(":")
                        rows.append((user_id, rank, int(anime_id),
                                     float(score), datetime.date.today()))
                        rank += 1

                # 批量插入
                sql = """
                      INSERT INTO user_recommendations
                      (user_id, rank_num, anime_id, score, stat_date)
                      VALUES (%s, %s, %s, %s, %s)
                      """
                batch = 5000
                for i in range(0, len(rows), batch):
                    cursor.executemany(sql, rows[i:i + batch])
                    conn.commit()
                    print(f"已导入 {min(i + batch, len(rows))} / {len(rows)} 行")
            print(f"推荐结果导入完成, 共 {len(rows)} 行")
    except Exception as e:
        conn.rollback()
        print(f"[错误] {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()