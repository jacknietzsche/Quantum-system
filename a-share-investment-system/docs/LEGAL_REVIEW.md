# A股智能投研系统 — 安全性与合法性审查报告

> 审查日期: 2026-05-31 (更新)
> 审查范围: 数据获取、存储、使用全流程

---

## 一、数据源合法性审查

### 1.1 当前使用的数据源 (全部合规)

| 数据源 | 类型 | 合法性 | 说明 |
|--------|------|--------|------|
| **AKShare** | 开源Python库 | ✅ 合规 | 调用东方财富/新浪/腾讯等公开API,15K+ GitHub stars |
| **Baostock** | 官方API | ✅ 合规 | 证券宝官方数据接口,免费使用 |
| **Tushare Pro** | 注册API | ✅ 合规 | 正规数据服务商,免费版有频率限制 |
| **efinance** | 开源Python库 | ✅ 合规 | 调用公开行情接口 |
| **Sina Finance** | 公开HTTP API | ✅ 合规 | hq.sinajs.cn 公开行情接口,无需认证 |
| **Tencent Finance** | 公开HTTP API | ✅ 合规 | qt.gtimg.cn 公开行情接口,无需认证 |
| **EastMoney** | 公开HTTP API | ✅ 合规 | push2.eastmoney.com 公开API |
| **TickFlow** | 商业API(免费版) | ✅ 合规 | 使用免费版token的正规API |

### 1.2 已移除的高风险模块

**eastmoney_auth.py** — 已删除 (2026-05-31)

该模块通过伪造浏览器指纹获取东方财富的认证令牌(NID),属于规避技术保护措施。已从系统中完全移除,包括:
- providers/eastmoney_auth.py.disabled (删除)
- launch.py 中的 patch_eastmoney() 调用 (移除)
- server.py 中的 patch_eastmoney() 调用 (移除)
- main.py 中的 patch_eastmoney() 调用和 --no-patch 参数 (移除)

---

## 二、合规性说明

### 2.1 数据获取方式

本系统使用的所有数据源均为以下合法方式之一:

1. **官方API** — Tushare Pro、Baostock、TickFlow (有正式服务协议)
2. **开源Python库** — AKShare、efinance (社区维护,调用公开接口)
3. **公开HTTP接口** — Sina、Tencent、EastMoney (无需认证的公开行情数据)

### 2.2 非逆向工程声明

- AKShare/efinance 是开源社区维护的数据访问库,不是逆向工程
- Sina/Tencent 公开行情接口无需登录或认证,属于公开数据
- 所有HTTP请求使用标准User-Agent和Referer头,属于正常HTTP行为

### 2.3 频率限制 (已实施)

```yaml
# 合规的请求频率限制
rate_limit:
  requests_per_second: 1      # 每秒最多1次
  daily_limit: 5000           # 每天最多5000次
  respect_retry_after: true   # 遵守服务器的Retry-After头
```

---

## 三、安全性审查

### 3.1 API密钥管理

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 密钥硬编码 | ✅ 良好 | 使用环境变量和.env文件 |
| .env文件 | ✅ 良好 | .gitignore已排除 |
| 日志泄露 | ✅ 良好 | 未在日志中输出密钥 |

### 3.2 网络安全

| 检查项 | 状态 | 说明 |
|--------|------|------|
| HTTPS | ✅ 良好 | API调用使用HTTPS |
| 证书验证 | ✅ 良好 | 默认启用证书验证 |
| 代理设置 | ✅ 良好 | NO_PROXY配置排除国内数据源 |

---

## 四、免责声明

本系统仅供个人学习和研究使用,不构成任何投资建议。

1. 数据来源: 本系统使用的数据来自公开渠道,数据准确性无法保证
2. 投资风险: 任何投资决策应基于个人独立判断,本系统不对投资损益负责
3. 合规声明: 使用本系统应遵守相关法律法规
4. 数据版权: 本系统展示的数据版权归原始数据提供方所有
