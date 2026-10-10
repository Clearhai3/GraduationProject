# 数据仓库层（HDFS + Hive + Sqoop）

任务书原文（第 3、4 项）要求：

> **存储至 HDFS 分布式文件系统，按数据类型与日期分区组织**
> 使用 **MapReduce 与 Hive** 进行动漫数量统计、评分分布、热度排行、类型分布、标签分析等多维统计分析，
> **结果通过 Sqoop 导入 MySQL**

本目录就是这条链的**可复现脚本**。完整证据（截图 + 输出留档）见 `~/文档/毕设-Hadoop证据/`。

---

## 一、数据流

```
本地 CSV / TSV
    │  hdfs dfs -put
    ▼
HDFS  ODS 层：/elarea/raw/<类型>/dt=<入库日>/        ← 按「数据类型 + 日期」分区
    │  Hive 外部表（ODS）
    ▼
Hive  ODS 表：ods_anime / ods_rating / ods_anime_tag / ods_rating_train / ods_rating_test
    │  HiveQL（编译成 MapReduce，提交 YARN）
    ▼
Hive  ADS 表：ads_overview / ads_score_distribution / ads_type_distribution
              ads_hot_anime / ads_tag_analysis / ads_year_trend
    │  sqoop export（HDFS → MySQL）
    ▼
MySQL  anime_db.ads_*        ← 供 Django Web 与大屏读取
```

## 二、环境依赖

| 组件 | 版本 | 说明 |
|---|---|---|
| JDK | **8**（`1.8.0_504`） | ⚠️ **只给大数据栈用**；Spark 侧仍是 JDK 17，两套互不干扰 |
| Hadoop | 3.3.6 | 伪分布式（NameNode/DataNode/ResourceManager/NodeManager）|
| Hive | 3.1.3 | 元数据库 = MySQL 的 `hive_metastore`；执行引擎 = **MapReduce**（未装 Tez）|
| Sqoop | 1.4.7 | HDFS → MySQL 导出 |
| MySQL | 8.0.46 | 落点库 `anime_db`；需 JDBC 驱动 **8.x**（`caching_sha2_password`）|

环境变量集中写在 `~/software/bigdata-env.sh`（`~/.bashrc` 里 source）。
启动集群：`start-dfs.sh && start-yarn.sh`（`jps` 应看到 5 个进程）。

⚠️ 三个易被忽略的前置：
1. **`ssh localhost` 免密必须通**（Hadoop 启停脚本靠它拉起进程）
2. **Hive 的 scratch 目录必须是 777**（`hdfs dfs -chmod -R 777 /elarea/tmp /elarea/warehouse`）
   —— Hive 只在「自己创建目录」时才设 777，手动建的要自己补
3. **`schematool` / `beeline` 不读 `hive-env.sh`** → 跑之前手动 `export JAVA_HOME=<JDK8路径>`

## 三、运行顺序

### 步骤 1：数据入港（HDFS 分区）

```bash
hdfs dfs -mkdir -p /elarea/raw/anime/dt=2026-10-10 \
                    /elarea/raw/ratings/dt=2026-10-10 \
                    /elarea/raw/tags/dt=2026-10-10 \
                    /elarea/raw/rating_train/dt=2026-10-10 \
                    /elarea/raw/rating_test/dt=2026-10-10

cd Spider/rawdata/data
hdfs dfs -put -f anime_cleaned.csv /elarea/raw/anime/dt=2026-10-10/
hdfs dfs -put -f user_ratings.csv  /elarea/raw/ratings/dt=2026-10-10/
hdfs dfs -put -f train_ratings.csv /elarea/raw/rating_train/dt=2026-10-10/
hdfs dfs -put -f test_ratings.csv  /elarea/raw/rating_test/dt=2026-10-10/
hdfs dfs -chmod -R 777 /elarea/raw
```

> ⚠️ **一张表 = 一个目录**。同一分区目录下的**所有文件都会被当成同一张表的行**——
> 最初把 `user_ratings.csv` / `train_ratings.csv` / `test_ratings.csv` 放在一起，
> 导致评分总数被读成 4,507,064（= 三份相加），正好是真值的 2 倍。
> 所以训练集/测试集各自独立成「一种类型」。

### 步骤 2：建 ODS 外部表

```bash
hive -f Spider/warehouse/hive/ods_ddl.hql
```

### 步骤 3：多维统计（6 张 ADS 表）

```bash
hive -f Spider/warehouse/hive/ads_build.hql     # 18 个 MapReduce 作业，约 19 分钟
```

### 步骤 4：Sqoop 导回 MySQL

先在 MySQL 建好落点表（DDL 见下），再：

```bash
export MYSQL_PASS=<密码>        # 或写进 Spider/mysql.text（该文件已 gitignore）
bash Spider/warehouse/sqoop/sqoop_export.sh
```

落点表 DDL：

```sql
CREATE TABLE IF NOT EXISTS ads_overview           (metric VARCHAR(50), value DOUBLE) DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ads_score_distribution (rate INT, cnt BIGINT, pct DOUBLE) DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ads_type_distribution  (anime_type VARCHAR(20), cnt BIGINT, pct DOUBLE) DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ads_hot_anime          (hot_rank INT, subject_id INT, name VARCHAR(255), anime_type VARCHAR(20), rating DOUBLE, rating_count INT) DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ads_tag_analysis       (tag_name VARCHAR(50), cnt BIGINT, pct DOUBLE) DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS ads_year_trend         (yr VARCHAR(10), cnt BIGINT) DEFAULT CHARSET=utf8mb4;
```

## 四、验收数字（对不上就说明口径错了）

| 检查项 | 应为 |
|---|---|
| 动漫总数 | 5,009 |
| 评分总数 | 2,253,532 |
| 用户数 | 10,303 |
| 评分分布十档合计 | 2,253,532（7 分档 753,228 为峰值）|
| 类型分布合计 | 5,009（TV 2412 / 剧场版 1154 / OVA 649 / WEB 492 / 未知 301 / 动态漫画 1）|
| 热度榜第一名 | 《孤独摇滚！》40,343 人 |
| 标签关联合计 | 10,728（49 个标签，榜首「搞笑」1178）|
| 年度趋势 | 93 个年份档、合计 4,979（另有 30 部无完整放送年份）|

## 五、踩过的坑（血泪记录，改脚本前先读）

| # | 坑 | 症状 | 修法 |
|---|---|---|---|
| 1 | **Hive 的表 = 目录** | 评分总数正好是真值的 2 倍 | 一张表一个目录；派生数据（train/test）独立成类型 |
| 2 | **`OpenCSVSerde` 把所有列都当 String** | `ORDER BY rating_count DESC` 变成字典序，榜首错成 `9982` | 数值列**显式 `CAST(... AS INT/DOUBLE)`** |
| 3 | **Sqoop 按「字母序」取列，不是建表顺序** | `(yr, cnt)` 被当成 `(cnt, yr)`，两列装反 | 必须写 `--columns "顺序与 Hive 表一致"` |
| 4 | **`sqoop export` 默认追加，不是覆盖** | 重跑一次数据翻倍 | 导出前 `TRUNCATE`（脚本已内置）|
| 5 | **Sqoop 缺 `commons-lang 2.6`**（Hadoop 3 只有 3.x）| `ClassNotFoundException: org.apache.commons.lang.StringUtils` | 往 `$SQOOP_HOME/lib/` 放一个 jar |
| 6 | **Sqoop 会在当前目录生成同名 `.java`**（自动 ORM 类）| 仓库里冒出一堆 `ads_*.java` | 脚本已 `cd` 到临时目录再跑 |

## 六、目录结构

```
Spider/warehouse/
├── README.md              ← 本文件
├── hive/
│   ├── ods_ddl.hql        ← ODS 层建表（外部表 + 分区）
│   └── ads_build.hql      ← ADS 层六项统计（6 条 INSERT，18 个 MR 作业）
└── sqoop/
    └── sqoop_export.sh    ← 六张表导出回 MySQL（幂等）
```
