"""Q1: Attachment-1 time alignment + 10 Hz fused trajectory (noise-free).

Model:
    Convention: Method-1 timestamp == physical time;
                Method-2 physical time = t2 + dt
    Joint sanity-check estimator:
        (dt, dx, dy) = argmin int || p1(t) - p2(t - dt) - (dx, dy) ||^2 dt
    Pure-time estimator (Q1 baseline) fixes (dx, dy) = 0.

Algorithm:
    1) Coarse scan over full feasible domain
       dt in [t2_min - t1_max, t2_max - t1_min]
    2) Mid scan +/- 1 s, step 0.01
    3) Brent refinement -> machine precision
    4) Joint (dt, dx, dy) refinement starting from baseline dt
    5) Cramer-Rao-style uncertainty via numerical Hessian

Outputs:
    output/Q1_trajectory_10Hz.xlsx              full coverage
    output/Q1_trajectory_10Hz_strict.xlsx       strict intersection
    output/Q1_summary.json                      dt, sigma_dt, joint estimate, ranges
    figures/Q1_alignment.png                    diagnostic plots
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d
from scipy.optimize import brent, minimize_scalar
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "A"))
from plot_style import setup_plot_style  # noqa: E402

setup_plot_style()

DATA = ROOT / "data"
FIGS = ROOT / "figures"
OUT = ROOT / "output"


def load_xlsx(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    xl = pd.ExcelFile(path)
    s1 = pd.read_excel(xl, "方式1(4Hz)")
    s2 = pd.read_excel(xl, "方式2(5Hz)")
    s1.columns = ["t", "x", "y"]
    s2.columns = ["t", "x", "y"]
    return (s1.sort_values("t").reset_index(drop=True),
            s2.sort_values("t").reset_index(drop=True))


def make_interp(df: pd.DataFrame):
    fx = interp1d(df["t"].values, df["x"].values, kind="linear",
                  bounds_error=False, fill_value=np.nan, assume_sorted=True)
    fy = interp1d(df["t"].values, df["y"].values, kind="linear",
                  bounds_error=False, fill_value=np.nan, assume_sorted=True)
    return fx, fy


def alignment_cost(dt: float, s1: pd.DataFrame, s2: pd.DataFrame,
                   fx2, fy2, n_grid: int = 4000) -> float:
    """约定：方式2 物理时间 = t2 + dt。
    对齐后方式2 样本 (t2 + dt, x2, y2)。
    在 [max(t1.min, t2.min+dt), min(t1.max, t2.max+dt)] 区间上比较。"""
    t_lo = max(s1["t"].min(), s2["t"].min() + dt)
    t_hi = min(s1["t"].max(), s2["t"].max() + dt)
    if t_hi - t_lo <= 1.0:
        return 1e9
    grid = np.linspace(t_lo, t_hi, n_grid)
    fx1, fy1 = make_interp(s1)
    x1 = fx1(grid); y1 = fy1(grid)
    x2 = fx2(grid - dt); y2 = fy2(grid - dt)
    mask = ~(np.isnan(x1) | np.isnan(y1) | np.isnan(x2) | np.isnan(y2))
    if mask.sum() < 100:
        return 1e9
    return float(np.mean((x1[mask] - x2[mask])**2 + (y1[mask] - y2[mask])**2))


def coarse_search(s1, s2, fx2, fy2, dt_lo=-500.0, dt_hi=500.0, step=1.0):
    grid = np.arange(dt_lo, dt_hi + step, step)
    costs = np.array([alignment_cost(d, s1, s2, fx2, fy2, n_grid=1500) for d in grid])
    return grid, costs


def feasible_domain(s1, s2, min_overlap_seconds=10.0):
    """Full feasible domain for dt: where the overlap >= min_overlap_seconds.
    overlap = min(t1_max, t2_max + dt) - max(t1_min, t2_min + dt) >= min_overlap
    => dt in [t2_min - t1_max + min_overlap, t2_max - t1_min - min_overlap]
    """
    t1_min, t1_max = float(s1["t"].min()), float(s1["t"].max())
    t2_min, t2_max = float(s2["t"].min()), float(s2["t"].max())
    return (t2_min - t1_max + min_overlap_seconds,
            t2_max - t1_min - min_overlap_seconds)


def joint_cost(params, s1, s2, fx2, fy2, n_grid=4000):
    """Cost with translation: r = p1(t) - (p2(t-dt) + offset)."""
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


def estimate_dt_uncertainty(dt_hat, s1, s2, fx2, fy2, h=0.001):
    """用代价函数二阶差分估计 Δt 的 Cramér-Rao 下界。
    σ_Δt ≈ sqrt(2 * J(Δt_hat) / J''(Δt_hat))
    J 是均方残差，h 是数值二阶差分步长。"""
    J0 = alignment_cost(dt_hat, s1, s2, fx2, fy2, n_grid=8000)
    Jp = alignment_cost(dt_hat + h, s1, s2, fx2, fy2, n_grid=8000)
    Jm = alignment_cost(dt_hat - h, s1, s2, fx2, fy2, n_grid=8000)
    J2 = (Jp - 2 * J0 + Jm) / (h ** 2)
    if J2 <= 0:
        return float("nan")
    # 类比线性化最小二乘：σ_dt ≈ sqrt(2 J0 / J2)
    return float(np.sqrt(max(2.0 * J0, 1e-30) / J2))


def solve_q1(path: Path, name: str):
    s1, s2 = load_xlsx(path)
    fx2, fy2 = make_interp(s2)
    fx1, fy1 = make_interp(s1)

    # ---- improvement 3: full feasible domain ----
    dt_lo_feas, dt_hi_feas = feasible_domain(s1, s2)
    print(f"[{name}] dt feasible domain: [{dt_lo_feas:.2f}, {dt_hi_feas:.2f}] s")

    grid, costs = coarse_search(s1, s2, fx2, fy2, dt_lo_feas, dt_hi_feas, 1.0)
    i0 = int(np.argmin(costs))
    dt0 = float(grid[i0])
    grid2, costs2 = coarse_search(s1, s2, fx2, fy2, dt0 - 1.0, dt0 + 1.0, 0.01)
    i1 = int(np.argmin(costs2))
    dt1 = float(grid2[i1])
    res = minimize_scalar(lambda d: alignment_cost(d, s1, s2, fx2, fy2, n_grid=8000),
                          bracket=(dt1 - 0.05, dt1, dt1 + 0.05),
                          method="brent",
                          options={"xtol": 1e-9})
    dt_hat = float(res.x)
    final_cost = float(res.fun)
    dt_sigma = estimate_dt_uncertainty(dt_hat, s1, s2, fx2, fy2)

    # ---- improvement 1: joint estimation (dt, dx, dy) sanity check ----
    from scipy.optimize import minimize
    res_joint = minimize(
        joint_cost,
        x0=np.array([dt_hat, 0.0, 0.0]),
        args=(s1, s2, fx2, fy2, 8000),
        method="Nelder-Mead",
        options={"xatol": 1e-8, "fatol": 1e-14, "maxiter": 5000},
    )
    dt_j, dx_j, dy_j = (float(v) for v in res_joint.x)
    cost_joint = float(res_joint.fun)

    # ---------- 输出 1：全覆盖（用所有可用数据） ----------
    # 物理时间窗口 = 两路在物理时间下的并集
    t_lo_full = min(s1["t"].min(), s2["t"].min() + dt_hat)
    t_hi_full = max(s1["t"].max(), s2["t"].max() + dt_hat)
    t_full = np.arange(np.ceil(t_lo_full * 10) / 10,
                       np.floor(t_hi_full * 10) / 10 + 1e-9, 0.1)
    x1f = fx1(t_full); y1f = fy1(t_full)
    x2f = fx2(t_full - dt_hat); y2f = fy2(t_full - dt_hat)
    # 单点处可用路数判断
    has1 = ~(np.isnan(x1f) | np.isnan(y1f))
    has2 = ~(np.isnan(x2f) | np.isnan(y2f))
    x_full = np.where(has1 & has2, np.nanmean(np.vstack([x1f, x2f]), axis=0),
                      np.where(has1, x1f, x2f))
    y_full = np.where(has1 & has2, np.nanmean(np.vstack([y1f, y2f]), axis=0),
                      np.where(has1, y1f, y2f))
    n_both = int(np.sum(has1 & has2))
    n_only1 = int(np.sum(has1 & ~has2))
    n_only2 = int(np.sum(~has1 & has2))

    # ---------- 输出 2：严格交集（高置信） ----------
    t_lo_int = max(s1["t"].min(), s2["t"].min() + dt_hat)
    t_hi_int = min(s1["t"].max(), s2["t"].max() + dt_hat)
    t_int = np.arange(np.ceil(t_lo_int * 10) / 10,
                      np.floor(t_hi_int * 10) / 10 + 1e-9, 0.1)
    x_int = (fx1(t_int) + fx2(t_int - dt_hat)) / 2
    y_int = (fy1(t_int) + fy2(t_int - dt_hat)) / 2

    # 双路差异（残差检查）
    diff_x = fx1(t_int) - fx2(t_int - dt_hat)
    diff_y = fy1(t_int) - fy2(t_int - dt_hat)
    rmse = float(np.sqrt(np.nanmean(diff_x ** 2 + diff_y ** 2)))

    summary = dict(
        attachment=name,
        feasible_domain=[float(dt_lo_feas), float(dt_hi_feas)],
        dt_hat_seconds=dt_hat,
        dt_sigma_seconds=dt_sigma,
        baseline_final_cost_m2=final_cost,
        two_path_rmse_m=rmse,
        coarse_min_dt=dt0,
        joint_estimate=dict(
            dt_seconds=dt_j,
            dx_meters=dx_j,
            dy_meters=dy_j,
            final_cost_m2=cost_joint,
            interpretation=("dx, dy expected ~ 0 for attachment-1 (no system bias). "
                            "Significant deviation would indicate hidden bias."),
        ),
        n_full_coverage=int(len(t_full)),
        n_strict_intersection=int(len(t_int)),
        n_overlap_only=n_both,
        n_only_method1=n_only1,
        n_only_method2=n_only2,
        t_full_range=[float(t_full[0]), float(t_full[-1])],
        t_intersection_range=[float(t_int[0]), float(t_int[-1])],
        convention=("Method-1 timestamp = physical time. "
                    "Method-2 physical time = t2 + dt. "
                    "Negative dt here means Method-2 was powered on |dt| s earlier."),
    )

    pd.DataFrame({"time_s": t_full, "X_m": x_full, "Y_m": y_full}).to_excel(
        OUT / "Q1_trajectory_10Hz.xlsx", index=False)
    pd.DataFrame({"time_s": t_int, "X_m": x_int, "Y_m": y_int}).to_excel(
        OUT / "Q1_trajectory_10Hz_strict.xlsx", index=False)

    # 沿用 t_grid/x_fused 旧名给画图函数
    t_grid = t_full
    x_fused = x_full
    y_fused = y_full

    # 画图
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    ax = axes[0, 0]
    ax.plot(grid, costs, lw=0.8)
    ax.axvline(dt_hat, color="r", linestyle="--", label=f"$\\hat{{\\Delta t}}={dt_hat:.4f}$ s")
    ax.set_title("粗扫代价 $J(\\Delta t)$，1 s 步长")
    ax.set_xlabel("$\\Delta t$ (s)")
    ax.set_ylabel("均方残差 ($m^2$)")
    ax.set_yscale("log")
    ax.legend()

    ax = axes[0, 1]
    ax.plot(grid2, costs2, lw=0.8)
    ax.axvline(dt_hat, color="r", linestyle="--")
    ax.set_title(f"精扫代价 $J(\\Delta t)$，0.01 s 步长（Δt={dt_hat:.6f} s）")
    ax.set_xlabel("$\\Delta t$ (s)")
    ax.set_ylabel("均方残差 ($m^2$)")
    ax.set_yscale("log")

    ax = axes[1, 0]
    ax.plot(s1["t"], s1["x"], lw=0.6, alpha=0.8, label="方式1 (原始时间戳)")
    ax.plot(s2["t"] + dt_hat, s2["x"], lw=0.6, alpha=0.8, linestyle="--",
            label=f"方式2 (移到物理时间，+{dt_hat:.3f} s)")
    ax.set_title(f"对齐后 X(t) 重合 — {name}")
    ax.set_xlabel("物理时间 t (s)")
    ax.set_ylabel("X (m)")
    ax.legend(fontsize=9)

    ax = axes[1, 1]
    ax.plot(t_grid, x_fused, label="融合 X", lw=0.7)
    ax.plot(t_grid, y_fused, label="融合 Y", lw=0.7)
    ax.set_title(f"10 Hz 融合轨迹 — {name}（n={len(t_grid)}, 双路RMSE={rmse:.2e} m）")
    ax.set_xlabel("物理时间 t (s)")
    ax.set_ylabel("位置 (m)")
    ax.legend(fontsize=9)

    fig.tight_layout()
    fig.savefig(FIGS / "Q1_alignment.png")
    plt.close(fig)

    return summary


if __name__ == "__main__":
    summary = solve_q1(DATA / "附件1.xlsx", "附件1")
    (OUT / "Q1_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
