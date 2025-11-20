#!/usr/bin/env python
# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from deepseekok2 import calculate_technical_indicators,deepseek_client,exchange,TRADE_CONFIG
from ttm_strategy import ttm_squeeze,squeeze_momentum
from nw import nw_envelope_lux
from atr import atr_stop_loss
from nw_new import *

def calculate_intelligent_position(df):
    try:
        # 移动平均线
        df['sma_5'] = df['close'].rolling(window=5, min_periods=1).mean()
        df['sma_20'] = df['close'].rolling(window=20, min_periods=1).mean()
        df['sma_50'] = df['close'].rolling(window=50, min_periods=1).mean()

        # 指数移动平均线
        df['ema_12'] = df['close'].ewm(span=12).mean()
        df['ema_26'] = df['close'].ewm(span=26).mean()
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']

        # 相对强弱指数 (RSI)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # 布林带
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

        # 成交量均线
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']

        # 支撑阻力位
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()

        # 填充NaN值
        df = df.bfill().ffill()

        return df
    except Exception as e:
        print(f"技术指标计算失败: {e}")
        return df
def rsi_trend(df):
    rsi_close = df['rsi'].iloc[-1]
    if rsi_close > 60:
        trend = '上涨'
    elif rsi_close < 40:
        trend = '下跌'
    else:
        trend = '横盘整理'
    return trend
def rsi_side(df,trend):
    rsi_close=df['rsi'].iloc[-1]

    if rsi_close > 80:
        side ='sell'
    elif rsi_close<20:
        side = "buy"
    if rsi_close > 60 and trend=='下跌':
        side = "sell"
    if rsi_close < 40 and trend=='上涨':
        side = 'buy'
    else:
        side='no'
    return {'side':side}
#rsi 超买和超卖，小级别需要去大级别确认
#rsi 下跌趋势最好不要做买入，上升趋势不要做卖出操作
def ris_handel(df):
     trend = rsi_trend(df)
     side = rsi_side(df,trend)
     return side


def macd_handel(df):
    macd_fast=df['macd'].iloc[-1]
    macd_slow=df['macd_histogram'].iloc[-1]
    macd_signal=df['macd_signal'].iloc[-1]
    if macd_signal>0 and macd_signal<5 :
        side = 'buy'

def boll_kc_handel(df):
    res = ttm_squeeze(df)
    rsi_last = df['rsi'].iloc[-2]
    rsi_close = df['rsi'].iloc[-1]
    if bool(res['Squeeze_On'].iloc[-1]) and rsi_last >= 80 > rsi_close and df['close'].iloc[-1] < df['open'].iloc[-1]:
        side = 'SELL'
    elif bool(res['Squeeze_On'].iloc[-1]) and rsi_last <= 20 < rsi_close and df['close'].iloc[-1] > df['open'].iloc[-1]:
        side = 'BUY'
    else:
        side = 'HOLD'
    return side


def main():
    print("BTC/USDT OKX自动交易机器人策略启动成功！")
    #5分钟线
    ohlfmcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], '5m',
                                   limit=TRADE_CONFIG['data_points'])
    #15分钟线
  #  ohlcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], TRADE_CONFIG['timeframe'],
     #                            limit=TRADE_CONFIG['data_points'])
    #1小时线
   # ohlohcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], '1h',
   #                                   limit=TRADE_CONFIG['data_points'])
    #4小时线
   #  ohlfhcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], '4h',
   #                                   limit=TRADE_CONFIG['data_points'])
    #日线
   #  ohlodcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], '1d',
   #                                   limit=TRADE_CONFIG['data_points'])
    #周线
   # ohlowcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], '1w',
   #                                limit=TRADE_CONFIG['data_points'])
    #月线
   # ohlomcv = exchange.fetch_ohlcv(TRADE_CONFIG['symbol'], '1m',
   #                                limit=36)
    #5min
    dffm = pd.DataFrame(ohlfmcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    dffm['timestamp'] = pd.to_datetime(dffm['timestamp'], unit='ms')
    # 15min
   # dfftym = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
   # dfftym['timestamp'] = pd.to_datetime(dfftym['timestamp'], unit='ms')
    #5min数据
    df = calculate_technical_indicators(dffm)
    nw_rsi_atr(df)

    # create example price series
    import matplotlib.pyplot as plt
    price = df['close']
    s = pd.Series(price)

    # parameters (Pine defaults from your script: h=8, mult=3, window=500 (0..499))
    h = 8.0
    mult = 3.0
    window = 200   # << for demo speed reduce from 500 to 200; set to 500 to fully match script

    # repaint-on-last (only last L points populated)
    res_rl = nwe_repaint_on_last(s, h=h, mult=mult, window=window)
    sig_rl = generate_signals(s, res_rl)
    print("Repaint-on-last signals (sample):", sig_rl[sig_rl != 0].to_dict())
    plot_nwe(s, res_rl, sig_rl, title='NWE (repaint-on-last)')



if __name__ == "__main__":
    main()
