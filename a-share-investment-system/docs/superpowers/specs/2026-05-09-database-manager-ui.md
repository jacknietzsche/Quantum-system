# 数据库管理页面

> 2026-05-09 | 参考 SQLite Browser + Supabase Studio | 6源数据链

## 后端 API (`api/routes/database.py`)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/db/stats | 库统计(总股票/最新更新/6源状态) |
| GET | /api/db/stockinfo | StockInfo列表(搜索+排序+分页) |
| POST | /api/db/stockinfo | 手动添加股票 |
| PUT | /api/db/stockinfo/{code} | 编辑股票 |
| DELETE | /api/db/stockinfo/{code} | 删除股票 |
| POST | /api/db/refresh | 刷新单只或多只股票(调DataInitializer) |
| GET | /api/db/kline/{code} | KlineCache查询 |
| GET | /api/db/snapshots | MarketSnapshot列表 |

## 前端页面 (`Database.jsx`)

- 统计卡片(股票数/最新更新/数据源链)
- 搜索+排序表格
- 添加/编辑弹窗
- 单只/批量刷新按钮
- 表切换标签(StockInfo/KlineCache/MarketSnapshot)

## 数据源显示
显示完整6源降级链: tencent → sina → baostock → efinance → tickflow → akshare
