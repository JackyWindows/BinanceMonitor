import requests
import json
import time
import os
from datetime import datetime
import schedule
from typing import Dict, List, Tuple, Optional
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class BinanceFundingRateTracker:
    def __init__(self, data_file="funding_rates_stats.json"):
        self.data_file = data_file
        self.previous_rates = {}  # 用于缓存上一次的费率
        self.current_rates = {}  # 当前费率

        # 如果文件存在，加载之前的数据
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    if 'previous_rates' in data:
                        self.previous_rates = data['previous_rates']
            except Exception as e:
                print(f"Error loading previous data: {e}")

    def get_usdt_perpetual_symbols(self) -> List[str]:
        """获取所有USDT结尾的永续合约交易对"""
        try:
            response = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo")
            data = response.json()

            usdt_symbols = []
            for symbol_info in data['symbols']:
                if symbol_info['symbol'].endswith('USDT') and symbol_info['status'] == 'TRADING' and symbol_info[
                    'contractType'] == 'PERPETUAL':
                    usdt_symbols.append(symbol_info['symbol'])

            return usdt_symbols
        except Exception as e:
            print(f"Error fetching symbols: {e}")
            return []

    def get_funding_rates(self) -> Dict[str, float]:
        """获取所有USDT交易对的资金费率"""
        try:
            response = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex")
            data = response.json()

            funding_rates = {}
            for item in data:
                symbol = item['symbol']
                if symbol.endswith('USDT'):
                    funding_rate = float(item['lastFundingRate'])
                    funding_rates[symbol] = funding_rate

            return funding_rates
        except Exception as e:
            print(f"Error fetching funding rates: {e}")
            return {}

    def get_top_n(self, rates: Dict[str, float], n: int, reverse: bool = True) -> List[Tuple[str, float]]:
        """获取费率最高/最低的n个交易对"""
        sorted_rates = sorted(rates.items(), key=lambda x: x[1], reverse=reverse)
        return sorted_rates[:n]

    def get_biggest_changes(self, current: Dict[str, float], previous: Dict[str, float], n: int,
                            increasing: bool = True) -> List[Tuple[str, float]]:
        """获取费率变化最大的n个交易对"""
        changes = {}
        for symbol, rate in current.items():
            if symbol in previous:
                change = rate - previous[symbol]
                if (increasing and change > 0) or (not increasing and change < 0):
                    changes[symbol] = change

        sorted_changes = sorted(changes.items(), key=lambda x: x[1], reverse=increasing)
        return sorted_changes[:n]

    def run_task(self):
        """执行主要任务"""
        print(f"Running task at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 获取当前所有USDT交易对的资金费率
        self.current_rates = self.get_funding_rates()

        if not self.current_rates:
            print("Failed to get funding rates, skipping this run")
            return

        # 统计1: 费率最高的5个symbol
        highest_rates = self.get_top_n(self.current_rates, 5, reverse=True)

        # 统计2: 费率最低的5个symbol
        lowest_rates = self.get_top_n(self.current_rates, 5, reverse=False)

        # 统计3 & 4: 费率变化最大的交易对
        increasing_rates = []
        decreasing_rates = []

        if self.previous_rates:
            # 统计3: 费率上升最大的5个symbol
            increasing_rates = self.get_biggest_changes(self.current_rates, self.previous_rates, 5, increasing=True)

            # 统计4: 费率下降最大的5个symbol
            decreasing_rates = self.get_biggest_changes(self.current_rates, self.previous_rates, 5, increasing=False)

        # 准备保存的数据
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        stats = {
            "timestamp": timestamp,
            "highest_rates": [{"symbol": s, "rate": r} for s, r in highest_rates],
            "lowest_rates": [{"symbol": s, "rate": r} for s, r in lowest_rates],
            "biggest_increases": [{"symbol": s, "change": c} for s, c in increasing_rates],
            "biggest_decreases": [{"symbol": s, "change": c} for s, c in decreasing_rates],
            "previous_rates": self.current_rates  # 保存当前费率作为下次比较的基准
        }

        # 保存到JSON文件
        try:
            with open(self.data_file, 'w') as f:
                json.dump(stats, f, indent=4)
            print(f"Data saved to {self.data_file}")
        except Exception as e:
            print(f"Error saving data: {e}")

        # 更新previous_rates为当前rates，以便下次比较
        self.previous_rates = self.current_rates.copy()

        # 打印结果
        print("\n===== Funding Rate Statistics =====")
        print("\nHighest Funding Rates:")
        for symbol, rate in highest_rates:
            print(f"{symbol}: {rate:.6f}")

        print("\nLowest Funding Rates:")
        for symbol, rate in lowest_rates:
            print(f"{symbol}: {rate:.6f}")

        if increasing_rates:
            print("\nBiggest Increases:")
            for symbol, change in increasing_rates:
                print(f"{symbol}: +{change:.6f}")

        if decreasing_rates:
            print("\nBiggest Decreases:")
            for symbol, change in decreasing_rates:
                print(f"{symbol}: {change:.6f}")

        print("\n================================\n")
        
        # 返回统计数据，以便在Streamlit中显示
        return stats


def main():
    # 设置页面配置
    st.set_page_config(
        page_title="资金费率监控",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 资金费率监控")
    st.markdown("监控币安永续合约的资金费率变化，帮助识别潜在交易机会")
    
    # 创建跟踪器实例
    tracker = BinanceFundingRateTracker()
    
    # 添加刷新按钮
    if st.button("🔄 刷新数据"):
        with st.spinner("正在获取最新数据..."):
            stats = tracker.run_task()
            st.success("数据已更新!")
            st.rerun()
    
    # 添加自动刷新选项
    auto_refresh = st.checkbox("自动刷新 (每5分钟)", value=True)
    
    # 读取并显示统计数据
    try:
        if os.path.exists(tracker.data_file):
            with open(tracker.data_file, 'r') as f:
                data = json.load(f)
                
                # 显示最后更新时间
                timestamp = data.get("timestamp", "未知")
                st.caption(f"最后更新时间: {timestamp}")
                
                # 创建两列布局
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("🟢 费率最高的交易对")
                    if "highest_rates" in data and data["highest_rates"]:
                        df_highest = pd.DataFrame([
                            {"交易对": f"🟢 {item.get('symbol', '')}",
                             "费率": f"{item.get('rate', 0) * 100:.4f}%"}
                            for item in data["highest_rates"]
                        ])
                        st.dataframe(df_highest, hide_index=True)
                        
                        # 创建柱状图
                        #fig_highest = go.Figure(data=[
                        #    go.Bar(
                        #        x=[item.get('symbol', '') for item in data["highest_rates"]],
                        #        y=[item.get('rate', 0) * 100 for item in data["highest_rates"]],
                        #        marker_color='green',
                        #        text=[f"{item.get('rate', 0) * 100:.4f}%" for item in data["highest_rates"]],
                        #        textposition='auto',
                        #    )
                        #])
                        #fig_highest.update_layout(
                        #    title="最高资金费率",
                        #    xaxis_title="交易对",
                        #    yaxis_title="资金费率 (%)",
                        #    height=400
                        #)
                        #st.plotly_chart(fig_highest, use_container_width=True)
                    else:
                        st.write("暂无数据")
                
                with col2:
                    st.subheader("🔴 费率最低的交易对")
                    if "lowest_rates" in data and data["lowest_rates"]:
                        df_lowest = pd.DataFrame([
                            {"交易对": f"🔴 {item.get('symbol', '')}",
                             "费率": f"{item.get('rate', 0) * 100:.4f}%"}
                            for item in data["lowest_rates"]
                        ])
                        st.dataframe(df_lowest, hide_index=True)
                        
                        # 创建柱状图
                        # fig_lowest = go.Figure(data=[
                        #     go.Bar(
                        #         x=[item.get('symbol', '') for item in data["lowest_rates"]],
                        #         y=[item.get('rate', 0) * 100 for item in data["lowest_rates"]],
                        #         marker_color='red',
                        #         text=[f"{item.get('rate', 0) * 100:.4f}%" for item in data["lowest_rates"]],
                        #         textposition='auto',
                        #     )
                        # ])
                        # fig_lowest.update_layout(
                        #     title="最低资金费率",
                        #     xaxis_title="交易对",
                        #     yaxis_title="资金费率 (%)",
                        #     height=400
                        # )
                        # st.plotly_chart(fig_lowest, use_container_width=True)
                    else:
                        st.write("暂无数据")
                
                # 创建两列布局显示变化最大的交易对
                col3, col4 = st.columns(2)
                
                with col3:
                    st.subheader("⬆️ 费率上升最快")
                    if "biggest_increases" in data and data["biggest_increases"]:
                        df_increases = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "变化": f"+{item.get('change', 0) * 100:.4f}%"}
                            for item in data["biggest_increases"]
                        ])
                        st.dataframe(df_increases, hide_index=True)
                        
                        # 创建柱状图
                        # fig_increases = go.Figure(data=[
                        #     go.Bar(
                        #         x=[item.get('symbol', '') for item in data["biggest_increases"]],
                        #         y=[item.get('change', 0) * 100 for item in data["biggest_increases"]],
                        #         marker_color='blue',
                        #         text=[f"+{item.get('change', 0) * 100:.4f}%" for item in data["biggest_increases"]],
                        #         textposition='auto',
                        #     )
                        # ])
                        # fig_increases.update_layout(
                        #     title="资金费率上升最快",
                        #     xaxis_title="交易对",
                        #     yaxis_title="变化率 (%)",
                        #     height=400
                        # )
                        # st.plotly_chart(fig_increases, use_container_width=True)
                    else:
                        st.write("暂无数据")
                
                with col4:
                    st.subheader("⬇️ 费率下降最快")
                    if "biggest_decreases" in data and data["biggest_decreases"]:
                        df_decreases = pd.DataFrame([
                            {"交易对": item.get("symbol", ""),
                             "变化": f"{item.get('change', 0) * 100:.4f}%"}
                            for item in data["biggest_decreases"]
                        ])
                        st.dataframe(df_decreases, hide_index=True)
                        
                        # 创建柱状图
                        # fig_decreases = go.Figure(data=[
                        #     go.Bar(
                        #         x=[item.get('symbol', '') for item in data["biggest_decreases"]],
                        #         y=[item.get('change', 0) * 100 for item in data["biggest_decreases"]],
                        #         marker_color='purple',
                        #         text=[f"{item.get('change', 0) * 100:.4f}%" for item in data["biggest_decreases"]],
                        #         textposition='auto',
                        #     )
                        # ])
                        # fig_decreases.update_layout(
                        #     title="资金费率下降最快",
                        #     xaxis_title="交易对",
                        #     yaxis_title="变化率 (%)",
                        #     height=400
                        # )
                        # st.plotly_chart(fig_decreases, use_container_width=True)
                    else:
                        st.write("暂无数据")
                
                # 显示所有交易对的资金费率分布
                st.subheader("📈 所有交易对资金费率分布")
                if "previous_rates" in data and data["previous_rates"]:
                    # 创建所有交易对的资金费率数据
                    all_rates = []
                    for symbol, rate in data["previous_rates"].items():
                        all_rates.append({"交易对": symbol, "费率": rate * 100})
                    
                    # 转换为DataFrame并排序
                    df_all = pd.DataFrame(all_rates)
                    df_all = df_all.sort_values(by="费率", ascending=False)
                    
                    # 显示数据表格
                    st.dataframe(df_all, hide_index=True)
                    
                    # 创建分布图
                    # fig_dist = go.Figure(data=[
                    #     go.Histogram(
                    #         x=[rate * 100 for rate in data["previous_rates"].values()],
                    #         nbinsx=50,
                    #         name="资金费率分布"
                    #     )
                    # ])
                    # fig_dist.update_layout(
                    #     title="资金费率分布直方图",
                    #     xaxis_title="资金费率 (%)",
                    #     yaxis_title="交易对数量",
                    #     height=400
                    # )
                    # st.plotly_chart(fig_dist, use_container_width=True)
                else:
                    st.write("暂无数据")
        else:
            st.warning("未找到数据文件，请点击刷新按钮获取数据")
            
            # 如果没有数据，运行一次任务
            if st.button("获取数据"):
                with st.spinner("正在获取数据..."):
                    tracker.run_task()
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
