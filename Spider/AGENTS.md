# AGENTS.md — 动漫数据离线分析项目

## 项目简介
毕业设计项目：从 Bangumi 网站爬取动漫数据，清洗后做
MapReduce 离线统计分析，结果存入 MySQL。
技术栈：Python 3 + requests/BeautifulSoup + Hadoop Streaming + MySQL(pymysql)

## 数据管道（脚本按顺序运行）
1. `Spider/anime_spider_v2.py`     爬取动漫列表 → 动漫信息_v2.json
2. `Spider/anime_data_cleaner.py`  清洗 → anime_cleaned.csv / .jsonl
3. `Spider/import_anime.py`        CSV 导入 MySQL 的 anime 表
4. `Spider/anime_data_mapreduce.py` Hadoop MapReduce 分析脚本
5. `Spider/import_to_mysql.py`     本地模拟管道，统计结果写 MySQL
6. `Spider/bangumi_user_spider.py` 用户爬虫 → 评分数据 user_ratings.jsonl

## 运行方式
每个脚本独立运行：`python Spider/xxx.py`（Windows 本机直接跑）。
MapReduce 脚本需配合 Hadoop 使用。

## 代码风格约定
- 全部 utf-8 编码，中文注释详细（教学风格），改动时保持中文注释
- 配置区集中在顶部：SCRIPT_DIR、文件路径、HEADERS、DB_CONFIG、日志
- 路径一律用 SCRIPT_DIR 拼接，禁止写死绝对路径
- 日志用 logging；MapReduce 脚本日志必须写 stderr（stdout 是数据通道）
- 爬虫带防封延迟 time.sleep(...)，并支持断点续爬（progress JSON）

## 陷阱与注意事项
- ⚠️ MapReduce 的 stdout 是数据通道，日志写 stdout 会导致数据全乱
- ⚠️ 本地管道必须手动 sort（Hadoop reducer 依赖相同 key 连续）
- 读 CSV 用 utf-8-sig，写文件用 utf-8，MySQL 用 utf8mb4（防中文乱码）
- 文件名含中文（动漫信息_v2.json），不要改名，脚本间靠 SCRIPT_DIR 引用
- import_to_mysql.py 的数据库密码是明文，改库前先看配置区
- 解析 HTML 用 BeautifulSoup；解析 API 用 resp.json()，先判 status_code==200
- 防御性编码：遍历 CSV 行先检查字段数量（如 `if len(row) < 12: continue`）