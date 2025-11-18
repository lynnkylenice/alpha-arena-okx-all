import numpy as np
import pandas as pd
from scipy.stats import linregress


def bollinger_bands(close, period=20, std=2):
    sma = close.rolling(period).mean()
    stdv = close.rolling(period).std(ddof=0)
    upper = sma + std * stdv
    lower = sma - std * stdv
    return sma, upper, lower


def true_range(df):
    prev_close = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - prev_close).abs()
    tr3 = (df['low'] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr


def keltner_channel(df, ema_period=20, atr_period=20, atr_mult=1.5):
    ema = df['close'].ewm(span=ema_period, adjust=False).mean()
    atr = true_range(df).rolling(atr_period).mean()
    upper = ema + atr * atr_mult
    lower = ema - atr * atr_mult
    return ema, upper, lower, atr


def squeeze_momentum(close, period=20):
    """
    Momentum = 对最近 period 的去趋势价格做线性回归，取斜率
    """
    mom = []
    x = np.arange(period)

    for i in range(len(close)):
        if i < period:
            mom.append(np.nan)
            continue
        y = close[i - period:i]
        slope, _, _, _, _ = linregress(x, y)
        mom.append(slope)

    return pd.Series(mom, index=close.index)


def ttm_squeeze(df,
                bb_period=20, bb_std=2,
                kc_period=20, atr_mult=1.5,
                mom_period=20):
    close = df['close']

    # --- Bollinger Bands ---
    bb_mid, bb_up, bb_low = bollinger_bands(close, bb_period, bb_std)

    # --- Keltner Channel ---
    kc_mid, kc_up, kc_low, atr = keltner_channel(df, kc_period, kc_period, atr_mult)

    # --- Squeeze Condition ---
    # squeeze_on: 布林带完全在肯特纳通道内
    squeeze_on = (bb_up < kc_up) & (bb_low > kc_low)
    squeeze_off = ~squeeze_on

    # --- Momentum ---
    momentum = squeeze_momentum(close, mom_period)

    result = pd.DataFrame({
        'close': close,
        'BB_Mid': bb_mid,
        'BB_Up': bb_up,
        'BB_Low': bb_low,
        'KC_Mid': kc_mid,
        'KC_Up': kc_up,
        'KC_Low': kc_low,
        'ATR': atr,
        'Squeeze_On': squeeze_on,
        'Squeeze_Off': squeeze_off,
        'Momentum': momentum
    })

    return result
