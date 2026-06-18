# 可视化日程安排记录

把一团乱麻的事情理顺，缓解焦虑和灾难性思维。

## 安装（首次）

需要已安装 Python 3.11+。在 PowerShell 中执行：

```powershell
cd "G:\vibe coding\可视化日程安排记录"
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## 启动

双击 `start.bat`，浏览器会自动打开：

http://127.0.0.1:18731

这是本机高位端口，只监听 `127.0.0.1`。

## 关闭

- 推荐：网页右上角点击「关闭服务」
- 或者：关闭启动时弹出的「日程安排-服务」窗口

## 数据在哪

- 数据库与上传的文件都在 `data/` 目录，已被 git 忽略，不会上传到 GitHub。
- 备份只需复制整个 `data/` 文件夹。

## 开发（跑测试）

```powershell
cd "G:\vibe coding\可视化日程安排记录\backend"
.venv\Scripts\python.exe -m pytest tests -v
```

## 当前功能

- 看板：新建、编辑、拖拽改状态、删除任务
- 总览：今日到期、本周截止、逾期、完成率
- 资料库：上传任意文件、搜索、图片/PDF 预览、删除
- 任务关联资料：任务弹窗里可添加/移除资料
- 明/暗主题切换
