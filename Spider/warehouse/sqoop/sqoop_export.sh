#!/bin/bash
# ============================================================
# 阶段 6：Sqoop 把 Hive 的 6 张 ADS 表导回 MySQL
#   证据：~/文档/毕设-Hadoop证据/09-Sqoop-导出输出.png
#
# 用法：
#   export MYSQL_PASS=<数据库密码>      # 或把密码写进 Spider/mysql.text（已 gitignore）
#   bash sqoop_export.sh
#
# ⚠️ 两个坑（都是实测踩出来的）：
#   1. Sqoop 从 MySQL 拿列清单是按【字母序】不是建表顺序
#      → 必须写 --columns，顺序与 Hive 表列顺序完全一致
#   2. sqoop export 默认是【追加】(INSERT) 不是覆盖
#      → 导出前先 TRUNCATE，否则重跑一次数据就翻倍
# ============================================================

export HADOOP_HOME=/home/mriya/software/hadoop-3.3.6
export HADOOP_CONF_DIR=$HADOOP_HOME/etc/hadoop
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
export SQOOP_HOME=/home/mriya/software/sqoop-1.4.7.bin__hadoop-2.6.0
export PATH=$PATH:$SQOOP_HOME/bin

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASS="${MYSQL_PASS:-$(cat "$REPO_ROOT/Spider/mysql.text" 2>/dev/null | tr -d '\r\n')}"
[ -n "$MYSQL_PASS" ] || { echo "❌ 先 export MYSQL_PASS=<密码>（或把密码写进 Spider/mysql.text，该文件已被 .gitignore 忽略）"; exit 1; }

J="jdbc:mysql://localhost:3306/anime_db?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=UTF-8"

# Sqoop 会在【当前目录】生成一张与表同名的 .java（自动生成的 ORM 类，用完即弃）
# → 先挪进临时目录，别脏了仓库
WORK="$(mktemp -d "${TMPDIR:-/tmp}/sqoop.XXXXXX")" && cd "$WORK"

export_one () {
  local tbl="$1" cols="$2"
  echo "──────────────────────────────────────────"
  echo "▶ $tbl   (列顺序: $cols)"
  mysql -u"$MYSQL_USER" -p"$MYSQL_PASS" anime_db -e "TRUNCATE TABLE $tbl;" 2>/dev/null
  sqoop export \
    --connect "$J" --username "$MYSQL_USER" --password "$MYSQL_PASS" \
    --table "$tbl" \
    --export-dir "/elarea/warehouse/$tbl" \
    --columns "$cols" \
    --input-fields-terminated-by '\001' \
    --input-lines-terminated-by '\n' \
    --num-mappers 1 2>&1 | grep -E "Exported|ERROR|Exception" | tail -2 \
    || echo "  ⚠️ 没抓到 Exported —— 大概率失败了，看上面输出"
}

export_one ads_overview           "metric,value"
export_one ads_score_distribution "rate,cnt,pct"
export_one ads_type_distribution  "anime_type,cnt,pct"
export_one ads_hot_anime          "hot_rank,subject_id,name,anime_type,rating,rating_count"
export_one ads_tag_analysis       "tag_name,cnt,pct"
export_one ads_year_trend         "yr,cnt"

cd / && rm -rf "$WORK"
echo "──────────────────────────────────────────"
echo "OK  六张表导出完毕"
