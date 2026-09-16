# DATA.md — 数据资产说明书

> **这份文档回答一个问题：数据在哪、谁在写、出错了去哪查。**
> 它不是 `SHOW CREATE TABLE` 的抄写（那是目录，MySQL 自己能打），它是**地图**。
>
> 建立：2026-09-16（起因：mriya 提出"是不是该给数据库整一个说明书"）
> 状态：骨架已建，**带 ❓ 的条目需要 mriya 确认**

---

## 0. 先说这条文档的定位

**每张表/每份文件都要答出四个问题，答不出的地方就是你的盲区。**

| 问题 | 决定什么 |
|---|---|
| ① 谁写的？ | 能不能手改（Django 托管的表手改会被迁移覆盖） |
| ② 多久变一次？ | 要不要备份（一年不变的，丢了不急） |
| ③ 能删吗？ | 出事时往哪砍 |
| ④ 上游是谁？ | 数据错了去哪查（派生品出错要查源头，不是查它） |

---

## 1. 数据流全景（谁是「真身」，谁是「副本」）

```
                 ┌─────────────────────────────────────────────┐
   【采集层】     │  bangumi 网站                                │
                 └───────────────┬─────────────────────────────┘
                                 │ 爬虫 anime_spider_v2.py / bangumi_user_spider.py
                                 ▼
   【原始层】     rawdata/raw/  动漫信息_v2.json · user_ratings.jsonl
                                 │ 清洗 anime_data_cleaner.py / clean_ratings.py
                                 ▼
   【清洗层】★    rawdata/data/ anime_cleaned.csv(5,009) · user_ratings.csv(2,253,532)
                                 │                          ↑
                    import_anime.py│                       │ 这份评分明细**从未入库**
                                 ▼                        │
   【数据库层】   MySQL anime_db                            │
                 anime_anime(5,009) ← 元数据副本 ✅与 CSV 一致
                 anime_rating(0)    ← ❓预留空表，方案C绕开
                 anime_userrating(0)← 站内用户打分（新）
                                 │
             ┌───────────────────┼────────────────────┐
             ▼                   ▼                    ▼
   【派生层】  4张统计表        8个大屏JSON        ItemCF结果txt
             (裸SQL)         (webdata/)        (algorithms/)
             可再生 ←──────── 可再生 ←────────── 真身（只此一份）★
```

**★ = 唯一真身的位置（丢了就真没了）**
**其余都是可从上游重算的派生品**

### ⚠️ 最大的隐患

**真身散在三处**（MySQL / CSV / txt），而在此之前**没有任何文档说明哪份是真身**。
典型坑：改了 MySQL 忘了改 CSV，或者反过来——**两边都有数据，但你已经不知道哪个是新的了**。

---

## 2. 数据库总览（anime_db，实测 2026-09-16）

数据总量约 **3.6 MB**（很简单的一个库，别慌）。

### 2.1 Django 托管 · 业务表

| 表 | 行数 | ①谁写 | ②变化频率 | ③能删 | ④上游 |
|---|---|---|---|---|---|
| `anime_anime` | 5,009 | `import_anime.py`（Django ORM） | **定期更新（补新番为主线）** | ❌ | `anime_cleaned.csv` |
| `anime_animeuser` | **0** | 无人（**库存表**） | — | 🟡 留着 | `user_pool.json`（方案C绕开，未导） |
| `anime_rating` | **0** | 无人（**库存表**） | — | 🟡 留着 | `user_ratings.csv`（**225万条只在文件里**） |
| `anime_userrating` | 0 | Web 站内用户打分 | 随用户 | ❌ | 用户输入（**本站自己的数据，非爬取**） |

**② `anime_anime` 的更新策略（mriya 2026-09-16 定）**：

> 「目前最基本的目的就是补新番；标签数据、OP/ED 这些**保留接口，但不急着完善**。」

- ✅ **近期主线 = 补新番**（定期追加新播出的番）
- 🕐 **预留能力 = 标签 / OP / ED**（官方归档有现成数据，但暂不导入）
- 📌 所以这张表**会变**，但**是追加，不是重建** → **备份要跟上**

> 🏷️ `anime_animeuser` / `anime_rating` 是**库存表（暂时没有用）**，mriya 定：**留着**。
> 它们记录的是「原本的设计意图」，**不是漏导的数据**。看到 0 行不要慌。

### 2.2 Django 托管 · 系统表

| 表 | 行数 | 说明 |
|---|---|---|
| `auth_user` | 1 | **本站注册用户**（与外键 `anime_userrating.user_id` 相连） |
| `auth_group` / `auth_permission` / `auth_user_groups` / `auth_user_user_permissions` | 0 / 40 / 0 / 0 | Django 权限体系，**没用到，别动** |
| `django_content_type` | 10 | Django 内部模型登记表 |
| `django_migrations` | 22 | **迁移账本**（记录哪些迁移已应用） |
| `django_admin_log` | 0 | admin 后台操作日志 |
| `django_session` | 1 | 登录会话（用户已登录就会有行） |

### 2.3 ⚠️ 裸 SQL 建的表（**不在 Django 迁移账本里**）

| 表 | 行数 | 上游 | 建表脚本 |
|---|---|---|---|
| `hot_anime` | 20 | `user_ratings.csv` | `import_user_stats_to_mysql.py` |
| `user_activity_stats` | 4 | 同上 | 同上 |
| `user_activity_top` | 10 | 同上 | 同上 |
| `user_score_distribution` | 10 | 同上 | 同上 |

**这一类表的特殊性（重要）：**

- ✅ **好处**：Django 永远不会 `ALTER` 它们 → **大屏的数据是安全的**
- 🔴 **坏处**：Django 也保护不了它们 → **改结构必须手动**，而且**这份文档是它们唯一的账本**

**加列流程（以后要改的话）：**
1. 改 `import_user_stats_to_mysql.py` 里的 `CREATE TABLE`
2. 手动对已存在的表执行 `ALTER TABLE`（脚本里的 `CREATE` 不会自动改已存在的表）
3. **回来更新这份文档**

---

## 3. 文件层数据资产（同样是"真身"）

| 文件 | 大小 | 行数 | 性质 | 能重算吗 |
|---|---|---|---|---|
| `rawdata/data/user_ratings.csv` | 32M | 2,253,532 | ★ **评分真身** | ❌ 要重爬 |
| `rawdata/data/train_ratings.csv` | 31M | 2,243,230 | 派生（留一法的训练集） | ✅ |
| `rawdata/data/test_ratings.csv` | 148K | 10,303 | 派生（每用户留 1 条） | ✅ |
| `rawdata/data/anime_cleaned.csv` | 1.5M | 5,009 | ★ 动漫元数据真身 | ❌ 要重爬 |
| `rawdata/data/anime_cleaned.jsonl` | 2.3M | 5,009 | 同上的 jsonl 版 | ✅ |
| `algorithms/itemcf/data/itemcf_rec_train.txt` | 1.4M | 10,303 | ★ 推荐结果真身 | ⚠️ 能，但要跑三 Job |
| `algorithms/itemcf/data/itemcf_sim_train.txt` | 1.5M | 10,018 | ★ 相似度矩阵真身 | ⚠️ 同上 |
| `algorithms/itemcf/data/itemcf_rec.txt` / `itemcf_sim.txt` | 1.4M / 344K | 9,981 / 2,400 | **旧版（1200 时代）**，留作对比 | — |
| `summary/paper_summary.json` | 4K | — | 派生（从 MySQL 统计） | ✅ |
| `webdata/**/*.json` | — | 8 个 | 派生（`build_dashboard.py` 重跑） | ✅ |

> 📌 **`*_train` 与老版的关系**：不带 `_train` 的是 1200 部动漫时代的结果，带 `_train` 的是 5009 部时代的结果。**论文里引用的必须是 `_train`（新版）**。

---

## 4. 🚨 危险操作清单

| 操作 | 危险度 | 说明 |
|---|---|---|
| 手改 Django 托管表的**结构** | 🔴 | 下次 `makemigrations` 会生成冲突迁移 |
| 手改**裸 SQL 统计表**的结构 | 🟡 | Django 不管，但**改完必须回来更新文档** |
| 往 `anime_rating` 灌 225 万条 | 🟡 | 灌之前先把模型定死（灌完之后 ALTER 要重建表，实测 225 万行 ≈ **9.5 秒锁表**） |
| 删 `anime_animeuser` / `anime_rating` | 🟡 | 它们没数据，但删了就丢了"设计意图"的记录 |
| 删 `rawdata/data/*.csv` | 🔴 | **要重爬几天** |
| 删 `algorithms/*/data/*_train.txt` | 🟡 | 能重算，但要重跑三 Job |
| 删 `webdata/*.json` | ✅ | 跑一次 `build_dashboard.py` 就回来 |

---

## 4.1 🚨🚨 头号雷：重跑 `import_anime.py` 会删光用户打分

**实测证据（2026-09-16，事务内演示后回滚）：**

```
① 用户打分后   : UserRating = 1 条,  Anime = 5009 部
② 跑 Anime.objects.all().delete() ...
   Anime      = 0 部    ← 脚本预期的（会重新灌）
   UserRating = 0 条    ← !!! 被级联删光了
```

**根因**：

```python
# Spider/rawdata/tools/import_anime.py 最后两行
Anime.objects.all().delete()      # ← 级联！
Anime.objects.bulk_create(rows)

# 而 models.py 里：
UserRating.anime = ForeignKey(Anime, on_delete=models.CASCADE)   # 动漫没了 → 打分跟着没
Rating.anime     = ForeignKey(Anime, on_delete=models.CASCADE)   # 同上
```

**触发场景（就是他定下的近期主线）**：为了补三部新番，跑一次 `import_anime.py` → **所有用户打过的分全部消失**。不报错、无提示。

**为什么以前没暴露**：`UserRating` 是 2026-09-16 才建的，且一直是空表。**这个雷从今天起才真的有了杀伤力。**

**正确方向（改之前要连爬虫的增量逻辑一起想）**：

```python
# ❌ 推倒重来（适合一次性初始化）
Anime.objects.all().delete()
Anime.objects.bulk_create(rows)

# ✅ 增量更新（适合日常补新番）——找得到就更新，找不到就新建，永不删除
Anime.objects.update_or_create(subject_id=..., defaults={...})
```

**为什么能精确对上**：`subject_id` 就是主键，且是从详情页 URL 里抽出来的 **Bangumi 固有编号**——重爬之后 ID 不变。

> 📌 **状态：已发现，未修。改的时候记得同步更新本节。**

---

## 5. 每次改结构前必跑（三件套）

```bash
cd WebCode

# ① 账本干不干净？（0=干净，现在是改结构的便宜窗口；1=有未结算改动）
python manage.py makemigrations --check --dry-run

# ② 它说要动什么？
python manage.py makemigrations

# ③ 亲眼看它写了什么（❗别跳这一步）
cat anime/migrations/000N_xxx.py

# ④ 它实际会发什么 SQL（"迁移的 X 光片"）
python manage.py sqlmigrate anime 000N

# ⑤ 确认无误才执行
python manage.py migrate
```

**看到不认识的 `AlterField`，问三个问题：动哪张表 / 表里多少数据 / 改的是什么。**

---

## 6. 备份现状

| 位置 | 内容 | 状态 |
|---|---|---|
| 服务器（106.15.77.145） | git 裸仓库：代码 + 数据文件 | ✅ 全量 |
| GitHub | 代码 + 清洗数据（**不含 train 文件、不含 `.github/`、不含图片**） | ✅ 门面 |
| 台式机（宿舍） | ❓ 待确认最新程度 | ❓ |
| **MySQL 数据库本身** | **没有任何备份机制** | 🔴 |

> 🔴 **当前最大的备份缺口：`anime_db` 没有 dump。**
>
> 现在丢了都不难重建（`anime_anime` 从 CSV 重导、4 张统计表重跑脚本）——
> **但这个「都能重建」的状态，在第一个用户打分的瞬间就结束了。**
>
> 从那一刻起，`anime_userrating` 里出现了**外面没有的数据**。

### 备份策略（待定，但窗口正在关闭）

- [ ] 做定期 `mysqldump`？（脚本 + 存到服务器）
- [ ] 频率？（建议：每周一次 + **任何改结构之前手动一次**）
- [ ] `anime_userrating` 是否单独备份？（它是唯一不可再生的表）

---

## 7. 变更日志

| 日期 | 变更 | 影响表 | 谁做的 |
|---|---|---|---|
| 2026-09-06 | 建 `AnimeUser` / `Rating` | 新表 ×2 | 迁移 0003 |
| 2026-09-16 | `anime_rating.id` `INT → BIGINT` | `anime_rating` | 迁移 0004（`DEFAULT_AUTO_FIELD` 滞后修正，表为空故瞬间完成） |
| 2026-09-16 | 建 `UserRating`（+ `unique_together`） | 新表 ×1 | 迁移 0004 |
| 2026-09-16 | 建立本文档 | — | mriya 提议 |

---

## 8. ❓ 待补

### ✅ 已定（2026-09-16 mriya 答）

| 问题 | 答案 |
|---|---|
| `anime_anime` 变化频率 | **定期更新，主线是"补新番"**；标签 / OP / ED **保留接口，不急完善** |
| 两张空表 | **留着**，标记为「**库存表（暂时没有用）**」 |
| 225 万条评分的归属 | 当作 **bangumi 源** 的数据 → **按来源分容器**，算法层统一（见 §9） |

### ❓ 还没定

- [ ] **数据库备份方案**（见 §6）——窗口正在关闭
- [ ] **多源架构的两个前置决策**（见 §9.2：ID 撞车 / `source` 落脚点）——**必须在灌 225 万条之前定**
- [ ] `import_anime.py` 的级联删除**怎么改成增量**（见 §4.1）

---

## 9. 多源数据架构（mriya 2026-09-16 提出）

### 9.1 他的构想（原话精神）

> 「这个依旧当作是 bangumi 的数据，但是它**可以融合到我们的算法数据里面**。意思就是单独有一个东西称为 bangumi 数据，但是做算法计算的时候它也加入。**后期如果找到一个类似于 bangumi 的网站，也是这样的做法，做一个单独其他网站的容器给他们**，但是它的数据依旧用于我们的算法。」

**这个思路在数据工程里叫「按来源分层（source layer）」，是标准做法：**

```
【原始层】按来源分容器，各自结构自由
    bangumi 容器     ← 225 万条（0~10 分制）
    anilist 容器     ← 以后可能会有（可能是五星制 / 喜欢-不喜欢二值）
         ↓ 统一 schema（用户 × 动漫 × 分数）
【加工层】算法用的一份数据
```

**为什么比「按用途分」好**：来源之间结构**本来就不一样**。塞进同一张表就得互相妥协；分开存，各自爱怎么长怎么长。

### 9.2 ⚠️ 两个必须现在决定的前置问题

#### 雷 A：动漫 ID 会撞车

Bangumi 的 `subject_id=8` 是《鲁路修 R2》；假如 AniList 的 `id=8` 是《轻音少女》——
**两个 8，两部完全不同的番。**

如果两个源都往同一个 `anime_id` 空间里塞，而算法只看 `anime_id` → **会把两部番当成同一部**，把两组用户的偏好混在一起算。**不报错。**

**两个解法**：
1. `source` 进唯一键：`UNIQUE(user, anime_id, source)` —— 简单
2. 给每部番一个**全局唯一**的内部 ID，各源 ID 只作「外部编号」—— 更规范，但要多一张映射表

#### 雷 B：`source` 这个概念要有落脚点

| 方案 | 落脚点 | 代价 |
|---|---|---|
| **每源一张表** | 表名即来源（`bangumi_rating` / `anilist_rating`） | 算法层要 `UNION`；ID 撞车要额外处理 |
| **一张表 + `source` 列** | 列本身 | 🔴 **这个列必须在灌 225 万条之前加**（表大了加东西要重建，实测 225 万行 ≈ 9.5 秒锁表） |

> 🔑 **一句话**：无论选哪种，**这两个决定现在做都很便宜，灌完数据之后就很贵**。
> 这跟「先设计表、再灌数据」是同一条铁律。
