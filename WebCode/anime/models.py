from django.db import models

class Anime(models.Model):
    # 主键: Bangumi subject ID （从详情页 URL 抽出）
    subject_id = models.IntegerField(primary_key=True)
    # 排行榜/列表
    rank = models.IntegerField()
    name = models.CharField(max_length=200)
    anime_type = models.CharField(max_length=50)  # TV / OVA / 剧场版
    episodes = models.IntegerField(null=True, blank=True)  # 话数 (连载中可能为空)
    # null=True = 数据库允许这个字段是空 (NULL)
    # blank=True = 表单允许不填
    air_date = models.DateField(null=True, blank=True)     # 放送时间（可能未知）
    # 制作人员（短文本）
    director = models.CharField(max_length=200, null=True, blank=True)
    # 制作人员（长文本：一长串名字）
    script_writer = models.TextField(null=True, blank=True)
    voice_actors = models.TextField(null=True, blank=True)
    # 评分
    rating = models.FloatField(null=True, blank=True)   # 0~10 一位小数
    rating_count = models.IntegerField(null=True, blank=True)
    # 图片/链接
    cover_url = models.CharField(max_length=500, null=True, blank=True)
    detail_url = models.CharField(max_length=500, null=True, blank=True)

    def __str__(self):
        return self.name 
    # 返回自己的名字

# Operations to perform:
#   Apply all migrations: admin, anime, auth, contenttypes, sessions
# Running migrations:
#   Applying anime.0001_initial... OK