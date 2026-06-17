"""
AI 指数基金分析系统 — Streamlit 交互看板

支持: 场内 ETF / 场外指数基金 / 场外主动基金 / QDII
双引擎: 技术指标 (70%) + 基本面指标 (30%)
核心方法: 持仓个股加权合成基金级别数据
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# 中文字体 (Noto Sans CJK SC)
_CJK_FONT = "Noto Sans CJK SC, Microsoft YaHei, SimHei, sans-serif"
pio.templates["cjk"] = pio.templates["plotly_dark"].update(
    font=dict(family=_CJK_FONT)
)
pio.templates.default = "cjk"
from plotly.subplots import make_subplots
from crawler.fund_crawler import FundCrawler
from crawler.index_crawler import IndexCrawler
from analyzer.holdings_engine import HoldingsEngine
from analyzer.decision_model import DecisionModel
from analyzer.technical_indicators import TechnicalIndicators
from cache.sqlite_cache import cache
from config import APP_CONFIG, EXPORT_CONFIG, TECHNICAL_INDICATOR_PARAMS, FUND_CONFIG
from utils.file_utils import ensure_dir, generate_filename
from utils.logger import logger
from utils.market_utils import is_a_market_open, candle_completeness_pct


# ── 初始化 ──────────────────────────────────────────────────

def init_app():
    st.set_page_config(
        page_title=APP_CONFIG['title'],
        page_icon='📊',
        layout='wide',
        initial_sidebar_state='expanded'
    )
    st.title(APP_CONFIG['title'])
    st.markdown(APP_CONFIG['description'])

    return FundCrawler(), HoldingsEngine(), DecisionModel()


# ── 侧边栏搜索 ──────────────────────────────────────────────

def search_component():
    with st.sidebar:
        st.header('🔍 搜索基金/指数')

        mode = st.radio(
            '分析模式',
            ['📊 基金分析 (持仓加权)', '📈 指数快速分析'],
            index=0,
        )

        if mode.startswith('📊'):
            code = st.text_input(
                '基金代码',
                value='110003',
                max_chars=6,
                placeholder='例: 110003 易方达上证50'
            )
        else:
            code = st.text_input(
                '指数代码',
                value='000001',
                max_chars=6,
                placeholder='例: 000001 上证指数'
            )

        search_button = st.button('开始分析', type='primary', use_container_width=True)

        st.divider()
        st.caption("📊 基金代码: 110003 上证50 | 510300 沪深300ETF")
        st.caption("📈 指数代码: 000001 上证 | 399006 创业板")
        st.caption("🔧 基本面指标由持仓个股加权计算")

    return mode, code, search_button


# ── 基金信息头部 ────────────────────────────────────────────

def fund_header(fund_info, decision_result):
    """基金名称 + 类型标签 + 综合评分"""
    category = fund_info.get('category', 'other')
    label = FUND_CONFIG['type_labels'].get(category, '未知类型')

    color_map = {
        'etf': '#3b82f6', 'otc_index': '#22c55e',
        'otc_active': '#f59e0b', 'qdii': '#8b5cf6', 'other': '#6b7280',
    }
    color = color_map.get(category, '#6b7280')

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            f"## {fund_info['name']} "
            f"<span style='font-size:0.5em; color:{color}; border:1px solid {color}; "
            f"border-radius:6px; padding:2px 8px; margin-left:8px;'>{label}</span>",
            unsafe_allow_html=True,
        )
        st.caption(f"代码: {fund_info['code']} | 类型: {fund_info['type']}")

    with col2:
        suggestion_map = {
            'strong_buy': '📈 强烈买入',
            'buy': '👍 买入', 'hold': '🤝 持有',
            'sell': '👎 卖出', 'strong_sell': '📉 强烈卖出',
        }
        st.metric(
            label="🎯 综合评分",
            value=f"{decision_result['total_score']:.1f}",
            delta=suggestion_map.get(decision_result['suggestion'], ''),
        )


# ── 数据时效性提示条 ──────────────────────────────────────

def data_freshness_bar(decision_result):
    """数据时效性提示条：持仓季度、K线完整度、PE来源。"""
    hs = decision_result.get('holdings_summary', {})
    is_open = is_a_market_open()
    candle_pct = candle_completeness_pct()

    # 1. 持仓季度 → 距今多少天
    quarter_str = ""
    detail = decision_result.get('holdings_detail', [])
    if detail:
        q = detail[0].get('quarter', '')
        quarter_str = q if q else "未知"

    if quarter_str and '季度' in quarter_str:
        # "2025年1季度股票投资明细" → parse
        import re, datetime
        m = re.match(r'(\d{4})年(\d)季度', quarter_str)
        if m:
            y, qtr = int(m.group(1)), int(m.group(2))
            # 季度最后一天
            q_end_month = qtr * 3
            q_end = datetime.date(y, q_end_month, 1)
            # last day of that month
            if q_end_month == 12:
                q_end = datetime.date(y, 12, 31)
            else:
                q_end = datetime.date(y, q_end_month + 1, 1) - datetime.timedelta(days=1)
            days_ago = (datetime.date.today() - q_end).days
            quarter_display = f"{y}年Q{qtr} · 距今 {days_ago} 天"
        else:
            quarter_display = quarter_str
    else:
        quarter_display = quarter_str if quarter_str else "未获取"

    # 2. K线完整度
    if not is_open:
        candle_display = "100% (已收盘)"
    else:
        candle_display = f"~{candle_pct:.0f}% (盘中预估)"

    # 3. PE 来源
    if is_open:
        pe_source = "实时快照" if decision_result.get('fundamental_score', 0) != 50 else "快照未获取·默认值"
    else:
        pe_source = "日线收盘价"

    st.info(
        f"📅 持仓: **{quarter_display}** | "
        f"🕯️ K线完整度: **{candle_display}** | "
        f"📊 PE/PB: **{pe_source}**"
    )


# ── 持仓明细表 ──────────────────────────────────────────────

def holdings_table(decision_result):
    """展示持仓个股明细"""
    holdings_detail = decision_result.get('holdings_detail', [])
    if not holdings_detail:
        return

    st.subheader("📋 持仓个股明细")

    rows = []
    for h in holdings_detail:
        rows.append({
            '代码': h['stock_code'],
            '名称': h['stock_name'],
            '权重(%)': f"{h['weight_pct']:.2f}",
            'PE': f"{h.get('pe', 0):.1f}",
            'PB': f"{h.get('pb', 0):.2f}",
            '换手率(%)': f"{h.get('turnover', 0):.2f}",
        })

    df = pd.DataFrame(rows)

    # 覆盖信息
    hs = decision_result.get('holdings_summary', {})
    if hs.get('is_full'):
        coverage_text = f"📊 覆盖全部 {hs['used_count']} 只个股, 权重覆盖率 {hs.get('coverage_pct', 0):.1f}%"
    else:
        coverage_text = (
            f"📊 前 {hs['used_count']}/{hs['total_count']} 大重仓股, "
            f"权重覆盖率 {hs.get('coverage_pct', 0):.1f}%"
        )
    st.caption(coverage_text)

    st.dataframe(df, use_container_width=True, hide_index=True)

    # 合成数据提示
    with st.expander("💡 关于合成数据"):
        st.markdown("""
        **OHLCV 合成方式**: 逐日对持仓个股的开高低收量按权重加权求和。
        例如: `基金收盘价[t] = Σ(个股收盘价[t] × 权重%) / Σ(权重%)`

        **基本面加权**: PE、ROE、PB、换手率 均为持仓个股对应指标的加权平均值。

        **适用性**: 技术指标（MA/EMA/VWAP/斐波那契等）在合成 OHLCV 上计算，
        反映的是"如果你按基金权重构建一个虚拟组合"的技术面特征。
        """)


# ── 技术指标仪表盘 ──────────────────────────────────────────

def technical_dashboard(decision_result):
    st.header("🔴 技术指标")
    indicators_scores = decision_result['indicators_scores']
    tech_indicators = {
        k: v for k, v in indicators_scores.items()
        if decision_result['indicator_categories'].get(k) == 'technical'
    }

    rows = [list(tech_indicators.items())[i:i+3] for i in range(0, 6, 3)]
    for row in rows:
        cols = st.columns(3)
        for col, (indicator, info) in zip(cols, row):
            score = info['score']
            if score >= 80:
                color, emoji = "#22c55e", "🟢"
            elif score >= 60:
                color, emoji = "#84cc16", "🟡"
            elif score >= 40:
                color, emoji = "#eab308", "🟠"
            elif score >= 20:
                color, emoji = "#f97316", "🔴"
            else:
                color, emoji = "#ef4444", "💀"

            name = {
                'price_action': '价格行为', 'fibonacci': '斐波那契',
                'volume': '成交量', 'vwap': 'VWAP均价',
                'ema': 'EMA', 'ma': 'MA',
            }.get(indicator, indicator)

            with col:
                st.markdown(
                    f"""<div style="border:1px solid #333; border-radius:12px; padding:16px;
                    text-align:center; background:linear-gradient(135deg,#1a1a2e,#16213e);">
                    <div style="font-size:0.85rem;color:#888;">{emoji} {name}</div>
                    <div style="font-size:2.2rem;font-weight:700;color:{color};">{score:.0f}</div>
                    <div style="font-size:0.75rem;color:#666;">权重 {info['weight']*100:.0f}%</div>
                    </div>""",
                    unsafe_allow_html=True,
                )


# ── 类别摘要 ────────────────────────────────────────────────

def category_summary(decision_result):
    st.header("📊 评分对比")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("🔴 技术得分 (70%)", f"{decision_result.get('technical_score', 0):.1f}")
    with col2:
        st.metric("🟢 基本面得分 (30%)", f"{decision_result.get('fundamental_score', 0):.1f}")
    with col3:
        st.metric("🎯 综合得分", f"{decision_result['total_score']:.1f}")


# ── 技术图表 ────────────────────────────────────────────────

def ohlcv_charts(index_data):
    ohlcv = index_data.get('ohlcv')
    if ohlcv is None or ohlcv.empty:
        st.info("无 OHLCV 数据")
        return
    df = ohlcv.copy()
    params = TECHNICAL_INDICATOR_PARAMS

    # ── 均线系统 ──
    st.subheader("📈 均线系统 (MA / EMA)")
    for period in params['ma_periods']:
        df[f'MA{period}'] = df['close'].rolling(window=period).mean()
    df['EMA12'] = df['close'].ewm(span=params['ema_short'], adjust=False).mean()
    df['EMA26'] = df['close'].ewm(span=params['ema_long'], adjust=False).mean()

    fig_ma = go.Figure()
    fig_ma.add_trace(go.Scatter(x=df.index, y=df['close'], mode='lines',
        name='价格', line=dict(color='#e0e0e0', width=2)))
    ma_colors = ['#fbbf24', '#f59e0b', '#ef4444', '#8b5cf6']
    for period, color in zip(params['ma_periods'], ma_colors):
        fig_ma.add_trace(go.Scatter(x=df.index, y=df[f'MA{period}'], mode='lines',
            name=f'MA{period}', line=dict(color=color, width=1.2, dash='dot')))
    fig_ma.add_trace(go.Scatter(x=df.index, y=df['EMA12'], mode='lines',
        name='EMA12', line=dict(color='#06b6d4', width=1.5)))
    fig_ma.add_trace(go.Scatter(x=df.index, y=df['EMA26'], mode='lines',
        name='EMA26', line=dict(color='#ec4899', width=1.5)))
    fig_ma.update_layout(height=400, margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation='h', yanchor='top', y=-0.15),
        xaxis_rangeslider_visible=False, template='cjk')
    st.plotly_chart(fig_ma, use_container_width=True)

    # ── 成交量 + VWAP ──
    st.subheader("📊 成交量 + VWAP")
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    df['VWAP'] = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    df['VolMA'] = df['volume'].rolling(window=params['volume_ma_period']).mean()

    fig_vol = make_subplots(rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.6, 0.4], vertical_spacing=0.05)
    fig_vol.add_trace(go.Scatter(x=df.index, y=df['close'], mode='lines',
        name='价格', line=dict(color='#e0e0e0', width=2)), row=1, col=1)
    fig_vol.add_trace(go.Scatter(x=df.index, y=df['VWAP'], mode='lines',
        name='VWAP', line=dict(color='#f59e0b', width=2, dash='dash')), row=1, col=1)
    colors = ['#ef4444' if df['close'].iloc[i] < df['open'].iloc[i] else '#22c55e'
              for i in range(len(df))]
    fig_vol.add_trace(go.Bar(x=df.index, y=df['volume'], name='成交量',
        marker_color=colors, opacity=0.6), row=2, col=1)
    fig_vol.add_trace(go.Scatter(x=df.index, y=df['VolMA'], mode='lines',
        name=f'VOL MA{params["volume_ma_period"]}',
        line=dict(color='#fbbf24', width=1.5)), row=2, col=1)
    fig_vol.update_layout(height=450, margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(orientation='h', yanchor='top', y=-0.12),
        xaxis_rangeslider_visible=False, template='cjk')
    st.plotly_chart(fig_vol, use_container_width=True)

    # ── 斐波那契 ──
    st.subheader("🔢 斐波那契回撤位")
    fib_lookback = params['fib_lookback']
    lookback_df = df.tail(fib_lookback)
    swing_high = lookback_df['high'].max()
    swing_low = lookback_df['low'].min()
    diff = swing_high - swing_low
    fig_fib = go.Figure()
    fig_fib.add_trace(go.Scatter(x=df.index[-fib_lookback:],
        y=df['close'].tail(fib_lookback), mode='lines',
        name='价格', line=dict(color='#e0e0e0', width=2)))
    fib_colors = {0.0: '#22c55e', 0.236: '#84cc16', 0.382: '#fbbf24',
                  0.5: '#f59e0b', 0.618: '#f97316', 0.786: '#ef4444', 1.0: '#dc2626'}
    for level in params['fib_levels']:
        price = swing_low + level * diff
        fig_fib.add_hline(y=price, line_dash="dash",
            line_color=fib_colors.get(level, '#888'),
            annotation_text=f"{level:.3f} ({price:.0f})",
            annotation_position="right", opacity=0.6)
    fig_fib.update_layout(height=350, margin=dict(l=0, r=0, t=0, b=0),
        template='cjk')
    st.plotly_chart(fig_fib, use_container_width=True)


# ── 全指标可视化 ────────────────────────────────────────────

def scores_visualization(decision_result):
    st.subheader("📊 全指标得分 & 权重")
    scores_data = []
    for indicator, info in decision_result['indicators_scores'].items():
        category = decision_result['indicator_categories'].get(indicator, 'unknown')
        scores_data.append({
            '指标': {
                'price_action': '价格行为', 'fibonacci': '斐波那契',
                'volume': '成交量', 'vwap': 'VWAP', 'ema': 'EMA', 'ma': 'MA',
                'pe': 'PE', 'roe': 'ROE', 'turnover': '换手率', 'fund_flow': '资金流向',
            }.get(indicator, indicator),
            '得分': info['score'], '权重(%)': info['weight'] * 100,
            '类别': '技术指标' if category == 'technical' else '基本面',
        })
    scores_df = pd.DataFrame(scores_data)

    col1, col2 = st.columns(2)
    with col1:
        fig_bar = px.bar(scores_df, x='指标', y='得分', color='类别',
            title='各指标得分', height=400,
            color_discrete_map={'技术指标': '#ef4444', '基本面': '#22c55e'})
        fig_bar.update_layout(template='cjk')
        st.plotly_chart(fig_bar, use_container_width=True)
    with col2:
        fig_pie = px.pie(scores_df, values='权重(%)', names='指标',
            title='权重分布', color='类别', height=400,
            color_discrete_map={'技术指标': '#ef4444', '基本面': '#22c55e'})
        fig_pie.update_layout(template='cjk')
        st.plotly_chart(fig_pie, use_container_width=True)


# ── 决策依据 ────────────────────────────────────────────────

def decision_basis_component(decision_result):
    st.header("📋 决策依据")
    st.text(decision_result['decision_basis'])


# ── 主应用 ──────────────────────────────────────────────────

def main():
    fund_crawler, holdings_engine, decision_model = init_app()
    mode, code, search_button = search_component()

    if search_button or code:
        if not code or not code.isdigit() or len(code) < 5:
            st.error("请输入有效的基金/指数代码（5-6位数字）")
            return

        with st.spinner('正在获取数据...'):
            if mode.startswith('📊'):
                # === 基金分析模式 ===
                index_data = _load_fund_data(code, fund_crawler, holdings_engine)
            else:
                # === 指数快速模式 ===
                index_data = _load_index_data(code)

        if index_data is None:
            st.error("获取数据失败，请检查代码或网络连接")
            return

        # 决策分析
        with st.spinner('正在分析...'):
            decision_result = decision_model.analyze(index_data)

        # Fund info for header
        fund_info = {
            'code': index_data.get('code', code),
            'name': index_data.get('name', f'基金{code}'),
            'type': index_data.get('fund_type_str', ''),
            'category': index_data.get('fund_category', 'other'),
        }

        # === 渲染 ===
        fund_header(fund_info, decision_result)
        st.divider()
        data_freshness_bar(decision_result)
        st.divider()
        holdings_table(decision_result)
        st.divider()
        category_summary(decision_result)
        st.divider()
        technical_dashboard(decision_result)
        st.divider()
        ohlcv_charts(index_data)
        st.divider()
        scores_visualization(decision_result)
        st.divider()
        decision_basis_component(decision_result)


def _load_fund_data(code: str, fund_crawler: FundCrawler,
                    holdings_engine: HoldingsEngine) -> dict | None:
    """加载基金数据: 获取持仓 → 个股加权合成"""
    # 1. 基金信息
    fund_info = fund_crawler.get_fund_info(code)
    if fund_info is None:
        return None

    # 2. 持仓明细
    top_n = FUND_CONFIG['active_top_n']
    holdings, summary = fund_crawler.get_filtered_holdings(
        code, fund_info['type'], top_n=top_n
    )

    if not holdings:
        st.warning(f"未获取到 {code} 的持仓数据，尝试使用指数快速模式")
        return _load_index_data(code)

    # 3. 个股加权合成
    synthetic = holdings_engine.build_synthetic_data(code, holdings)
    if synthetic is None:
        return None

    return {
        'code': code,
        'name': fund_info['name'],
        'source': 'holdings_weighted',
        'fund_type': fund_info['category'],
        'fund_type_str': fund_info['type'],
        'fund_category': fund_info['category'],
        'ohlcv': synthetic['ohlcv'],
        'pe': synthetic['pe'],
        'roe': synthetic['roe'],
        'turnover': synthetic['turnover'],
        'fund_flow': synthetic['fund_flow'],
        'fund_inflow': synthetic['fund_inflow'],
        'fund_outflow': synthetic['fund_outflow'],
        'fund_net_change': synthetic['fund_net_change'],
        'holdings_summary': summary,
        'holdings_detail': synthetic['holdings_detail'],
    }


def _load_index_data(code: str) -> dict | None:
    """指数快速模式 (保留原有逻辑)"""
    crawler = IndexCrawler()
    return crawler.get_index_data(code)


if __name__ == '__main__':
    try:
        logger.info("AI 指数基金分析系统启动")
        main()
    except Exception as e:
        logger.error(f"应用运行出错: {str(e)}")
        st.error(f"应用运行出错: {str(e)}")
