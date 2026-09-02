#!/bin/bash
# 第一行: 告诉系统用 bash 跑这个脚本

cd "$(dirname "$0")"
# 不管你在哪个目录敲 ./sync.sh，都先切回脚本所在的毕设仓库根目录
# "$0" 是脚本自己的路径，dirname 取它的文件夹——这样脚本在哪都能用

if [ -n "$(git status --porcelain)" ]; then
    git add .
    git commit -m "sync: $(date '+%Y-%m-%d %H:%M')"
fi
# 有改动才提交: git status --porcelain 输出非空说明有未提交改动
# -n 判断"非空"，成立就 add 全部 + commit，提交信息带时间戳
# 没改动就跳过——避免"nothing to commit"报错中断

git push server main
# 推给服务器灯塔（快车道，免代理）

git push origin main
# 推给 GitHub（云端备份）

echo "同步完成 ✔"
# 收尾提示