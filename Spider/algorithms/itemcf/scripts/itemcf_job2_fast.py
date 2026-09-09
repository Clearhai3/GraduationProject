# -- 头部导入 --
import math
import os

TOP_K = 20

# 本脚本所在目录的上级 data/ = ItemCF 产物舱 (cooccur 输入 / sim 输出)
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
COOCCUR_FILE = os.path.join(DATA_DIR, "itemcf_cooccur_train.txt")   # Job1 输出
SIM_FILE = os.path.join(DATA_DIR, "itemcf_sim_train.txt")           # 本 Job 输出

# -- 1. 三个字典 --
item_count = {}     # 动漫ID -> 被评次数
pair_count = {}     # (A, B) -> 共现次数
top_neighbors = {}  # 动漫ID -> [(邻居, 相似度), ...]


def main():
    # -- 2. 读文件, 填字典 --
    out = open(SIM_FILE, 'w', encoding='utf-8')
    with open(COOCCUR_FILE, 'r', encoding = 'utf-16') as f:
        for line in f:
            line = line.strip().lstrip('\ufeff')
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            key = parts[0]
            value = int(parts[1])

            if key.startswith('单品:'):
                anime_id = key.replace('单品:', '')
                item_count[anime_id] = item_count.get(anime_id, 0) + value
            elif key.startswith('共现:'):
                pair = key.replace('共现:', '')
                a, b = pair.split('|')
                pair_count[(a, b)] = pair_count.get((a, b), 0) + value

    # -- 3. 算相似度 --
    for (a, b), co in pair_count.items():
        ca = item_count.get(a, 1)
        cb = item_count.get(b, 1)
        sim = co / math.sqrt(ca * cb)
        top_neighbors.setdefault(a, []).append((b, sim))
        top_neighbors.setdefault(b, []).append((a, sim))

    # -- 4. 输出 --
    # 输出1: 计数
    for a in sorted(item_count):
        print(f"计数:{a}\t{item_count[a]}", file=out)

    # 输出2: 每部动漫的 Top-K 相似动漫
    for a, neighbors in top_neighbors.items():
        neighbors.sort(key = lambda x: -x[1])   # 按相似度降序
        top = neighbors[:TOP_K]                 # 只留前 20 个
        # 拼成 "100:1.0000|300:0.7071" 格式
        sim_str = "|".join(f"{b}:{sim:.4f}" for b, sim in top)
        print(f"相似Top:{a}\t{sim_str}", file=out)
    out.close()

# 主程序
if __name__ == "__main__":
    main()



