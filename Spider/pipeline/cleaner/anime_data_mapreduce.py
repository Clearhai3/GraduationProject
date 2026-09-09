# -*- coding: utf-8 -*-
"""
    Hadoop MapReduce 分析 - 动漫数据离线统计
    功能: 从 HDFS 读取清洗后的动漫数据，进行多维度统计分析
    输入: HDFS 上 /anime/data/anime_cleaned.csv
    输出: 各维度统计结果，最终存入 MySQL
"""

# -- 头部导入 --
import sys
import re
# re 是 Python 自带的正则表达式工具库。
# re 模块就是用这套语法去检查、查找、替换文字的函数集合。
import logging

# -- 日志配置 --
# 流式任务的标准输出 (stdout) 被 Hadoop 用来传输数据,
# 日志只能写到 stderr，否则会干扰 MapReduce 数据传输。

logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    # 把日志输出标准错误流 (stderr)，不影响 MapReduce 的数据流
    # 在 MapReduce 里，程序的 stdout (标准输出) 是数据通道 —— Mapper 输出的统计结果要靠 stdout 传给 Hadoop
    # 如果日志也写到 stdout，日志会混进数据里，Hadoop 就会把日志当成数据，结果全乱
    # 所以这里把日志强制写到 stderr (错误流), 和数据通道完全隔离
    handlers = [logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("anime_analysis")

# 工具函数
# 功能: 把一行 CSV 文本变成一个"字典" (方便按字段名取值) 。
def parse_csv_line(line):
    """
    解析 CSV 一行，返回字典。
    
    注意: CSV 中某些字段可能包含逗号 (如导演列表)，
    这里接单按逗号分割，因为 HDFS 数据是清洗过的字段，
    不包含内嵌逗号 (列表字段已用顿号连接) 。
    """
    parts = line.strip().split(",")     # 按逗号拆成列表
    if len(parts) < 10:
        return None

    try:
        record = {
            "排名": int(parts[0]) if parts[0].isdigit() else 0,
            # parts[0].isdigit(): 判断"排名"这列是否由纯数字组成
            # int(parts[0]): 把文本 "1" 转成数字 1
            "名称": parts[1],
            "类型": parts[2],
            "话数": int(parts[3]) if parts[3].isdigit() else 0,
            "放送时间": parts[4],
            "导演": parts[5],
            "脚本": parts[6],
            "声优": parts[7],
            "评分": float(parts[8]) if parts[8] else 0.0,
            "评分人数": int(parts[9]) if parts[9].isdigit() else 0,
        }
        return record
    except (ValueError, IndexError) as e:
        logger.warning(f"解析行失败: {line[:50]}... 错误: {e}")
        # logger.warning(...) —— 记录一条"警告级"日志
        # {line[:50]} —— 切片，取这一行的前 50 个字符
        # {e} —— 异常对象的文字描述
        return None

def extract_year(date_str):
    """
    从放送时间提取年份。
    标准化后的格式是 '2004-01-01'、'2004-10'、'2004' 或 '未知'。
    """
    # 空值判断
    if not date_str or date_str == "未知":
        return "未知"
    
    # 正则匹配
    m = re.match(r"(\d{4})", date_str)
    # re.match: 从字符串开头开始匹配 (用 match 而不是 search，是因为日期拥有以年份开头)。
    # 语法: m = re.match(规律, 待检查的字符串)
    # r: 原始字符串标记，让 \d 里的反斜杠不被"转义"，原样传给正则引擎
    # \d: 恰好重复 4 次

    # 取结果
    return m.group(1) if m else "未知"
    # m.group(1) 就是"取第 1 个括号里的内容"，也就是 (\d{4}) 抓到的那 4 个字。

# Mapper 1: 按类型统计
# map 输出: key = "类型:{类型名}"   value = "1\t评分\t评分人数"

# 流程图:
# 一行 CSV 数据进入
#    ↓
# 去首尾空白
#    ↓
# 是表头吗？ ──是──→ 跳过这行
#    ↓否
# 解析成字典失败吗？ ──失败──→ 跳过这行
#    ↓成功
# 取出"类型、评分、评分人数"三个值
#    ↓
# 打印一行输出  类型:TV  1  9.2  10006

def mapper_type():
    """
    类型统计 Mapper。
    输出格式: 类型: TV\t1\t8.5\t10006
    """
    for line in sys.stdin:
    # 数据的入口
    # sys.stdin 是标准输入。

        line = line.strip()
        # strip() 去掉字符串开头和结尾的空白字符。
        # 读进来的每行末尾都带一个换行符 \n (看不见)，必须去掉，否则会影响后面的拆分和比较。
        # 跳过表头行
        if line.startswith("排名,名称,类型"):
        # startswith(...): 判断这一行是不是以"排名,名称,类型"开头 (即表头行)
            continue
        # parse_csv_line(line): 把这一行变成字典
        record = parse_csv_line(line)
        # 防御性编程的衔接: 解析函数保证"失败的返回 None，不抛异常"，这里保证"遇到 None 不处理、直接跳过"。
        if not record:
            continue

        # 取出需要的三个值
        anime_type = record.get("类型", "未知")
        # record.get(键, 默认值) 是字典的"安全取值": 取得到就返回值，取不到就返回默认值 (第二个参数)。
        score = record.get("评分", 0.0)
        score_count = record.get("评分人数", 0)

        # 输出格式: 键\t值      (Hadoop 默认用制表符分隔 key 和 value)
        print(f"类型:{anime_type}\t1\t{score}\t{score_count}")
        # 类型:TV  ←←← 制表符 →→→  1   ←←→  9.2  ←←→  10006
        # └─ key ─┘                     └──── value ────┘
        # \t 是制表符 (按 Tab 键的效果)，Hadoop 规定用它分隔"键 key"和"值 value"
        # key = 类型:TV : 统计的关键词，后面 Reducer 按它分组
        # value = 1\t9.2\t10006 : 三个子值用制表符连在一起，分别是 计数1、评分、评分人数

        # 为什么腰带 类型: 前缀？两个作用:
        # 1. 语义清晰: 一眼看出这是按类型统计
        # 2. reducer 方便去前缀: Reducer 里 current_key.replace("类型:", "") 一替换就还原出干净的类型名

# Reducer 1: 按类型统计
# reduce 输入:  key = "类型:TV"     values = ["1\t8.5\t10006", ...]
# reduce 输出: TV\t120\t7.6\t12500

# "汇总员"函数，负责把 Mapper 拆出来的零散数据按类型汇总。
# 它是这个脚本里最核心、也最典型的算法模式。

# Mapper 输出的每一行是 类型:TV\t1\t9.2\t10006。
# 在进 Reducer 之前，Hadoop 已经自动把所有行按 key 排序，相同 key 的行会连续排在一起。
# 所以 Reducer 实际读到的是这样的数据流:
# 类型:OVA  1  7.8  5000      ← OVA 的三行连在一起
# 类型:OVA  1  7.5  3000
# 类型:OVA  1  7.2  2000
# 类型:TV   1  8.5  10006     ← 然后 TV 的行
# 类型:TV   1  9.2  31321
# 类型:WEB  1  8.0  800       ← WEB 的行
# 注意: 这是一个重要的前提: 正是因为相同 key 连续出现，Reducer 才能用"边读边累加"的方式统计。
def reducer_type():
    """
    类型统计 Reducer。
    统计每种类型的: 数量、平均评分、总评分人数
    """
    current_key = None
    # 当前正在统计的类型 (比如"类型:TV")
    count = 0
    # 该类型累计的番剧数量
    score_sum = 0.0
    # 该类型所有番剧的评分之和
    score_count_sum = 0
    # 该类型所有番剧的评分人数之和
    # 通俗理解: 4 个临时账本，每切换一个类型，就翻到新的一页重新记。

    # 输入的每行格式: 类型:TV\t1\t8.5\t10006
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
    # 逐行读取，去掉换行，空行跳过。

        # 把一行拆开
        parts = line.split("\t")    # 按制表符拆开

        # 是代码防御机制, len(parts) < 4 是防御 —— 格式不完整的行直接跳过。
        if len(parts) < 4:
            continue

        key = parts[0]      # "类型:TV"
        item_count = int(parts[1])  # 1
        score = float(parts[2])     # 9.2
        score_count = int(parts[3]) # 10006

        # Hadoop 会按键排序，相同的 key 会连续出现
        # 判断"是不是同一个类型" (算法核心)
        if key != current_key:
            # 输出上一个 key 的统计结果
            if current_key is not None:
                avg_score = round(score_sum / count, 2) if count > 0 else 0.0
                # 输出格式: 类型名\t数量\t平均评分\t总评分人数
                type_name = current_key.replace("类型:", "")
                print(f"{type_name}\t{count}\t{avg_score}\t{score_count_sum}")

            # 切换新 key
            current_key = key
            count = 0
            score_sum = 0.0
            score_count_sum = 0

        # 累加当前 key 的统计
        count += item_count
        score_sum += score
        score_count_sum += score_count

    # 不要忘记输出最后一个 key
    if current_key is not None:
        avg_score = round(score_sum / count, 2) if count > 0 else 0.0
        type_name = current_key.replace("类型:", "")
        print(f"{type_name}\t{count}\t{avg_score}\t{score_count_sum}")

# Mapper 2: 按年份趋势统计
# map 输出: key = "年份:2004"  value = "1\t评分"

def mapper_year():
    """
    年份趋势统计 Mapper。
    从放送时间提取年份，统计每年番剧数量和评分评分。
    """
    for line in sys.stdin:
    # 数据入口
    # sys.stdin 是标准输入
        line = line.strip()
        if line.startswith("排名,名称,类型"):
            continue
        record = parse_csv_line(line)
        if not record:
            continue

        # extract_year(): 将年份时间进行标准化处理。
        year = extract_year(record.get("放送时间", ""))
        score = record.get("评分", 0.0)
        score_count = record.get("评分人数", 0)

        print(f"年份:{year}\t1\t{score}\t{score_count}")
        # 输出为:  年份:1998	1	9.1	19404

# Reducer 2: 按年份趋势统计
# reduce 输出: 2004\t10\t8.2\t50000

def reducer_year():
    """
    年份趋势统计 Reducer。
    统计每年的: 番剧数量、平均评分、总评分人数
    """
    # 临时配置
    current_key = None
    count = 0
    score_sum = 0.0
    score_count_sum = 0

    for line in sys.stdin:
        line = line.strip()
        # 没有数据去掉，防止崩溃
        if not line:
            continue
        
        # 拆开文本
        parts = line.split("\t")
        # 防止脏数据进来
        if len(parts) < 4:
            continue
        
        # 获取赋值，准备进行判断
        key = parts[0]
        item_count = int(parts[1])
        score = float(parts[2])
        score_count = int(parts[3])

        # 这个地方必进入
        if key != current_key:

            # 在第一次不进入后，在后面都会进入。
            if current_key is not None:
                avg_score = round(score_sum / count, 2) if count > 0 else 0.0
                year_name = current_key.replace("年份:", "")
                print(f"{year_name}\t{count}\t{avg_score}\t{score_count_sum}")

            # 将判断后的key进行刷新
            current_key = key
            # 为下一次循环做好准备
            count = 0
            score_sum = 0.0
            score_count_sum = 0

        # 赋值
        count += item_count
        score_sum += score
        score_count_sum += score_count

    # 为最后一个key准备的
    if current_key is not None:
        avg_score = round(score_sum / count, 2) if count > 0 else 0.0
        year_name = current_key.replace("年份:", "")
        print(f"{year_name}\t{count}\t{avg_score}\t{score_count_sum}")
        # 输出样式:
        # 1998	3	8.53	39404
        # 2004	2	9.05	41327
        # 2011	1	8.5	15660

# Mapper 3: 评分分布统计
# map 输出: key = "评分段:9.0-10.0"     value = "1"

def score_range(score):
    """
    将评分映射到区间段。
    比如 8.7 分 -> "8.0-8.9"
    """
    if score <= 0:
        return "未平分"
    if score < 6.0:
        return "0-5.9"
    if score < 7.0:
        return "6.0-6.9"
    if score < 8.0:
        return "7.0-7.9"
    if score < 9.0:
        return "8.0-8.9"
    return "9.0-10.0"

def mapper_score():
    """评分分布统计 Mapper"""
    for line in sys.stdin:
        line = line.strip()
        if line.startswith("排名,名称,类型"):
            continue

        # 转换为字典。
        record = parse_csv_line(line)
        if not record:
            continue

        score = record.get("评分", 0.0)
        s_range = score_range(score)
        print(f"评分段:{s_range}\t1")

def reducer_score():
    """评分分布统计 Reducer"""
    current_key = None
    count = 0

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        key = parts[0]
        if key != current_key:

            if current_key is not None:
                range_name = current_key.replace("评分段:", "")
                print(f"{range_name}\t{count}")

            current_key = key
            count = 0
            
        count += 1

    if current_key is not None:
        range_name = current_key.replace("评分段:", "")
        print(f"{range_name}\t{count}")

# Mapper 4: 导演作品数统计
# map 输出: key = "导演:新房昭之"  value = "1"

def mapper_director():
    """
    导演作品数统计 Mapper。
    导演字段可能有多人 (用顿号连接), 按人拆分统计。
    """
    for line in sys.stdin:

        line = line.strip()
        if line.startswith("排名,名称,类型"):
            continue
        
        record = parse_csv_line(line)
        if not record:
            continue

        director = record.get("导演", "未知")
        if director == "未知":
            continue

        # 导演字段可能包含多个导演，用顿号分隔
        directors = re.split(r"[、,，]", director)
        for d in directors:
            d = d.strip()
            if d:
                print(f"导演:{d}\t1")

def reducer_director():
    """导演作品数统计 Reducer"""
    current_key = None
    count = 0

    for line in sys.stdin:

        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 2:
            continue

        key = parts[0]
        if key != current_key:

            if current_key is not None:
                director_name = current_key.replace("导演:", "")
                print(f"{director_name}\t{count}")

            current_key = key
            count = 0

        count += 1

    if current_key is not None:
        director_name = current_key.replace("导演:", "")
        print(f"{director_name}\t{count}")

# Mapper 5: 声优作品数统计
# map 输出: key = "声优:花澤香菜"   value = "1"
def mapper_seiyuu():
    """
    声优作品数统计 Mapper。
    声优字段可能有多人 (用顿号连接), 按人拆分统计。
    输出格式: 声优:花澤香菜\t1
    """
    for line in sys.stdin:

        line = line.strip()
        if line.startswith("排名,名称,类型"):
            continue

        record = parse_csv_line(line)
        if not record:
            continue

        seiyuu = record.get("声优", "")
        if not seiyuu:
            continue

        # 声优字段可能包含多个声优，用顿号分隔
        seiyuu = re.split(r"[、,，]", seiyuu)
        for s in seiyuu:
            s = s.strip()
            if s:
                print(f"声优:{s}\t1")

def reducer_seiyuu():
    """声优作品数统计 Reducer。输出格式: 声优名\t"""
    current_key = None
    count = 0

    for line in sys.stdin:

        line = line.strip()
        if not line:
            continue
        
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        key = parts[0]
        if key != current_key:
            
            if current_key is not None:
                seiyuu_name = current_key.replace("声优:", "")
                print(f"{seiyuu_name}\t{count}")
            
            current_key = key
            count = 0
        
        count += 1

    if current_key is not None:
        seiyuu_name = current_key.replace("声优:", "")
        print(f"{seiyuu_name}\t{count}")

# Mapper 6: 话数分布统计
# map 输出: key = "话数段:13-24集"      value = "1"

def episodes_range(episodes):
    """
    将话数映射到区间段。
    比如 24 话 -> "13-24集数"
    """
    if episodes <= 0:
        return "0集"
    if episodes == 1:
        return "1集"
    if episodes <= 12:
        return "2-12集"
    if episodes <= 24:
        return "13-24集"
    if episodes <= 52:
        return "25-52集"
    return "53集以上"

def mapper_episodes():
    """
    话术分布统计 Mapper。
    将话数映射到区间段。
    输出格式: 话数段:13-24集\t1
    """
    for line in sys.stdin:

        line = line.strip()
        if line.lstrip("\ufeff").startswith("排名,名称,类型"):
            continue
        
        record = parse_csv_line(line)
        if not record:
            continue

        episodes = record.get("话数", 0)
        e_range = episodes_range(episodes)
        print(f"话数段:{e_range}\t1")

def reducer_episodes():
    """话数分布统计 Reducer。输出格式: 区间名\t数量"""
    current_key = None
    count = 0

    for line in sys.stdin:

        line = line.strip()
        if not line:
            continue
        
        parts = line.split("\t")
        if len(parts) < 2:
            continue

        key = parts[0]
        if key != current_key:
            
            if current_key is not None:
                range_name = current_key.replace("话数段:", "")
                print(f"{range_name}\t{count}")
            
            current_key = key
            count = 0
        
        count += 1

    if current_key is not None:
        range_name = current_key.replace("话数段:", "")
        print(f"{range_name}\t{count}")

# Mapper 7: 评分 TOP 榜
# map 输出: key = "评分"  value = "名称\t评分人数"

def mapper_top():
    """
    评分 TOP 榜 Mapper。
    输出格式: 评分\t名称\t评分人数
    注意: 评分不为 0 才输出 (未评分的排除)
    """
    for line in sys.stdin:
        
        line = line.strip()
        if line.startswith("排名,名称,类型"):
            continue
        
        record = parse_csv_line(line)
        if not record:
            continue

        score = record.get("评分", 0.0)
        if score <= 0:
            continue

        name = record.get("名称", "未知")
        score_count = record.get("评分人数", 0)
        print(f"{score}\t{name}\t{score_count}")

def reducer_top():
    """
    评分 TOP 榜 Reducer。
    收集全部数据，按评分降序排序 (评分相同则评分人数多的优先)，输出前 20 名。
    注意: 此模式必须使用 1 个 reducer，否则无法得到全局排名。
    """
    top_n = 20
    items = []

    for line in sys.stdin:

        line = line.strip()
        if not line:
            continue
        
        parts = line.split("\t")
        if len(parts) < 3:
            continue

        try:
            score = float(parts[0])
            name = parts[1]
            score_count = int(parts[2])
        except (ValueError, TypeError):
            continue

        items.append((score, name, score_count))

    # 按评分降序，评分相同按评分人数降序
    items.sort(key = lambda x: (-x[0], -x[2]))
    # items.sort(...) —— 列表的排序方法
    # 把 items 里的元素从小到大排好序 (直接修改原列表)。
    # lambda 是 Python 写"一次性小函数"的简写。等价于:
    # def 匿名函数(x):        # 每个元素 x 都会被传进来
    #   return (-x[0], -x[2])
    # x 就是列表里的每个包裹 (score, name, score_count) :
    #   x[0] = 评分
    #   x[2] = 评分人数
    # 负号 - 的意义 —— 把升序变降序
    # sort 默认从小到大排 (升序)。加了负号，评分越高，-x[0] 越小，排得越靠前 —— 变成降序。

    # 输出前 20 名
    for i, (score, name, score_count) in enumerate(items[:top_n], 1):
    # enumerate(列表, 1) —— 自动编号 enumerate 会给列表里每个元素配上序号，第二个参数 1 表示从 1 开始编号 (默认是 0 )。
    # for i, (score, name, score_count) in ... —— 解包 每个元素是 (序号, 包裹)，把序号给 i，把包裹的三个值分别给 score、name、score_count。
        print(f"{i}\t{name}\t{score}\t{score_count}")

# Mapper 8: 季度趋势统计
# map 输出: key = "季度:2004-Q1"   value = "1\t评分\t评分人数"

def extract_season(date_str):
    """
    从放送时间提取年份+季度。
    标准化后的格式是 '2004-01-01'、'2004-10'、'2004' 或 '未知'。
    返回: '2004-Q1'、'2004-未知' 或 '未知'
    """
    if not date_str or date_str == "未知":
        return "未知"

    # 完整日期或年月: 2004-01-01 / 2004-10
    m = re.match(r"(\d{4})-(\d{1,2})", date_str)
    # (\d{1,2}) : 1 或 2 个数字 (月份)
    if m:
        year, month = m.group(1), int(m.group(2))
        quarter = (month - 1) // 3 + 1
        # 季度所属区域的计算
        return f"{year}-Q{quarter}"

    # 只有年份: 2004
    m = re.match(r"(\d{4})", date_str)
    if m:
        return f"{m.group(1)}-未知"

    return "未知"

def mapper_season():
    """
    季度趋势统计 Mapper。
    从放送时间提取年份+季度，统计每季度番剧数量和评分。
    输出格式: 季度:2004-Q1\t1\t8.5\t10006
    """
    for line in sys.stdin:

        line = line.strip()
        if line.startswith("排名,名称,类型"):
            continue
        
        record = parse_csv_line(line)
        if not record:
            continue

        season = extract_season(record.get("放送时间", ""))
        score = record.get("评分", 0.0)
        score_count = record.get("评分人数", 0)

        print(f"季度:{season}\t1\t{score}\t{score_count}")

def reducer_season():
    """
    季度趋势统计 Reducer。
    统计每季度的: 番剧数量、平均评分、总评分人数
    """
    current_key = None
    count = 0
    score_sum = 0.0
    score_count_sum = 0

    for line in sys.stdin:

        line = line.strip()
        if not line:
            continue

        parts = line.split("\t")
        if len(parts) < 4:
            continue

        key = parts[0]
        item_count = int(parts[1])
        score = float(parts[2])
        score_count = int(parts[3])

        if key != current_key:
            
            if current_key is not None:
                avg_score = round(score_sum / count, 2) if count > 0 else 0.0
                season_name = current_key.replace("季度:", "")
                print(f"{season_name}\t{count}\t{avg_score}\t{score_count_sum}")

            current_key = key
            count = 0
            score_sum = 0.0
            score_count_sum = 0

        count += item_count
        score_sum += score
        score_count_sum += score_count

    if current_key is not None:
        avg_score = round(score_sum / count, 2) if count > 0 else 0.0
        season_name = current_key.replace("季度:", "")
        print(f"{season_name}\t{count}\t{avg_score}\t{score_count_sum}")
# 主程序入口

if __name__ == "__main__":
    """
    运行方式: 由 Hadoop Streaming 指定运行哪个 mapper/reducer
    例如:
        hadoop jar $HADOOP_HOME/share/hadoop/tools/lib/hadoop-streaming-*.jar \\
            -input /anime/data/anime_cleaned.csv \\
            -output /anime/analysis/type \\
            -mapper "python anime_analysis.py mapper_type" \\
            -reducer "python snime_analysis.py reducer_type" \\
            -file anime_analysis.py
    
    解释:
        -input:     HDFS 上的输入文件路径
        -output:    分析结果输出到 HDFS 的目录
        -mapper:    指定 mapper 命令
        -reducer:   指定 reducer 命令
        -file:      把 Python 脚本分发到所有 Hadoop 节点
    """
    if len(sys.argv) < 2:
        logger.error("请指定运行模式: mapper_type/reducer_type/mapper_year/...")
        sys.exit()

    mode = sys.argv[1]
    logger.info(f"启动分析模式: {mode}")

    # 根据命令行参数选择对应的 mapper 或 reducer
    mode_map = {
        "mapper_type": mapper_type,
        "reducer_type": reducer_type,
        "mapper_year": mapper_year,
        "reducer_year": reducer_year,
        "mapper_score": mapper_score,
        "reducer_score": reducer_score,
        "mapper_director": mapper_director,
        "reducer_director": reducer_director,
        "mapper_seiyuu": mapper_seiyuu,
        "reducer_seiyuu": reducer_seiyuu,
        "mapper_episodes": mapper_episodes,
        "reducer_episodes": reducer_episodes,
        "mapper_top": mapper_top,
        "reducer_top": reducer_top,
        "mapper_season": mapper_season,
        "reducer_season": reducer_season,
    }

    func = mode_map.get(mode)
    if func is None:
        logger.error(f"未知模式: {mode}")
        logger.error(f"可用的模式: {list(mode_map.keys())}")
        sys.exit(1)

    func()
    logger.info(f"分析完成: {mode}")