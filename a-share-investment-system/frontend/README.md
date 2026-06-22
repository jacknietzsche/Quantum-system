# AShare Investment System - Frontend

基于 Vue 3 + Element Plus 的现代化前端界面，采用 TradingAgents-CN 的前端架构方法。

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| **框架** | Vue 3 | ^3.4.0 |
| **构建工具** | Vite | ^5.0.10 |
| **UI 组件库** | Element Plus | ^2.4.4 |
| **状态管理** | Pinia | ^2.1.7 |
| **路由** | Vue Router | ^4.2.5 |
| **图表库** | ECharts | ^5.4.3 |
| **HTTP 客户端** | Axios | ^1.6.2 |
| **CSS 预处理** | Sass | ^1.69.5 |
| **类型系统** | TypeScript | ~5.3.3 |

## 目录结构

```
frontend/
├── index.html                 # HTML 入口
├── package.json               # 依赖配置
├── vite.config.ts             # Vite 构建配置
├── tsconfig.json              # TypeScript 配置
├── public/                    # 静态资源
└── src/
    ├── main.ts                # Vue 应用入口
    ├── App.vue                # 根组件
    ├── api/                   # API 请求层
    │   ├── request.ts         # Axios 封装
    │   └── index.ts           # API 模块导出
    ├── components/            # 公共组件
    │   └── StockDetail.vue    # 个股详情弹窗
    ├── layouts/               # 布局组件
    │   └── BasicLayout.vue    # 基础布局（侧边栏+内容区）
    ├── router/                # 路由配置
    │   └── index.ts           # 路由表
    ├── stores/                # Pinia 状态管理
    ├── styles/                # 全局样式
    │   └── index.scss         # 主样式文件
    ├── utils/                 # 工具函数
    └── views/                 # 页面视图
        ├── Dashboard/         # 总览仪表盘
        ├── Portfolio/         # 持仓管理
        ├── Screening/         # 选股筛选
        ├── Database/          # 数据库管理
        └── Logs/              # 日志查看
```

## 开发指南

### 安装依赖

```bash
cd frontend
npm install
```

### 启动开发服务器

```bash
npm run dev
```

开发服务器将在 http://localhost:5173 启动，并自动代理 `/api` 请求到后端 http://127.0.0.1:8765。

### 构建生产版本

```bash
npm run build
```

构建产物将输出到 `../static` 目录，由后端 FastAPI 提供静态文件服务。

## 页面功能

### Dashboard（总览）
- 市场态势展示（BULL/BEAR/PANIC/OVERHEAT/NEUTRAL）
- 风控状态监控
- 策略信号展示
- 因子分析概览
- 数据质量评估
- 行业分布图表
- 活跃因子列表
- 数据源状态监控

### Portfolio（持仓）
- 持仓列表展示
- 盈亏分析
- 权重计算
- 风险评分
- 个股详情查看

### Screening（选股）
- 三阶段选股流程
- 实时进度展示
- 推荐股票列表
- 评分和信号展示

### Database（数据库）
- 股票信息管理
- 热榜 TOP100
- 龙虎榜数据
- 行业分布统计
- 数据质量监控
- 数据源连接测试

### Logs（日志）
- 实时日志流
- 日志级别过滤
- 错误统计
- 自动滚动

## 与旧版前端的对比

| 特性 | 旧版 (React + Tailwind) | 新版 (Vue 3 + Element Plus) |
|------|------------------------|---------------------------|
| 框架 | React 18 | Vue 3 |
| UI 库 | Tailwind CSS | Element Plus |
| 状态管理 | useState | Pinia |
| 路由 | 手动状态切换 | Vue Router |
| 类型系统 | JavaScript (JSX) | TypeScript |
| 组件库 | Lucide Icons | Element Plus Icons |
| 构建工具 | Vite 6 | Vite 5 |

## 后端 API

前端通过以下 API 与后端通信：

- `/api/market/regime` - 市场态势数据
- `/api/risk/status` - 风控状态
- `/api/signals/today` - 今日信号
- `/api/system/status` - 系统状态
- `/api/portfolio/holdings` - 持仓数据
- `/api/screening/*` - 选股相关
- `/api/db/*` - 数据库管理
- `/api/logs/*` - 日志相关
- `/api/analysis/*` - 分析相关
