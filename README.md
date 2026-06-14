# AI Index Fund Analyzer

> AI 驱动的指数基金投资决策系统：多因子加权评分 + Streamlit 交互看板 + 实时数据爬取

[![Python](https://img.shields.io/badge/Python-3.8+-blue)](app.py)
[![Streamlit](https://img.shields.io/badge/Streamlit-Web%20UI-ff4b4b)](app.py)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## 项目概述

基于多因子加权评分模型，对指数基金进行量化分析和投资决策支持。系统自动爬取实时数据，通过 AI 决策模型生成买入/持有/卖出建议。

### 核心特性

- **AI 决策模型**：4 维度加权评分（PE 估值 30% + ROE 25% + 换手率 20% + 资金流向 25%）
- **实时数据**：自动爬取新浪财经、东方财富等数据源
- **交互看板**：Streamlit + Plotly 构建可视化分析界面
- **历史回测**：支持指定时间段的投资决策回测

---

## 技术栈

| 组件 | 技术 | 用途 |
|------|------|------|
| Web 界面 | Streamlit + Plotly | 交互式数据看板 |
| 决策模型 | Python (加权评分) | 多因子投资决策 |
| 数据爬取 | BeautifulSoup / Jsoup | 财经网站数据抓取 |
| 数据缓存 | SQLite | 本地数据持久化 |
| 后端（Java） | Maven + JavaFX | 桌面端增强功能 |

---

## AI 决策模型

### 多因子加权评分

```
投资评分 = PE_Score × 30% + ROE_Score × 25%
          + Turnover_Score × 20% + FundFlow_Score × 25%

输出:
  • 评分 > 70 → 🟢 买入 (Buy)
  • 评分 40-70 → 🟡 持有 (Hold)
  • 评分 < 40 → 🔴 卖出 (Sell)
```

### 因子说明

| 因子 | 权重 | 说明 |
|------|------|------|
| PE 估值 | 30% | 市盈率越低越有投资价值 |
| ROE | 25% | 净资产收益率，反映盈利能力 |
| 换手率 | 20% | 市场活跃度指标 |
| 资金流向 | 25% | 主力资金净流入/流出 |

---

## 架构

```
┌──────────────────────────────────────┐
│         Streamlit Web UI             │
│    (app.py + Plotly 可视化)          │
└────────────┬─────────────────────────┘
             │
┌────────────┴─────────────────────────┐
│          Analyzer Layer              │
│  ┌──────────────────────────────┐   │
│  │   decision_model.py          │   │
│  │   • 多因子评分                │   │
│  │   • Buy/Hold/Sell 决策        │   │
│  └──────────────────────────────┘   │
└────────────┬─────────────────────────┘
             │
┌────────────┴─────────────────────────┐
│          Data Layer                  │
│  ┌──────────────┐ ┌───────────────┐ │
│  │  Crawler     │ │  SQLite Cache │ │
│  │  (Sina/EM)   │ │               │ │
│  └──────────────┘ └───────────────┘ │
└──────────────────────────────────────┘
```

---

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 界面
streamlit run app.py
```

---

## 📁 项目结构

```
ai-index-fund-analyzer/
├── README.md
├── LICENSE
├── app.py                 # Streamlit 主入口
├── config.py              # 配置文件
├── requirements.txt       # Python 依赖
├── analyzer/              # 分析引擎
│   └── decision_model.py  # AI 决策模型
├── crawler/               # 数据爬取
│   ├── base_crawler.py
│   └── index_crawler.py
├── cache/                 # 数据缓存
│   └── sqlite_cache.py
└── utils/                 # 工具函数
    ├── file_utils.py
    └── logger.py
```

---

## ⚠️ 免责声明

本系统仅供学习和研究目的。投资有风险，决策需谨慎。AI 模型生成的建议不构成投资指导。

---

## 📄 License

MIT

---

## 👤 作者

**Lambert Liu** (CS231-Alambert)
- GitHub: [@CS231-Alambert](https://github.com/CS231-Alambert)
- 计算机科学与技术（中外合作办学）
