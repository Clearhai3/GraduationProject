import json
import csv
import os
import re

# 配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RATINGS_FILE = os.path.join(SCRIPT_DIR, "user_ratings.jsonl")   # 输入: 爬虫产物
CSV_FILE = os.path.join(SCRIPT_DIR, "anime_cleaned.csv")        # 输入: 动漫表
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "user_ratings.csv")       # 输出: 清洗后的标准评分
REPORT_FILE = os.path.join(SCRIPT_DIR, "cleaning_report.json")  # 输出: 报告
MIN_RATINGS = 5     # 用户打分限制

# 输入加载动漫表 ID 
def load_anime_ids(csv_file):
    """返回: set 类型，装着动漫表里所有的 subject_id"""
    anime_ids = set()
    with open(csv_file, "r", encoding = "utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)        # 跳过表头
        for row in reader:
            if len(row) < 12:
                continue
            m = re.search(r"/subject/(\d+)", row[11])
            if m:
                anime_ids.add(int(m.group(1)))
    return anime_ids

# 读评分 + 过滤
def load_and_filter(anime_ids, min_ratings):
    """
    读评分文件，过滤出动漫表内的记录
    返回: 过滤后的评分列表 [(用户名, subject_id, rate), ...]
    """
    keep = []
    stats = {"总数": 0, "表内": 0, "表外": 0}

    with open(RATINGS_FILE, "r", encoding = "utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue        # 跳过空行
            rec = json.loads(line)        # 一行一条 JSON
            stats["总数"] += 1
            if rec["subject_id"] in anime_ids:      # 关键判断
            # 用 set 直接进行哈希值的查找，查找效率是O(1)
                keep.append((rec["用户名"], rec["subject_id"], rec["rate"]))
                stats["表内"] += 1
            else:
                stats["表外"] += 1

    return keep, stats

# 用户名 -> 整数 ID
def assign_user_ids(keep):
    """
    把用户名映射成整数 ID。
    返回: (带整数ID的列表，用户名->ID的字典)
    """
    id_map = {}     
    result = []
    next_id = 1

    for username, sid, rate in keep:
        if username not in id_map:      # 第一次见到这个用户
            id_map[username] = next_id  # 发一个新编号
            next_id += 1
        result.append((id_map[username], sid, rate))

    return result, id_map

# 过滤冷用户 (评分 < 5 条)
def filter_cold_users(records, min_ratings):
    """
    去掉评分条数少于 min_ratings 的用户。
    """
    # 第一次遍历: 统计每个用户评了多少条
    user_counts = {}
    for uid, sid, rate in records:
        user_counts[uid] = user_counts.get(uid, 0) + 1

    # 第二次遍历: 只保留评分够多的用户
    result = [r for r in records if user_counts[r[0]] >= min_ratings]
    return result

# 写 CSV
def save_csv(records, output_file):
    """
    把 (user_id, subject_id, rate) 写成三列 CSV
    """
    with open(output_file, "w", encoding = "utf-8", newline = "") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "anime_id", "rate"])    # 表头
        writer.writerows(records)       #  全部数据一次性写入

# 汇总报告 (写论文)
def save_report(stats, final_records, output_file):
    """
    把清洗前后的对比数据存成 JSON 报告
    """
    report = {
        "评分总数": stats["总数"],
        "动漫表内评分": stats["表内"],
        "动漫表外评分(已丢弃)": stats["表外"],
        "清洗后评分": len(final_records),
        "清洗后用户数": len(set(r[0] for r in final_records)),
        "清洗后动漫数": len(set(r[1] for r in final_records)),
    }
    with open(output_file, "w", encoding = "utf-8") as f:
        json.dump(report, f, ensure_ascii = False, indent = 2)

# 主程序
def main():
    anime_ids = load_anime_ids(CSV_FILE)
    keep, stats = load_and_filter(anime_ids, MIN_RATINGS)
    records, id_mmap = assign_user_ids(keep)
    records = filter_cold_users(records, MIN_RATINGS)
    save_csv(records, OUTPUT_CSV)
    save_report(stats, records, REPORT_FILE)
    print(f"清洗完成: 保留 {len(records)} 条评分")

if __name__ == "__main__":
    main()

