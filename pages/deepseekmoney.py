import requests
import pandas as pd
from datetime import datetime, timedelta
import time
import concurrent.futures
import json
import streamlit as st
import plotly.graph_objects as go
import os

# Binance API 端点
SPOT_BASE_URL = "https://api.binance.com/api/v3"
FUTURES_BASE_URL = "https://fapi.binance.com/fapi/v1"

# DeepSeek API 配置（假设使用官方API，需替换为你的API Key）
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = "sk-678e106a83314b3fb2db62689c224399"  # 请替换为实际的API Key

# 稳定币列表（美元稳定币和欧元稳定币）
STABLECOINS = {'USDC', 'TUSD', 'BUSD', 'DAI', 'USDP', 'EUR', 'GYEN'}

def get_all_usdt_symbols(is_futures=False):
    """获取所有以USDT结尾的交易对，剔除稳定币对"""
    base_url = FUTURES_BASE_URL if is_futures else SPOT_BASE_URL
    endpoint = "/exchangeInfo"

    response = requests.get(f"{base_url}{endpoint}")
    data = response.json()

    symbols = []
    if is_futures:
        for item in data['symbols']:
            symbol = item['symbol']
            base_asset = item['baseAsset']
            if (item['status'] == 'TRADING' and
                item['quoteAsset'] == 'USDT' and
                base_asset not in STABLECOINS):
                symbols.append(symbol)
    else:
        for item in data['symbols']:
            symbol = item['symbol']
            base_asset = item['baseAsset']
            if (item['status'] == 'TRADING' and
                item['quoteAsset'] == 'USDT' and
                base_asset not in STABLECOINS):
                symbols.append(symbol)
    return symbols

def format_number(value):
    """将数值格式化为K/M表示，保留两位小数"""
    if abs(value) >= 1000000:
        return f"{value / 1000000:.2f}M"
    elif abs(value) >= 1000:
        return f"{value / 1000:.2f}K"
    else:
        return f"{value:.2f}"

def get_klines_parallel(symbols, is_futures=False, max_workers=20):
    """使用线程池并行获取多个交易对的K线数据（使用倒数第二根已完成的日线蜡烛图）"""
    results = []

    def fetch_kline(symbol):
        try:
            base_url = FUTURES_BASE_URL if is_futures else SPOT_BASE_URL
            endpoint = "/klines"

            now = datetime.utcnow()
            today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
            end_time = int(today_start.timestamp() * 1000)
            start_time = int((today_start - timedelta(days=2)).timestamp() * 1000)

            params = {
                'symbol': symbol,
                'interval': '4h',
                'startTime': start_time,
                'endTime': end_time,
                'limit': 2
            }

            response = requests.get(f"{base_url}{endpoint}", params=params)
            data = response.json()

            if not data or len(data) < 2:
                print(f"Insufficient data for {symbol}: {len(data)} candles returned")
                return None

            k = data[1]  # 使用倒数第一根已完成K线
            open_time = datetime.fromtimestamp(k[0] / 1000).strftime('%Y-%m-%d %H:%M:%S')
            close_time = datetime.fromtimestamp(k[6] / 1000).strftime('%Y-%m-%d %H:%M:%S')

            return {
                'symbol': symbol,
                'open_time': open_time,
                'close_time': close_time,
                'open': float(k[1]),
                'high': float(k[2]),
                'low': float(k[3]),
                'close': float(k[4]),
                'volume': float(k[5]),
                'quote_volume': float(k[7]),
                'trades': int(k[8]),
                'taker_buy_base_volume': float(k[9]),
                'taker_buy_quote_volume': float(k[10]),
                'net_inflow': 2 * float(k[10]) - float(k[7])
            }
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_kline, symbol): symbol for symbol in symbols}
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    return results

def send_to_deepseek(data):
    """将数据发送给DeepSeek API并获取解读"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = (
        "以下是Binance现货和期货市场中USDT交易对的资金流入流出数据（基于前一天的已完成日线数据），请分析：\n"
        "1. 期货和现货市场中出现的相同交易对及其流入流出情况。\n"
        "2. 从资金流角度解读这些数据，可能的市场趋势或交易信号。\n"
        "3. 提供专业的资金分析视角，例如大资金动向、潜在的市场操纵迹象等。\n"
        "数据如下：\n" + json.dumps(data, indent=2, ensure_ascii=False) +
        "\n请以中文回复，尽量简洁但专业。"
    )

    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1000,
        "temperature": 0.7
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"DeepSeek API error: {e}")
        return "无法获取DeepSeek分析结果"

def run_analysis():
    """执行分析并返回结果"""
    # 获取所有USDT交易对（剔除稳定币）
    spot_symbols = get_all_usdt_symbols(is_futures=False)
    futures_symbols = get_all_usdt_symbols(is_futures=True)

    # 使用线程池并行获取数据
    spot_data = get_klines_parallel(spot_symbols, is_futures=False, max_workers=20)
    futures_data = get_klines_parallel(futures_symbols, is_futures=True, max_workers=20)

    # 转换为DataFrame并排序
    spot_df = pd.DataFrame(spot_data)
    futures_df = pd.DataFrame(futures_data)

    # 提取Top 20数据
    spot_inflow_top20 = spot_df.sort_values(by='net_inflow', ascending=False).head(20)
    futures_inflow_top20 = futures_df.sort_values(by='net_inflow', ascending=False).head(20)
    spot_outflow_top20 = spot_df.sort_values(by='net_inflow', ascending=True).head(20)
    futures_outflow_top20 = futures_df.sort_values(by='net_inflow', ascending=True).head(20)

    # 准备发送给DeepSeek的数据
    deepseek_data = {
        "spot_inflow_top20": spot_inflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records'),
        "futures_inflow_top20": futures_inflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records'),
        "spot_outflow_top20": spot_outflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records'),
        "futures_outflow_top20": futures_outflow_top20[['symbol', 'net_inflow', 'quote_volume']].to_dict('records')
    }

    # 发送给DeepSeek并获取分析
    analysis = send_to_deepseek(deepseek_data)
    
    # 返回所有结果
    return {
        "spot_inflow_top20": spot_inflow_top20,
        "futures_inflow_top20": futures_inflow_top20,
        "spot_outflow_top20": spot_outflow_top20,
        "futures_outflow_top20": futures_outflow_top20,
        "analysis": analysis,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

def main():
    # 设置页面配置
    st.set_page_config(
        page_title="资金流向分析",
        page_icon="💰",
        layout="wide"
    )
    
    st.title("💰 资金流向分析")
    st.markdown("分析币安现货和期货市场的资金流向，识别潜在交易机会")
    
    # 添加刷新按钮
    if st.button("🔄 刷新数据"):
        with st.spinner("正在获取最新数据..."):
            results = run_analysis()
            
            # 保存结果到JSON文件
            with open("money_flow_analysis.json", "w") as f:
                json.dump({
                    "spot_inflow_top20": results["spot_inflow_top20"].to_dict('records'),
                    "futures_inflow_top20": results["futures_inflow_top20"].to_dict('records'),
                    "spot_outflow_top20": results["spot_outflow_top20"].to_dict('records'),
                    "futures_outflow_top20": results["futures_outflow_top20"].to_dict('records'),
                    "analysis": results["analysis"],
                    "timestamp": results["timestamp"]
                }, f, indent=4, ensure_ascii=False)
            
            st.success("数据已更新!")
            st.rerun()
    
    # 添加自动刷新选项
    auto_refresh = st.checkbox("自动刷新 (每5分钟)", value=True)
    
    # 读取并显示统计数据
    try:
        if os.path.exists("money_flow_analysis.json"):
            with open("money_flow_analysis.json", "r") as f:
                data = json.load(f)
                
                # 显示最后更新时间
                timestamp = data.get("timestamp", "未知")
                st.caption(f"最后更新时间: {timestamp}")
                
                # 显示DeepSeek分析结果
                st.subheader("🤖 DeepSeek 分析")
                st.markdown(data.get("analysis", "暂无分析结果"))
                
                # 创建两列布局
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🟢 现货市场净流入TOP20")
                    if "spot_inflow_top20" in data and data["spot_inflow_top20"]:
                        df_spot_inflow = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "净流入": f"{format_number(item.get('net_inflow', 0))} USDT",
                             "成交额": f"{format_number(item.get('quote_volume', 0))} USDT"}
                            for item in data["spot_inflow_top20"]
                        ])
                        st.dataframe(df_spot_inflow, hide_index=True)
                        
                        
                    else:
                        st.write("暂无数据")
                
                with col2:
                    st.subheader("🔴 现货市场净流出TOP20")
                    if "spot_outflow_top20" in data and data["spot_outflow_top20"]:
                        df_spot_outflow = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "净流出": f"{format_number(item.get('net_inflow', 0))} USDT",
                             "成交额": f"{format_number(item.get('quote_volume', 0))} USDT"}
                            for item in data["spot_outflow_top20"]
                        ])
                        st.dataframe(df_spot_outflow, hide_index=True)
                        
                        
                    else:
                        st.write("暂无数据")
                
                # 创建两列布局显示期货市场数据
                col3, col4 = st.columns(2)
                
                with col3:
                    st.subheader("🟢 期货市场净流入TOP20")
                    if "futures_inflow_top20" in data and data["futures_inflow_top20"]:
                        df_futures_inflow = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "净流入": f"{format_number(item.get('net_inflow', 0))} USDT",
                             "成交额": f"{format_number(item.get('quote_volume', 0))} USDT"}
                            for item in data["futures_inflow_top20"]
                        ])
                        st.dataframe(df_futures_inflow, hide_index=True)
                        
                        
                    else:
                        st.write("暂无数据")
                
                with col4:
                    st.subheader("🔴 期货市场净流出TOP20")
                    if "futures_outflow_top20" in data and data["futures_outflow_top20"]:
                        df_futures_outflow = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "净流出": f"{format_number(item.get('net_inflow', 0))} USDT",
                             "成交额": f"{format_number(item.get('quote_volume', 0))} USDT"}
                            for item in data["futures_outflow_top20"]
                        ])
                        st.dataframe(df_futures_outflow, hide_index=True)
                        
                        
                    else:
                        st.write("暂无数据")
        else:
            st.warning("未找到数据文件，请点击刷新按钮获取数据")
            
            # 如果没有数据，运行一次任务
            if st.button("获取数据"):
                with st.spinner("正在获取数据..."):
                    results = run_analysis()
                    
                    # 保存结果到JSON文件
                    with open("money_flow_analysis.json", "w") as f:
                        json.dump({
                            "spot_inflow_top20": results["spot_inflow_top20"].to_dict('records'),
                            "futures_inflow_top20": results["futures_inflow_top20"].to_dict('records'),
                            "spot_outflow_top20": results["spot_outflow_top20"].to_dict('records'),
                            "futures_outflow_top20": results["futures_outflow_top20"].to_dict('records'),
                            "analysis": results["analysis"],
                            "timestamp": results["timestamp"]
                        }, f, indent=4, ensure_ascii=False)
                    
                    st.success("数据已获取!")
                    st.rerun()
    
    except Exception as e:
        st.error(f"读取数据时出错: {e}")
    
    # 如果启用了自动刷新，设置定时刷新
    if auto_refresh:
        st.caption("页面将在5分钟后自动刷新")
        time.sleep(300)  # 等待5分钟
        st.rerun()

if __name__ == "__main__":
    main()
