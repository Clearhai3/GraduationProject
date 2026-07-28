import json
from multiprocessing.reduction import duplicate
import re
import csv
import os
import logging
from datetime import datetime

# -- 配置区 --
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "动漫信息_v2.json")
OUTPUT_JSONL = os.path.join(SCRIPT_DIR, "anime_cleaned.jsonl")
OUTPUT_CSV = os.path.join(SCRIPT_DIR, "anime_cleaned.csv")
REPORT_FILE = os.path.join(SCRIPT_DIR, "cleaning_report.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "data_cleaner.log")

# -- 日志配置 --
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [
        logging.FileHandler(LOG_FILE, encoding = "utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# -- 阶段1: 数据加载与质量检查 --

# 文件获取
def load_and_check(input_file):
    """
    读取原始 JSONL 文件，检查数据质量
    返回: (records, report)
    - records: 原始数据列表
    - report: 质量报告字典
    """
    logger.info(f"开始加载数据: {input_file}")

    records = []
    with open(input_file, "r", encoding = "utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError as e:
                logger.error(f"第 {line_num} 行 JSON 解析失败: {e}")

    total_count = len(records)
    logger.info(f"加载完成，共 {total_count} 条数据")

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

    episodes_zero = 0
    air_date_invalid = 0
    score_zero = 0

    for record in records:
        # 字符串字段缺失检查
        if not record.get("名称") or record.get("名称") == "未知":
            missing_fields["名称"] += 1

        if not record.get("放送时间") or record.get("放送时间") == "未知":
            missing_fields["放送时间"] += 1
            air_date_invalid += 1

        if not record.get("导演") or record.get("导演") == "未知":
            missing_fields["导演"] += 1
        
        if not record.get("类型") or record.get("类型") == "未知":
            missing_fields["类型"] += 1

        # 数值字段缺失检查
        if record.get("话数", 0) == 0:
            missing_fields["话数"] += 1
            episodes_zero += 1

        if record.get("评分", 0.0) == 0.0:
            missing_fields["评分"] += 1
            score_zero += 1

        if record.get("评分人数", 0) == 0:
            missing_fileds["评分人数"] += 1

        # 列表字段确实检查
        if not record.get("脚本"):
            missing_fields["脚本"] += 1

        if not record.get("声优"):
            missing_fields["声优"] += 1

    # 统计重复
    seen = set()
    duplicates = 0
    for record in records:
        key = json.dumps(record, ensure_ascii = False, sort_keys = True)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)

    report = {
        "total_count": total_count,
        "missing_fields": missing_fields,
        "duplicates": duplicates,
        "episodes_zero": episodes_zero,
        "air_date_invalid": air_date_invalid,
        "score_zeor": score_zero,
        "stage1_time": datetime.now().isoformat(),
    }

    logger.info("质量检查完成")
    logger.info(f"缺失字段: {missing_fields}")
    logger.info(f"重复条数: {duplicates}")

        