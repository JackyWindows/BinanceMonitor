import streamlit as st
import pandas as pd
import time
import requests
import json
import os
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from decimal import Decimal, InvalidOperation
from openai import OpenAI

# OpenAI配置
OPENAI_API_KEY = "sk-C9b9fUXzuqQzW7Biq5NdFK0v6BrgicfsjFurqDpz2Ilul6O1"
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://api.tu-zi.com/v1"
)


def format_price(price):
    """
    根据价格大小智能格式化价格显示
    """
    if price is None or price == float('inf') or price == float('-inf'):
        return "N/A"

    try:
        price_decimal = Decimal(str(price))

        # 处理科学计数法格式
        price_str = str(price_decimal).upper()
        if 'E' in price_str:
            # 科学计数法处理
            exponent = abs(price_decimal.as_tuple().exponent)
            if exponent > 4:
                return f"{price_decimal:.0f}"
            elif exponent > 2:
                return f"{price_decimal:.2f}"
            return f"{price_decimal:.6f}"

        # 根据价格大小决定小数位数
        if abs(price_decimal) >= 10000:
            return f"{price_decimal:,.0f}"  # 添加千位分隔符
        elif abs(price_decimal) >= 1000:
            return f"{price_decimal:,.0f}"  # 添加千位分隔符
        elif abs(price_decimal) >= 100:
            return f"{price_decimal:.2f}"
        elif abs(price_decimal) >= 1:
            return f"{price_decimal:.3f}"
        elif abs(price_decimal) >= 0.1:
            return f"{price_decimal:.4f}"
        elif abs(price_decimal) >= 0.01:
            return f"{price_decimal:.5f}"
        elif abs(price_decimal) >= 0.001:
            return f"{price_decimal:.6f}"
        else:
            # 对于非常小的数，显示8位小数并去除尾随零
            formatted = f"{price_decimal:.8f}"
            return formatted.rstrip('0').rstrip('.') if '.' in formatted else formatted

    except (InvalidOperation, ValueError, TypeError):
        return "N/A"


# 页面配置
st.set_page_config(
    page_title="加密货币费率监控系统",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"  # 默认显示侧边栏
)

# 初始化会话状态
if 'symbol1' not in st.session_state:
    st.session_state.symbol1 = "AUCTIONUSDT"
    st.session_state.symbol1_data = {
        "timestamps": [],
        "spot_prices": [],
        "futures_prices": [],
        "premiums": [],
        "funding_rates": [],
        "open_interest": [],
        "last_funding_rate": None,
        "historical_data_loaded": False,
        "charts": [None, None, None],
        "running": False  # 添加单独的运行状态
    }

if 'symbol2' not in st.session_state:
    st.session_state.symbol2 = "FUNUSDT"
    st.session_state.symbol2_data = {
        "timestamps": [],
        "spot_prices": [],
        "futures_prices": [],
        "premiums": [],
        "funding_rates": [],
        "open_interest": [],
        "last_funding_rate": None,
        "historical_data_loaded": False,
        "charts": [None, None, None],
        "running": False  # 添加单独的运行状态
    }

if 'running' not in st.session_state:
    st.session_state.running = False
if 'stats_data' not in st.session_state:
    st.session_state.stats_data = None
if 'last_stats_update' not in st.session_state:
    st.session_state.last_stats_update = None

# 添加AI分析相关的会话状态
if 'last_ai_analysis_time' not in st.session_state:
    st.session_state.last_ai_analysis_time = None
if 'ai_analysis_result' not in st.session_state:
    st.session_state.ai_analysis_result = None
if 'ai_analysis_symbol' not in st.session_state:
    st.session_state.ai_analysis_symbol = None

# 常量
UPDATE_INTERVAL = 10  # 数据更新间隔（秒）
MAX_DATA_POINTS = 240  # 最大数据点数量 (4小时 = 240分钟)
HOURS_TO_DISPLAY = 4  # 显示过去多少小时的数据
STATS_FILE = "funding_rates_stats.json"  # 统计数据文件
AI_ANALYSIS_INTERVAL = 1800  # AI分析间隔（秒）= 30分钟


# 读取统计数据
def load_stats_data():
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r') as f:
                data = json.load(f)
                st.session_state.stats_data = data
                st.session_state.last_stats_update = datetime.now()
                return data
        return None
    except Exception as e:
        st.error(f"读取统计数据出错: {e}")
        return None


# 获取现货价格
def get_spot_price(symbol):
    try:
        url = "https://api.binance.com/api/v3/ticker/price"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "price" in data:
            return float(data["price"])
        else:
            st.error(f"无法获取现货价格: {data}")
            return None
    except Exception as e:
        st.error(f"获取现货价格时出错: {e}")
        return None


# 获取期货价格
def get_futures_price(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "price" in data:
            return float(data["price"])
        else:
            st.error(f"无法获取期货价格: {data}")
            return None
    except Exception as e:
        st.error(f"获取期货价格时出错: {e}")
        return None


# 获取资金费率
def get_funding_rate(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "lastFundingRate" in data:
            return float(data["lastFundingRate"])
        else:
            st.error(f"无法获取资金费率: {data}")
            return None
    except Exception as e:
        st.error(f"获取资金费率时出错: {e}")
        return None


# 获取持仓量
def get_open_interest(symbol):
    try:
        url = "https://fapi.binance.com/fapi/v1/openInterest"
        params = {"symbol": symbol}
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        if "openInterest" in data:
            return float(data["openInterest"])
        else:
            st.error(f"无法获取持仓量: {data}")
            return None
    except Exception as e:
        st.error(f"获取持仓量时出错: {e}")
        return None


# 获取历史K线数据
def get_historical_klines(symbol, interval, limit):
    try:
        # 计算结束时间（当前时间）和开始时间（4小时前）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY)).timestamp() * 1000)

        # 获取现货历史数据
        spot_url = "https://api.binance.com/api/v3/klines"
        spot_params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        spot_response = requests.get(spot_url, params=spot_params)
        spot_response.raise_for_status()
        spot_data = spot_response.json()

        # 获取期货历史数据
        futures_url = "https://fapi.binance.com/fapi/v1/klines"
        futures_params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        futures_response = requests.get(futures_url, params=futures_params)
        futures_response.raise_for_status()
        futures_data = futures_response.json()

        # 处理数据
        historical_timestamps = []
        historical_spot_prices = []
        historical_futures_prices = []
        historical_premiums = []

        # 确保两个数据集长度相同
        min_length = min(len(spot_data), len(futures_data))

        for i in range(min_length):
            timestamp = datetime.fromtimestamp(spot_data[i][0] / 1000, tz=timezone.utc)
            spot_close = float(spot_data[i][4])
            futures_close = float(futures_data[i][4])
            premium = (futures_close - spot_close) / spot_close * 100

            historical_timestamps.append(timestamp)
            historical_spot_prices.append(spot_close)
            historical_futures_prices.append(futures_close)
            historical_premiums.append(premium)

        return historical_timestamps, historical_spot_prices, historical_futures_prices, historical_premiums
    except Exception as e:
        st.error(f"获取历史K线数据时出错: {e}")
        return [], [], [], []


# 获取历史资金费率数据
def get_historical_funding_rates(symbol, limit=MAX_DATA_POINTS):
    try:
        # 计算结束时间（当前时间）和开始时间（4小时前）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY)).timestamp() * 1000)

        url = "https://fapi.binance.com/fapi/v1/fundingRate"
        params = {
            "symbol": symbol,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        timestamps = []
        funding_rates = []

        for item in data:
            timestamps.append(datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc))
            funding_rates.append(float(item["fundingRate"]) * 100)  # 转换为百分比

        return timestamps, funding_rates
    except Exception as e:
        st.error(f"获取历史资金费率数据时出错: {e}")
        return [], []


# 获取历史持仓量数据
def get_historical_open_interest(symbol, period="5m", limit=MAX_DATA_POINTS):
    try:
        # 计算结束时间（当前时间）和开始时间（4小时前）
        end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
        start_time = int((datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY)).timestamp() * 1000)

        url = "https://fapi.binance.com/futures/data/openInterestHist"
        params = {
            "symbol": symbol,
            "period": period,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }

        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        timestamps = []
        open_interests = []

        for item in data:
            timestamps.append(datetime.fromtimestamp(item["timestamp"] / 1000, tz=timezone.utc))
            open_interests.append(float(item["sumOpenInterest"]))

        return timestamps, open_interests
    except Exception as e:
        st.error(f"获取历史持仓量数据时出错: {e}")
        return [], []


# 更新数据
def update_data(symbol, symbol_data):
    # 获取当前时间
    now = datetime.now(timezone.utc)

    # 获取价格、资金费率和持仓量
    spot_price = get_spot_price(symbol)
    futures_price = get_futures_price(symbol)
    funding_rate = get_funding_rate(symbol)
    open_interest = get_open_interest(symbol)

    # 如果价格数据可用，则更新数据
    if spot_price is not None and futures_price is not None:
        # 计算溢价率
        premium = (futures_price - spot_price) / spot_price * 100

        # 添加数据到列表
        symbol_data["timestamps"].append(now)
        symbol_data["spot_prices"].append(spot_price)
        symbol_data["futures_prices"].append(futures_price)
        symbol_data["premiums"].append(premium)

        # 如果资金费率可用，则更新
        if funding_rate is not None:
            symbol_data["funding_rates"].append(funding_rate * 100)  # 转换为百分比
            symbol_data["last_funding_rate"] = funding_rate
        elif symbol_data["funding_rates"]:  # 如果有历史数据，则使用最后一个值
            symbol_data["funding_rates"].append(symbol_data["funding_rates"][-1])
        else:
            symbol_data["funding_rates"].append(0)
            funding_rate = 0  # 设置默认值

        # 如果持仓量可用，则更新
        if open_interest is not None:
            symbol_data["open_interest"].append(open_interest)
        elif symbol_data["open_interest"]:  # 如果有历史数据，则使用最后一个值
            symbol_data["open_interest"].append(symbol_data["open_interest"][-1])
            open_interest = symbol_data["open_interest"][-1]  # 使用最后一个值
        else:
            symbol_data["open_interest"].append(0)
            open_interest = 0  # 设置默认值

        # 清理过期数据 - 只保留过去4小时的数据
        # 但确保不会因为历史数据不足而导致数据减少
        if len(symbol_data["timestamps"]) > 1:  # 确保至少有数据
            cutoff_time = now - timedelta(hours=HOURS_TO_DISPLAY)

            # 检查最早的时间戳是否已经在4小时内
            # 如果是，则不需要清理，让数据自然累积到4小时
            if symbol_data["timestamps"][0] < cutoff_time:
                # 找到第一个不小于cutoff_time的时间戳的索引
                valid_indices = [i for i, ts in enumerate(symbol_data["timestamps"]) if ts >= cutoff_time]
                if valid_indices:
                    start_idx = valid_indices[0]
                    symbol_data["timestamps"] = symbol_data["timestamps"][start_idx:]
                    symbol_data["spot_prices"] = symbol_data["spot_prices"][start_idx:]
                    symbol_data["futures_prices"] = symbol_data["futures_prices"][start_idx:]
                    symbol_data["premiums"] = symbol_data["premiums"][start_idx:]
                    symbol_data["funding_rates"] = symbol_data["funding_rates"][start_idx:]
                    symbol_data["open_interest"] = symbol_data["open_interest"][start_idx:]

        return spot_price, futures_price, premium, funding_rate, open_interest

    # 如果价格数据不可用，返回默认值
    return None, None, None, funding_rate, open_interest


# 创建溢价率图表
def create_premium_chart(symbol, symbol_data):
    if not symbol_data["timestamps"]:
        return None

    fig = go.Figure()

    # 添加溢价率线
    fig.add_trace(
        go.Scatter(
            x=symbol_data["timestamps"],
            y=symbol_data["premiums"],
            mode='lines',
            line=dict(color='green')
        )
    )

    # 更新布局
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=40, t=50, b=30),
        yaxis_title="期现溢价率 (%)",
        xaxis=dict(
            range=[
                datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY),
                datetime.now(timezone.utc)
            ]
        )
    )

    # 添加零线
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    return fig


# 创建资金费率图表
def create_funding_rate_chart(symbol, symbol_data):
    if not symbol_data["timestamps"]:
        return None

    fig = go.Figure()

    # 添加资金费率线
    fig.add_trace(
        go.Scatter(
            x=symbol_data["timestamps"],
            y=symbol_data["funding_rates"],
            mode='lines',
            name='资金费率 (%)',
            line=dict(color='red')
        )
    )

    # 更新布局
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=40, t=50, b=30),
        yaxis_title="资金费率 (%)",
        xaxis=dict(
            range=[
                datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY),
                datetime.now(timezone.utc)
            ]
        )
    )

    # 添加零线
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    return fig


# 创建持仓量图表
def create_open_interest_chart(symbol, symbol_data):
    if not symbol_data["timestamps"]:
        return None

    fig = go.Figure()

    # 添加持仓量线
    fig.add_trace(
        go.Scatter(
            x=symbol_data["timestamps"],
            y=symbol_data["open_interest"],
            mode='lines',
            name='持仓量',
            line=dict(color='blue')
        )
    )

    # 更新布局
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=40, t=50, b=30),
        yaxis_title="持仓量",
        xaxis=dict(
            range=[
                datetime.now(timezone.utc) - timedelta(hours=HOURS_TO_DISPLAY),
                datetime.now(timezone.utc)
            ]
        )
    )

    return fig


# 加载历史数据
def load_historical_data(symbol, symbol_data):
    if not symbol_data["historical_data_loaded"]:
        with st.spinner(f"正在加载 {symbol} 历史数据..."):
            # 获取过去4小时的1分钟K线数据
            timestamps, spot_prices, futures_prices, premiums = get_historical_klines(
                symbol, "1m", MAX_DATA_POINTS
            )

            # 获取历史资金费率数据
            funding_timestamps, funding_rates = get_historical_funding_rates(symbol)

            # 获取历史持仓量数据
            oi_timestamps, open_interests = get_historical_open_interest(symbol)

            if timestamps:
                symbol_data["timestamps"] = timestamps
                symbol_data["spot_prices"] = spot_prices
                symbol_data["futures_prices"] = futures_prices
                symbol_data["premiums"] = premiums

                # 初始化资金费率列表
                if funding_rates:
                    # 将资金费率数据映射到时间戳上
                    mapped_funding_rates = []
                    for ts in timestamps:
                        # 找到最接近的资金费率时间戳
                        closest_idx = 0
                        min_diff = float('inf')
                        for i, fts in enumerate(funding_timestamps):
                            diff = abs((ts - fts).total_seconds())
                            if diff < min_diff:
                                min_diff = diff
                                closest_idx = i

                        # 使用最接近时间的资金费率
                        if closest_idx < len(funding_rates):
                            mapped_funding_rates.append(funding_rates[closest_idx])
                        else:
                            mapped_funding_rates.append(0)

                    symbol_data["funding_rates"] = mapped_funding_rates
                else:
                    symbol_data["funding_rates"] = [0] * len(timestamps)

                # 初始化持仓量列表
                if open_interests:
                    # 将持仓量数据映射到时间戳上
                    mapped_open_interests = []
                    for ts in timestamps:
                        # 找到最接近的持仓量时间戳
                        closest_idx = 0
                        min_diff = float('inf')
                        for i, ots in enumerate(oi_timestamps):
                            diff = abs((ts - ots).total_seconds())
                            if diff < min_diff:
                                min_diff = diff
                                closest_idx = i

                        # 使用最接近时间的持仓量
                        if closest_idx < len(open_interests):
                            mapped_open_interests.append(open_interests[closest_idx])
                        else:
                            mapped_open_interests.append(0)

                    symbol_data["open_interest"] = mapped_open_interests
                else:
                    symbol_data["open_interest"] = [0] * len(timestamps)

                # 获取当前资金费率和持仓量
                funding_rate = get_funding_rate(symbol)
                open_interest = get_open_interest(symbol)

                if funding_rate is not None:
                    symbol_data["last_funding_rate"] = funding_rate
                    if symbol_data["funding_rates"]:
                        symbol_data["funding_rates"][-1] = funding_rate * 100

                if open_interest is not None and symbol_data["open_interest"]:
                    symbol_data["open_interest"][-1] = open_interest

                symbol_data["historical_data_loaded"] = True
                return True

            return False
    return True

def get_ai_analysis(spot_price2, futures_price2, premium2, funding_rate2, open_interest2):
    """获取AI分析结果"""
    try:
        prompt = f"""
        作为一位专业的期货交易分析师，请基于以下持仓数据变化及图表变化提供详细的市场分析报告：

        当前数据：
        - 现货价格：{spot_price2}
        - 期货价格：{futures_price2}
        - 期现溢价：{premium2}
        - 资金费率：{funding_rate2}
        - 持仓量：{open_interest2}

        请提供以下分析（使用markdown格式）：

        ## 后续价格走势
        [分析后续价格预判]

        ## 交易机会分析
        - 潜在趋势机会：
        - 风险提示：

        请从专业交易员的角度进行分析，注重实用性和操作性。
        """

        # 设置超时时间，避免长时间等待
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=10  # 10秒超时
        )
        return response.choices[0].message.content
    except requests.exceptions.RequestException as e:
        # 处理网络连接错误
        st.warning("AI服务连接失败，显示本地分析结果")
        return generate_local_analysis(spot_price2, futures_price2, premium2, funding_rate2, open_interest2)
    except Exception as e:
        # 处理其他错误
        st.warning("AI分析生成失败，显示本地分析结果")
        return generate_local_analysis(spot_price2, futures_price2, premium2, funding_rate2, open_interest2)

def generate_local_analysis(spot_price, futures_price, premium, funding_rate, open_interest):
    """生成本地分析结果，当AI服务不可用时使用"""
    # 格式化数据
    spot_price_formatted = format_price(spot_price)
    futures_price_formatted = format_price(futures_price)
    premium_formatted = format_price(premium)
    funding_rate_formatted = format_price(funding_rate)
    open_interest_formatted = format_price(open_interest)
    
    # 分析资金费率
    funding_analysis = ""
    if funding_rate > 0.01:
        funding_analysis = "当前资金费率为正且较高，表明市场看多情绪强烈，但需警惕可能的回调风险。"
    elif funding_rate > 0:
        funding_analysis = "当前资金费率为正，表明市场整体偏多，但情绪不算极端。"
    elif funding_rate < -0.01:
        funding_analysis = "当前资金费率为负且绝对值较大，表明市场看空情绪强烈，但需警惕可能的反弹机会。"
    elif funding_rate < 0:
        funding_analysis = "当前资金费率为负，表明市场整体偏空，但情绪不算极端。"
    else:
        funding_analysis = "当前资金费率接近零，表明市场多空情绪平衡。"
    
    # 分析期现溢价
    premium_analysis = ""
    if premium > 0.01:
        premium_analysis = "期现溢价较高，表明期货市场看多情绪强烈，但需警惕可能的回调风险。"
    elif premium > 0:
        premium_analysis = "期现溢价为正，表明期货市场整体偏多，但情绪不算极端。"
    elif premium < -0.01:
        premium_analysis = "期现溢价为负且绝对值较大，表明期货市场看空情绪强烈，但需警惕可能的反弹机会。"
    elif premium < 0:
        premium_analysis = "期现溢价为负，表明期货市场整体偏空，但情绪不算极端。"
    else:
        premium_analysis = "期现溢价接近零，表明期货市场多空情绪平衡。"
    
    # 生成分析报告
    analysis = f"""
## 后续价格走势
基于当前数据，现货价格为 {spot_price_formatted}，期货价格为 {futures_price_formatted}。
{premium_analysis}
{funding_analysis}

持仓量为 {open_interest_formatted}，{'持仓量较大，表明市场参与度高' if open_interest > 1000000 else '持仓量适中，市场参与度一般'}。

## 交易机会分析
- 潜在趋势机会：
  - 如果资金费率和期现溢价同向，可考虑跟随趋势
  - 如果资金费率和期现溢价反向，可考虑反向操作
  - 关注持仓量变化，持仓量增加通常意味着趋势延续

- 风险提示：
  - 极端资金费率可能导致价格反转
  - 高期现溢价可能预示回调风险
  - 持仓量突然减少可能预示趋势转折
"""
    return analysis

# 侧边栏控件
with st.sidebar:
    st.markdown("<h1 style='text-align: center; color: #ffffff;'>⚔️ 合约费率战法监控系统</h1>", unsafe_allow_html=True)
    st.title("🛰️监控设置")

    # 交易对1和交易对2输入框并排显示
    col1, col2 = st.columns(2)

    with col1:
        new_symbol1 = st.text_input(
            "交易对1",
            value=st.session_state.symbol1,
            placeholder="例如: FUNUSDT",
            key="symbol1_input",
            label_visibility="collapsed"
        )

    with col2:
        new_symbol2 = st.text_input(
            "交易对2",
            value=st.session_state.symbol2,
            placeholder="例如: AUCTIONUSDT",
            key="symbol2_input",
            label_visibility="collapsed"
        )

    # 处理交易对1变更
    if new_symbol1 != st.session_state.symbol1:
        st.session_state.symbol1 = new_symbol1
        st.session_state.symbol1_data = {
            "timestamps": [],
            "spot_prices": [],
            "futures_prices": [],
            "premiums": [],
            "funding_rates": [],
            "open_interest": [],
            "last_funding_rate": None,
            "historical_data_loaded": False,
            "charts": [None, None, None],
            "running": False
        }
        st.rerun()

    # 处理交易对2变更
    if new_symbol2 != st.session_state.symbol2:
        st.session_state.symbol2 = new_symbol2
        st.session_state.symbol2_data = {
            "timestamps": [],
            "spot_prices": [],
            "futures_prices": [],
            "premiums": [],
            "funding_rates": [],
            "open_interest": [],
            "last_funding_rate": None,
            "historical_data_loaded": False,
            "charts": [None, None, None],
            "running": False
        }
        st.rerun()

    # 交易对1和交易对2控制按钮并排显示
    col1, col2 = st.columns(2)

    with col1:
        if st.button('1️⃣停止监控' if st.session_state.symbol1_data["running"] else '1️⃣开始监控',
                     key="toggle_symbol1"):
            st.session_state.symbol1_data["running"] = not st.session_state.symbol1_data["running"]
            if st.session_state.symbol1_data["running"]:
                success = load_historical_data(st.session_state.symbol1, st.session_state.symbol1_data)
                if not success:
                    st.error(f"无法加载 {st.session_state.symbol1} 历史数据，请检查交易对是否正确")
                    st.session_state.symbol1_data["running"] = False
            st.rerun()

    with col2:
        if st.button('2️⃣停止监控' if st.session_state.symbol2_data["running"] else '2️⃣开始监控',
                     key="toggle_symbol2"):
            st.session_state.symbol2_data["running"] = not st.session_state.symbol2_data["running"]
            if st.session_state.symbol2_data["running"]:
                success = load_historical_data(st.session_state.symbol2, st.session_state.symbol2_data)
                if not success:
                    st.error(f"无法加载 {st.session_state.symbol2} 历史数据，请检查交易对是否正确")
                    st.session_state.symbol2_data["running"] = False
            st.rerun()

    # 统计数据部分
    st.markdown("---")
    st.subheader("📊 统计数据")
    stats_placeholder = st.empty()  # 创建占位符用于动态更新统计数据

    # 初次加载统计数据并显示
    if st.session_state.stats_data is None:
        load_stats_data()
    with stats_placeholder.container():
        if st.session_state.stats_data:
            data = st.session_state.stats_data
            timestamp = data.get("timestamp", "未知")

            col1, col2 = st.columns(2)
            with col1:
                st.write("😱 **费率最高的交易对**")
                if "highest_rates" in data and data["highest_rates"]:
                    df_highest = pd.DataFrame([
                        {"交易对": f"🟢 {item.get('symbol', '')}",
                         "费率": f"{item.get('rate', 0) * 100:.2f}%"}
                        for item in data["highest_rates"]
                    ])
                    st.dataframe(df_highest, hide_index=True)
                else:
                    st.write("暂无数据")

            with col2:
                st.write("😍 **费率最低的交易对**")
                if "lowest_rates" in data and data["lowest_rates"]:
                    df_lowest = pd.DataFrame([
                        {"交易对": f"🔴 {item.get('symbol', '')}",
                         "费率": f"{item.get('rate', 0) * 100:.2f}%"}
                        for item in data["lowest_rates"]
                    ])
                    st.dataframe(df_lowest, hide_index=True)
                else:
                    st.write("暂无数据")

            col3, col4 = st.columns(2)
            with col3:
                st.write("⬆️ **费率上升最快**")
                if "biggest_increases" in data and data["biggest_increases"]:
                    df_increases = pd.DataFrame([
                        {"交易对": item.get("symbol", ""),
                         "变化": f"{item.get('change', 0) * 100:.4f}%"}
                        for item in data["biggest_increases"]
                    ])
                    st.dataframe(df_increases, hide_index=True)
                else:
                    st.write("暂无数据")

            with col4:
                st.write("⬇️ **费率下降最快**")
                if "biggest_decreases" in data and data["biggest_decreases"]:
                    df_decreases = pd.DataFrame([
                        {"交易对": item.get("symbol", ""),
                         "变化": f"{item.get('change', 0) * 100:.4f}%"}
                        for item in data["biggest_decreases"]
                    ])
                    st.dataframe(df_decreases, hide_index=True)
                else:
                    st.write("暂无数据")

            st.caption(f"更新时间: {timestamp}")
        else:
            st.error("未能加载数据，请检查文件或API连接")


# 创建固定容器 - 显示最新数据
title_placeholder1 = st.empty()  # 为标题创建占位符
metrics_placeholder1 = st.empty()  # 为指标创建占位符
symbol1_container = st.container()

title_placeholder2 = st.empty()  # 为标题创建占位符
metrics_placeholder2 = st.empty()  # 为指标创建占位符
symbol2_container = st.container()

# 创建图表占位符
with symbol1_container:
    # 创建图表布局
    chart_col1_1, chart_col1_2, chart_col1_3 = st.columns(3)

    with chart_col1_1:
        chart1_premium = st.empty()
    with chart_col1_2:
        chart1_funding = st.empty()
    with chart_col1_3:
        chart1_oi = st.empty()

with symbol2_container:
    # 创建图表布局
    chart_col2_1, chart_col2_2, chart_col2_3 = st.columns(3)

    with chart_col2_1:
        chart2_premium = st.empty()
    with chart_col2_2:
        chart2_funding = st.empty()
    with chart_col2_3:
        chart2_oi = st.empty()

# 主循环
last_stats_refresh = time.time()

while True:
    current_time = time.time()

    # 检查是否需要更新统计数据（每60秒更新一次）
    if current_time - last_stats_refresh > 60:
        load_stats_data()  # 更新统计数据
        last_stats_refresh = current_time

        # 动态更新统计数据
        with stats_placeholder.container():
            if st.session_state.stats_data:
                data = st.session_state.stats_data
                timestamp = data.get("timestamp", "未知")

                col1, col2 = st.columns(2)
                with col1:
                    st.write("😱 **费率最高的交易对**")
                    if "highest_rates" in data and data["highest_rates"]:
                        df_highest = pd.DataFrame([
                            {"交易对": f"🟢 {item.get('symbol', '')}",
                             "费率": f"{item.get('rate', 0) * 100:.2f}%"}
                            for item in data["highest_rates"]
                        ])
                        st.dataframe(df_highest, hide_index=True)
                    else:
                        st.write("暂无数据")

                with col2:
                    st.write("😍 **费率最低的交易对**")
                    if "lowest_rates" in data and data["lowest_rates"]:
                        df_lowest = pd.DataFrame([
                            {"交易对": f"🔴 {item.get('symbol', '')}",
                             "费率": f"{item.get('rate', 0) * 100:.2f}%"}
                            for item in data["lowest_rates"]
                        ])
                        st.dataframe(df_lowest, hide_index=True)
                    else:
                        st.write("暂无数据")

                col3, col4 = st.columns(2)
                with col3:
                    st.write("⬆️ **费率上升最快**")
                    if "biggest_increases" in data and data["biggest_increases"]:
                        df_increases = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "变化": f"{item.get('change', 0) * 100:.4f}%"}
                            for item in data["biggest_increases"]
                        ])
                        st.dataframe(df_increases, hide_index=True)
                    else:
                        st.write("暂无数据")

                with col4:
                    st.write("⬇️ **费率下降最快**")
                    if "biggest_decreases" in data and data["biggest_decreases"]:
                        df_decreases = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "变化": f"{item.get('change', 0) * 100:.4f}%"}
                            for item in data["biggest_decreases"]
                        ])
                        st.dataframe(df_decreases, hide_index=True)
                    else:
                        st.write("暂无数据")

                st.caption(f"更新时间: {timestamp}")
            else:
                st.error("未能加载数据，请检查文件或API连接")

    # 获取UTC时间并格式化
    current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 更新交易对1数据（如果正在运行）
    if st.session_state.symbol1_data["running"]:
        if not st.session_state.symbol1_data["historical_data_loaded"]:
            success = load_historical_data(st.session_state.symbol1, st.session_state.symbol1_data)
            if not success:
                st.error(f"无法加载 {st.session_state.symbol1} 历史数据，请检查交易对是否正确")
                st.session_state.symbol1_data["running"] = False
                st.rerun()

        spot_price1, futures_price1, premium1, funding_rate1, open_interest1 = update_data(
            st.session_state.symbol1, st.session_state.symbol1_data
        )

        if spot_price1 is not None and futures_price1 is not None:
            title_placeholder1.markdown(f"### 1️⃣ {st.session_state.symbol1} 当前数据 - ({current_time_str})")
            with metrics_placeholder1.container():
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric(label="现货价格", value=format_price(spot_price1))
                col2.metric(label="期货价格", value=format_price(futures_price1))
                premium_indicator = "🟢" if premium1 > 0 else "🔴"
                col3.metric(label="期现溢价", value=f"{premium_indicator} {premium1:.2f}%")
                funding_indicator = "🟢" if funding_rate1 > 0 else "🔴"
                col4.metric(label="资金费率", value=f"{funding_indicator} {funding_rate1 * 100:.2f}%")
                col5.metric(label="持仓量", value=f"{open_interest1:,.0f}")

        premium_fig1 = create_premium_chart(st.session_state.symbol1, st.session_state.symbol1_data)
        funding_fig1 = create_funding_rate_chart(st.session_state.symbol1, st.session_state.symbol1_data)
        open_interest_fig1 = create_open_interest_chart(st.session_state.symbol1, st.session_state.symbol1_data)

        if premium_fig1:
            chart1_premium.plotly_chart(premium_fig1, use_container_width=True)
        if funding_fig1:
            chart1_funding.plotly_chart(funding_fig1, use_container_width=True)
        if open_interest_fig1:
            chart1_oi.plotly_chart(open_interest_fig1, use_container_width=True)


    # 更新交易对2数据（如果正在运行）
    if st.session_state.symbol2_data["running"]:
        if not st.session_state.symbol2_data["historical_data_loaded"]:
            success = load_historical_data(st.session_state.symbol2, st.session_state.symbol2_data)
            if not success:
                st.error(f"无法加载 {st.session_state.symbol2} 历史数据，请检查交易对是否正确")
                st.session_state.symbol2_data["running"] = False
                st.rerun()

        spot_price2, futures_price2, premium2, funding_rate2, open_interest2 = update_data(
            st.session_state.symbol2, st.session_state.symbol2_data
        )

        if spot_price2 is not None and futures_price2 is not None:
            title_placeholder2.markdown(f"### 2️⃣ {st.session_state.symbol2} 当前数据 - ({current_time_str})")
            with metrics_placeholder2.container():
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric(label="现货价格", value=format_price(spot_price2))
                col2.metric(label="期货价格", value=format_price(futures_price2))
                premium_indicator = "🟢" if premium2 > 0 else "🔴"
                col3.metric(label="期现溢价", value=f"{premium_indicator} {premium2:.2f}%")
                funding_indicator = "🟢" if funding_rate2 > 0 else "🔴"
                col4.metric(label="资金费率", value=f"{funding_indicator} {funding_rate2 * 100:.2f}%")
                col5.metric(label="持仓量", value=f"{open_interest2:,.0f}")

        premium_fig2 = create_premium_chart(st.session_state.symbol2, st.session_state.symbol2_data)
        funding_fig2 = create_funding_rate_chart(st.session_state.symbol2, st.session_state.symbol2_data)
        open_interest_fig2 = create_open_interest_chart(st.session_state.symbol2, st.session_state.symbol2_data)

        if premium_fig2:
            chart2_premium.plotly_chart(premium_fig2, use_container_width=True)
        if funding_fig2:
            chart2_funding.plotly_chart(funding_fig2, use_container_width=True)
        if open_interest_fig2:
            chart2_oi.plotly_chart(open_interest_fig2, use_container_width=True)

    # 检查是否需要更新AI分析（每30分钟更新一次）
    # should_update_ai = False
    # if st.session_state.last_ai_analysis_time is None:
    #     should_update_ai = True
    # elif current_time - st.session_state.last_ai_analysis_time > AI_ANALYSIS_INTERVAL:
    #     should_update_ai = True
    
    # # 如果需要进行AI分析
    # if should_update_ai:
    #     # 确定要分析的交易对
    #     analysis_symbol = None
    #     analysis_data = None
        
    #     if st.session_state.symbol1_data["running"] and spot_price1 is not None:
    #         analysis_symbol = st.session_state.symbol1
    #         analysis_data = (spot_price1, futures_price1, premium1, funding_rate1, open_interest1)
    #     elif st.session_state.symbol2_data["running"] and spot_price2 is not None:
    #         analysis_symbol = st.session_state.symbol2
    #         analysis_data = (spot_price2, futures_price2, premium2, funding_rate2, open_interest2)
        
        # 如果有可分析的交易对，则进行AI分析
        # if analysis_symbol and analysis_data:
        #     with st.spinner(f"正在为 {analysis_symbol} 生成AI分析..."):
        #         analysis = get_ai_analysis(*analysis_data)
        #         st.session_state.ai_analysis_result = analysis
        #         st.session_state.ai_analysis_symbol = analysis_symbol
        #         st.session_state.last_ai_analysis_time = current_time
        #         st.rerun()  # 重新运行应用以更新UI

    # 显示AI分析结果
    # st.subheader("🤖 AI 分析")
    # if st.session_state.ai_analysis_result:
    #     st.markdown(f"**分析交易对: {st.session_state.ai_analysis_symbol}**")
    #     st.markdown(st.session_state.ai_analysis_result)
    #     if st.session_state.last_ai_analysis_time:
    #         last_analysis_time = datetime.fromtimestamp(st.session_state.last_ai_analysis_time).strftime("%Y-%m-%d %H:%M:%S")
    #         st.caption(f"上次分析时间: {last_analysis_time}")
    #         next_analysis_time = datetime.fromtimestamp(st.session_state.last_ai_analysis_time + AI_ANALYSIS_INTERVAL).strftime("%Y-%m-%d %H:%M:%S")
    #         st.caption(f"下次分析时间: {next_analysis_time}")
    # else:
    #     st.info("等待数据收集完成，将自动生成AI分析...")

    # 暂停一段时间再更新
    time.sleep(UPDATE_INTERVAL)