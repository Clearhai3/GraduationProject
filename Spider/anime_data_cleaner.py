import json         # 处理 JSON 格式数据 (读写 JSON 文件)
import re           # 正则表达式，用来从文本里抠数字、日期
import csv          # 读写 CSV 文件 (Excel 能打开的那种)
import os           # 操作系统相关功能，这里主要用来拼文件路径
import logging      # 日志模块，记录程序运行过程
from datetime import datetime   # 从 datetime 包里取出 datetime 类，用来打时间戳

# -- 配置区 --
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# __file__: 当前这个 .py 文件的路径
# os.path.abspath(__file__): 转成绝对路径
# os.path.dirname(...): 取它所在的文件夹
# 整句: 拿到这个脚本所在的目录，存到 SCRIPT_DIR
# 好处: 把整个文件夹搬到别处，路径依然有效。
INPUT_FILE = os.path.join(SCRIPT_DIR, "动漫信息_v2.json")
OUTPUT_JSONL = os.path.join(SCRIPT_DIR, "anime_cleaned.jsonl")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "anime_cleaned.csv")
REPORT_FILE = os.path.join(SCRIPT_DIR, "cleaning_report.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "data_cleaner.log")
# 把文件夹路径和文件名拼起来，得到输入文件的完整路径 (爬虫的输出文件，作为清洗的输入)。

# -- 日志配置 --
logging.basicConfig(
    level = logging.INFO,
    # 设置日志最低级别为 INFO。
    # 日志分 5 级: DEBUG < INFO < WARNING < ERROR < CRITICAL。
    # 设成 INFO 表示 DEBUG 不输出，INFO 及以上才输出。
    format = "%(asctime)s [%(levelname)s] %(message)s",
    # 定义日志格式: 时间 [级别] 内容，比如 2026-07-30 15:00:00 [INFO] 开始清洗。

    # handlers 决定日志输出到哪里:
    handlers = [
        logging.FileHandler(LOG_FILE, encoding = "utf-8"),
        # FileHandler: 写到文件 date_cleaner.log
        logging.StreamHandler(),
        # StreamHandler: 打印到终端屏幕
        # 两个都配，同一条日志会同时去两个地方。
    ],
)
logger = logging.getLogger(__name__)
# 获取一个 logger 对象，名字用 __name__ (即模块名)。后续代码用 logger.info(...) 写日志。

# -- 阶段1: 数据加载与质量检查 --

# 文件获取
# 定义函数 load_and_check, 接收一个参数 input_file (输入文件路径)。
def load_and_check(input_file):
    """
    读取原始 JSONL 文件，检查数据质量
    返回: (records, report)
    - records: 原始数据列表
    - report: 质量报告字典
    """
    logger.info(f"开始加载数据: {input_file}")
    # 写一条 INFO 日志。f"..." 是 f-string, {input_file} 会被替换成实际路径。

    records = []
    # records = [] : 准备一个空列表，存所有记录
    with open(input_file, "r", encoding = "utf-8") as f:
    # with open(...) as f: 打开文件，with 保证用完自动关闭
    # "r": 只读模式
    # encoding = "utf-8": 用 UTF-8 编码读，中文不乱码
        for line_num, line in enumerate(f, 1):
        # 逐行读文件。enumerate(f, 1) 给每行编号，从 1 开始，得到 (行号, 行内容)。

            line = line.strip()
            # 去掉行首尾的空白字符 (包括换行符 \n)。
            if not line:
                continue
            # 如果这一行是空的，跳过，处理下一行。
            try:
                record = json.loads(line)
                records.append(record)
            # try: 尝试执行下面代码，出错就跳到 except
            # json.loads(line): 把这行文本解析成 Python 字典
            # records.append(record): 加到列表里
            except json.JSONDecodeError as e:
                logger.error(f"第 {line_num} 行 JSON 解析失败: {e}")
            # 如果这行不是合法 JSON (坏数据), 就记一条 ERROR 日志，跳过这行继续。
            # as e 把错误对象存到 e。

    total_count = len(records)
    logger.info(f"加载完成，共 {total_count} 条数据")
    # 统计总共读了多少条，写日志。

    # 统计缺失字段
    missing_fields = {
        "名称": 0,
        "话数": 0,
        "放送时间": 0,
        "导演": 0,
        "脚本": 0,
        "声优": 0,
        "评分": 0,
        "评分人数": 0,
        "类型": 0,
    }
    # 建一个字典，每个字段初始计算 0，用来统计各字段有多少条缺失。

    episodes_zero = 0
    air_date_invalid = 0
    score_zero = 0
    # 三个专门的计数器: 话数为 0、放送时间无效、评分为 0 的条数。

    for record in records:
    # 遍历每一条记录。
        # 字符串字段缺失检查
        if not record.get("名称") or record.get("名称") == "未知":
            missing_fields["名称"] += 1
        # record.get("名称"): 从字典取"名称", 没有就返回 None (不会报错)
        # not ... : 如果是空字符串或 None, 结果 True
        # or: 或者值等于 "未知"
        # 命中任一条件，就把"名称"的缺失计数 +1

        if not record.get("放送时间") or record.get("放送时间") == "未知":
            missing_fields["放送时间"] += 1
            air_date_invalid += 1
        # 放送时间缺失时，同时给两个计数器 +1 (既算字段缺失，也算日期无效)。

        if not record.get("导演") or record.get("导演") == "未知":
            missing_fields["导演"] += 1
        # 导演、类型的缺失检查同理。
        
        if not record.get("类型") or record.get("类型") == "未知":
            missing_fields["类型"] += 1

        # 数值字段缺失检查
        if record.get("话数", 0) == 0:
        # record.get("话数", 0): 取"话数"，没有就返回默认值 0
        # 如果等于 0，认为是缺失，两个计数器都 +1
            missing_fields["话数"] += 1
            episodes_zero += 1
        
        if record.get("评分", 0.0) == 0.0:
        # 评分缺失检查 (默认值用 0.0 表示这是浮点数)。
            missing_fields["评分"] += 1
            score_zero += 1

        if record.get("评分人数", 0) == 0:
        # 评分人数缺失检查。
            missing_fields["评分人数"] += 1

        # 列表字段缺失检查
        if not record.get("脚本"):
            missing_fields["脚本"] += 1
        # "脚本" 是列表，空列表 [] 在 not 判断里是 True，所以空列表也算缺失。

        if not record.get("声优"):
            missing_fields["声优"] += 1
        # 声优缺失检查同理。

    # 统计重复
    seen = set()
    # 建一个空集合，存"见过的指纹"
    duplicates = 0
    for record in records:
        key = json.dumps(record, ensure_ascii = False, sort_keys = True)
        # 把记录转成字符串当"指纹"
        # ensure_ascii = False: 中文不转 \uXXXX
        # sort_keys = True: 字段按字母排序，保证同样内容的记录指纹一致。
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
        # 指纹在集合里出现过 -> 重复 +1; 没出现过 -> 加进集合。

    report = {
        "total_count": total_count,
        "missing_fields": missing_fields,
        "duplicates": duplicates,
        "episodes_zero": episodes_zero,
        "air_date_invalid": air_date_invalid,
        "score_zero": score_zero,
        "stage1_time": datetime.now().isoformat(),
    }
    # 把所有统计结果打包成一个字典 report。datetime.now().isoformat() 
    # 是当前时间的标准格式字符串，比如 2026-07-30T15:00:00。

    logger.info("质量检查完成")
    logger.info(f"缺失字段: {missing_fields}")
    logger.info(f"重复条数: {duplicates}")
    # 写几条日志，然后返回两个值: records (原始数据列表) 和 report (体检报告)。

    return records, report

# -- 阶段2: 去重 + 缺失值填充 --
def deduplicate(records):
    """按详情页URL去重 (比按整行更稳，同部番抓两次可能有细微差异)"""
    seen_keys = set()
    unique_records = []
    removed = 0
    # 准备: 空集合存见过的 key、空列表存去重后的记录、计数器记删了几条。
    for record in records:
        # 优先用详情页URL做key, 没有就用名称兜底
        key = record.get("详情页") or record.get("名称", "")
        # record.get("详情页"): 先取详情页 URL
        # or: 如果 URL 为空，就用名称当 key
        # 同一部番的详情页 URL 是唯一的，比用整行内容更可靠
        if key in seen_keys:
            removed += 1
            continue
        seen_keys.add(key)
        unique_records.append(record)
        # key 见过 -> 重复，计数 +1，跳过 (continue); 没见过 -> 加进集合，记录保留。
    logger.info(f"去重完成: 移除 {removed}，剩余 {len(unique_records)} 条")
    return unique_records, removed
    # 写日志，返回去重后的列表和移除条数。

# fill_missing() 缺失值填充 
def fill_missing(records):
    """
    缺失值填充: 
    - 字符串字段 -> "未知"
    - 数值字段 -> 0 (并强制类型转换)
    - 列表字段 -> []
    """
    filled_count = {"字符串": 0, "数值": 0, "列表": 0}
    # 建计数器，分三类统计填了几次。
    for record in records:
        # 字符串
        for field in ["名称", "放送时间", "导演", "类型"]:
            val = record.get(field)
            if not val or val == "未知":
                record[field] = "未知"
                filled_count["字符串"] += 1
        # 对 4 个字符串字段循环: 值为空或已经是 "未知", 统一填 "未知", 计数 + 1

        # 整数字段: 强制转 int
        for field in ["话数", "排名", "评分人数"]:
            try:
                record[field] = int(record.get(field, 0))
                # int(...): 把值转成整数。如果原值是字符串 "26"，会转成数字 26
            except (ValueError, TypeError):
            # 如果转不动 (比如值是 "abc")，就填 0，计数 +1
                record[field] = 0
                filled_count["数值"] += 1
                # 这样保证这 3 个字段一定是整数
                

        # 浮点字段: 强制转 float
        try:
            record["评分"] = float(record.get("评分", 0.0))
        except (ValueError, TypeError):
            record["评分"] = 0.0
            filled_count["数值"] += 1
        # 评分单独处理，转成浮点数 (带小数) 。
        
        # 列表字段
        for field in ["脚本", "声优"]:
            if not isinstance(record.get(field), list):
            # isinstance(x, list): 判断 x 是不是列表
                record[field] = []
                # 如果脚本 / 声优不是列表 (比如是 None 或字符串) , 就替换成空列表 []
                filled_count["列表"] += 1

    logger.info(f"缺失值填充完成: {filled_count}")
    return records, filled_count
    # 写日志，返回填充后的记录和计数。

# -- 阶段3: 格式标准化 --

# 日期解析
def parse_air_date(raw_date):
    """
    解析放送时间，返回标准日期字符串。
    优先级:
        1. '2004年10月1日' -> '2004-10-01'
        2. '2004年10月'    -> '2004-10'
        3. '2004年'        -> '2004'
        4. 脏文本里随便找4位数字 -> 当年份
        5. 都失败 -> '未知'
    """
    # 空值或 "未知" 直接返回 "未知"。
    if not raw_date or raw_date == "未知":
        return "未知"

    # 完整日期
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw_date)
    # re.search(pattern, text): 在 text 里找符合 pattern 的内容
    # \d{4}: 4 个数字 (年份)
    # \d{1,2}: 1~2 个数字 (月/日)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # (): 捕获组，把匹配的内容"抓"出来
    # m.groups(): 返回所有捕获组，比如 ("2004", "10", "1")
    # int(mo):02d: 转整数后格式化成至少 2 位，不够前面补 0 ( 5 -> 05)
    # 最终拼成 2004-10-01
    
    # 年月
    m = re.search(r"(\d{4})年(\d{1,2})月", raw_date)
    if m:
        y, mo = m.groups()
        return f"{y}-{int(mo):02d}"
    # 没有"日", 只匹配"年月", 返回 2004-10。

    # 仅年
    m = re.search(r"(\d{4})年", raw_date)
    if m:
        return m.group(1)
    # 只有"年"，返回 2004。m.group(1) 是第一个捕获组。

    # 兜底: 提取任意4位数字当年份
    m = re.search(r"(\d{4})", raw_date)
    if m:
        return m.group(1)
    # 连"年"字都没有，就随便找 4 位连续数字当年份
    
    return "未知"
    # 再不行返回"未知"。

# 类型提取
def extract_type(raw_type):
    """
    从类型字段提取核心类型。
    原始可能是 '(TV Series, 25 episodes)' 这种带括号的长文本。
    """
    # 空值检查。
    if not raw_type or raw_type == "未知":
        return "未知"

    # 关键词映射表: 标准名 -> 可能出现的关键词
    type_map = {
        "TV":       ["TV", "TV Series", "电视"],
        "OVA":      ["OVA", "Original Video Animation"],
        "剧场版":    ["剧场版", "Movie", "Theatrical"],
        "Web":      ["Web", "网络"],
    }
    # 建映射表，每个标准类型对应多个可能的关键词。
    for std_name, keywords in type_map.items():
        for kw in keywords:
            if kw in raw_type:
                return std_name
    return raw_type     # 都没匹配上就保留原值
    # 外层循环遍历映射表 (items() 返回 (key, value) 对)
    # 内层循环遍历每个标准名下的关键词
    # 只要原文本里包含某个关键词，就返回对应的标准名
    # 全部没匹配上，保留原值

# 导演标准化
def standardize_director(director):
    """统一导演字段的分隔符为顿号，去掉多余空白"""
    # 空值检查。
    if not director or director == "未知":
        return "未知"
    # 把各种分隔符都按顿号切
    parts = re.split(r"[、,，;：\s]+", str(director).strip())
    # re.split(pattern, text): 按 pattern 切割文本
    # [、,，;：\s]+ : 方括号表示"其中任意一个字符", + 表示"一个或多个"
    # str(director).strip(): 先转字符串 (防 None), 再去首尾空白
    parts = [p.strip() for p in parts if p.strip()]
    return "、".join(parts) if parts else "未知"
    # 列表推导式: 对每个 part 去空白，过滤掉空的
    # "、".join(parts): 用顿号把列表拼成字符串
    # 如果切完是空的，返回"未知"

# 标准化主函数
def standardize(records):
    """格式标准化主函数"""
    date_changed = 0
    type_changed = 0
    director_changed = 0
    # 三个计数器，统计每个字段改了几条。

    for record in records:
        # 日期
        old = record.get("放送时间", "")
        new = parse_air_date(old)
        if new != old:
            date_changed += 1
        record["放送时间"] = new
        # 保存原值 -> 调用 parse_air_date 得到新值
        # 如果变了，计数 + 1
        # 写回记录

        # 类型
        old = record.get("类型", "")
        new = extract_type(old)
        if new != old:
            type_changed += 1
        record["类型"] = new
        # 类型字段同理

        # 导演
        old = record.get("导演", "")
        new = standardize_director(old)
        if new != old:
            director_changed += 1
        record["导演"] = new
        # 导演字段同理。

    # 写日志，返回记录和统计字典
    logger.info(f"格式标准化完成: 日期{date_changed}条, 类型{type_changed}条, 导演{director_changed}条")
    return records, {
        "date_changed": date_changed,
        "type_changed": type_changed,
        "director_changed": director_changed,
    }

# -- 阶段4: 输出 --
# 写 JSONL
def save_jsonl(records, output_file):
    """保存为 JSONL 格式 (每行一个JSON对象，保留列表字段)"""
    with open(output_file, "w", encoding = "utf-8") as f:
    # "w": 覆盖写模式
        for r in records:
        # 遍历每条记录，转成 JSON 字符串 (中文不转义), 加换行符 \n, 写入文件
            f.write(json.dumps(r, ensure_ascii = False) + "\n")
            # JSONL 保留列表字段 (脚本、声优还是 list)
    logger.info(f"已保存 JSONL: {output_file} （{len(records)}条）")

# 写 CSV
def save_csv(records, output_file):
    """保存为 CSV 格式 (列表字段用顿号连接成字符串，方便 Excel 打开)"""
    if not records:
        return
    # 如果没有数据，直接返回 (不写空文件) 。
    # 定义列顺序
    fieldnames = ["排名", "名称", "类型", "话数", "放送时间",
                  "导演", "脚本", "声优", "评分", "评分人数", "封面", "详情页"]
    # 固定 CSV 的列顺序，保证每次输出一致

    # utf-8-sig 带 BOM, Excel 打开中文不乱码
    # newline = "" : 避免 CSV 在 Windows 上出现空行
    with open(output_file, "w", encoding = "utf-8-sig", newline = "") as f:
        # DictWriter: 把字典按 fieldnames 顺序写成 CSV 行
        writer = csv.DictWriter(f, fieldnames = fieldnames)
        # writeheader(): 先写表头 (列名)
        writer.writeheader()
        for r in records:
            row = dict(r)
            # dict(r): 复制一份记录 (避免改原数据)
            # 列表字段 -> 字符串
            if isinstance(row.get("脚本"), list):
                row["脚本"] = "、".join(row["脚本"])
            if isinstance(row.get("声优"), list):
                row["声优"] = "、".join(row["声优"])
            # writer.writerow(row): 写一行
            writer.writerow(row)
    logger.info(f"已保存 CSV: {output_file} ({len(records)} 条) ")
    # 写日志。

# -- 阶段5: 生成报告 + 主函数 --

# 保存报告
def save_report(report, report_file):
    """保存清洗报告"""
    report["stage5_time"] = datetime.now().isoformat()
    # 给报告加一个第 5 阶段时间戳。
    with open(report_file, "w", encoding = "utf-8") as f:
        json.dump(report, f, ensure_ascii = False, indent = 2)
        # json.dump(obj, file): 把对象写成 JSON 文件
        # indent = 2 : 缩进 2 个空格，方便人读
    logger.info(f"清洗报告已保存: {report_file}")

# 主函数
def main():
    logger.info("=" * 50)
    logger.info("开始数据清洗流程")
    logger.info("=" * 50)

    # 阶段1: 加载与质量检查
    records, report = load_and_check(INPUT_FILE)
    input_count = report["total_count"]
    # 调用阶段1，拿到记录和报告，记下输入总数

    # 阶段2: 去重 + 缺失值填充
    records, removed = deduplicate(records)
    report["deduplicated_removed"] = removed
    records, filled = fill_missing(records)
    report["filled_count"] = filled
    # 调用阶段2的两个函数，把统计塞进 report。

    # 阶段3: 格式标准化
    records, std_stats = standardize(records)
    report["standardize_stats"] = std_stats

    # 阶段4: 输出
    save_jsonl(records, OUTPUT_JSONL)
    save_csv(records, OUTPUT_CSV)
    report["output_count"] = len(records)
    # 调用阶段 4，输出两个文件，记下输出条数。

    # 阶段5: 保存报告
    save_report(report, REPORT_FILE)

    logger.info("=" * 50)
    logger.info(f"清洗完成! 输入 {input_count} 条 -> 输出 {len(records)} 条")
    logger.info(f"JSONL: {OUTPUT_JSONL}")
    logger.info(f"CSV: {OUTPUT_CSV}")
    logger.info(f"报告: {REPORT_FILE}")
    logger.info("=" * 50)
    # 打印完成日志，告诉用户输入输出对比和文件位置。

if __name__ == "__main__":
    main()
