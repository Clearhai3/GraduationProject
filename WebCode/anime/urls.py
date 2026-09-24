from django.urls import path
from . import views

urlpatterns = [
    path("", views.anime_list, name="anime_list"),
    path("anime/<int:anime_id>/", views.anime_detail, name="anime_detail"),
    path("rank/", views.anime_rank, name="anime_rank"),
    path("search/", views.anime_search, name="anime_search"),
    path("dashboard/", views.anime_dashboard, name = "anime_dashboard"),
    path("dashboard/chart/<slug:name>/", views.anime_chart_detail, name = "anime_chart_detail"),
    path("anime/<int:anime_id>/rate/", views.anime_rate, name="anime_rate"),

    # 登录系统
    path("register/", views.user_register, name = "user_register"),
    path("login/", views.user_login, name = "user_login"),
    path("logout/", views.user_logout, name = "user_logout"),

    # 用户评分界面
    path("profile/", views.user_profile, name = "user_profile"),

    # 头像
    path("avatar/upload", views.user_avatar_upload, name="user_avatar_upload"),
]
