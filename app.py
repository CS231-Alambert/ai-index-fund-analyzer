import streamlit as st
import pandas as pd
import plotly.express as px
from crawler.index_crawler import IndexCrawler
from analyzer.decision_model import DecisionModel
from cache.sqlite_cache import cache
from config import APP_CONFIG, EXPORT_CONFIG
from utils.file_utils import ensure_dir, generate_filename
from utils.logger import logger


# 初始化应用
def init_app():
    """初始化应用"""
    st.set_page_config(
        page_title=APP_CONFIG['title'],
        page_icon='📊',
        layout='wide',
        initial_sidebar_state='expanded'
    )
    
    st.title(APP_CONFIG['title'])
    st.markdown(APP_CONFIG['description'])
    
    # 初始化组件
    crawler = IndexCrawler()
    decision_model = DecisionModel()
    
    return crawler, decision_model


# 搜索组件
def search_component():
    """搜索组件"""
    with st.sidebar:
        st.header('搜索指数')
        code = st.text_input(
            '请输入6位指数代码',
            value=APP_CONFIG['default_index'],
            max_chars=6,
            placeholder='例如：000001'
        )
        
        source = st.selectbox(
            '数据源',
            ['default', 'eastmoney'],
            index=0
        )
        
        search_button = st.button('搜索', type='primary')
    
    return code, source, search_button


# 数据展示组件
def data_display_component(index_data):
    """数据展示组件"""
    st.header(f"{index_data['name']} ({index_data['code']}) 实时数据")
    
    # 使用三列布局展示关键指标
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            label="市盈率 (PE)",
            value=round(index_data['pe'], 2)
        )
        
        st.metric(
            label="净资产收益率 (ROE)",
            value=f"{round(index_data['roe'], 2)}%"
        )
        
        st.metric(
            label="换手率",
            value=f"{round(index_data['turnover'], 2)}%"
        )
    
    with col2:
        st.metric(
            label="主力资金流入量",
            value=f"{round(index_data['fund_inflow'] / 100000000, 2)} 亿"
        )
        
        st.metric(
            label="主力资金流出量",
            value=f"{round(index_data['fund_outflow'] / 100000000, 2)} 亿"
        )
        
        st.metric(
            label="主力资金净变化额",
            value=f"{round(index_data['fund_net_change'] / 100000000, 2)} 亿"
        )
    
    with col3:
        # 显示数据源信息
        st.info(f"数据来源: {index_data['source']}")
        
        # 显示更新时间
        from datetime import datetime
        st.info(f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# 历史数据下载组件
def historical_data_download_component(crawler, code, name):
    """历史数据下载组件"""
    st.subheader("历史数据下载")
    
    # 获取历史数据
    historical_data = crawler.get_historical_data(code)
    
    if historical_data is not None and not historical_data.empty:
        # 显示历史数据概览
        st.write(f"共 {len(historical_data)} 条历史数据")
        
        # 生成文件名
        filename = generate_filename(
            EXPORT_CONFIG['file_name_pattern'],
            code,
            name
        )
        
        # 转换为CSV格式
        csv = historical_data.to_csv(index=False, encoding=EXPORT_CONFIG['encoding'])
        
        # 下载按钮
        st.download_button(
            label="下载完整估值数据 (CSV)",
            data=csv,
            file_name=filename,
            mime="text/csv",
            key=f"download_{code}"
        )
        
        # 显示历史数据图表
        st.subheader("历史估值走势")
        
        # PE走势图
        fig_pe = px.line(historical_data, x='date', y='pe', title=f'{name} 历史市盈率走势')
        st.plotly_chart(fig_pe, use_container_width=True)
        
        # ROE走势图
        fig_roe = px.line(historical_data, x='date', y='roe', title=f'{name} 历史净资产收益率走势')
        st.plotly_chart(fig_roe, use_container_width=True)
        
        # 资金流走势图
        fig_fund = px.line(historical_data, x='date', y='fund_net_change', title=f'{name} 历史资金流走势')
        st.plotly_chart(fig_fund, use_container_width=True)
    else:
        st.error("获取历史数据失败")


# 决策分析组件
def decision_analysis_component(decision_result):
    """决策分析组件"""
    st.header("决策分析")
    
    # 获取建议文本
    suggestion_text = {
        'strong_buy': '📈 强烈买入',
        'buy': '👍 买入',
        'hold': '🤝 持有',
        'sell': '👎 卖出',
        'strong_sell': '📉 强烈卖出'
    }[decision_result['suggestion']]
    
    # 显示综合得分和建议
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric(
            label="综合得分",
            value=decision_result['total_score'],
            delta=None
        )
    
    with col2:
        st.success(suggestion_text, icon="📋")
    
    # 显示决策依据
    st.subheader("决策依据")
    st.text(decision_result['decision_basis'])
    
    # 显示指标权重
    st.subheader("指标权重")
    weights_df = pd.DataFrame(
        list(decision_result['indicator_weights'].items()),
        columns=['指标', '权重']
    )
    weights_df['权重'] = weights_df['权重'] * 100
    weights_df['权重'] = weights_df['权重'].map('{:.1f}%'.format)
    
    st.dataframe(weights_df, use_container_width=True)
    
    # 可视化指标得分
    st.subheader("指标得分分析")
    
    # 准备指标得分数据
    indicators_scores = decision_result['indicators_scores']
    scores_data = []
    
    for indicator, score_info in indicators_scores.items():
        scores_data.append({
            '指标': {
                'pe': '市盈率(PE)',
                'roe': '净资产收益率(ROE)',
                'turnover': '换手率',
                'fund_flow': '主力资金净流入'
            }[indicator],
            '得分': score_info['score'],
            '权重': score_info['weight'] * 100
        })
    
    scores_df = pd.DataFrame(scores_data)
    
    # 指标得分条形图
    fig_scores = px.bar(
        scores_df,
        x='指标',
        y='得分',
        title='各指标得分',
        color='指标',
        height=400
    )
    st.plotly_chart(fig_scores, use_container_width=True)
    
    # 指标权重饼图
    fig_weights = px.pie(
        scores_df,
        values='权重',
        names='指标',
        title='指标权重分布',
        height=400
    )
    st.plotly_chart(fig_weights, use_container_width=True)


# 主应用逻辑
def main():
    """主应用逻辑"""
    # 初始化应用
    crawler, decision_model = init_app()
    
    # 获取搜索参数
    code, source, search_button = search_component()
    
    # 搜索逻辑
    if search_button or code:
        # 验证输入
        if len(code) != 6 or not code.isdigit():
            st.error("请输入有效的6位数字指数代码")
            return
        
        # 尝试从缓存获取数据
        cache_key = f"index_data:{code}:{source}"
        index_data = cache.get(cache_key)
        
        if index_data is None:
            # 显示加载状态
            with st.spinner('正在获取数据...'):
                # 获取指数数据
                index_data = crawler.get_index_data(code)
                
                if index_data is not None:
                    # 缓存数据
                    cache.set(cache_key, index_data)
                else:
                    st.error("获取数据失败，请检查指数代码或数据源")
                    return
        
        # 显示数据
        data_display_component(index_data)
        
        # 进行决策分析
        decision_result = decision_model.analyze(index_data)
        
        # 显示决策分析结果
        decision_analysis_component(decision_result)
        
        # 显示历史数据下载
        historical_data_download_component(crawler, code, index_data['name'])


# 运行应用
if __name__ == '__main__':
    try:
        logger.info("指数市场分析应用启动")
        main()
    except Exception as e:
        logger.error(f"应用运行出错: {str(e)}")
        st.error(f"应用运行出错: {str(e)}")
