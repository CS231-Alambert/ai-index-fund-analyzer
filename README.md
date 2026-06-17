# AI Index Fund Analyzer

> 持仓穿透式基金分析系统 — 从个股加权到基金评分，技术面+基本面双引擎

[![Python](https://img.shields.io/badge/Python-3.8+-blue)](app.py)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web%20UI-ff4b4b)](app.py)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 核心理念

**不直接分析基金本身，而是穿透到持仓个股层面。**

对于 ETF、场外指数基金、主动基金、QDII，系统自动获取其持仓个股，逐只取 OHLCV 和 PE/PB/ROE，按权重加权合成基金级别的虚拟 K 线和估值指标。然后在这组合成数据上运行 10 因子评分模型。

```
基金代码 → 持仓个股列表 → 个股OHLCV+基本面 → 加权合成 → 技术指标+估值 → 买入/持有/卖出
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

| 指标 | 权重 | 说明 |
|------|------|------|
| PRICE ACTION | 15% | 趋势结构 (HH/HL/LH/LL) + **7 种K线形态识别** |
| VOLUME | 12% | 量价关系 (放量上涨/缩量下跌) |
| FIBONACCI | 10% | 回撤位信号 (0.382/0.618 买卖点) |
| VWAP | 11% | 成交量加权均价偏离度 |
| EMA | 11% | 双线交叉 (EMA12/26 金叉死叉) |
| MA | 11% | 四线排列 (MA5/10/20/60 多头空头) |

### 基本面指标 (30%)

| 指标 | 权重 | 说明 |
|------|------|------|
| PE | 10% | 市盈率 (越低越好) — 持仓加权 |
| ROE | 8% | 净资产收益率 (越高越好) |
| 换手率 | 5% | 市场活跃度 (适中最好) |
| 资金流向 | 7% | 主力资金净流入 — 持仓加权 |

### 输出

```
综合得分 (0-100) → strong_buy / buy / hold / sell / strong_sell
+ 技术得分 / 基本面得分拆分
+ 每只持仓个股的 PE/PB/权重明细
```

---

## K线形态识别

PRICE ACTION 指标内嵌 7 种经典 K 线形态检测，与趋势结构分析互补：

| 形态 | 类型 | 信号 |
|------|------|------|
| 锤子线 | 单K线 | 底部反转 ↑ |
| 倒锤子 | 单K线 | 底部反转 ↑ |
| 看涨吞没 | 双K线 | 强烈反转 ↑ |
| 看跌吞没 | 双K线 | 强烈反转 ↓ |
| 启明星 | 三K线 | 底部反转 ↑ |
| 黄昏星 | 三K线 | 顶部反转 ↓ |
| 十字星 | 单K线 | 变盘信号 ↔ |

当 K 线形态评分与趋势结构评分偏差超过 20% 时，按 60% 趋势 + 40% 形态加权融合。

---

## 市场感知

系统自动判断 A 股交易状态 (9:30–11:30, 13:00–15:00, Mon–Fri)：

- **盘中** → 尝试获取实时 PE/PB 快照
- **收盘后** → 跳过实时 API，使用日线收盘价
- **周末** → 回退到最近周五收盘数据

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
│   └── decision_model.py          # 10 因子决策模型
│
├── crawler/
│   ├── fund_crawler.py            # 基金信息 + 持仓明细
│   ├── stock_crawler.py           # 个股 OHLCV + PE/PB/资金流
│   ├── index_crawler.py           # 宽基指数 (快速模式)
│   ├── base_crawler.py            # HTTP 基础爬虫
│   └── robots_checker.py          # robots.txt 合规
│
├── cache/
│   └── sqlite_cache.py            # SQLite 数据缓存
│
└── utils/
    ├── market_utils.py            # A股交易时间判断
    ├── logger.py                  # 日志
    └── file_utils.py              # 文件导出工具
```

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动
streamlit run app.py
```

打开浏览器后，输入基金代码即可分析。默认示例：**110003** (易方达上证50增强)。

---

## 数据源

| 数据 | 来源 | 提供方 |
|------|------|--------|
| 基金信息 & 持仓 | akshare `fund_name_em` / `fund_portfolio_hold_em` | 东方财富 |
| 个股日线 OHLCV | akshare `stock_zh_a_hist_tx` | 腾讯 |
| 个股 PE / PB / 换手率 | akshare `stock_zh_a_spot_em` (盘中) | 东方财富 |
| 宽基指数日线 | akshare `stock_zh_index_daily` | 东方财富 |

全部数据源均为公开接口，无需 API Key。

---

## ⚠️ 免责声明

本系统仅供学习和研究目的。AI 模型生成的建议不构成投资指导。投资有风险，决策需谨慎。

---

## License

MIT
