import pandas as pd
import numpy as np


def compute_atr(df, n=14):
    """
    计算 ATR (Wilder 版本)

    参数：
        df: DataFrame，必须包含 high, low, close 列
        n : ATR 周期（常用 14）

    返回：
        atr : pandas.Series
    """
    high = df['high']
    low = df['low']
    close = df['close']

    # TR: True Range
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    # Wilder’s smoothing (RMA)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()

    return atr

def atr_stop_loss(df, atr_period=14, mul=3):
    """
    生成 ATR 动态止损（long / short）

    参数：
        df          : DataFrame，包含 high, low, close
        atr_period  : ATR 周期
        mul         : ATR 倍数（常用 2～3）

    返回：
        DataFrame: 增加 stop_long, stop_short 列
    """
    df = df.copy()
    atr = compute_atr(df, n=atr_period)
    close = df['close']

    # 多头止损（低于价格 X ATR）
    stop_long = close - mul * atr

    # 空头止损（高于价格 X ATR）
    stop_short = close + mul * atr

    df['atr'] = atr
    df['stop_long'] = stop_long
    df['stop_short'] = stop_short

    return df
