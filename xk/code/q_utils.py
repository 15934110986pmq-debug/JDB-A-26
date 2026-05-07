"""Common utilities shared by Q1, Q2, Q3 solvers.

Functions:
    load_xlsx(path)               -> (s1, s2) DataFrames with cols [t, x, y]
    make_interp(df, kind)         -> (fx, fy) callable interpolators
    feasible_domain(s1, s2, ov)   -> (dt_lo, dt_hi)
    alignment_cost_dt(dt, ...)    -> scalar J(dt)
    alignment_cost_joint(p, ...)  -> scalar J(dt, dx, dy)
    estimate_dt_uncertainty(...)  -> sigma_dt via 2nd-order finite diff
    fuse_10hz(s1, s2, dt, dx, dy, w1, w2) -> (t_grid, x, y, mask_full, mask_strict)
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
from scipy.interpolate import interp1d


def load_xlsx(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    xl = pd.ExcelFile(path)
    s1 = pd.read_excel(xl, "方式1(4Hz)")
    s2 = pd.read_excel(xl, "方式2(5Hz)")
    s1.columns = ["t", "x", "y"]
    s2.columns = ["t", "x", "y"]
    return (s1.sort_values("t").reset_index(drop=True),
            s2.sort_values("t").reset_index(drop=True))


def make_interp(df: pd.DataFrame, kind: str = "linear"):
    fx = interp1d(df["t"].values, df["x"].values, kind=kind,
                  bounds_error=False, fill_value=np.nan, assume_sorted=True)
    fy = interp1d(df["t"].values, df["y"].values, kind=kind,
                  bounds_error=False, fill_value=np.nan, assume_sorted=True)
    return fx, fy


def feasible_domain(s1, s2, min_overlap: float = 10.0):
    t1_min, t1_max = float(s1["t"].min()), float(s1["t"].max())
    t2_min, t2_max = float(s2["t"].min()), float(s2["t"].max())
    return (t2_min - t1_max + min_overlap,
            t2_max - t1_min - min_overlap)


def alignment_cost_dt(dt, s1, s2, fx2, fy2, n_grid=4000):
    t_lo = max(s1["t"].min(), s2["t"].min() + dt)
    t_hi = min(s1["t"].max(), s2["t"].max() + dt)
    if t_hi - t_lo <= 1.0:
        return 1e9
    grid = np.linspace(t_lo, t_hi, n_grid)
    fx1, fy1 = make_interp(s1)
    rx = fx1(grid) - fx2(grid - dt)
    ry = fy1(grid) - fy2(grid - dt)
    mask = ~(np.isnan(rx) | np.isnan(ry))
    if mask.sum() < 100:
        return 1e9
    return float(np.mean(rx[mask] ** 2 + ry[mask] ** 2))


def alignment_cost_joint(params, s1, s2, fx2, fy2, n_grid=4000):
    dt, dx, dy = params
    t_lo = max(s1["t"].min(), s2["t"].min() + dt)
    t_hi = min(s1["t"].max(), s2["t"].max() + dt)
    if t_hi - t_lo <= 1.0:
        return 1e9
    grid = np.linspace(t_lo, t_hi, n_grid)
    fx1, fy1 = make_interp(s1)
    rx = fx1(grid) - (fx2(grid - dt) + dx)
    ry = fy1(grid) - (fy2(grid - dt) + dy)
    mask = ~(np.isnan(rx) | np.isnan(ry))
    if mask.sum() < 100:
        return 1e9
    return float(np.mean(rx[mask] ** 2 + ry[mask] ** 2))


def estimate_dt_uncertainty(dt_hat, s1, s2, fx2, fy2, h: float = 1e-3):
    J0 = alignment_cost_dt(dt_hat, s1, s2, fx2, fy2, n_grid=8000)
    Jp = alignment_cost_dt(dt_hat + h, s1, s2, fx2, fy2, n_grid=8000)
    Jm = alignment_cost_dt(dt_hat - h, s1, s2, fx2, fy2, n_grid=8000)
    J2 = (Jp - 2 * J0 + Jm) / (h ** 2)
    if J2 <= 0:
        return float("nan")
    return float(np.sqrt(max(2.0 * J0, 1e-30) / J2))


def coarse_search_dt(s1, s2, fx2, fy2, dt_lo, dt_hi, step):
    grid = np.arange(dt_lo, dt_hi + step, step)
    costs = np.array([alignment_cost_dt(d, s1, s2, fx2, fy2, n_grid=1500) for d in grid])
    return grid, costs


def fuse_10hz(s1, s2, dt, dx, dy, w1=0.5, w2=0.5):
    """Build 10 Hz fused trajectory.
    Returns: (t_grid, x_fused, y_fused,
              mask_strict_intersection, mask_only_method1, mask_only_method2)
    """
    fx1, fy1 = make_interp(s1)
    fx2, fy2 = make_interp(s2)

    t_lo = min(s1["t"].min(), s2["t"].min() + dt)
    t_hi = max(s1["t"].max(), s2["t"].max() + dt)
    t_grid = np.arange(np.ceil(t_lo * 10) / 10,
                       np.floor(t_hi * 10) / 10 + 1e-9, 0.1)

    x1 = fx1(t_grid); y1 = fy1(t_grid)
    x2c = fx2(t_grid - dt) + dx
    y2c = fy2(t_grid - dt) + dy

    has1 = ~(np.isnan(x1) | np.isnan(y1))
    has2 = ~(np.isnan(x2c) | np.isnan(y2c))
    both = has1 & has2

    x = np.full_like(t_grid, np.nan)
    y = np.full_like(t_grid, np.nan)
    # Weighted average in overlap; use convex combination
    x[both] = w1 * x1[both] + w2 * x2c[both]
    y[both] = w1 * y1[both] + w2 * y2c[both]
    only1 = has1 & ~has2
    only2 = ~has1 & has2
    x[only1] = x1[only1]; y[only1] = y1[only1]
    x[only2] = x2c[only2]; y[only2] = y2c[only2]

    return t_grid, x, y, both, only1, only2
