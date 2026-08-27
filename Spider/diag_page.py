# -*- coding: utf-8 -*-
"""
诊断脚本: 查看 bgm.tv 收藏页的真实 HTML 结构
用法: python diag_page.py
作用: 打印一个收藏页里所有 /user/ 链接的 href / title / 文字 / class,
      用来判断"垃圾用户名"到底是从哪里混进来的。
"""
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
}

# 用 326 号条目(一个热门条目)的收藏页第 1 页做测试
URL = "https://bgm.tv/subject/326/collections?page=1"

resp = requests.get(URL, headers = HEADERS, timeout = 15)
print(f"状态码: {resp.status_code}")
if resp.status_code != 200:
    print("请求失败，无法诊断")
    exit()

soup = BeautifulSoup(resp.text, "lxml")

# 找出所有 /user/ 开头的链接
links = soup.find_all("a", href = lambda x: x and x.startswith("/user/"))
print(f"共找到 {len(links)} 个 /user/ 链接\n")

# 只打印前 15 个，避免刷屏
for i, a in enumerate(links[:15], 1):
    print(f"--- 第 {i} 个链接 ---")
    print(f"  href     : {a.get('href')}")
    print(f"  title    : {a.get('title')}")
    print(f"  class    : {a.get('class')}")
    print(f"  链接文字 : {a.get_text(strip = True)!r}")
    # 打印这个链接的原始 HTML，看里面到底包了什么
    print(f"  原始HTML : {str(a)[:200]}")
    print()
