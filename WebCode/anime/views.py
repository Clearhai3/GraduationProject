from .models import Anime               # 导入你建的 Anime 模型
from django.shortcuts import render, get_object_or_404  # 自动回复 404 未找到
import os   # 借 os 工具 (操作系统接口)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def anime_list(request):                # 函数名必须和 urls 里一致
    animes = Anime.objects.all()[:20]    # 查数据库: 取前 20 部
    return render(request, "anime/list.html", {"animes": animes})

def anime_detail(request, anime_id):
    anime = get_object_or_404(Anime, pk=anime_id)   # 原样保留: 查当前动漫

    # 新增: 相关推荐
    similar_animes = []
    sim_file = os.path.join(BASE_DIR, "../../Spider/itemcf_sim_train.txt")
    with open(sim_file, encoding = "utf-8") as f:   
        for line in f:
            if line.startswith(f"相似Top:{anime_id}\t"):    # 找到本动漫那行
                # 解析: Tab切开 -> 取第2段 -> 按|切开 -> 每项按: 切开拿id
                parts = line.split("\t")[1].split("|")
                similar_ids = [int(p.split(":")[0]) for p in parts[:6]] # 只要前 6 个邻居
                similar_animes = list(Anime.objects.filter(subject_id__in=similar_ids))
                break       # 找到就停
    # 新增结束

    return render(request, "anime/detail.html", {"anime": anime, "similar_animes": similar_animes})
# Create your views here.
