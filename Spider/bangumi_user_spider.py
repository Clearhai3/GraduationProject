"""
从 Bangumi 网站收集一批用户
"""
import json
import re
import csv
import os
import time
import random
import logging
import requests
from bs4 import BeautifulSoup

# 配置区
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILE = os.path.join(SCRIPT_DIR, "anime_cleaned.csv")        # 输入: 已有动漫数据
COLLECTED_USERS_FILE = os.path.join(SCRIPT_DIR, "user_pool.json")       # 引导层产物: 用户名池
RATINGS_FILE = os.path.join(SCRIPT_DIR, "user_ratings.jsonl")       # 数据层产物: 评分数据
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "user_spider_progress.json") # 断点续爬进度
LOG_FILE = os.path.join(SCRIPT_DIR, "user_spider.log")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain. */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 配置日志
logging.basicConfig(
    level = logging.INFO,
    format = "%(asctime)s [%(levelname)s] %(message)s",
    handlers = [
        logging.FileHandler(LOG_FILE, encoding = "utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# 工具函数
# 所有网络请求都走这一个函数，统一处理错误
def safe_get(session, url, timeout = 15):
    """统一请求，失败返回 None"""
    try:
        resp = session.get(url, timeout = timeout)
        # 发 GET 请求，15 秒没响应就放弃 (超时)
        if resp.status_code != 200:
            logger.warning("状态码异常 %s: %s", resp.status_code, url)
            return None
        return resp
    except requests.RequestException as e:
        logger.error("请求失败 %s: %s", url, e)
        return None

# 获取用户数据id
def get_subject_ids(csv_file):
    """
    从 anime_cleaned.csv 的"详情页"列提取所有 subject_id。
    返回: [326, 876, 25961, ...]
    """
    subject_ids = []
    with open(csv_file, "r", encoding = "utf-8-sig") as f:
        reader = csv.reader(f)      # 逐行读取
        next(reader)                # 跳过表头
        for row in reader:
            if len(row) < 12:
                continue            # 防御: 字段不齐跳过
            detail_url = row[11]    # 第12列 = 详情页 URL
            m = re.search(r"/subject/(\d+)", detail_url)    # 提取数字
            # r"...": 原始字符串，告诉 Python "别转义里面的反斜杠"
            # \d 匹配数字，+ 表示"一个或多个"，括号是捕获组——把匹配到的数字单独记下来
            # re.search 在整串文字里找第一个能匹配的位置
            if m:
                subject_ids.append(int(m.group(1)))
    logger.info(f"共提取 {len(subject_ids)} 个 subject_id")
    # logger.info: 输出日志，告诉一共提取了多少个
    return subject_ids

# 提取用户名，返回用户名列表
def crawl_collection_users(session, subject_id, max_pages = 3):
    """
    爬取单部番的收藏页，提取用户名。
    返回: 用户名列表，例如 ["azulim", "akym4869", ...]
    """
    usernames = []
    # 翻页循环
    for page in range(1, max_pages + 1):
        # 拼 URL + 发请求
        url = f"https://bgm.tv/subject/{subject_id}/collections?page={page}"
        # safe_get()
        resp = safe_get(session, url)
        if not resp:
            break           # 请求失败，放弃这一部

        soup = BeautifulSoup(resp.text, "lxml")
        # BeautifulSoup(..., "lxml"): 把这段文本解析成一颗可查询的"文档树"
        # lxml: 是解析引擎，把 HTML 变成结构化的树状数据，之后就能用 soup.find_all() 精准地"找元素"

        # 找所有 href="/user/xxx" 的链接
        found = 0
        for a in soup.find_all("a", href = lambda x: x and x.startswith("/user/")):
            # 关键: 用户名在 href 里，不在链接文字里!
            # 链接文字是"显示昵称"（可能是中文，如"外行侦探浅黄鞠丸"）
            # href 里的 /user/xxx 才是真正的用户名，例如 /user/akym4869
            m = re.search(r"/user/([^/]+)", a.get("href", ""))
            if not m:
                continue            # 防御: 提取不到就跳过
            username = m.group(1)
            # 过滤掉空用户名
            if username:
                usernames.append(username)
                found += 1

        if found == 0:
            break       # 这页没用户了，停止翻页

        time.sleep(random.uniform(0.5, 1.5))    # 防封延迟
        # 输出日志
        logger.info(f"subject {subject_id} 第 {page} 页: 找到 {found} 个用户")

    return usernames

# 汇总用户名，对用户名进行保存。
def collect_user_pool(session, subject_ids):
    """
    遍历所有 subject_id, 汇总用户名，去重后保存。
    """
    all_users = set()       # set 自动去重
    for i, sid in enumerate(subject_ids, 1):
        users = crawl_collection_users(session, sid)
        all_users.update(users)     # 把新用户加进集合
        logger.info(f"[{i}/{len(subject_ids)}] {sid}: 累计用户 {len(all_users)}")

    # 保存用户池
    with open(COLLECTED_USERS_FILE, "w", encoding = "utf-8") as f:
        json.dump(sorted(all_users), f, ensure_ascii = False, indent = 2)
        # indent = 2: 每层缩进2个空格。

    logger.info(f"用户池构建完成，共 {len(all_users)} 个唯一用户")
    return sorted(all_users)

# 调用官方api，对用户收藏过的动漫进行调查。
def fetch_user_collections(session, username):
    """
    调用官方 API 拉取单个用户的动漫收藏（含评分）。
    返回: [(subject_id, rate), ...]，只返回打过分(rate>0)的
    """
    results = []
    offset = 0
    limit = 50

    while True:
        # 调用官方 API
        url = f"https://api.bgm.tv/v0/users/{username}/collections?subject_type=2&limit={limit}&offset={offset}"
        resp = safe_get(session, url)
        if not resp:
            break

        try:
            date = resp.json()      # 把 JSON 文本转成 Python 字典
        except ValueError:
            logger.error(f"{username} 响应不是合法 JSON")
            break

        items = date.get("data", [])    # 安全取值: 拿不到 data 就返回空列表
        for item in items:
            rate = item.get("rate", 0)
            subject = item.get("subject", {})
            sid = subject.get("id", 0)
            if rate > 0 and sid:        # 只保留打过分(rate>0)的
                results.append((sid, rate))

        total = date.get("total", 0)
        offset += limit

        if offset >= total or not items:
            break       # 翻完所有页了

        time.sleep(random.uniform(0.5, 1.5))    # 每夜之间延迟

    return results

# 断点续爬
def fetch_all_ratings(session, usernames):
    """
    遍历所有用户名，拉取评分，支持断点续爬。
    """
    # 读取进度: 已完成哪些用户
    done_users = set()
    if os.path.exists(PROGRESS_FILE):
    # 检查文件是否在
        with open(PROGRESS_FILE, "r", encoding = "utf-8") as f:
            done_users = set(json.load(f))

    for i, username in enumerate(usernames, 1):
        if username in done_users:
            logger.info(f"[{i}/{len(usernames)}] {username} 已完成，跳过")
            continue

        ratings = fetch_user_collections(session, username)
        if ratings:
            with open(RATINGS_FILE, "a", encoding = "utf-8") as f:
                for sid, rate in ratings:
                    record = {"用户名": username, "subject_id": sid, "rate": rate}
                    f.write(json.dumps(record, ensure_ascii = False) + "\n")

        # 保存进度（每个用户完成就存一次，崩溃不丢）
        done_users.add(username)
        with open(PROGRESS_FILE, "w", encoding = "utf-8") as f:
            json.dump(sorted(done_users), f)

        logger.info(f"[{i}/{len(usernames)}] {username}: {len(ratings)} 条评论")

    logger.info(f"全部完成，共 {len(done_users)} 个用户")

def main():
    session = requests.Session()
    session.headers.update(HEADERS)

    # 阶段1: 构建用户池
    subject_ids = get_subject_ids(CSV_FILE)
    usernames = collect_user_pool(session, subject_ids)

    # 阶段2: 拉取评分
    fetch_all_ratings(session, usernames)

    logger.info("爬取全部完成")

if __name__ == "__main__":
    main()