# AI Index Fund Analyzer

> 持仓穿透式基金分析系统 — 从个股加权到基金评分，技术面+基本面双引擎，全链路闭环

[![Python](https://img.shields.io/badge/Python-3.8+-blue)](app.py)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web%20UI-ff4b4b)](app.py)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 核心理念

**不直接分析基金本身，而是穿透到持仓个股层面。**

对于 ETF、场外指数基金、主动基金、QDII，系统自动获取其持仓个股，逐只取 OHLCV 和 PE/PB/ROE/换手率/资金流，按权重加权合成基金级别的虚拟 K 线和估值指标。然后在这组合成数据上运行 10 因子评分模型。

```
基金代码 → 持仓个股列表 → 个股OHLCV+基本面 → 加权合成 → 技术指标+估值 → 置信度折扣 → 买入/持有/卖出
```

---

## 支持范围

| 类型 | 示例 | 持仓策略 | 技术分析 |
|------|------|----------|----------|
| 场内 ETF | 510050 上证50ETF | 全部成分股 | OHLCV 加权合成 |
| 场外指数基金 | 110003 易方达上证50增强 | 全部持仓 | OHLCV 加权合成 |
| 场外主动基金 | — | 前 10 大重仓股 | OHLCV 加权合成 |
| QDII 基金 | — | 前 10 大重仓股 | OHLCV 加权合成 |
| 宽基指数 (快速) | 000001 上证指数 | 指数级别 | 指数 OHLCV 直取 |

---

## 评分模型

### 技术指标 (70%)

| 指标 | 权重 | 说明 | 数据链路 |
|------|------|------|----------|
| PRICE ACTION | 15% | 趋势结构 (HH/HL) + **7种K线形态** | OHLCV → swing + candlestick |
| VOLUME | 12% | 量价关系 | OHLCV → volume ratio vs MA |
| FIBONACCI | 10% | 回撤位信号 (0.382/0.618) | OHLCV → fib levels |
| VWAP | 11% | 成交量加权均价偏离 | OHLCV → cumulative VWAP |
| EMA | 11% | 双线交叉 (EMA12/26) | OHLCV → EMA crossover |
| MA | 11% | 四线排列 (MA5/10/20/60) | OHLCV → MA alignment |

### 基本面指标 (30%)

| 指标 | 权重 | 说明 | 盘中源 | 盘后源 |
|------|------|------|--------|--------|
| PE | 10% | 市盈率 (越低越好) | `spot_em` 动态PE | 财报 EPS×4 / close 推算 |
| ROE | 8% | 净资产收益率 (越高越好) | 财报 `加权净资产收益率` | 同一来源 |
| 换手率 | 5% | 市场活跃度 (适中最好) | `spot_em` 换手率 | 新浪日线 turnover |
| 资金流向 | 7% | 主力资金净流入 | 外部API / OHLCV Money Flow | OHLCV Money Flow |

### 覆盖率置信度折扣

低覆盖率评分不可与高覆盖率等同。系统自动应用折扣公式：

```
调整后得分 = 50 + (原始得分 - 50) × min(1.0, 覆盖率%)
```

| 原始分 | 覆盖率 | 折扣后 | 场景 |
|--------|--------|--------|------|
| 80 | 30% | 59 | 主动基金 Top 10 — 大幅回归中性 |
| 80 | 74% | 72 | 指数增强 — 温和折扣 |
| 80 | 100% | 80 | 全持仓指数 — 完整信任 |

---

## K线形态识别

PRICE ACTION 内嵌 7 种经典 K 线形态，与趋势结构互补（偏差>20% 时 60%趋势+40%形态加权）：

| 形态 | 类型 | 信号 |
|------|------|------|
| 锤子线 | 单K线 | 底部反转 ↑ |
| 倒锤子 | 单K线 | 底部反转 ↑ |
| 看涨吞没 | 双K线 | 强烈反转 ↑ |
| 看跌吞没 | 双K线 | 强烈反转 ↓ |
| 启明星 | 三K线 | 底部反转 ↑ |
| 黄昏星 | 三K线 | 顶部反转 ↓ |
| 十字星 | 单K线 | 变盘信号 ↔ |

---

## 数据链路韧性

### OHLCV 多源 Fallback

```
get_ohlcv(code)
  ├── ① stock_zh_a_hist_tx (腾讯)  ← 主力, 含当日数据
  ├── ② stock_zh_a_daily  (新浪)  ← 独立提供商, 不同限流策略
  ├── ③ stock_zh_a_hist   (东方财富) ← 预留
  └── ④ 模拟数据                  ← 最终兜底
```

任一源连续失败 3 次 → 自动冷却 60s → 日志警告。腾讯和新浪是独立提供商，同时挂的概率极低。

### 全指标稳定性审计

| 指标 | 稳定性 | 盘中 | 盘后 | Fallback 层数 |
|------|--------|------|------|--------------|
| price_action | 🟢 极高 | ✅ | ✅ | 4 (OHLCV) |
| fibonacci | 🟢 极高 | ✅ | ✅ | 4 |
| ema | 🟢 极高 | ✅ | ✅ | 4 |
| ma | 🟢 极高 | ✅ | ✅ | 4 |
| vwap | 🟢 极高 | ✅ | ✅ | 4 |
| volume | 🟢 极高 | ✅ | ✅ | 4 (V=amount/C推算) |
| pe | 🟢 极高 | spot | EPS推算 | 2 + 默认值15 |
| pb | 🟢 极高 | spot | BPS推算 | 2 + 默认值2.0 |
| roe | 🟢 极高 | 财报 | 财报 | 1 + 默认值10 |
| turnover | 🟢 极高 | spot | 新浪日线 | 2 + 默认值2.0 |
| fund_flow | 🟢 极高 | API/MF | OHLCV MF | 3 + 默认值0 |

---

## 市场感知

- **盘中** → 实时 PE/PB 快照 + volume 按时间比例外推
- **收盘后** → 财报推算 PE/PB + 新浪 turnover + 日线收盘价
- **UI 时效性提示条** → 显示"持仓 Q1 · 距今 78 天 | K线完整度 ~87% | PE: 实时快照"

---

## 项目结构

```
ai-index-fund-analyzer/
├── app.py                         # Streamlit Web 入口
├── config.py                      # 权重、阈值、数据源配置
├── requirements.txt               # Python 依赖
│
├── analyzer/
│   ├── technical_indicators.py    # 6 技术指标 + 7 K线形态
│   ├── holdings_engine.py         # 持仓加权合成引擎 (核心)
│   └── decision_model.py          # 10 因子决策 + 覆盖率折扣
│
├── crawler/
│   ├── fund_crawler.py            # 基金信息 + 持仓明细
│   ├── stock_crawler.py           # 个股 OHLCV (多源) + 财报 PE/ROE/PB + Money Flow
│   ├── index_crawler.py           # 宽基指数 (快速模式)
│   ├── base_crawler.py            # HTTP 基础爬虫
│   └── robots_checker.py          # robots.txt 合规
│
├── cache/
│   └── sqlite_cache.py            # SQLite 数据缓存
│
└── utils/
    ├── market_utils.py            # A股交易时间 + K线完整度
    ├── logger.py                  # 日志
    └── file_utils.py              # 文件导出工具
```

---

## 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
```

默认示例：**110003** (易方达上证50增强)。

---

## 数据源

| 数据 | API | 提供方 | 可用时段 |
|------|-----|--------|----------|
| 基金信息 & 持仓 | `fund_name_em` / `fund_portfolio_hold_em` | 东方财富 | 全时段 |
| 个股日线 OHLCV | `stock_zh_a_hist_tx` (主) / `stock_zh_a_daily` (备) | 腾讯 / 新浪 | 全时段 |
| 个股 PE / PB / 换手率 | `stock_zh_a_spot_em` (盘中) + 新浪日线 (盘后) | 东方财富 / 新浪 | 全天 |
| 个股 ROE / EPS / BPS | `stock_financial_analysis_indicator` | 东方财富 | 全时段 |
| 个股资金流 | `stock_individual_fund_flow` / OHLCV Money Flow | 东方财富 / 自算 | 全天 |
| 宽基指数日线 | `stock_zh_index_daily` | 东方财富 | 全时段 |

全部数据源均为公开接口，无需 API Key。

---

## ⚠️ 免责声明

本系统仅供学习和研究目的。AI 模型生成的建议不构成投资指导。投资有风险，决策需谨慎。

---

## License

MIT
