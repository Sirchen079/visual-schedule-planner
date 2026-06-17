# 可视化日程安排记录

读研期间的事务管理工具：把一团乱麻的事情理顺，缓解焦虑。

> 当前状态：**后端地基**（任务 CRUD API）。前端界面在后续计划中实现。

## 安装（首次）

需要已安装 Python 3.11+。在 PowerShell 中执行：

```powershell
cd "G:\vibe coding\可视化日程安排记录"
python -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

## 启动

双击 `start.bat`，浏览器会自动打开 http://127.0.0.1:8000 。

## 数据在哪

- 数据库与上传的文件都在 `data/` 目录，已被 git 忽略，不会上传到 GitHub。
- 备份只需复制整个 `data/` 文件夹。

## 开发（跑测试）

```powershell
cd "G:\vibe coding\可视化日程安排记录\backend"
.venv\Scripts\python.exe -m pytest tests -v
```

## 任务 API（当前可用）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks` | 新建任务 |
| GET | `/tasks` | 列出全部任务 |
| GET | `/tasks/{id}` | 获取单个任务 |
| PUT | `/tasks/{id}` | 更新任务 |
| DELETE | `/tasks/{id}` | 软删除任务 |
