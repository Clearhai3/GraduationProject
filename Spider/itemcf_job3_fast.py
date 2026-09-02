# -- 头部导入 --
import math

TOP_K = 10

# 数据结构
sim_table = {}      # 动漫ID -> {邻居ID: 相似度}
user_ratings = {}   # 用户ID -> [(动漫ID, 评分)]

def main():
    # 读文件
    out = open('itemcf_rec_train.txt', 'w', encoding = 'utf-8')
    with open('itemcf_sim_train.txt', 'r', encoding = 'utf-8') as f:
        for line in f:
            line = line.strip().lstrip('\ufeff')
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            key = parts[0]
            value = parts[1]

            if key.startswith('相似Top:'):
                anime_id = key.replace('相似Top:', '')
                neighbors = {}
                for item in parts[1].split('|'):
                    nid, sim = item.split(':')
                    neighbors[int(nid)] = float(sim)
                sim_table[int(anime_id)] = neighbors
            elif key.startswith('计数'):
                continue    # 计数行跳过，Job3 用不到

    # 读评分表
    with open('train_ratings.csv', 'r', encoding = 'utf-8') as f:
        for line in f:
            line = line.strip().lstrip('\ufeff')
            if not line or line.startswith('user_id'):
                continue    # 跳过表头
            parts = line.split(',')
            if len(parts) < 3:
                continue
            user_id = int(parts[0])
            anime_id = int(parts[1])
            rate = int(parts[2])
            user_ratings.setdefault(user_id, []).append((anime_id, rate))

    for uid, ratings in user_ratings.items():
        scores = {}  # 候选动漫ID -> 累加分
        seen = {anime_id for anime_id, rate in ratings}
        for anime_id, rate in ratings:
            # 用户看过 anime_id, 它的邻居都是候选
            for nid, sim in sim_table.get(anime_id, {}).items():
                if nid in seen:
                    continue
                scores[nid] = scores.get(nid, 0.0) + sim * rate
                # 取 Top10, 降序，输出
        top = sorted(scores.items(), key = lambda x: -x[1])[:TOP_K]
        rec_str = '|'.join(f"{nid}:{score:.2f}" for nid, score in top)
        print(f"推荐:{uid}\t{rec_str}", file = out)
    out.close()

if __name__ == "__main__":
    main()

