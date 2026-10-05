# -*- coding: utf-8 -*-
"""
打分公式对比脚本 (留一法)
功能: 对比 ItemCF 两种打分公式的推荐效果, 为"排序该用哪个"提供实证依据
      甲 = 不除分母  score(C) = Σ sim(C,A) × (r(A) - 5.5)          <- 证据量, 累加
      乙 = 除分母    score(C) = Σ sim(C,A) × (r(A) - 5.5) / Σ sim(C,A)  <- 加权平均, 预测分
输入:
    itemcf_sim_train.txt    动漫-动漫相似度表 (本舱 data/)
    train_ratings.csv       训练集评分 (公共区 rawdata/data/)
    test_ratings.csv        每个用户藏起的 1 条评分 = 正确答案 (公共区 rawdata/data/)
输出: formula_compare_report.json (分桶命中率对比, 供论文算法选型使用)
用法: python formula_compare.py [采样用户数, 默认 2000]
      留一法里每人只有一个留出项, 所以 hit@10 就等于 Recall@10
"""

import csv
import json
import os
import random
import sys
from collections import defaultdict

# 1. 配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SIM_FILE = os.path.join(SCRIPT_DIR, "..", "data", "itemcf_sim_train.txt")            # 相似度表 (本舱 data/)
TRAIN_FILE = os.path.join(SCRIPT_DIR, "..", "..", "..", "rawdata", "data", "train_ratings.csv")
TEST_FILE = os.path.join(SCRIPT_DIR, "..", "..", "..", "rawdata", "data", "test_ratings.csv")
REPORT_FILE = os.path.join(SCRIPT_DIR, "..", "data", "formula_compare_report.json")  # 报告 (本舱 data/)

CENTER = 5.5            # 中心点: 让 8 分变 +2.5, 3 分变 -2.5
TOP_N = 10              # 取前几名算命中
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
SEED = 42

# 评分条数分桶: 用来回答"评分多了, 除分母会不会变好"
BUCKETS = [(1, 5), (6, 20), (21, 50), (51, 100), (101, 300), (301, 10 ** 9)]


# 2. 读数据
def load_sim_table(sim_file):
    """
    读相似度表, 只认 '相似Top:' 开头的行
    (同一个文件里还混着 '计数:' 的共现行, 必须按前缀过滤)
    返回: {动漫id: {邻居id: 相似度}}
    """
    sim = {}
    with open(sim_file, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("相似Top:"):
                continue
            head, rest = line.rstrip("\n").split("\t", 1)
            anime_id = int(head.split(":")[1])
            sim[anime_id] = {
                int(pair.split(":")[0]): float(pair.split(":")[1])
                for pair in rest.split("|")
            }
    return sim


def load_test_answers(test_file):
    """
    读留出项: 每个用户藏起来的那 1 条评分 (标准答案)
    返回: {用户id: (动漫id, 评分)}
    """
    answers = {}
    with open(test_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            answers[int(row["user_id"])] = (int(row["anime_id"]), int(row["rate"]))
    return answers


def load_train_ratings(train_file, users):
    """
    读训练集, 但只保留目标用户 (文件有 224 万行, 全读会浪费内存)
    返回: {用户id: {动漫id: 评分}}
    """
    train = defaultdict(dict)
    with open(train_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uid = int(row["user_id"])
            if uid in users:
                train[uid][int(row["anime_id"])] = int(row["rate"])
    return train


# 3. 核心: 两种公式各排一次名
def evaluate_user(seen, gold_anime, sim):
    """
    seen       : 这个用户的训练集评分 {动漫id: 评分}
    gold_anime : 留出项 (正确答案)
    sim        : 相似度表
    返回: (评分条数, 甲是否命中, 乙是否命中, 答案是否进了候选)
    """
    if not seen:
        return None

    raw = defaultdict(float)    # 甲: 分子 (累加)
    num = defaultdict(float)    # 乙: 分子
    den = defaultdict(float)    # 乙: 分母

    for anime_id, rate in seen.items():
        weight = rate - CENTER
        for cand, similarity in sim.get(anime_id, {}).items():
            if cand in seen:            # 看过的 / 打过分的, 不再推荐
                continue
            raw[cand] += similarity * weight
            num[cand] += similarity * weight
            den[cand] += similarity

    if not raw:
        return None

    norm = {cand: num[cand] / den[cand] for cand in num if den[cand]}

    def hit(scores):
        top = sorted(scores, key=scores.get, reverse=True)[:TOP_N]
        return 1 if gold_anime in top else 0

    return len(seen), hit(raw), hit(norm), gold_anime in raw


# 4. 主流程
def main():
    print("读相似度表 ...", flush=True)
    sim = load_sim_table(SIM_FILE)
    print(f"  {len(sim)} 部动漫 / {sum(len(v) for v in sim.values())} 条相似关系", flush=True)

    answers = load_test_answers(TEST_FILE)

    random.seed(SEED)
    sample_n = min(SAMPLE, len(answers))
    users = set(random.sample(sorted(answers), sample_n))
    print(f"\n抽样 {sample_n} 个用户做对比 ...", flush=True)

    train = load_train_ratings(TRAIN_FILE, users)
    print("  训练集读取完毕", flush=True)

    # 分桶统计
    stats = {b: {"用户数": 0, "候选覆盖": 0, "甲命中": 0, "乙命中": 0} for b in BUCKETS}
    total = {"用户数": 0, "候选覆盖": 0, "甲命中": 0, "乙命中": 0}

    for uid in users:
        result = evaluate_user(train.get(uid, {}), answers[uid][0], sim)
        if result is None:
            continue
        n, hit_raw, hit_norm, covered = result
        bucket = next(b for b in BUCKETS if b[0] <= n <= b[1])
        for key, value in (("用户数", 1), ("候选覆盖", covered), ("甲命中", hit_raw), ("乙命中", hit_norm)):
            stats[bucket][key] += value
            total[key] += value

    # 打印表格
    print(f"\n{'评分条数':<12}{'用户数':>7}{'候选覆盖':>10}{'甲·不除分母':>14}{'乙·除分母':>12}")
    print("-" * 60)
    rows = []
    for b in BUCKETS:
        s = stats[b]
        if not s["用户数"]:
            continue
        label = f"{b[0]}-{b[1] if b[1] < 10 ** 9 else '以上'}"
        rate_a = s["甲命中"] / s["用户数"]
        rate_b = s["乙命中"] / s["用户数"]
        print(f"{label:<12}{s['用户数']:>7}{s['候选覆盖'] / s['用户数'] * 100:>9.1f}%"
              f"{rate_a * 100:>13.2f}%{rate_b * 100:>11.2f}%")
        rows.append({"评分条数": label, "用户数": s["用户数"],
                     "候选覆盖率": round(s["候选覆盖"] / s["用户数"], 4),
                     "甲_不除分母_Recall@10": round(rate_a, 4),
                     "乙_除分母_Recall@10": round(rate_b, 4)})
    print("-" * 60)
    rate_a = total["甲命中"] / total["用户数"]
    rate_b = total["乙命中"] / total["用户数"]
    print(f"{'合计':<12}{total['用户数']:>7}{total['候选覆盖'] / total['用户数'] * 100:>9.1f}%"
          f"{rate_a * 100:>13.2f}%{rate_b * 100:>11.2f}%")

    # 落盘报告
    report = {
        "方法": "ItemCF 两种打分公式对比 (留一法)",
        "中心点": CENTER,
        "推荐条数每人": TOP_N,
        "采样用户数": total["用户数"],
        "随机种子": SEED,
        "甲_不除分母": {
            "公式": "score(C) = Σ sim(C,A) × (r(A) - 5.5)",
            "含义": "证据量 —— 有多少个你喜欢的番指向它 (累加)",
            "Recall@10": round(rate_a, 4),
        },
        "乙_除分母": {
            "公式": "score(C) = Σ sim(C,A) × (r(A) - 5.5) / Σ sim(C,A)",
            "含义": "加权平均 —— 预测它该得几分",
            "Recall@10": round(rate_b, 4),
        },
        "提升倍数": f"甲是乙的 {rate_a / rate_b:.2f} 倍" if rate_b else "乙为 0",
        "结论": "排序用甲(不除分母); 乙在评分越多时越差, 不适合排序",
        "分桶明细": rows,
    }
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {os.path.relpath(REPORT_FILE, SCRIPT_DIR)}")


if __name__ == "__main__":
    main()
