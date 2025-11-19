import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def compute_kdj(df, n=9, m1=3, m2=3, price_cols=('high', 'low', 'close')):
    """
    计算 KDJ 指标并返回包含 K, D, J 的 DataFrame 副本。

    参数:
      df : pandas.DataFrame，必须包含高/低/收盘价列
      n  : int，计算 RSV 的周期（默认 9）
      m1 : int，K 的平滑因子（默认 3，即 K_t = (K_{t-1}*(m1-1) + RSV_t)/m1）
      m2 : int，D 的平滑因子（默认 3）
      price_cols : tuple，(high_col, low_col, close_col) 列名

    返回:
      result_df : pandas.DataFrame，原始数据的副本，新增 'RSV','K','D','J' 列
    """
    high_col, low_col, close_col = price_cols
    df = df.copy()

    # 计算 n 周期内的最高价和最低价
    highest = df[high_col].rolling(window=n, min_periods=1).max()
    lowest = df[low_col].rolling(window=n, min_periods=1).min()

    # 防止除以 0
    denom = (highest - lowest).replace(0, np.nan)

    # RSV (Raw Stochastic Value)，取 0-100
    rsv = (df[close_col] - lowest) / denom * 100
    rsv = rsv.fillna(0)  # 当最高最低相等时（或前期数据不足）填 0（也可按需改为 50）

    df['RSV'] = rsv

    # 初始化 K 和 D（常用做法：第一期 K=D=50，或用第一期 RSV）
    K = pd.Series(np.nan, index=df.index)
    D = pd.Series(np.nan, index=df.index)

    # 用 50 初始化（更稳健），也可以改为 K.iloc[0] = rsv.iloc[0]
    if len(df) > 0:
        K.iloc[0] = 50.0
        D.iloc[0] = 50.0

    # 递推计算 K 和 D
    # K_t = (m1-1)/m1 * K_{t-1} + 1/m1 * RSV_t
    # D_t = (m2-1)/m2 * D_{t-1} + 1/m2 * K_t
    alpha_k = 1.0 / m1
    beta_k = 1.0 - alpha_k
    alpha_d = 1.0 / m2
    beta_d = 1.0 - alpha_d

    for i in range(1, len(df)):
        K.iloc[i] = beta_k * K.iloc[i - 1] + alpha_k * df['RSV'].iloc[i]
        D.iloc[i] = beta_d * D.iloc[i - 1] + alpha_d * K.iloc[i]

    df['K'] = K
    df['D'] = D
    df['J'] = 3 * df['K'] - 2 * df['D']

    return df


# ---------------------------
# 示例用法
# ---------------------------
if __name__ == '__main__':
    # 构造示例数据（真实使用时替换为你的 price DataFrame）
    dates = pd.date_range('2023-01-01', periods=50, freq='D')
    np.random.seed(0)
    close = np.cumsum(np.random.randn(50)) + 100
    high = close + np.random.rand(50) * 1.5
    low = close - np.random.rand(50) * 1.5
    df = pd.DataFrame({'date': dates, 'high': high, 'low': low, 'close': close}).set_index('date')

    # 计算 KDJ
    kdj_df = compute_kdj(df, n=9, m1=3, m2=3)

    # 显示最后几行
    print(kdj_df[['high', 'low', 'close', 'RSV', 'K', 'D', 'J']].tail(10))

    # 可视化（可选）
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2, 1]})
    ax1.plot(df.index, df['close'])
    ax1.set_title('Price')
    ax2.plot(kdj_df.index, kdj_df['K'], label='K')
    ax2.plot(kdj_df.index, kdj_df['D'], label='D')
    ax2.plot(kdj_df.index, kdj_df['J'], label='J')
    ax2.axhline(80, linestyle='--', linewidth=0.7)
    ax2.axhline(20, linestyle='--', linewidth=0.7)
    ax2.set_ylim(-50, 150)
    ax2.legend()
    plt.tight_layout()
    plt.show()
