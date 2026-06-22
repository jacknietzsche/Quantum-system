# AShare-X 轻量桌面方案

> 2026-05-09 | 舍弃Electron壳 | 浏览器即桌面 | 1条命令启动

## 架构

```
python main.py → FastAPI :8765 (serve静态文件) → 系统浏览器打开
```

## 变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | server.py | 增加StaticFiles serve + webbrowser.open |
| 修改 | main.py | cmd_desktop改为启动server+打开浏览器 |
| 修改 | electron/vite.config.js | build输出 → ../static/ |
| 修改 | electron/package.json | 移除electron/concurrently/wait-on依赖 |
| 删除 | electron/main.js | 不再需要 |
| 删除 | electron/preload.js | 不再需要 |
| 删除 | start.bat | 不再需要 |

## 启动方式

```bash
python main.py                    # 默认: 打开浏览器窗口
python main.py analyze 600519     # CLI分析
```

## 构建前端

```bash
cd electron && npm run build      # 输出到 ../static/
```
