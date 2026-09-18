from django.db import models
from django.contrib.auth.models import User

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
    director = models.TextField(null=True, blank=True)
    # 制作人员（长文本：一长串名字）
    script_writer = models.TextField(null=True, blank=True)
    voice_actors = models.TextField(null=True, blank=True)
    # 评分
    rating = models.FloatField(null=True, blank=True)   # 0~10 一位小数
    rating_count = models.IntegerField(null=True, blank=True)
    # 图片/链接
    cover_url = models.CharField(max_length=500, null=True, blank=True)
    detail_url = models.CharField(max_length=500, null=True, blank=True)

    @property
    def local_cover(self):
        """本地封面路径(相对 static/) —— 数据库不动，渲染时把网上地址换成自家门牌"""
        if self.cover_url and "lain.bgm.tv" in self.cover_url:
            return f"images/anime/{self.subject_id}.jpg"
        return "images/anime/no_icon_subject.png"       # 没真图的用兜底

    def __str__(self):
        return self.name 
    # 返回自己的名字

class AnimeUser(models.Model):
    # 主键: 动漫用户的 id
    user_id = models.IntegerField(primary_key=True)
    username = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.username

class Rating(models.Model):
    user_id = models.IntegerField(db_index=True)
    anime = models.ForeignKey(Anime, on_delete=models.CASCADE, db_index=True, related_name="ratings")
    rate = models.FloatField(null=True, blank=True)     # blank = True 用于检测烂数据bug

    def __str__(self):
        return f"{self.user_id} 给 {self.anime} 打了 {self.rate}"

class UserRating(models.Model):
    """站内用户打分 —— 与 Rating(爬来的) 物理隔离"""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name="site_ratings", db_index=True,
    )
    anime = models.ForeignKey(
        Anime, on_delete=models.CASCADE,
        related_name="site_ratings", db_index=True,
    )
    rate = models.IntegerField()    # 1~10，站内打分必须是整数
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # 同一个用户对同一部动漫只能有一条记录 —— 数据库层面强制
        unique_together = ("user", "anime")

    def __str__(self):
        return f"{self.user.username} 给 《{self.anime.name}》打了 {self.rate} 分"

class UserProfile(models.Model):
    """站内用户的附加资料 —— 外挂在 auth_user 旁边，不碰 Django 的地基"""
    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name="profile",
    )
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} 的资料"

# Operations to perform:
#   Apply all migrations: admin, anime, auth, contenttypes, sessions
# Running migrations:
#   Applying anime.0001_initial... OK