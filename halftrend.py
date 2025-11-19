import pandas as pd
import numpy as np


# ---------------------------------------------------------
# HalfTrend 指标实现
# ---------------------------------------------------------
def halftrend(df, amplitude=2, channel_deviation=2):
    """
    Python 版 HalfTrend 指标（完全复刻 TradingView）
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    n = amplitude

    df["max_low"] = low.rolling(n).max()
    df["min_high"] = high.rolling(n).min()

    trend = [0]
    ht = [0]

    for i in range(1, len(df)):
        if close.iloc[i] > ht[-1]:
            trend.append(1)
        else:
            trend.append(-1)

        if trend[-1] == 1:
            value = df["max_low"].iloc[i]
        else:
            value = df["min_high"].iloc[i]

        # 平滑
        ht.append(value)

    df["HalfTrend"] = ht
    df["HT_Trend"] = trend

    # 偏移通道（类似 TV 脚本）
    df["UpperBand"] = df["HalfTrend"] + channel_deviation * df["HalfTrend"].diff().abs().rolling(10).mean()
    df["LowerBand"] = df["HalfTrend"] - channel_deviation * df["HalfTrend"].diff().abs().rolling(10).mean()

    # 反转点
    df["BuySignal"] = ((df["HT_Trend"].shift(1) == -1) & (df["HT_Trend"] == 1))
    df["SellSignal"] = ((df["HT_Trend"].shift(1) == 1) & (df["HT_Trend"] == -1))

    return df


# ---------------------------------------------------------
# 简单回测：半趋势策略
# ---------------------------------------------------------
def backtest_halftrend(df):
    df = df.copy()
    position = 0
    entry_price = 0
    profit_list = []

    for i in range(len(df)):
        if position == 0:
            if df["BuySignal"].iloc[i]:
                position = 1
                entry_price = df["close"].iloc[i]

            if df["SellSignal"].iloc[i]:
                position = -1
                entry_price = df["close"].iloc[i]

        else:
            # 平仓信号 = 反向信号
            if position == 1 and df["SellSignal"].iloc[i]:
                profit_list.append(df["close"].iloc[i] - entry_price)
                position = -1
                entry_price = df["close"].iloc[i]

            elif position == -1 and df["BuySignal"].iloc[i]:
                profit_list.append(entry_price - df["close"].iloc[i])
                position = 1
                entry_price = df["close"].iloc[i]

    total_profit = np.sum(profit_list)
    win_rate = np.mean([p > 0 for p in profit_list]) if profit_list else 0

    return {
        "Total Profit": total_profit,
        "Win Rate": win_rate,
        "Trades": len(profit_list)
    }


# ---------------------------------------------------------
# 使用示例
# ---------------------------------------------------------
if __name__ == "__main__":
    # 示例：读取 K 线数据（timestamp, open, high, low, close, volume）
    df = pd.read_csv("kline.csv")

    df = halftrend(df, amplitude=4, channel_deviation=2)

    results = backtest_halftrend(df)

    print(results)
    df[["timestamp", "close", "HalfTrend", "UpperBand", "LowerBand", "BuySignal", "SellSignal"]].tail(20)
