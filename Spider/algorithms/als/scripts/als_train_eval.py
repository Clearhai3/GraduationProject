"""ALS 冒烟版: 小样本验证全流程可跑通"""
from pyspark.sql import SparkSession

# 1. 本地模式，进行验证点火
spark = (
    SparkSession.builder
    .appName("AlsSmokeTest")
    .master("local[*]")
    .getOrCreate()
)

# 2. 读取数据
train_df = spark.read.csv(
    "rawdata/data/train_ratings.csv",
    header = True, inferSchema = True,
)

# 3. 确认类型
from pyspark.sql.types import IntegerType, DoubleType
train_df = train_df \
    .withColumn("user_id", train_df["user_id"].cast(IntegerType())) \
    .withColumn("anime_id", train_df["anime_id"].cast(IntegerType())) \
    .withColumn("rate", train_df["rate"].cast(DoubleType()))

# 冒烟: 进行 5 万行，验证流程
# train_df = train_df.limit(50000)

# 4. 训练: ALS 起步参数 rank=10, regParam=0.1, maxIter=10
from pyspark.ml.recommendation import ALS
als = ALS(
    userCol="user_id", itemCol="anime_id", ratingCol="rate",
    rank=10, regParam=0.1,maxIter=10,
    coldStartStrategy="drop",   # 遇到冷启动不炸, 直接跳过
)
model = als.fit(train_df)

# 5. 自我检验: 
train_pred = model.transform(train_df)
train_pred.show(5)

# 6. 读 test 数据 (它从没见过的评分)
test_df = spark.read.csv(
    "rawdata/data/test_ratings.csv",
    header=True, inferSchema=True,
)
# 类型保险丝
test_df = test_df \
    .withColumn("user_id", test_df["user_id"].cast(IntegerType())) \
    .withColumn("anime_id", test_df["anime_id"].cast(IntegerType())) \
    .withColumn("rate", test_df["rate"].cast(DoubleType()))

# 进行评分
test_pred = model.transform(test_df)

# 算 RMSE (RegressionEvaluator)
from pyspark.ml.evaluation import RegressionEvaluator
evaluator = RegressionEvaluator(
    metricName="rmse",
    labelCol="rate",            # 真答案在哪列
    predictionCol="prediction"  # 它猜的答案在哪列
)
rmse = evaluator.evaluate(test_pred)
print(f"RMSE = {rmse:.4f}")

# 基准线: 假设对所有评分都猜"平均分"
from pyspark.sql.functions import avg, lit
mean_rate = test_df.agg(avg("rate")).first()[0]     # 拿到 test 的平均分

baseline_df = test_df.withColumn("prediction", lit(mean_rate))  # 加一列假预测
baseline_rmse = evaluator.evaluate(baseline_df)                 # 同一个阅卷老师

import json

report = {
    "方法": "ALS (Spark MLlib 矩阵分解)",
    "评估方式": "留一法 (Leave-One-Out)",
    "用户数": train_df.select("user_id").distinct().count(),
    "动漫数": train_df.select("anime_id").distinct().count(),
    "训练条数": train_df.count(),
    "参数": {"rank": 10, "regParam": 0.1, "maxIter": 10},
    "RMSE": round(rmse, 4),
    "基准RMSE_全猜平均分": round(baseline_rmse, 4),
    "提升": f"{(1 - rmse/baseline_rmse) * 100:.2f}%"
}

with open("algorithms/als/data/als_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"报告已存: algorithms/als/data/als_report.json")

spark.stop()