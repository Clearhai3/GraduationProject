-- ============================================================
-- ADS 层统计（任务书点名的五类 + 年份趋势）
-- 每条 INSERT 都会真的起一个 MapReduce 作业
-- ============================================================
USE default;

-- ---------- 结果表（放在数仓 warehouse 里，供 Sqoop 导出）----------
CREATE TABLE IF NOT EXISTS ads_overview (
  metric STRING COMMENT '指标名', value DOUBLE COMMENT '数值')
COMMENT 'ADS：总量指标';

CREATE TABLE IF NOT EXISTS ads_score_distribution (
  rate INT COMMENT '评分档', cnt BIGINT COMMENT '条数', pct DOUBLE COMMENT '占比%')
COMMENT 'ADS：评分分布';

CREATE TABLE IF NOT EXISTS ads_type_distribution (
  anime_type STRING COMMENT '类型', cnt BIGINT COMMENT '数量', pct DOUBLE COMMENT '占比%')
COMMENT 'ADS：类型分布';

CREATE TABLE IF NOT EXISTS ads_hot_anime (
  hot_rank INT COMMENT '热度排名', subject_id INT COMMENT 'Bangumi ID',
  name STRING COMMENT '动漫名', anime_type STRING COMMENT '类型',
  rating DOUBLE COMMENT '评分', rating_count INT COMMENT '评分人数')
COMMENT 'ADS：热度排行 Top20';

CREATE TABLE IF NOT EXISTS ads_tag_analysis (
  tag_name STRING COMMENT '标签', cnt BIGINT COMMENT '关联动漫数', pct DOUBLE COMMENT '占比%')
COMMENT 'ADS：标签分析';

CREATE TABLE IF NOT EXISTS ads_year_trend (
  yr STRING COMMENT '年份', cnt BIGINT COMMENT '放送数量')
COMMENT 'ADS：年度放送趋势';

-- ---------- ① 动漫数量统计（总量指标）----------
INSERT OVERWRITE TABLE ads_overview
SELECT '动漫总数', CAST(COUNT(*) AS DOUBLE) FROM ods_anime WHERE dt='2026-10-10';

INSERT INTO TABLE ads_overview
SELECT '评分总数', CAST(COUNT(*) AS DOUBLE) FROM ods_rating WHERE dt='2026-10-10';

INSERT INTO TABLE ads_overview
SELECT '用户数', CAST(COUNT(DISTINCT user_id) AS DOUBLE) FROM ods_rating WHERE dt='2026-10-10';

INSERT INTO TABLE ads_overview
SELECT '平均评分', ROUND(AVG(rate), 4) FROM ods_rating WHERE dt='2026-10-10';

-- ---------- ② 评分分布（窗口函数算占比）----------
INSERT OVERWRITE TABLE ads_score_distribution
SELECT rate, cnt, ROUND(cnt * 100.0 / SUM(cnt) OVER (), 2) AS pct
FROM (
  SELECT rate, COUNT(*) AS cnt FROM ods_rating WHERE dt='2026-10-10' GROUP BY rate
) t
ORDER BY rate;

-- ---------- ③ 热度排行 Top20（窗口函数排名）----------
-- ⚠️ OpenCSVSerde 把所有列都返回成 String → 数值列必须显式 CAST，否则排序变字典序
INSERT OVERWRITE TABLE ads_hot_anime
SELECT ROW_NUMBER() OVER (ORDER BY rc DESC, rk) AS hot_rank,
       subject_id, name, anime_type, rating, rc AS rating_count
FROM (
  SELECT CAST(rank_no AS INT)                AS rk,
         CAST(regexp_extract(detail_url, '/subject/([0-9]+)', 1) AS INT) AS subject_id,
         name, anime_type,
         CAST(rating AS DOUBLE)              AS rating,
         CAST(rating_count AS INT)           AS rc
  FROM ods_anime WHERE dt='2026-10-10'
) t
ORDER BY rc DESC
LIMIT 20;

-- ---------- ④ 类型分布 ----------
INSERT OVERWRITE TABLE ads_type_distribution
SELECT anime_type, cnt, ROUND(cnt * 100.0 / SUM(cnt) OVER (), 2) AS pct
FROM (
  SELECT anime_type, COUNT(*) AS cnt FROM ods_anime WHERE dt='2026-10-10' GROUP BY anime_type
) t
ORDER BY cnt DESC;

-- ---------- ⑤ 标签分析 ----------
INSERT OVERWRITE TABLE ads_tag_analysis
SELECT tag_name, cnt, ROUND(cnt * 100.0 / SUM(cnt) OVER (), 2) AS pct
FROM (
  SELECT tag_name, COUNT(*) AS cnt FROM ods_anime_tag WHERE dt='2026-10-10' GROUP BY tag_name
) t
ORDER BY cnt DESC;

-- ---------- ⑥ 年度放送趋势（附赠）----------
INSERT OVERWRITE TABLE ads_year_trend
SELECT yr, cnt FROM (
  SELECT regexp_extract(air_date, '([0-9]{4})', 1) AS yr, COUNT(*) AS cnt
  FROM ods_anime WHERE dt='2026-10-10' GROUP BY regexp_extract(air_date, '([0-9]{4})', 1)
) t
WHERE yr <> ''
ORDER BY yr;

-- ---------- 出结果 ----------
SELECT '=== ① 总量 ===' AS s;
SELECT * FROM ads_overview;
SELECT '=== ② 评分分布 ===' AS s;
SELECT * FROM ads_score_distribution;
SELECT '=== ③ 热度 Top20 ===' AS s;
SELECT * FROM ads_hot_anime;
SELECT '=== ④ 类型分布 ===' AS s;
SELECT * FROM ads_type_distribution;
SELECT '=== ⑤ 标签分析 ===' AS s;
SELECT * FROM ads_tag_analysis;
