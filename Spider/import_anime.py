"""
导入 anime 基础表
功能: 读取 anime_cleaned.csv, 把 1200 条记录写入 anime 表
用法: python import_anime.py
"""

import csv          # 读 csv 文件
import os           # 拼文件路径
import pymysql      # 连 MySQL

# 1.配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "anime_cleaned.csv")

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",
    "database": "anime_db",
    "charset": "utf8mb4",
}

# 2.主程序
def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM anime")      # 先清空，防止重复导入
            print("已清空 anime 表")

            rows = []
            with open(CSV_FILE, "r", encoding = "utf-8-sig") as f:  # 自动去BOM
                reader = csv.reader(f)  # 一个"读一行给一行"的机器
                header = next(reader)   # 先吐第一行(表头)，扔掉不用
                for record in reader:
                    if len(record) < 12:
                        continue        # 防御: 字段不齐的行跳过
                    # 类型转换 + 控制兜底
                    rank_num    = int(record[0]) if record[0].isdigit() else 0
                    # isdigit() 判断"排名"是不是纯数字
                    episodes    = int(record[3]) if record[3].isdigit() else 0
                    score       = float(record[8]) if record[8] else 0.0
                    score_count = int(record[9]) if record[9].isdigit() else 0
                    rows.append((
                        rank_num,   # rank_num
                        record[1],  # name
                        record[2],  # category
                        episodes,   # episodes
                        record[4],  # air_date
                        record[5],  # director
                        record[6],  # script_writer
                        record[7],  # seiyuu
                        score,      # score
                        score_count,# score_count
                        record[10], # cover_url
                        record[11], # detail_url
                    ))

            sql = """
                  INSERT INTO anime
                  (rank_num, name, category, episodes, air_date,
                  director, script_writer, seiyuu, score, score_count,
                  cover_url, detail_url)
                  VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                  """
            # 12 个 %s 对应 12 列 -> 对应元组里的 12 个值，顺序必须一一对应
            cursor.executemany(sql, rows)
            # 一次性插 1200 行
        conn.commit()
        # 提交才生效
        print(f"anime 表导入完成, 共 {len(rows)} 行")
    except Exception as e:
        conn.rollback()
        # 出错全撤销
        print(f"[错误] {e}")
    finally:
        conn.close()
        # 必关连接

if __name__ == "__main__":
    main()