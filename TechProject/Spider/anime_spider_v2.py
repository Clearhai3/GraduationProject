import json
import os
import random
import time
import logging
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# -- 配置区 --

TOTAL_PAGE = 50
BASE_URL = "https://bangumi.tv/anime/browser?sort=rank&page={}"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "动漫信息_v2.json")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "progress_v2.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "anime_spider_v2.log")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" 
        "AppleWebKit/537.36 (KHTML, like Gecko)"
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://bangumi.tv/anime/browser?sort=rank",
}

# -- 日志 --
logging.basicConfig(
    # 设置日志的最低输出级别。
    # 级别       数值       含义
    # DEBUG      10     调试信息，最详细
    # INFO       20     普通运行信息
    # WARNING    30     警告
    # ERROR      40     错误
    # CRITICAL   50     严重错误
    # 设为 INFO 意味着: DEBUG 级别的日志会被忽略，INFO 及以上级别的日志才会输出。
    # 所以你在代码里看到的 logger.info(...)、logger.warning(...)、logger.error(...) 都会输出，但如果有 logger.debug(...) 就不会显示。
    level = logging.INFO,
    # 定义每条日志的输出格式。%(...)s 是占位符:
    # 占位符            实际输出        示例
    # %(asctime)s      时间戳         2026-07-27 10:43:06, 591
    # %(levelname)s    日志级别名      INFO / WARNING / ERROR
    # %(message)s      日志正文       正在爬取第 1 页
    format = "%(asctime)s [%(levelname)s] %(message)s",
    # 最终效果就是
    # 2026-07-27 10:43:06,591 [INFO] 正在爬取第 1 页
    # 2026-07-27 10:43:08,166 [INFO] 第 1 页解析出 24 条
    handlers = [
        logging.FileHandler(LOG_FILE, encoding = "utf-8"),
        logging.StreamHandler(),
    ],
    # handlers 决定日志输出到哪里。这里配了两个 handler, 意味着同一条日志灰同时输出两个地方。
    # logging.FileHandler(LOG_FILE, encoding = "utf-8")
    # 把日志写入文件 (LOG_FILE 即 anime_spider_v2.log)
    # 文件以追加模式打开 (默认 "a"), 不会覆盖之前的日志

    # logging.StreamHandler()
    # 把日志输出到控制台 (终端)
    # 没有额外参数，默认输出到 sys.stderr

)
logger = logging.getLogger(__name__)
# getLogger 的作用是获取一个logger 对象 (日志记录器), 用来在代码里写日志。
# 传进去的字符串叫 logger 的名字，他有两个作用: 
# 1. 标识这个 logger 属于哪个模块
# getLogger("anime_spider_v2") -> 标识是 spider 模块的 logger
# getLogger("__main__") -> 标识是主程序的 logger
# 用 __name__ 的好处是自动适配，无论直接运行还是被导入，名字都正确。

# 2. 继承日志配置
# basicConfig 设置的是根 logger(root logger) 的配置，子 logger 会自动集成这些配置。
# 所以你前面 basicConfig 配的 level、format、handlers 都会总用到 getLogger(__name__)拿到的 logger 上。

def create_session():
    """创建带重试和连接复用的 Session"""
    # 创建一个 Session 对象。
    # requests.Session() 和普通 requests.get() 的区别:
    # 方式                  连接复用            自动携带 Cookie
    # requests.get(url)    每次请求新建连接        不保留
    # Session().get(url)   复用同一个连接         自动保留
    # 连接复用能减少 TCP 握手开销，爬取同一个网站时速度更快。
    session = requests.Session()
    
    # 把之前定义的 HEADERS (User-Agent、Accept等) 注入到 session 里。之后用这个 session 发的所有请求都会自动带上这些请求头，不用每次手动传。
    session.headers.update(HEADERS)

    # 配置自动重试策略
    retry = Retry(
        # 最多重试 5 次
        total = 5,
        # 退因子，控制重试间隔
        # 公式是 backoff_factor x 2^(重试次数-1)。递增等待能避免频繁请求被服务器封禁。
        # 重试次数      等待时间
        # 第 1 次       0秒(立即)
        # 第 2 次       2秒
        # 第 3 次       4秒
        # 第 4 次       8秒
        # 第 5 次       16秒
        backoff_factor = 1,
        # 遇到这些状态码才重试
        # 500/502/503/504 -> 服务器端错误
        # 429 -> 请求太多 (Too Many Requests)
        # 遇到这些错误码才会触发重试，404、403 这类不会重试。
        status_forcelist = [500, 502, 503, 504, 429],
        # 只对 GET 请求重试
        allowed_methods = ["GET"],
    )

    adapter = HTTPAdapter(
        max_retries = retry,        # 绑定上面定义的重试策略
        pool_connections = 10,      # 连接池大小: 最多保持 10 个不同的主机连接
        pool_maxsize = 20           # 每个主机的最大连接数: 20
    )
    # HTTPAdapter 是 requests 底层管理 HTTP 连接的适配器: 
    # pool+connections = 10: 你只爬取 bangumi 一个站，10个连接
    # pool_maxsize = 20: 单站最多 20 个并发连接

    # mount 的作用是把 adapter 绑定到 URL 前缀。
    # "https://" 表示所有 HTTPS 请求都用这个adapter。
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    # 把配置好的 session 返回，供后续爬取使用。
    return session

    # 普通 requests.get()
    # ↓ 加上 Session（连接复用）
    # ↓ 加上 HEADERS（伪装浏览器）
    # ↓ 加上 Retry（失败自动重试）
    # ↓ 加上 HTTPAdapter（连接池管理）
    # = 更稳定、更快的爬虫请求工具


# 读取文件
def load_progress():
    """读取已完成的页面"""
    # 检查进度文件是否存在。
    # 第一次运行爬虫时，进度文件还没创建，os.path.exists() 返回 False
    # 此时直接返回空集合 set()，表示 "还没有爬过任何页"
    if not os.path.exists(PROGRESS_FILE):
        # 返回空集合。set() 是 Python 的集合类型，支持 in 快速查找，后面判断"某页是否已爬过"时效率更高。 
        return set()
    # 打开进度文件，以只读模式 ("r") 读取，编码 UTF-8。
    # with 语句的好处是自动关闭文件，不用手动写 f.close()。
    with open(PROGRESS_FILE, "r", encoding = "utf-8") as f:
        # 1. json.load(f): 文件读取 JSON 数据，解析成 Python 列表。
        # 2. set(...): 把列表转成集合
        return set(json.load(f))
# 进度文件存在吗？
#     ↓ 不存在
# 返回空集合 set()  →  爬虫从头开始

#     ↓ 存在
# 读取 JSON 文件  →  解析成列表  →  转成集合  →  返回

# 为什么要用 set 而不是 list?
# 后面爬虫主循环里有这段判断:
# if page in done_pages:
#       continue    # 跳过已爬的页

# list 查找: in 操作是 O(n)，要遍历整个列表
# set 查找: in 操作是 O(1)，直接哈希定位，快得多


# 写入文件
def save_progress(done_pages):
    """保存已完成的页面"""
    # 打开进度文件，以写入模式 ("w"), 编码 UTF-8。
    # "w" 模式会覆盖原有内容 (不是追加)，每次保存都是全新的文件。
    with open(PROGRESS_FILE, "w", encoding = "utf-8") as f:
        json.dump(sorted(done_pages), f, ensure_ascii = False)
        # 1. sorted(done_pages)
        # done_pages 是一个 set(集合), 集合是无序的
        # sorted() 把它转成排序后的列表，比如 {5, 2, 1, 3} -> [1, 2, 3, 5]
        # 为什么要排序? 为了让进度文件可读性更好，方便人工检查。
        # 2. json.dump(..., f)
        # 把数据序列化成 JSON 格式，写入文件 f
        # 3.ensure_ascii = False
        # 默认 True: 中文会被转成 \uXXXX 编码 (如  "\u7b2c1\u9875")
        # 设为 False: 中文直接保存为 UTF-8 字符 (如 "第1页")
# 爬完第 5 页
#     ↓
# done_pages.add(5)  →  done_pages = {1, 2, 3, 4, 5}
#     ↓
# save_progress(done_pages)
#     ↓
# 排序 → [1, 2, 3, 4, 5]
#     ↓
# 写入文件 → progress_v2.json 内容: [1, 2, 3, 4, 5]

# 参数          类型                含义
# session    requests.Session   之前创建好的 session 对象
# url          str              要请求的网址
# tiemout      int              超时
# "安全的 GET 请求"，封装了错误处理逻辑
def safe_get(session, url, timeout = 15):
    """统一请求，失败返回 None"""
    try:
        # 用 session 发送 GET 请求，带上超时限制。
        # 如果 15 秒内没响应，会抛出 requests.exceptions.Timeout 异常，跳到 except 块处理。
        resp = session.get(url, timeout = timeout)
        # 强制设置响应编码为 UTF-8。
        resp.encoding = "utf-8"
        # 检查状态码
        # HTTP 状态码 200 表示成功
        # 其他状态码 (如 404、503) 都是异常
        # 异常时记录警告日志，返回None
        if resp.status_code != 200:
            logger.warning("状态码异常 %s: %s", resp.status_code, url)
            return None
        # 状态码正常，返回响应对象 resp，后续可以取 resp.text 解析网页。
        return resp
    except requests.RequestException as e:
        # 异常类型              触发场景
        # ConnectionError      连接失败
        # Timeout              请求超时
        # TooManyRedirects     重定向次数过多
        # HTTPError            HTTP 协议错误
        logger.error("请求失败 %s: %s", url, e)
        return None

# 核心区域
def parse_list_page(session, page):
    """解析列表页，返回改页所有动漫的基础信息"""
    # BASE_URL 是 "https://bangumi.tv/anime/browser?sort=rank&page={}"，用 format(page) 把 {} 替换成页码，得到完整 URL 。
    url = BASE_URL.format(page)
    logger.info("正在爬取第 %d 页: %s", page, url)

    # 请求网页
    # 用之前封装的 safe_get 请求网页。失败则返回空列表。
    resp = safe_get(session, url)
    if not resp:
        return []

    # 把 HTML 文本解析成 BeautifulSoup(resp.text, "lxml")
    # 用 "lxml" 解析器 (速度块、容错好)。
    soup = BeautifulSoup(resp.text, "lxml")

    # 定位动漫列表容器
    item_ul = soup.find("ul", id = "browserItemList")
    if not item_ul:
        logger.warning("第 %d 页未找到 browserItemList", page)
        return []

    results = []
    # 遍历每个动漫项
    # 获取所有 <li> 元素，每个 <li> 就是一部动漫的信息卡片。
    items = item_ul.find_all("li")
    for item in items:
        try:
            # <img src="//lain.bgm.tv/r/400/pic/cover/...">
            img_tag = item.find("img")
            # 网页上的 src 是 // 开头的协议相对路径，需要补上 https: 才能直接访问。
            img = "https:" + img_tag["src"] if img_tag and img_tag.get("src") else ""

            # 提取名称和详情页链接
            h3 = item.find("h3")
            # 列表项结构是: 
            # <h3><a href="/subject/326">攻壳机动队</a></h3>
            name = h3.a.text.strip() if h3 and h3.a else "未知"
            # urljoin 把相对路径 /subject/326 拼成完整 URL。
            dm_url = urljoin("https://bangumi.tv", h3.a["href"]) if h3 and h3.a else ""

            # 提取排名
            rank_tag = item.find("span", class_ = "rank")
            # 排名标签的文本可能是 "Rank 1" 或 "1"，用 split()[-1] 取最后一段 (数字部分)。
            rank_text = rank_tag.text.strip().split()[-1] if rank_tag and rank_tag.text.strip() else "0"

            # 提取基本信息文本
            info_tag = item.find("p", class_ = "info tip")
            info_text = info_tag.text.strip().replace(" ", "") if info_tag else ""
            # info 格式大致为：26话 / 2011年7月7日 / 新房昭之 / 木泽行人 ...

            # 解析各字段
            # 用 / 分割，过滤空字符串
            parts = [p for p in info_text.split("/") if p]
            # "26话" 去掉最后一个字 "话" -> "26"
            hua_count = parts[0][:-1] if parts else "0"
            # 日期
            date = parts[1] if len(parts) > 1 else "未知"
            # 创作者列表
            peoples = parts[2:] if len(parts) > 2 else []

            # 列表页无法区分角色类型，这里只作兜底，详情页会覆盖
            daoyan = peoples[0] if peoples else "未知"
            jiaoben = peoples[1:] if len(peoples) > 1 else []

            # 评分信息
            rate_info = item.find("p", class_ = "rateInfo")
            score = 0.0
            score_count = 0
            if rate_info:
                score_tag = rate_info.find("small", class_ = "fade")
                score = float(score_tag.text.strip()) if score_tag else 0.0

                # 评分人数在 <span class = "tip_j"> 或 <span class = "..."> 中，格式如 "(9999人评分)"
                count_tag = rate_info.find("span", class_ = "tip_j")
                if count_tag:
                    count_text = count_tag.text.strip()             # "(9999人评分)"
                    count_text = count_text.strip("()")             # "9999人评分"
                    count_text = count_text.replace("人评分", "")     # "9999"
                    count_text = count_text.replace(",", "")        # 处理千位分隔符
                    score_count = int(count_text) if count_text.isdigit() else 0
                # 评分区域的 HTML 结构:
                # <p class="rateInfo">
                #   <small class="fade">9.2</small>
                #   <span class="tip_j">(9999人评分)</span>
                # </p>

                results.append({
                    "封面": img,
                    "名称": name,
                    "排名": int(rank_text) if rank_text.isdigit() else 0,
                    "话数": int(hua_count) if hua_count.isdigit() else 0,
                    "放送时间": date,
                    "导演": daoyan,
                    "脚本": jiaoben,
                    "评分": score,
                    "评分人数": score_count,
                    "详情页": dm_url
                })
        except Exception as e:
            logger.error("解析列表项出错: %s", e)

    logger.info("第 %d 页解析出 %d 条", page, len(results))
    return results

def parse_detail_page(session, base_info):
    """进入详情页补全类型、声优等信息"""
    url = base_info.get("详情页")
    if not url:
        return base_info

    resp = safe_get(session, url, timeout = 15)
    if not resp:
        # 详情页失败也不丢弃整行，只是字段填未知
        base_info["类型"] = "未知"
        base_info["声优"] = []
        # 导演和脚本保留列表页的兜底值，不用额外设置
        return base_info

    soup = BeautifulSoup(resp.text, "lxml")

    # 类型: 在 #headerSubject 下的小字，例如 "(TV Series, 25 episodes)"
    leixing = "未知"
    header_div = soup.find("div", id = "headerSubject")
    if header_div:
        small = header_div.find("small")
        
        if small:
            leixing = small.get_text(strip = True)

    # 声优: 需要单独请求角色页 /subject/{id}/characters
    # 初始化一个空列表，用来存放最终找到的声优名字
    cv_shengyou = []
    try:
        # url 是动漫详情页地址，例如: https://bangumi.tv/subject/326
        # .rstrip("/") 去掉末尾可能多余的 / ，防止拼出 https://bangumi.tv/subject/326/characters
        # 为什么不能直接用详情页？
        # 因为声优信息在 bangumi 网站上是在单独的“角色”页面里，详情页上没有。
        cv_url = url.rstrip("/") + "/characters"

        # 用之前定义好的 safe_get 函数 (自带重试、超时、错误处理) 去请求角色页。
        cv_resp = safe_get(session, cv_url, timeout = 15)

        if cv_resp:
            # 把角色页的 HTML 文本解析成 BeautifulSoup 对象，方便后续用选择器查找元素。
            cv_soup = BeautifulSoup(cv_resp.text, "lxml")

            # 这是核心查找逻辑:
            # 找页面上所有 <a> 标签
            # 条件是 href 属性里包含 /person/ (bangumi 用 /person/数字 链接到人物页面，声优就是 /person/ 类型的链接)
            for a in cv_soup.find_all("a", href = lambda x: x and "/person/" in x):
                # 1， a.parent.name != "p": 如果这个 <a> 标签的父元素不是 <p>, 跳过。因为头像区域的 <a> 被包在 <div> 里，而声优名字的 <a> 被包在 <p> 里，这样就能排除掉头像链接。
                # 2. not a.get_text(strip = True): 如果 <a> 标签里的文字为空 (比如纯图片链接)，跳过。
                if a.parent.name != "p" or not a.get_text(strip = True):
                    continue
                # 区分 CV / 英配 / 粤配，只取日配 CV
                cv_type = "CV"
                p = a.parent
                for sib in p.next_siblings:
                    if isinstance(sib, str) and sib.strip() in ("CV", "英配", "粤配"):
                        cv_type = sib.strip()
                        break
                    if hasattr(sib, "get_text"):
                        text = sib.get_text(strip = True)
                        if text in ("CV", "英配", "粤配"):
                            cv_type = text
                            break
                if cv_type == "CV":
                    cv_shengyou.append(a.get_text(strip = True))
    except Exception as e:
        logger.error("解析声优出错 %s: %s", url, e)

    daoyan = base_info.get("导演", "未知")
    jiaoben = base_info.get("脚本", [])
    try:
        # 详情页的信息区是一个 <ul id="infobox"> , 每个字段是一行 <li>。
        infobox = soup.find("ul", id = "infobox")
        if infobox:
            # 遍历每一行，提取标签名
            for li in infobox.find_all("li"):
                span = li.find("span", class_ = "tip")
                if not span:
                    continue
                label = span.get_text(strip = True)     # "导演:" / "脚本:" / "原作:" 等
                # 找人物链接
                # 只取带 /person/ 链接的人名，忽略纯文字部分 (如备注、集数说明)。
                links = li.find_all("a", class_ = "l", href = lambda x: x and "/person/" in x)
                # 按标签类型赋值
                if label == "导演:" and links:
                    daoyan = "、".join(a.get_text(strip = True) for a in links)     # 多导演用顿号连续
                elif label == "脚本:" and links:
                    jiaoben = [a.get_text(strip = True) for a in links]     # 脚本存为列表
                
                # 导演: 字符串格式, 多导演用 、 连接 
                # 脚本: 列表格式 
    except Exception as e:
        logger.error("解析导演/脚产出错 %s: %s", url, e)

    base_info["类型"] = leixing
    base_info["声优"] = cv_shengyou
    base_info["导演"] = daoyan
    base_info["脚本"] = jiaoben
    return base_info 

# 参数          类型            含义
# file_path    str            输出文件路径
# records      list[dict]     一页爬取结果 (字典列表)
def append_to_jsonl(file_path, records):
    """以 JSON Lines 形式追加写入，断点爬友好"""
    # JSON Lines (也叫 JSONL) 是一种文件格式: 每行一个独立得 JSON 对象.
    # 和普通 JSON 的区别: 
    # 普通 JSON:                     JSON Lines:
# [                              {"名称":"攻壳","评分":9.2}
#   {"名称":"攻壳","评分":9.2},  {"名称":"星际","评分":9.1}
#   {"名称":"星际","评分":9.1}   每行独立，互不依赖
# ]
# 整体是一个数组，必须完整

# 为什么用 JSONL? 因为追加写入很方便.
# 普通 JSON 是一个完整数组, 追加数据要读取 -> 解析 -> 加元素 -> 重写整个文件; 
# JSONL 直接在文件末尾追加一行就行, 断点续爬时不会覆盖之前的数据.

    # 以追加模式 ("a" = append) 打开文件
    # 模式      行为
    # "w"      覆盖写入, 之前的内容没了
    # "a"      追加写入, 新内容加到文件末尾
    # 如果文件不存在, "a" 模式会自动创建
    with open(file_path, "a", encoding = "utf-8") as f:
        for r in records:
            # 1. json.dumps(r, ensure_ascii = False): 把字典序列化成 JSON 字符串。ensure_ascii = False 保证中文不转成 \uXXXX，直接保存 UTF-8 字符
            # 2. + "\n": 末尾加换行符，确保每条记录独占一行
            # 3. f.write(...): 写入文件
            f.write(json.dumps(r, ensure_ascii = False) + "\n")

def main():
    # 创建带重试、连接复用、请求头的 session 对象 (之前解释过的 create_session)。
    session = create_session()
    # 读取进度文件，返回已完成页码的集合。如果是首次运行，返回空集合 set()。
    done_pages = load_progress()

    # 记录日志，告诉用户有多少页已经爬过了。 %d 是占位符，会被 len(done_pages) 替换。
    logger.info("开始爬取，已跳过 %d 页", len(done_pages))

    # 遍历第 1 页到目标页数。range(1, 51) 生成 1~50 的页码
    for page in range(1, TOTAL_PAGE + 1):
        # 跳过已爬的页
        # done_pages 是 set，page in done_pages 是 O(1) 查找。已爬过的页直接跳过，这就是断点续爬的核心。
        if page in done_pages:
            logger.info("第 %d 页已存在，跳过", page)
            continue

        # 解析列表页
        base_records = parse_list_page(session, page)
        # 从列表提取动漫基础信息。如果返回空列表 (请求失败或页面异常)，跳过这页。
        if not base_records:
            logger.warning("第 %d 页无数据，跳过", page)
            continue

        # 逐条请求详情页
        final_records = []
        for record in base_records:
            # 随机延迟 0.8 ~ 2.5 秒，降低被封风险
            time.sleep(random.uniform(0.8, 2.5))
            # 调用 parse_detail_page: 进入详情页，补全类型、声优、导演、脚本
            final_records.append(parse_detail_page(session, record))

        # 把这一页所有动漫的完整信息追加写入 JSONL 文件。
        append_to_jsonl(OUTPUT_FILE, final_records)

        # 保存进度
        # 把这页标记为已完成，立即写入进度文件。这样即使爬虫在下一页崩溃，这页的数据和进度都不会丢。
        done_pages.add(page)
        save_progress(done_pages)

        # 每页之间也随机休息
        time.sleep(random.uniform(1, 3))

    logger.info("全部完成，结果保存至 %s", OUTPUT_FILE)

    # 开始
    #   ↓
    # 创建 session，加载进度
    #   ↓
    # 遍历 page 1 → 50
    #   ├─ 已爬过？ → 跳过
    #   ├─ 请求列表页 → 失败？ → 跳过
    #   ├─ 逐条请求详情页（每条延迟 0.8~2.5s）
    #   │    └─ 补全：类型、声优、导演、脚本
    #   ├─ 追加写入 JSONL 文件
    #   ├─ 保存进度
    #   └─ 页间延迟 1~3s
    #   ↓
# 全部完成

if __name__ == "__main__":
    main()
