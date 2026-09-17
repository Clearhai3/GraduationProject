from .models import Anime, UserRating               # 导入你建的 Anime 模型
from django.shortcuts import render, redirect, get_object_or_404  # 自动回复 404 未找到
from django.contrib.auth import authenticate, login, logout     # 登录三件套
from django.contrib.auth.decorators import login_required       # 登录请求，用于登录后操作
from django.contrib.auth.forms import UserCreationForm          # 注册表单(含加密)
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.http import HttpResponse
import os   # 借 os 工具 (操作系统接口)
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def anime_list(request):                # 函数名必须和 urls 里一致
    page_num = request.GET.get("page", 1)   # 前段要第几页，默认第 1 页
    paginator = Paginator(Anime.objects.all(), 20)  # 5009 部 ÷ 20 = 251 页
    try:
        page = paginator.page(page_num)     # 要第 N 页 (页码非法会报错)
    except (PageNotAnInteger, EmptyPage):
        page = None                         # 页码是乱写的 / 超出范围 = 没货
    
    # 带暗号 X-Requested-With 的请求 = AJAX 滚动加载，只回数据行
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        if page is None:
            return HttpResponse("")         # 空响应 = 告诉前端"到底了"
        return render(request, "anime/_rows.html", {"page": page, "total_count": paginator.count})

    # 普通访问: 渲染完整首页
    return render(request, "anime/list.html", {"page": page, "total_count": paginator.count})

def anime_detail(request, anime_id):
    anime = get_object_or_404(Anime, pk=anime_id)   # 原样保留: 查当前动漫

    # 新增: 相关推荐
    similar_animes = []
    sim_file = os.path.join(BASE_DIR, "../../Spider/algorithms/itemcf/data/itemcf_sim_train.txt")
    with open(sim_file, encoding = "utf-8") as f:   
        for line in f:
            if line.startswith(f"相似Top:{anime_id}\t"):    # 找到本动漫那行
                # 解析: Tab切开 -> 取第2段 -> 按|切开 -> 每项按: 切开拿id
                parts = line.split("\t")[1].split("|")
                similar_ids = [int(p.split(":")[0]) for p in parts[:6]] # 只要前 6 个邻居
                similar_animes = list(Anime.objects.filter(subject_id__in=similar_ids))
                break       # 找到就停
    # 新增结束

    # 我在这页打的分: 没登录 / 没打过 -> 都是 None
    my_rating = None
    if request.user.is_authenticated:
        my_rating = UserRating.objects.filter(user = request.user, anime = anime).first()

    return render(request, "anime/detail.html", {
        "anime": anime, 
        "similar_animes": similar_animes, 
        "score_range": range(1, 11),
        "my_rating": my_rating,
    })

@login_required
def anime_rate(request, anime_id):
    anime = get_object_or_404(Anime, pk=anime_id)
    raw = request.POST.get("rate", "")          
    score = int(raw) if raw.isdigit() else 0    # 从表单里捞出分数

    if 1 <= score <= 10:        
        UserRating.objects.update_or_create(
            user = request.user,
            anime = anime,
            defaults = {"rate": score},
        )

    return redirect("anime_detail", anime_id = anime_id)

def anime_rank(request):        # 排行榜
    animes = Anime.objects.order_by("-rating")[:20]     # 评分倒叙，取前 20
    return render(request, "anime/rank.html", {"animes": animes})

def anime_search(request):      # 搜索
    keyword = request.GET.get("q", "")      # 拿用户输入，没输就空
    results = Anime.objects.filter(name__icontains=keyword)[:20] # 名字模糊索
    return render(request, "anime/search.html", {"results": results, "keyword": keyword})

def anime_dashboard(request):
    # 大屏数据: 预计算好的 JSON，脚本算一次，这里直接读
    data_dir = os.path.join(BASE_DIR, "../../Spider/webdata")

    with open(os.path.join(data_dir, "ratings/score_distribution.json"), encoding = "utf-8") as f:
        score_data = json.load(f)

    # 关键: dict 必须先变成 JSON 字符串才能交给模板
    score_json = json.dumps(score_data, ensure_ascii = False)

    with open(os.path.join(data_dir, "users/user_activity.json"), encoding = "utf-8") as f:
        activity_data = json.load(f)

    activity_json = json.dumps(activity_data, ensure_ascii = False)

    with open(os.path.join(data_dir, "anime/type_distribution.json"), encoding = "utf-8") as f:
        type_data = json.load(f)

    type_json = json.dumps(type_data, ensure_ascii = False)

    with open(os.path.join(data_dir, "anime/rating_top10.json"), encoding="utf-8") as f:
        top_data = json.load(f)

    top_json = json.dumps(top_data, ensure_ascii=False)

    with open(os.path.join(data_dir, "anime/hot_anime_top20.json"), encoding="utf-8") as f:
        hot_data = json.load(f)

    hot_json = json.dumps(hot_data, ensure_ascii=False)

    with open(os.path.join(data_dir, "anime/yearly_trend.json"), encoding = "utf-8") as f:
        trend_data = json.load(f)

    trend_json = json.dumps(trend_data, ensure_ascii = False)

    with open(os.path.join(data_dir, "users/active_users_top10.json"), encoding = "utf-8") as f:
        active_users_data = json.load(f)

    active_users_json = json.dumps(active_users_data, ensure_ascii = False)

    with open(os.path.join(data_dir, "algorithms/algorithm_compare.json"), encoding = "utf-8") as f:
        algorithm_data = json.load(f)

    algorithm_json = json.dumps(algorithm_data, ensure_ascii = False)

    return render(request, "anime/dashboard.html", {
        "score_data": score_json,
        "activity_data": activity_json,
        "type_data": type_json,
        "top_data": top_json,
        "hot_data": hot_json,
        "trend_data": trend_json,
        "active_users_data": active_users_json,
        "algorithm_data": algorithm_json,
    })

def user_register(request):
    """注册 —— 表单帮我们把密码加密后入库"""
    if request.method == "POST":
        form = UserCreationForm(request.POST)   # 把用户填的东西装进表单
        if form.is_valid():                     # 表单自检: 密码够长吗/两次一样吗
            user = form.save()                  # 存库(密码已加密)
            login(request, user)                # 顺手登录
            return redirect("anime_list")
    else:
        form = UserCreationForm()               # GET 请求 = 给一张空表

    return render(request, "anime/register.html", {"form": form})

def user_login(request):
    """登录 —— 两步: 先验证正身，再发通行证"""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        # 第一步: 验证正身 (查无此人 或 密码不对 -> 返回 None)
        user = authenticate(request, username = username, password = password)

        if user is not None:
            login(request, user)                # 第二步: 发通行证(写 session)
            return redirect("anime_list")

        return render(request, "anime/login.html", {"error": "账号或密码不对"})

    return render(request, "anime/login.html")

def user_logout(request):
    """退出 —— 撕掉通行证"""
    logout(request)
    return redirect("anime_list")

# Create your views here.
