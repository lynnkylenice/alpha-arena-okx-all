import numpy as np
import pandas as pd
import math
from scipy.stats import norm

def nadaraya_watson(y, h=20):
    """
    计算 Nadaraya-Watson 核回归平滑曲线（Gaussian kernel）

    参数:
        y : 1D 数组 或 pandas Series
        h : 核带宽 (越大越平滑)

    返回:
        m : 平滑后的回归值数组
    """
    y = np.asarray(y)
    n = len(y)
    x = np.arange(n)
    m = np.zeros(n)

    for i in range(n):
        weights = norm.pdf((x - x[i]) / h)
        weights /= weights.sum()  # 权重归一化
        m[i] = np.sum(weights * y)

    return m


def nw_envelope_lux(series, h=20, k=3.0):
    """
    Nadaraya-Watson Envelope (Lux version)

    参数:
        series : pandas Series 价格序列
        h      : 核回归带宽
        k      : 包络倍数（类似布林带的 nσ）

    返回:
        pd.DataFrame: 包含中轨、上轨、下轨
    """
    y = series.values
    mid = nadaraya_watson(y, h=h)

    # 残差
    residual = y - mid

    # 使用 RMS 残差作为波动度
    vol = np.sqrt(pd.Series(residual).rolling(h).mean() ** 2)

    upper = mid + k * vol
    lower = mid - k * vol

    return pd.DataFrame({
        "mid": mid,
        "upper": upper,
        "lower": lower
    }, index=series.index)

def gauss(x, h):
    return math.exp(-(x * x) / (2 * h * h))


# ===============================
# 示例
# ===============================
if __name__ == "__main__":
    import matplotlib.pyplot as plt

    np.random.seed(0)
    price = np.cumsum(np.random.randn(300)) + 100
    s = pd.Series(price)

    env = nw_envelope_lux(s, h=20, k=2.0)

    plt.figure(figsize=(10,5))
    plt.plot(s.index, s, label="Price")
    plt.plot(env.index, env["mid"], label="NW Mid")
    plt.plot(env.index, env["upper"], label="NW Upper")
    plt.plot(env.index, env["lower"], label="NW Lower")
    plt.legend()
    plt.title("Nadaraya–Watson Envelope (Lux)")
    plt.show()
