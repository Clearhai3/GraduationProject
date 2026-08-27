"""
导入 user_ratings 评分表
功能: 读取 user_ratings.csv, 把 120 万条评分写入 user_ratings 表
用法: python import_user_ratings.py
"""

# 导入库
import csv          # 读 csv 文件
import os           # 拼文件路径
import pymysql      # 连 MySQL

# 1.配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "user_ratings.csv")

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "12345678",
    "database": "anime_db",
    "charset": "utf8mb4",
}

def main():
    # 建立连接
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            # 建表 (表不存在才建)，然后清空旧数据, 防止重复导入
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_ratings (
                    user_id  INT NOT NULL,      -- 用户整数 ID
                    anime_id INT NOT NULL,      -- 动漫 ID
                    rate     INT NOT NULL,      -- 评分 1~10
                    PRIMARY KEY (user_id, anime_id),    -- 同一用户同一动漫只评一次
                    INDEX idx_name (anime_id)   -- 按动漫查评分时用这个索引
                ) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4
            """)
            cursor.execute("DELETE FROM user_ratings")
            print("已清空 user_ratings 表")

            rows = []
            with open(CSV_FILE, "r", encoding = "utf-8-sig") as f:  # 自动去BOM
                reader = csv.reader(f)
                header = next(reader)   # 跳过表头: user_id,anime_id,rate
                for record in reader:
                    if len(record) < 3:
                        continue        # 防御: 字段不齐的行跳过
                    user_id  = int(record[0])   # 第0列: 用户ID
                    anime_id = int(record[1])   # 第1列: 动漫ID
                    rate     = int(record[2])   # 第2列: 评分
                    rows.append((user_id, anime_id, rate))

            # 分批插入数据
            sql = """
                  INSERT INTO user_ratings (user_id, anime_id, rate)
                  VALUES (%s, %s, %s)
                  """
            # 120 万条不能一次全插 (会卡死), 分批插入, 每批 10000 条提交一次
            batch = 10000
            for i in range(0, len(rows), batch):
                # 一次执行多条插入, 比一条条 execute 快百倍
                cursor.executemany(sql, rows[i:i + batch])
                conn.commit()   # 每批提交一次, 万一出错最多丢一批
                print(f"已导入 {min(i + batch, len(rows))} / {len(rows)} 条")
        print(f"user_ratings 表导入完成, 共 {len(rows)} 行")
    except Exception as e:
        conn.rollback() # 出错全撤销
        print(f"[错误] {e}")
    finally:
        conn.close      # 必关连接

if __name__ == "__main__":
    main()