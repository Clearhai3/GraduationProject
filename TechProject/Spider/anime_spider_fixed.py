import requests
import json
import time
from bs4 import BeautifulSoup

TOTAL_PAGE = 200

BASE_URL = 'https://bangumi.tv/anime/browser?sort=rank&page={}'

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9"
}

all_anime_infos = []

with open('动漫信息.json', 'w', encoding='utf8') as file_writer:

    for page in range(1, TOTAL_PAGE + 1):

        print(f'正在爬取第{page}页的数据')

        url = BASE_URL.format(page)
        print(url)

        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.encoding = 'utf8'
        except requests.RequestException as e:
            print(f'请求第{page}页失败: {e}')
            time.sleep(3)
            continue

        if response.status_code != 200:
            print(f'第{page}页返回状态码: {response.status_code}')
            time.sleep(3)
            continue

        list_soup = BeautifulSoup(response.text, 'lxml')

        item_ul = list_soup.find(name="ul", attrs={"id": "browserItemList"})
        if item_ul is None:
            print(f'第{page}页未找到列表元素，可能页面结构变化或被反爬')
            time.sleep(3)
            continue

        items = item_ul.find_all(name="li")
        for item in items:
            try:
                img = item.find('img')['src']
                img = 'https:' + img

                name = item.find('h3').a.text

                rank = item.find('span', attrs={'class': 'rank'}).text
                rank = rank.split(' ')[-1]

                info = item.find('p', attrs={'class': 'info tip'}).text
                info = info.strip().replace(' ', '').split('/')

                hua_count = info[0][:-1]
                date = info[1]
                peoples = info[2:] if len(info) > 2 else []

                daoyan = peoples[0] if len(peoples) > 0 else '未知'
                jiaoben = peoples[1:] if len(peoples) > 1 else []

                rate_info = item.find('p', attrs={'class': 'rateInfo'})
                score_count_tag = rate_info.find('span', attrs={'class': 'rateInfo'})
                score_tag = rate_info.find('small', attrs={'class': 'fade'})

                score = float(score_tag.text) if score_tag else 0.0
                score_count = int(score_count_tag.text) if score_count_tag else 0

                dm_url = 'https://bangumi.tv' + item.find('h3').a['href']

                try:
                    resp = requests.get(dm_url, headers=HEADERS, timeout=10)
                    resp.encoding = 'utf8'
                except requests.RequestException as e:
                    print(f'请求详情页失败 {dm_url}: {e}')
                    time.sleep(1)
                    continue

                if resp.status_code != 200:
                    print(f'详情页返回状态码 {resp.status_code}: {dm_url}')
                    time.sleep(1)
                    continue

                detail_soup = BeautifulSoup(resp.text, 'lxml')
                header_div = detail_soup.find('div', attrs={'id': 'headerSubject'})
                leixing = header_div.small.text if header_div and header_div.small else '未知'

                juese = detail_soup.find_all('div', attrs={'class': 'info'})
                cv_shengyou = []
                for js in juese:
                    js_links = js.find_all('a')
                    cv_shengyou.extend([j.text.strip() for j in js_links])

                anime_info = {
                    '封面': img,
                    '名称': name,
                    '类型': leixing,
                    '排名': int(rank),
                    '话数': int(hua_count),
                    '放送时间': date,
                    '导演': daoyan,
                    '声优': cv_shengyou,
                    '脚本': jiaoben,
                    '评分': score,
                    '评分人数': score_count
                }
                line_str = json.dumps(anime_info, ensure_ascii=False)
                print(line_str)
                all_anime_infos.append(line_str + '\n')

                if len(all_anime_infos) % 10 == 0:
                    file_writer.writelines(all_anime_infos)
                    file_writer.flush()
                    all_anime_infos.clear()

                time.sleep(1)

            except Exception as e:
                print(f'解析单条数据出错: {e}')
                continue

        time.sleep(1)

    if len(all_anime_infos) > 0:
        file_writer.writelines(all_anime_infos)
        all_anime_infos.clear()