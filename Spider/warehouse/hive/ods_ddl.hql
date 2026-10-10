-- ============================================================
-- ODS 层建表脚本（Hive 3.1.3）
-- 源：/elarea/raw/{anime,ratings}/dt=2026-10-10/*.csv
-- 注意：这是 HiveQL，不是 MySQL SQL —— 必须在 hive CLI / beeline 里跑
-- ============================================================

-- ① 动漫维表：番名里有英文逗号且用引号包住 → 必须 OpenCSVSerde
CREATE EXTERNAL TABLE IF NOT EXISTS ods_anime (
  rank_no       INT     COMMENT 'Bangumi 排名',
  name          STRING  COMMENT '中文名',
  anime_type    STRING  COMMENT '类型 TV/剧场版/OVA/WEB',
  episodes      INT     COMMENT '话数',
  air_date      STRING  COMMENT '放送日期（可能为"未知"）',
  director      STRING  COMMENT '导演',
  script_writer STRING  COMMENT '脚本',
  voice_actors  STRING  COMMENT '声优',
  rating        DOUBLE  COMMENT '评分',
  rating_count  INT     COMMENT '评分人数',
  cover_url     STRING  COMMENT '封面图地址',
  detail_url    STRING  COMMENT '详情页地址'
)
COMMENT 'ODS 层：动漫维表（源：Bangumi 清洗后导出）'
PARTITIONED BY (dt STRING COMMENT '入库日期分区')
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES ("separatorChar" = ",", "quoteChar" = "\"")
STORED AS TEXTFILE
LOCATION '/elarea/raw/anime'
TBLPROPERTIES ("skip.header.line.count" = "1");

-- ② 评分事实表：纯数字三列，无引号 → 最朴素的 Delimited 就够
CREATE EXTERNAL TABLE IF NOT EXISTS ods_rating (
  user_id  BIGINT COMMENT '用户ID',
  anime_id BIGINT COMMENT '动漫ID（Bangumi subject_id）',
  rate     INT    COMMENT '评分 1~10'
)
COMMENT 'ODS 层：用户评分事实表'
PARTITIONED BY (dt STRING COMMENT '入库日期分区')
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/elarea/raw/ratings'
TBLPROPERTIES ("skip.header.line.count" = "1");

-- ③ 让 Hive 去目录里认分区（dt=xxx 命名法的兑现）
MSCK REPAIR TABLE ods_anime;
MSCK REPAIR TABLE ods_rating;

SHOW PARTITIONS ods_anime;
SHOW PARTITIONS ods_rating;

-- ④ 动漫-标签关联表（源：站内标签体系，MySQL 导出，制表符分隔）
CREATE EXTERNAL TABLE IF NOT EXISTS ods_anime_tag (
  anime_id INT     COMMENT '动漫ID（Bangumi subject_id）',
  tag_id   BIGINT  COMMENT '标签ID',
  tag_name STRING  COMMENT '标签名'
)
COMMENT 'ODS 层：动漫-标签关联表'
PARTITIONED BY (dt STRING COMMENT '入库日期分区')
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
STORED AS TEXTFILE
LOCATION '/elarea/raw/tags';

MSCK REPAIR TABLE ods_anime_tag;
SHOW PARTITIONS ods_anime_tag;

-- ⑤⑥ 留一法拆分的训练/测试集（各占一个类型目录 —— 一张表 = 一个目录）
CREATE EXTERNAL TABLE IF NOT EXISTS ods_rating_train (
  user_id BIGINT, anime_id BIGINT, rate INT
)
COMMENT 'ODS 层：留一法训练集'
PARTITIONED BY (dt STRING)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/elarea/raw/rating_train'
TBLPROPERTIES ("skip.header.line.count"="1");

CREATE EXTERNAL TABLE IF NOT EXISTS ods_rating_test (
  user_id BIGINT, anime_id BIGINT, rate INT
)
COMMENT 'ODS 层：留一法测试集'
PARTITIONED BY (dt STRING)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION '/elarea/raw/rating_test'
TBLPROPERTIES ("skip.header.line.count"="1");

MSCK REPAIR TABLE ods_rating_train;
MSCK REPAIR TABLE ods_rating_test;
SHOW PARTITIONS ods_rating_train;
SHOW PARTITIONS ods_rating_test;
