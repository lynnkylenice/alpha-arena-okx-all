"""
Nadaraya-Watson Envelope — Python port of LuxAlgo Pine Script
- Supports repaint = False (non-repaint endpoint method)
- repaint = True (two variants):
    * repaint_on_last: compute only at final bar (like Pine: barstate.islast and repaint)
    * repaint_full_history: simulate TV repaint across history (slow)
Author: ported to Python (pandas + numpy + matplotlib)
"""

import numpy as np
import pandas as pd
import math
import matplotlib.pyplot as plt
from typing import Tuple, Optional

# -----------------------
# Kernel
# -----------------------
def gauss(x: float, h: float) -> float:
    """Gaussian kernel (Pine-style, un-normalized factor).
       gauss(x,h) = exp(-(x^2) / (2 h^2))
    """
    return math.exp(- (x * x) / (2.0 * h * h))

def gauss_np(x: np.ndarray, h: float) -> np.ndarray:
    return np.exp(- (x * x) / (2.0 * h * h))

# -----------------------
# Core computations
# -----------------------
def nwe_norepaint(series: pd.Series, h: float = 8.0, mult: float = 3.0, window: int = 500) -> pd.DataFrame:
    """
    Non-repaint endpoint method (equivalent to Pine 'not repaint' branch).
    - For each t compute mid_t = sum_{i=0..L-1} src[t-i] * w[i] / sum(w[:L]) where w[i] = gauss(i,h)
    - mae_t = rolling_sma(abs(src - mid), window=L) * mult  (Pine used ta.sma(...,499)*mult)
    Returns DataFrame with columns: mid, upper, lower, mae
    Complexity: O(n * window)
    """
    src = series.values.astype(float)
    n = len(src)
    W = min(window, 500)  # keep parity with Pine's 0..499 if window >=500
    # precompute weights w[i] for i in 0..W-1
    w = np.array([gauss(i, h) for i in range(W)], dtype=float)

    mid = np.full(n, np.nan, dtype=float)
    # compute mid for each t
    for t in range(n):
        L = min(W, t + 1)
        weights = w[:L]
        vals = src[t - np.arange(L)]   # [src[t], src[t-1], ...]
        mid[t] = np.dot(weights, vals) / weights.sum()

    # mae as rolling SMA of abs(src - mid) with window = W (min_periods=1)
    abs_err = np.abs(src - mid)
    mae = pd.Series(abs_err).rolling(window=W, min_periods=1).mean().values * mult

    upper = mid + mae
    lower = mid - mae

    return pd.DataFrame({'mid': mid, 'upper': upper, 'lower': lower, 'mae': mae}, index=series.index)


def nwe_repaint_on_last(series: pd.Series, h: float = 8.0, mult: float = 3.0, window: int = 500) -> pd.DataFrame:
    """
    Repaint but only computed for the final bar (like Pine: if barstate.islast and repaint).
    Only last L = min(window, n) points are populated; earlier are NaN.
    Complexity: O(window^2) for the final computation.
    """
    src = series.values.astype(float)
    n = len(src)
    L = min(window, n)
    nwe = np.full(L, np.nan, dtype=float)
    sae = 0.0

    # in Pine, i iterates 0..min(499,n-1), j iterates 0..min(499,n-1)
    # here we map src indices: src[n-1 - j] corresponds to Pine src[j] relative to last bar
    for i in range(L):
        sumv = 0.0
        sumw = 0.0
        for j in range(L):
            w = gauss(i - j, h)
            sumw += w
            sumv += src[n - 1 - j] * w
        y2 = sumv / sumw if sumw != 0 else np.nan
        nwe[i] = y2
        sae += abs(src[n - 1 - i] - y2)

    sae = (sae / L) * mult if L > 0 else np.nan

    mid = np.full(n, np.nan, dtype=float)
    upper = np.full(n, np.nan, dtype=float)
    lower = np.full(n, np.nan, dtype=float)
    mae = np.full(n, np.nan, dtype=float)

    for i in range(L):
        idx = n - 1 - i
        mid[idx] = nwe[i]
        upper[idx] = nwe[i] + sae
        lower[idx] = nwe[i] - sae
        mae[idx] = sae

    return pd.DataFrame({'mid': mid, 'upper': upper, 'lower': lower, 'mae': mae}, index=series.index)


def nwe_repaint_full_history(series: pd.Series, h: float = 8.0, mult: float = 3.0, window: int = 500, show_progress: bool = False) -> pd.DataFrame:
    """
    Simulate TradingView repaint across history:
    For each t = 0..n-1 treat bar t as 'last', compute nwe offsets i=0..min(window-1,t),
    and write (overwrite) results at absolute positions pos = t - i.
    This reproduces how Pine's repaint will change historical values as new bars arrive.
    WARNING: Very slow for large n and window (naive O(n * window^2)).
    """
    src = series.values.astype(float)
    n = len(src)
    mid = np.full(n, np.nan, dtype=float)
    upper = np.full(n, np.nan, dtype=float)
    lower = np.full(n, np.nan, dtype=float)
    mae = np.full(n, np.nan, dtype=float)

    rng = range(n)
    if show_progress:
        try:
            from tqdm import tqdm
            rng = tqdm(rng, desc='repaint-sim')
        except Exception:
            pass

    for t in rng:
        L = min(window, t + 1)
        nwe_local = np.full(L, np.nan, dtype=float)
        sae = 0.0
        for i in range(L):
            sumv = 0.0
            sumw = 0.0
            for j in range(L):
                w = gauss(i - j, h)
                sumw += w
                sumv += src[t - j] * w
            y2 = sumv / sumw if sumw != 0 else np.nan
            nwe_local[i] = y2
            sae += abs(src[t - i] - y2)
        sae = (sae / L) * mult if L > 0 else np.nan

        for i in range(L):
            pos = t - i
            mid[pos] = nwe_local[i]
            upper[pos] = nwe_local[i] + sae
            lower[pos] = nwe_local[i] - sae
            mae[pos] = sae

    return pd.DataFrame({'mid': mid, 'upper': upper, 'lower': lower, 'mae': mae}, index=series.index)


# -----------------------
# Generate signals (▲/▼) aligned with Pine logic
# -----------------------
def generate_signals(series: pd.Series, nwe_df: pd.DataFrame) -> pd.Series:
    """
    Reconstruct the Pine script crossing-arrow logic:
      Pine condition (in repaint branch):
        if src[i] > nwe.get(i) + sae and src[i+1] < nwe.get(i) + sae -> label.new at n-i  (▼)
        if src[i] < nwe.get(i) - sae and src[i+1] > nwe.get(i) - sae -> label.new at n-i  (▲)
    In our absolute indexing:
      we check consecutive bars k (older) and k+1 (newer):
        if src[k] > upband[k] and src[k+1] < upband[k] -> bearish arrow at k+1 (newer)
        if src[k] < loband[k] and src[k+1] > loband[k] -> bullish arrow at k+1
    Returns a Series with 1 (▲), -1 (▼), 0 no signal.
    """
    src = series.values.astype(float)
    mid = nwe_df['mid'].values
    mae = nwe_df['mae'].values
    n = len(src)
    sig = np.zeros(n, dtype=int)

    for k in range(n - 1):
        if np.isnan(mid[k]) or np.isnan(mid[k + 1]) or np.isnan(mae[k]):
            continue
        upband = mid[k] + mae[k]
        loband = mid[k] - mae[k]
        if src[k] > upband and src[k + 1] < upband:
            sig[k + 1] = -1
        if src[k] < loband and src[k + 1] > loband:
            sig[k + 1] = 1
    return pd.Series(sig, index=series.index)


# -----------------------
# Plot helper (matplotlib)
# -----------------------
def plot_nwe(series: pd.Series, nwe_df: pd.DataFrame, signals: Optional[pd.Series] = None, title: str = 'Nadaraya-Watson Envelope', show: bool = True):
    plt.figure(figsize=(12, 6))
    plt.plot(series.index, series.values, label='price', linewidth=1.2)
    if 'mid' in nwe_df:
        plt.plot(nwe_df.index, nwe_df['mid'].values, label='mid', linewidth=1.0)
    if 'upper' in nwe_df:
        plt.plot(nwe_df.index, nwe_df['upper'].values, label='upper', linewidth=0.9)
    if 'lower' in nwe_df:
        plt.plot(nwe_df.index, nwe_df['lower'].values, label='lower', linewidth=0.9)
    # draw arrows
    if signals is not None:
        buys = signals[signals == 1].index
        sells = signals[signals == -1].index
        plt.scatter(buys, series.loc[buys].values, marker='^', color='green', s=60, label='▲ buy')
        plt.scatter(sells, series.loc[sells].values, marker='v', color='red', s=60, label='▼ sell')
    plt.legend()
    plt.title(title)
    plt.grid(alpha=0.25)
    if show:
        plt.show()


# -----------------------
# Example usage
# -----------------------
if __name__ == "__main__":
    # generate toy price data
    np.random.seed(0)
    n = 300
    price = np.cumsum(np.random.randn(n)) + 100.0
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    s = pd.Series(price, index=idx)

    # parameters (Pine defaults from your script: h=8, mult=3, window=500 (0..499))
    h = 8.0
    mult = 3.0
    window = 200   # << for demo speed reduce from 500 to 200; set to 500 to fully match script

    # non-repaint (fast)
    res_nr = nwe_norepaint(s, h=h, mult=mult, window=window)
    sig_nr = generate_signals(s, res_nr)
    print("Non-repaint signals (sample):", sig_nr[sig_nr != 0].head(10).to_dict())
    plot_nwe(s, res_nr, sig_nr, title='NWE (non-repaint)')

    # repaint-on-last (only last L points populated)
    res_rl = nwe_repaint_on_last(s, h=h, mult=mult, window=window)
    sig_rl = generate_signals(s, res_rl)
    print("Repaint-on-last signals (sample):", sig_rl[sig_rl != 0].to_dict())
    plot_nwe(s, res_rl, sig_rl, title='NWE (repaint-on-last)')

    # repaint full history (very slow if window large)
    # set show_progress=True to see progress (requires tqdm)
    res_rh = nwe_repaint_full_history(s, h=h, mult=mult, window=window, show_progress=False)
    sig_rh = generate_signals(s, res_rh)
    print("Repaint-full-history signals (sample):", sig_rh[sig_rh != 0].head(20).to_dict())
    plot_nwe(s, res_rh, sig_rh, title='NWE (repaint-full-history)')
