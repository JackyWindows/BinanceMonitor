import streamlit as st

# 侧边栏控件
with st.sidebar:
    st.header("Home")
    st.sidebar.page_link('pages/deepseekmoney.py',label='资金流向分析')
    st.sidebar.page_link('pages/ratemonitor.py',label='费率监控')
    st.sidebar.page_link('pages/binanceperpsanalysis.py',label='合约分析')
    st.sidebar.page_link('pages/CryptoRateTradeMonitor.py',label='加密货币费率监控系统')
    st.sidebar.page_link('pages/CryptoCycleAnlysisi.py',label='加密货币多周期分析')

st.title("🛰️Binance Relate Analysis")

