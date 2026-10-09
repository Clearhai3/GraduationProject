from .models import Anime, UserRating, UserProfile, Tag, UserTag  # 导入你建的 Anime 模型
from django.shortcuts import render, redirect, get_object_or_404  # 自动回复 404 未找到
from django.contrib.auth import authenticate, login, logout     # 登录三件套
from django.contrib.auth.decorators import login_required       # 登录请求，用于登录后操作
from django.contrib.auth.forms import UserCreationForm          # 注册表单(含加密)
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.http import HttpResponse, Http404, JsonResponse
from django.core.files.base import ContentFile  # 把内存里的字节变成 Dajngo 认的文件
from functools import wraps
from .permissions import can_view_dashboard
from .recommend import recommend_for_user, get_sim, pick_by_tags
from .bangumi import sync_user_tags, BangumiError
from django.contrib import messages
from io import BytesIO                          # 内存里的"文件"
from PIL import Image, ImageOps                 # 图片工具
from uuid import uuid4
import os   # 借 os 工具 (操作系统接口)
import json
import random


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AVATAR_SIZE = 400                       # 头像输出边长(px)
AVATAR_MAX_UPLOAD = 5 * 1024 * 1024     # 允许上传的原始大小上限 5MB
CHART_PAGES = {
    "score": {
        "file": "ratings/score_distribution.json", 
        "kind": "bar",
        "title": "评分分布", 
        "sub": "全部 2,253,532 条评分，按 1~10 分十档统计"
    },
    "activity": {
        "file": "users/user_activity.json", 
        "kind": "pie",
        "title": "用户活跃度分层", 
        "sub": "10,303 位用户, 按评分条数分四档"
    },
    "type": {
        "file": "anime/type_distribution.json",
        "kind": "hbar",
        "title": "动漫类型分布", 
        "sub": "5,009 部作品的播放形式"
    },
    "trend": {
        "file": "anime/yearly_trend.json", 
        "kind": "line",
        "title": "年度放送趋势", 
        "sub": "1908~2026 · 249 部无日期未计"
    },
    "top": {
        "file": "anime/rating_top10.json",
        "kind": "hbar",
        "title": "评分 Top10", 
        "sub": "按 Bangumi 平均分排序"
    },
    "hot": {
        "file": "anime/hot_anime_top20.json",
        "kind": "hbar",
        "title": "热门动漫 Top20",
        "sub": "按评分人数排序 (全站热度)"
    },
    "active_users": {
        "file": "users/active_users_top10.json",
        "kind": "hbar",
        "title": "活跃用户 Top10",
        "sub": "样本内评分条数最多的用户"
    },
    "itemcf": {
        "file": "algorithms/algorithm_compare.json",
        "kind": "bar",
        "pick": "itemcf",
        "title": "ItemCF 推荐效果",
        "sub": "留一法评估 · 随机基线 0.20%"
    },
    "als": {
        "file": "algorithms/algorithm_compare.json",
        "kind": "bar",
        "pick": "als",
        "title": "ALS 评分预测",
        "sub": "RMSE 越低越好 · 基准 1.3456"
    },
}

def _foryou_pool(seed, user):
    """『猜你喜欢』池子: 20 部。
    · 有评分 -> 相似度扩散，结果由评分决定
    · 没评分 -> 热门池随机，冷启动兜底，跟首页共用同一颗种子
    """
    # 甲: 有燃料 -> 真推荐
    recs = recommend_for_user(user, 20)
    if recs:
        return [aid for aid, _ in recs]

    rng = random.Random(seed + "-foryou")

    pool = list(Anime.objects.filter(rating_count__gte=300)
                .values_list("subject_id", flat=True))

    if user.is_authenticated:
        rated = set(UserRating.objects.filter(user=user)
                    .values_list("anime_id", flat=True))
        pool = [i for i in pool if i not in rated]
        if len(pool) < 20:
            pool = list(Anime.objects.filter(rating_count__gte=300)
                        .values_list("subject_id", flat=True))

    return rng.sample(pool, min(20, len(pool)))

def anime_list(request):                # 函数名必须和 urls 里一致
    # 种子三级兜底: URL > session > 现生一颗
    # URL 优先是为了无限滚动分页能带回来 (那段逻辑不变)
    seed = request.GET.get("seed")
    if not seed:
        seed = request.session.get("home_seed")     # 老访客: 拿到上次那颗 -> 同一批 48 部
        if not seed:
            seed = str(random.random())
            request.session["home_seed"] = seed
    
    rng = random.Random(seed)

    # 0. 『猜你喜欢』池子 (先算 —— 下面五个来源都得让开它)
    pool_ids = _foryou_pool(seed, request.user)
    pool_set = set(pool_ids)

    # 1. 标签召回 —— 登录 + 勾了标签才有
    #    有它 -> 最新和最高分各让 4 部出来 (热门/随机一根毛不动)
    tag_pool = pick_by_tags(request.user, 8, exclude=pool_set)
    if tag_pool:
        N_LATEST, N_BEST = 16, 4
    else:
        N_LATEST, N_BEST = 20, 8
    N_HOT, N_RAND = 12, 8

    # 2. 抽五批 (每批守自己的规矩)
    # 最新: 从"最近 100 部"里随机抽 (不是取前 N —— 那样永远一样)
    latest_pool = list(Anime.objects.exclude(air_date=None).order_by("-air_date")[:100]
                       .values_list("subject_id", flat=True))
    latest = list(Anime.objects.filter(subject_id__in=rng.sample(latest_pool, N_LATEST)))

    hot_pool = list(Anime.objects.filter(rating_count__gte=300)
                    .values_list("subject_id", flat=True))
    hot = list(Anime.objects.filter(subject_id__in=rng.sample(hot_pool, N_HOT)))

    best_pool = list(Anime.objects.exclude(rating=None).filter(rating_count__gte=500)
                    .order_by("-rating")[:100].values_list("subject_id", flat=True))
    best = list(Anime.objects.filter(subject_id__in=rng.sample(best_pool, N_BEST)))

    tag = list(Anime.objects.filter(subject_id__in=tag_pool))

    all_ids = list(Anime.objects.values_list("subject_id", flat=True))
    rand = list(Anime.objects.filter(subject_id__in=rng.sample(all_ids, N_RAND)))

    # 猜你喜欢: 首屏 2 部 + 散点 18 部
    foryou_head = pool_ids[:2]
    foryou_tail = pool_ids[2:]
    foryou_picks = [Anime.objects.get(subject_id=i) for i in foryou_head]

    # 3. 混成一锅: 先去重，再打散
    mixed, seen = [], set()
    for a in latest + hot + best + tag + rand:
        if a.subject_id in seen or a.subject_id in pool_set:
            continue
        seen.add(a.subject_id)
        mixed.append(a)
    rng.shuffle(mixed)    

    # 3.5 去重可能剔掉几张(热门和高分会撞车)，从全站补回来，凑够 48
    if len(mixed) < 48:
        spare_pool = [i for i in all_ids if i not in seen and i not in pool_set]
        for sid in rng.sample(spare_pool, 48 - len(mixed)):
            seen.add(sid)
            mixed.append(Anime.objects.get(subject_id=sid))
    
    # 2 部推荐混进 48 部，随机位置 (像普通卡片一样出现)
    for a in foryou_picks:
        seen.add(a.subject_id)
        mixed.insert(rng.randint(0, len(mixed)), a)


    # 4. 滚动流
    PER_SCREEN = 2
    PER_PAGE = 20

    normal_ids = list(
        Anime.objects.exclude(subject_id__in=seen)
        .order_by("subject_id")
        .values_list("subject_id", flat=True)
    )

    rest_ids = []
    cursor = 0
    pending = list(foryou_tail)

    while pending:
        chunk = normal_ids[cursor:cursor + PER_PAGE]
        cursor += PER_PAGE
        for sid in pending[:PER_SCREEN]:
            chunk.insert(rng.randint(0, len(chunk)), sid)
        pending = pending[PER_SCREEN:]
        rest_ids.extend(chunk)

    rest_ids.extend(normal_ids[cursor:])

    # 分页分的是"id 列表"(便宜)，每次只按当页 id 取回对象
    paginator = Paginator(rest_ids, 20)

    # 带暗号 X-Requested-With = AJAX 滚动加载，只回数据行
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        try:
            # 前端第 2 页 = rest 的第 1 页 (第 1 屏被混合流占掉了)
            rest_page = paginator.page(int(request.GET.get("page", 2)) - 1)
        except (ValueError, PageNotAnInteger, EmptyPage):
            return HttpResponse("") # 空响应 = 告诉前端"到底了"

        # filter() 出来是 id 升序，得按 id 列表的顺序摆回去
        order = {}
        for i, sid in enumerate(rest_page.object_list):
            order[sid] = i
            
        rows = sorted(Anime.objects.filter(subject_id__in=rest_page.object_list),
                      key=lambda a: order[a.subject_id]
        )
        
        return render(request, "anime/_rows.html",
                      {"page": rows, "foryou_ids": pool_ids})

    # 普通访问: 渲染完整首页
    return render(request, "anime/list.html", {
        "mixed": mixed,
        "foryou_ids": pool_ids,
        "seed": seed,
        "total_count": Anime.objects.count(),
    })

def anime_reshuffle(request):
    """换一批: 丢掉首页那颗种子，再回首页 (回去时会生新的) """
    request.session.pop("home_seed", None)
    return redirect("anime_list")

def anime_for_you(request):
    mark = request.GET.get("mark", "")  # 首页点进来的那一部 (闪烁提醒它)

    seed = request.session.get("home_seed")     # 读首页那颗种子
    if not seed:                                # 直接输网址进来的，现生一颗
        seed = str(random.random())
        request.session["home_seed"] = seed

    pool_ids = _foryou_pool(seed, request.user)

    # 按池子自己的顺序取回来 
    order = {sid: i for i, sid in enumerate(pool_ids)}
    picks = sorted(Anime.objects.filter(subject_id__in=pool_ids)
                                .prefetch_related("tag_links__tag"),
                   key=lambda a: order[a.subject_id]
    )

    # 点到的动漫放到最前面
    if mark.isdigit():
        picks.sort(key=lambda a: a.subject_id != int(mark))

    my_rating_count = 0
    if request.user.is_authenticated:
        my_rating_count = UserRating.objects.filter(user=request.user).count()

    return render(request, "anime/for_you.html", {
        "picks": picks,
        "mark": mark,
        "my_rating_count": my_rating_count,
    })

def anime_detail(request, anime_id):
    anime = get_object_or_404(Anime, pk=anime_id)   # 原样保留: 查当前动漫

    # 新增: 相关推荐
    neighbors = get_sim().get(anime_id, {})
    similar_ids = [aid for aid, _ in sorted(neighbors.items(), key=lambda kv: (-kv[1], kv[0]))[:6]]

    # filter(_in=) 不保存(实测 99% 的番顺序错, MySQL 按主键升序返回) -> 自己拼回去
    order = {sid: i for i, sid in enumerate(similar_ids)}
    similar_animes = sorted(
        Anime.objects.filter(subject_id__in=similar_ids),
        key=lambda a: order[a.subject_id]
    )
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

def _compress_avatar(uploaded):
    """转正 -> 转 RGB -> 居中裁方 -> 缩到 400 -> 压缩 JPEG (全在内存里做) """
    img = ImageOps.exif_transpose(Image.open(uploaded))     # 1. 按 EXIF 转正

    # 2. 统一成 RGB: JPEG 村不了透明通道 / CMYK / 调色板
    if img.mode != "RGB":
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, {255, 255, 255})        # 铺一张白底
            bg.paste(img, mask=img.split()[-1])                     # 用透明通道当蒙板贴上去
            img = bg
        else:
            img = img.convert("RGB")

    # 3. 居中裁成正方形
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    # 4. 压缩到 400x400
    img = img.resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)

    # 5. 压成 JPEG，写进内存 (不落临时文件)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)

    return ContentFile(buf.getvalue())

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

@login_required
def user_profile(request):
    # select_related = 联手把关联的动漫一起查回来 (避免 N+1 查询)
    ratings = UserRating.objects.filter(user=request.user).select_related("anime")

    # 算法算出来的标签 (绑了 Bangumi 之后才有)
    algo_tags = list(
        UserTag.objects.filter(user=request.user, source="algorithm")
        .values_list("tag__name", flat=True)
    )

    return render(request, "anime/profile.html", {
        "ratings": ratings,
        "algo_tags": algo_tags,
    })

@login_required
def user_tags(request):
    """选标签 —— GET 看 / POST 存 (同一个地址)"""
    if request.method == "POST":
        # 1. 收: 表单里所有被勾上的标签 id
        #    注意不是 .get() —— 勾了三个就是三条，.get 只会拿到最后一个
        picked = request.POST.getlist("tags")

        # 2. 删: 只删"他自己选的那一档", 别碰 admin / algorithm
        UserTag.objects.filter(user=request.user, source="self").delete()

        # 4. 存
        UserTag.objects.bulk_create([
            UserTag(user=request.user, tag_id=tid, source="self")
            for tid in picked
        ])

        return redirect("user_tags")

    # GET: 把货摆出来
    all_tags = Tag.objects.filter(is_active=True).order_by("sort_order", "id")

    # 他已经选了哪些 (用 set，模板里做 in 判断快)
    my_ids = set(
        UserTag.objects.filter(
            user=request.user, source="self"
        ).values_list("tag_id", flat=True)
    )

    return render(request, "anime/tags.html", {
        "all_tags": all_tags,
        "my_ids": my_ids,
    })

@login_required
def user_bangumi(request):
    """绑 Bangumi —— 拉"看过" -> 算算法标签
    
    一个地址管两件事:
        用户名非空 -> 绑定并同步
        用户名是空 -> 解绑 (算法标签一起清)
    """
    if request.method != "POST":
        return redirect("user_profile")

    username = request.POST.get("bangumi_username", "").strip()
    profile, _ = UserProfile.objects.get_or_create(user=request.user)   # 老用户可能还没资料表

    # 1. 空 = 解绑
    if not username:
        profile.bangumi_username = None
        profile.save()
        UserTag.objects.filter(user=request.user, source="algorithm").delete()  
        messages.success(request, "已解锁绑定，算法标签也一起清掉了")
        return redirect("user_profile")

    # 2. 拉 + 算 + 写 (走代理，几白部要几秒)
    try:
        report = sync_user_tags(request.user, username)
    except BangumiError as e:
        # 拉失败就什么都不改 —— 别留下一个"看绑上了、其实没数据"的假记录
        messages.error(request, f"同步失败: {e}")
        return redirect("user_profile")

    # 3. 成功了才记帐
    profile.bangumi_username = username
    profile.save()

    messages.success(
        request,
        f"同步成功: {username} 看过 {report['total']} 部，"
        f"其中 {report['matched']} 部在我们库里，"
        f"算出 {len(report['tags'])} 个标签"
    )
    return redirect("user_profile")

@login_required
def user_avatar_upload(request):
    """上传头像 —— 文件走 request.FILES, 不走 request.POST"""
    f = request.FILES.get("avatar")
    if request.method == "POST" and f and f.size <= AVATAR_MAX_UPLOAD:
        new_file = _compress_avatar(f)      # 先压 (这步会失败，所以放最前)
        # get_or_create: 老用户可能还没有资料记录，先给他开一份空的
        profile, create = UserProfile.objects.get_or_create(user=request.user)
        if profile.avatar:
            profile.avatar.delete(save=False)   # 删掉旧文件，不在磁盘上留孤儿
        profile.avatar.save(f"{request.user.id}_{uuid4().hex[:8]}.jpg", new_file, save=False)
        profile.save()

    return redirect("user_profile")

def anime_rank(request):        # 排行榜
    animes = Anime.objects.order_by("-rating")[:20]     # 评分倒叙，取前 20
    return render(request, "anime/rank.html", {"animes": animes})

def anime_search(request):      # 搜索
    keyword = request.GET.get("q", "")      # 拿用户输入，没输就空
    if keyword:
        results = Anime.objects.filter(name__icontains=keyword)[:20] # 名字模糊索
    else:
        results = []
    return render(request, "anime/search.html", {"results": results, "keyword": keyword})

def anime_suggest(request):     # 搜索建议: 只回名字，越轻越好
    keyword = request.GET.get("q", "").strip()

    if not keyword:
        return JsonResponse({"items": []})

    rows = Anime.objects.filter(name__icontains=keyword).values("subject_id", "name")[:8]
    return JsonResponse({"items": list(rows)})

def dashboard_only(view):
    """不是自己人 -> 当这页不存在"""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not can_view_dashboard(request.user):
            raise Http404
        return view(request, *args, **kwargs)
    return wrapper

@dashboard_only
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

@dashboard_only
def anime_chart_detail(request, name):
    # 单图页: 九张图共用着一个视图，差异全部查登记表
    cfg = CHART_PAGES.get(name)
    if cfg is None:
        raise Http404

    data_dir = os.path.join(BASE_DIR, "../../Spider/webdata")

    with open(os.path.join(data_dir, cfg["file"]), encoding = "utf-8") as f:
        chart_data = json.load(f)

    # algorithm_compare.json 里装着两组，取走这一页要的那组
    if "pick" in cfg:
        chart_data = chart_data[cfg["pick"]]

    return render(request, "anime/chart_detail.html", {
        "title": cfg["title"],
        "sub": cfg["sub"],
        "kind": cfg["kind"],
        "chart_data": json.dumps(chart_data, ensure_ascii=False),
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
