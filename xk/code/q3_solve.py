"""Q3: 附件3 实测数据 — 系统偏差判定 + 时空对齐 + 不等方差融合.

核心流程:
    1) 数据画像 + per-path 噪声分别估 (Q3 关键: σ_1 ≠ σ_2)
    2) 完整粗扫 + 多候选两阶段 Nelder-Mead 联合精化 (沿用 Q2 修正)
    3) 系统偏差判定 (题面 Q3 第一问):
       - 拟合 H0: Δt-only (无偏差) vs H1: full 3-param 联合
       - F 检验 + Bootstrap CI on (Δx, Δy)
       - 给出"存在/不存在系统偏差"结论
    4) 高斯诊断 (KS/AD/SW) + Ljung-Box 自相关
    5) Bootstrap (B=80) — 主 basin 局部不确定度
    6) BLUE 不等方差加权静态融合 (Q3 关键: w_k = 1/σ_k² / Σ)
    7) Kalman/RTS 融合 (per-source R = σ_k² I) + NIS 诊断
    8) 输出 10 Hz 轨迹 (双版本: 静态 + KF/RTS)

输出:
    xk/output/Q3_summary.json
    xk/output/Q3_trajectory_10Hz.xlsx          (静态全覆盖)
    xk/output/Q3_trajectory_10Hz_strict.xlsx   (静态严格交集)
    xk/output/Q3_trajectory_10Hz_kalman.xlsx   (KF+RTS)
    xk/figures/Q3_alignment.png
    xk/figures/Q3_residual_diag.png
    xk/figures/Q3_kalman_compare.png
    xk/figures/Q3_bootstrap.png
    xk/figures/Q3_system_bias_test.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import kstest, anderson, shapiro, pearsonr, f as f_dist
from statsmodels.stats.diagnostic import acorr_ljungbox

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "A"))
sys.path.insert(0, str(ROOT / "code"))
from plot_style import setup_plot_style  # noqa: E402
from q_utils import (  # noqa: E402
    load_xlsx, make_interp,
    alignment_cost_dt, alignment_cost_joint,
    fuse_10hz,
)
from q2_kalman import fuse_kf_rts, resample_to_10hz  # noqa: E402

setup_plot_style()
DATA = ROOT / "data"
FIGS = ROOT / "figures"
OUT = ROOT / "output"


# =====================================================================
# Q3-specific: 正确的 feasible domain
# =====================================================================
def feasible_domain_correct(s1: pd.DataFrame, s2: pd.DataFrame,
                            min_overlap: float = 10.0):
    """Δt 可行域 under convention t_phys = t1 = t2 + Δt:
        Δt ∈ (t1_min - t2_max, t1_max - t2_min) 才有非空重叠
    与 q_utils.feasible_domain 反号 (后者在 Q2 数据上巧合工作但概念错误).
    """
    t1_min, t1_max = float(s1["t"].min()), float(s1["t"].max())
    t2_min, t2_max = float(s2["t"].min()), float(s2["t"].max())
    return (t1_min - t2_max + min_overlap,
            t1_max - t2_min - min_overlap)


def coarse_search_correct(s1, s2, fx2, fy2, dt_lo, dt_hi, step):
    grid = np.arange(dt_lo, dt_hi + step, step)
    costs = np.array([alignment_cost_dt(d, s1, s2, fx2, fy2, n_grid=1500)
                      for d in grid])
    return grid, costs


# =====================================================================
# Per-path noise estimation (Q3 关键: σ_1 ≠ σ_2)
# =====================================================================
def estimate_noise_per_path(s1, s2, dt, dx, dy, n_grid: int = 8000):
    """估计两路各自的噪声 σ_1, σ_2.

    思路: 将方式 1 与方式 2 分别用滑动平均做"软真值", 得到各自的残差; σ_k 是残差标准差.
    优于 双路差分(只能给 σ_1²+σ_2² 而无法分离), 用平滑残差估两个独立量.

    返回: 两路各自的 σ_x, σ_y, 整体 σ_per_path, 以及双路差分 σ (作为对照).
    """
    fx1, fy1 = make_interp(s1)
    fx2, fy2 = make_interp(s2)

    # 1) 单路滑动平均残差估各自 σ
    def smooth_resid(df, win=11):
        x, y = df["x"].values, df["y"].values
        k = np.ones(win) / win
        xs = np.convolve(x, k, mode="same")
        ys = np.convolve(y, k, mode="same")
        edge = win // 2
        return (x - xs)[edge:-edge], (y - ys)[edge:-edge]

    rx1, ry1 = smooth_resid(s1, win=11)
    rx2, ry2 = smooth_resid(s2, win=11)
    sigma_1_x = float(np.std(rx1, ddof=1))
    sigma_1_y = float(np.std(ry1, ddof=1))
    sigma_2_x = float(np.std(rx2, ddof=1))
    sigma_2_y = float(np.std(ry2, ddof=1))
    # 各路平均
    sigma_1 = float(np.sqrt((sigma_1_x ** 2 + sigma_1_y ** 2) / 2))
    sigma_2 = float(np.sqrt((sigma_2_x ** 2 + sigma_2_y ** 2) / 2))

    # 2) 双路差分残差 (跨路) 作对照
    t_lo = max(s1["t"].min(), s2["t"].min() + dt)
    t_hi = min(s1["t"].max(), s2["t"].max() + dt)
    grid = np.linspace(t_lo, t_hi, n_grid)
    rx_diff = fx1(grid) - (fx2(grid - dt) + dx)
    ry_diff = fy1(grid) - (fy2(grid - dt) + dy)
    mask = ~(np.isnan(rx_diff) | np.isnan(ry_diff))
    rx_diff, ry_diff = rx_diff[mask], ry_diff[mask]
    var_diff_x = float(np.var(rx_diff, ddof=1))
    var_diff_y = float(np.var(ry_diff, ddof=1))
    # 假定两路独立: σ_1² + σ_2² = Var(r_diff). 这是已知的 σ_1² + σ_2² 一维约束.

    # 3) 高斯诊断 (基于双路差分残差)
    sd_x = float(np.std(rx_diff, ddof=1))
    sd_y = float(np.std(ry_diff, ddof=1))
    ks_x = kstest((rx_diff - rx_diff.mean()) / sd_x, "norm")
    ks_y = kstest((ry_diff - ry_diff.mean()) / sd_y, "norm")
    ad_x = anderson((rx_diff - rx_diff.mean()) / sd_x, dist="norm")
    ad_y = anderson((ry_diff - ry_diff.mean()) / sd_y, dist="norm")
    rng = np.random.default_rng(0)
    rx_sw = rx_diff if len(rx_diff) <= 5000 else rng.choice(rx_diff, 5000, replace=False)
    ry_sw = ry_diff if len(ry_diff) <= 5000 else rng.choice(ry_diff, 5000, replace=False)
    sw_x = shapiro((rx_sw - rx_sw.mean()) / rx_sw.std(ddof=1))
    sw_y = shapiro((ry_sw - ry_sw.mean()) / ry_sw.std(ddof=1))
    rho_xy, p_rho = pearsonr(rx_diff, ry_diff)
    lb_x = acorr_ljungbox(rx_diff, lags=[10, 20], return_df=True)
    lb_y = acorr_ljungbox(ry_diff, lags=[10, 20], return_df=True)

    return dict(
        # Per-path (Q3 关键)
        sigma_1=sigma_1, sigma_1_x=sigma_1_x, sigma_1_y=sigma_1_y,
        sigma_2=sigma_2, sigma_2_x=sigma_2_x, sigma_2_y=sigma_2_y,
        # Cross-path 校验
        sigma_diff_x=float(np.sqrt(var_diff_x)),
        sigma_diff_y=float(np.sqrt(var_diff_y)),
        sigma_sum_check=float(np.sqrt(sigma_1 ** 2 + sigma_2 ** 2)),
        sigma_diff_observed=float(np.sqrt((var_diff_x + var_diff_y) / 2)),
        # Diagnostics
        rx_diff=rx_diff, ry_diff=ry_diff,
        ks_x_pvalue=float(ks_x.pvalue), ks_y_pvalue=float(ks_y.pvalue),
        ad_x_stat=float(ad_x.statistic), ad_x_critical_5pct=float(ad_x.critical_values[2]),
        ad_y_stat=float(ad_y.statistic), ad_y_critical_5pct=float(ad_y.critical_values[2]),
        sw_x_pvalue=float(sw_x.pvalue), sw_y_pvalue=float(sw_y.pvalue),
        rho_xy=float(rho_xy), rho_xy_pvalue=float(p_rho),
        lb_x_lag10_pvalue=float(lb_x.iloc[0]["lb_pvalue"]),
        lb_x_lag20_pvalue=float(lb_x.iloc[1]["lb_pvalue"]),
        lb_y_lag10_pvalue=float(lb_y.iloc[0]["lb_pvalue"]),
        lb_y_lag20_pvalue=float(lb_y.iloc[1]["lb_pvalue"]),
        residual_mean_x=float(rx_diff.mean()),
        residual_mean_y=float(ry_diff.mean()),
    )


# =====================================================================
# 系统偏差判定 (题面 Q3 第一问)
# =====================================================================
def system_bias_test(s1, s2, dt_hat_full, dx_hat, dy_hat, J_star_full,
                     n_grid: int = 8000):
    """对比 H0: (Δx, Δy)=(0, 0) 与 H1: 自由 (Δx, Δy).

    H0 模型: Δt-only, 强制 Δx=Δy=0. 从 Δt = dt_hat_full 起做 1D Brent 精化.
    H1 模型: full 3-param, 已经在 dt_hat_full, dx_hat, dy_hat 处给出 J*_full.

    使用 F 检验:
        F = (J*_0 - J*_1) / J*_1  × (N - p_full) / (p_full - p_0)
        df_num = p_full - p_0 = 2 (2 个新参数)
        df_den = N - p_full
        若 p < 0.05: 拒绝 H0, 存在系统偏差.

    + Bootstrap CI on (Δx, Δy): 是否包含 0?
    """
    fx2, fy2 = make_interp(s2)

    # H0: Δt-only (Δx=Δy=0). 因为强制 (0, 0), 极小位置可能与 H1 不同 → 全局扫.
    # 步骤: 在可行域粗扫 J(d, 0, 0), 取最小处, 再用 minimize_scalar bounded 精化.
    t1_min, t1_max = float(s1["t"].min()), float(s1["t"].max())
    t2_min, t2_max = float(s2["t"].min()), float(s2["t"].max())
    dt_lo_h0 = t1_min - t2_max + 10.0
    dt_hi_h0 = t1_max - t2_min - 10.0
    grid_h0 = np.arange(dt_lo_h0, dt_hi_h0 + 0.5, 0.5)
    costs_h0 = np.array([alignment_cost_joint([d, 0.0, 0.0], s1, s2, fx2, fy2, 1500)
                         for d in grid_h0])
    i_min = int(np.argmin(costs_h0))
    dt_h0_init = float(grid_h0[i_min])

    # bounded Brent 精化在该极小邻域 (±2 s)
    res0 = minimize_scalar(
        lambda d: alignment_cost_joint([d, 0.0, 0.0], s1, s2, fx2, fy2, 4000),
        bounds=(dt_h0_init - 2.0, dt_h0_init + 2.0),
        method='bounded', options={'xatol': 1e-9})
    dt_h0 = float(res0.x)
    J_h0 = alignment_cost_joint([dt_h0, 0.0, 0.0], s1, s2, fx2, fy2, n_grid)

    # F-test
    # 重叠区点数估计 N (用 8000 网格点近似)
    t_lo = max(s1["t"].min(), s2["t"].min() + dt_hat_full)
    t_hi = min(s1["t"].max(), s2["t"].max() + dt_hat_full)
    # 严格 10 Hz 点数才是真正独立观测数 (上限). 实际 J 由插值积分给出, 自由度更复杂.
    # 这里取 N = 严格 10 Hz 点数作为名义自由度上界.
    N_eff = int(np.floor((t_hi - t_lo) * 10))
    p_full = 3
    p_0 = 1
    df_num = p_full - p_0  # = 2
    df_den = N_eff - p_full
    # F-statistic (using SSR ratio; assumes σ² same; 2D residuals → multiply N by 2)
    SSR_0 = J_h0 * 2 * N_eff  # 2D residuals
    SSR_1 = J_star_full * 2 * N_eff
    F_stat = ((SSR_0 - SSR_1) / df_num) / (SSR_1 / max(df_den, 1))
    p_value = float(1.0 - f_dist.cdf(F_stat, df_num, df_den)) if df_den > 0 else float('nan')

    return dict(
        H0_model="Δt-only (Δx=Δy=0)",
        H1_model="full 3-param",
        dt_under_H0=dt_h0,
        J_star_H0=J_h0,
        dt_under_H1=dt_hat_full,
        dx_under_H1=dx_hat,
        dy_under_H1=dy_hat,
        J_star_H1=J_star_full,
        delta_J_star=float(J_h0 - J_star_full),
        relative_improvement_pct=float(100 * (J_h0 - J_star_full) / J_h0),
        F_statistic=float(F_stat),
        df_numerator=df_num, df_denominator=df_den,
        F_critical_5pct=float(f_dist.ppf(0.95, df_num, df_den)) if df_den > 0 else float('nan'),
        p_value=p_value,
        N_effective_samples=N_eff,
        reject_H0_at_5pct=bool(p_value < 0.05) if not np.isnan(p_value) else False,
        conclusion=(
            "存在系统偏差: F 检验显著拒绝 H0 (Δx=Δy=0)" if p_value < 0.05
            else "无系统偏差或不显著: F 检验未拒绝 H0"
        ),
    )


# =====================================================================
# Bootstrap (复用 Q2 思路, 但残差按 per-path 加扰动)
# =====================================================================
def bootstrap_uncertainty(s1, s2, dt_hat, dx_hat, dy_hat,
                          sigma_1: float, sigma_2: float,
                          n_boot: int = 80, rng_seed: int = 42):
    rng = np.random.default_rng(rng_seed)
    estimates = np.zeros((n_boot, 3))
    for b in range(n_boot):
        s1b = s1.copy(); s2b = s2.copy()
        s1b["x"] = s1b["x"].values + rng.normal(0, sigma_1, len(s1b))
        s1b["y"] = s1b["y"].values + rng.normal(0, sigma_1, len(s1b))
        s2b["x"] = s2b["x"].values + rng.normal(0, sigma_2, len(s2b))
        s2b["y"] = s2b["y"].values + rng.normal(0, sigma_2, len(s2b))
        fx2b, fy2b = make_interp(s2b)
        x0 = np.array([dt_hat, dx_hat, dy_hat])
        res = minimize(
            alignment_cost_joint, x0=x0,
            args=(s1b, s2b, fx2b, fy2b, 4000),
            method="Nelder-Mead",
            options={"xatol": 1e-5, "fatol": 1e-9, "maxiter": 5000})
        estimates[b] = res.x
    return dict(
        n_boot=n_boot,
        dt_mean=float(estimates[:, 0].mean()),
        dt_std=float(estimates[:, 0].std(ddof=1)),
        dx_mean=float(estimates[:, 1].mean()),
        dx_std=float(estimates[:, 1].std(ddof=1)),
        dy_mean=float(estimates[:, 2].mean()),
        dy_std=float(estimates[:, 2].std(ddof=1)),
        dt_ci95=[float(np.percentile(estimates[:, 0], 2.5)),
                 float(np.percentile(estimates[:, 0], 97.5))],
        dx_ci95=[float(np.percentile(estimates[:, 1], 2.5)),
                 float(np.percentile(estimates[:, 1], 97.5))],
        dy_ci95=[float(np.percentile(estimates[:, 2], 2.5)),
                 float(np.percentile(estimates[:, 2], 97.5))],
        estimates=estimates,
    )


# =====================================================================
# 不等方差 BLUE
# =====================================================================
def fuse_10hz_unequal(s1, s2, dt, dx, dy, sigma_1, sigma_2):
    """BLUE 不等方差加权: w_k = (1/σ_k²) / Σ (1/σ_j²)."""
    inv_var_1 = 1.0 / (sigma_1 ** 2)
    inv_var_2 = 1.0 / (sigma_2 ** 2)
    w1 = inv_var_1 / (inv_var_1 + inv_var_2)
    w2 = inv_var_2 / (inv_var_1 + inv_var_2)
    sigma_fused = float(np.sqrt(1.0 / (inv_var_1 + inv_var_2)))
    t_full, x_full, y_full, both, only1, only2 = fuse_10hz(s1, s2, dt, dx, dy, w1, w2)
    return t_full, x_full, y_full, both, only1, only2, w1, w2, sigma_fused


# =====================================================================
# 主流程
# =====================================================================
def solve_q3(path: Path, name: str = "附件3"):
    print("=" * 72)
    print(f"Q3 求解流程  -  {name}")
    print("=" * 72)
    s1, s2 = load_xlsx(path)
    fx2, fy2 = make_interp(s2)
    print(f"[{name}] 方式1: N={len(s1)}, t∈[{s1.t.min():.3f}, {s1.t.max():.3f}]")
    print(f"[{name}] 方式2: N={len(s2)}, t∈[{s2.t.min():.3f}, {s2.t.max():.3f}]")

    # ---- 1. Feasible domain (correct, Q3-specific) ----
    dt_lo, dt_hi = feasible_domain_correct(s1, s2, min_overlap=10.0)
    print(f"\n[1] dt 可行域 (修正): [{dt_lo:.2f}, {dt_hi:.2f}] s")
    grid, costs = coarse_search_correct(s1, s2, fx2, fy2, dt_lo, dt_hi, 1.0)

    # 找局部极小
    is_local_min = np.r_[False,
                         (costs[1:-1] < costs[:-2]) & (costs[1:-1] < costs[2:]),
                         False]
    local_min_idx = np.where(is_local_min)[0]
    K = min(10, len(local_min_idx))
    top_local = sorted(local_min_idx, key=lambda i: costs[i])[:K]
    print(f"\n[2] 完整粗扫: 局部极小数 = {len(local_min_idx)}, 前 {K} 名 J(dt, 0, 0):")
    for i in top_local:
        print(f"    dt = {grid[i]:>+9.2f},  J = {costs[i]:8.4f}")

    # ---- 3. 多候选两阶段 NM 联合精化 (Q3 加: 强制 initial_simplex + 最小重叠门槛) ----
    print(f"\n[3] 两阶段 Nelder-Mead 联合精化 (最小重叠门槛 60 s)")
    MIN_OVERLAP_S = 60.0
    candidates = []
    rejected_short_overlap = []
    best = None
    for i in top_local:
        dt0 = float(grid[i])
        # explicit initial simplex 让 (dx, dy) 维度有 5 m 量级的搜索半径
        # (Q3 噪声 ~3 m, 系统偏差可能 ~0-50 m, 需要更大 simplex)
        init_simplex = np.array([
            [dt0,        0.0, 0.0],
            [dt0 + 1.0,  0.0, 0.0],
            [dt0,        5.0, 0.0],
            [dt0,        0.0, 5.0],
        ])
        res1 = minimize(alignment_cost_joint, x0=init_simplex[0],
                        args=(s1, s2, fx2, fy2, 4000),
                        method="Nelder-Mead",
                        options={"xatol": 1e-7, "fatol": 1e-7,
                                 "maxiter": 5000,
                                 "initial_simplex": init_simplex})
        res = minimize(alignment_cost_joint, x0=res1.x,
                       args=(s1, s2, fx2, fy2, 8000),
                       method="Nelder-Mead",
                       options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 20000})
        # 检查精化解的公共重叠区, 若 < 门槛则丢弃 (避免过拟合到小窗)
        dt_r, dx_r, dy_r = res.x
        t_lo_r = max(s1["t"].min(), s2["t"].min() + dt_r)
        t_hi_r = min(s1["t"].max(), s2["t"].max() + dt_r)
        overlap_r = float(t_hi_r - t_lo_r)
        candidates.append((float(res.fun), tuple(map(float, res.x)),
                           float(grid[i]), overlap_r))
        if overlap_r < MIN_OVERLAP_S:
            rejected_short_overlap.append((res.fun, res.x, overlap_r))
            continue
        if best is None or res.fun < best[0]:
            best = (float(res.fun), tuple(map(float, res.x)), float(grid[i]))

    if rejected_short_overlap:
        print(f"    [被拒绝] {len(rejected_short_overlap)} 个候选重叠 < {MIN_OVERLAP_S} s "
              f"(过拟合风险):")
        for J_r, x_r, ov in rejected_short_overlap:
            print(f"        J*={J_r:.3f}, dt={x_r[0]:.2f}, "
                  f"(dx, dy)=({x_r[1]:+.2f}, {x_r[2]:+.2f}), 重叠={ov:.1f}s")

    candidates_sorted = sorted(candidates, key=lambda x: x[0])
    print(f"\n[{name}] 候选清单 (按 J* 升序; 不含被门槛剔除的):")
    for k, item in enumerate(candidates_sorted[:8]):
        J, (dt_, dx_, dy_), dt0_init, overlap_ = item
        flag = "❌ 重叠不足" if overlap_ < MIN_OVERLAP_S else "✓"
        print(f"    rank {k+1:2}  dt = {dt_:>+9.4f}  "
              f"(dx, dy) = ({dx_:>+7.3f}, {dy_:>+7.3f})  "
              f"J* = {J:7.4f}  重叠 = {overlap_:>6.1f}s  {flag}")

    if best is None:
        raise RuntimeError(f"所有候选重叠 < {MIN_OVERLAP_S}s, 无可用主解!")
    final_cost, (dt_hat, dx_hat, dy_hat), dt0 = best
    print(f"\n[{name}] 主解 (J* 最小, 通过重叠门槛): dt = {dt_hat:.4f}, "
          f"(dx, dy) = ({dx_hat:.4f}, {dy_hat:.4f}), J* = {final_cost:.4f}")

    # ---- 4. σ_dt CR 下界 ----
    def J_dt(dt):
        return alignment_cost_joint([dt, dx_hat, dy_hat], s1, s2, fx2, fy2, 8000)
    h = 0.01
    J0_, Jp_, Jm_ = J_dt(dt_hat), J_dt(dt_hat + h), J_dt(dt_hat - h)
    J2 = (Jp_ - 2 * J0_ + Jm_) / (h ** 2)
    sigma_dt_CR = float(np.sqrt(2 * J0_ / J2)) if J2 > 0 else float("nan")

    # ---- 5. 噪声 + 高斯诊断 (Q3 关键: per-path) ----
    print(f"\n[5] 噪声估计 (per-path)")
    noise = estimate_noise_per_path(s1, s2, dt_hat, dx_hat, dy_hat)
    print(f"    σ_1 (per-path 平滑) = {noise['sigma_1']:.4f} m  "
          f"[X: {noise['sigma_1_x']:.4f}, Y: {noise['sigma_1_y']:.4f}]")
    print(f"    σ_2 (per-path 平滑) = {noise['sigma_2']:.4f} m  "
          f"[X: {noise['sigma_2_x']:.4f}, Y: {noise['sigma_2_y']:.4f}]")
    print(f"    σ₁² + σ₂² = {noise['sigma_sum_check']:.4f},  "
          f"双路差分 σ_diff = {noise['sigma_diff_observed']:.4f}  (应近似一致)")
    print(f"    KS p (X) = {noise['ks_x_pvalue']:.4f}, KS p (Y) = {noise['ks_y_pvalue']:.4f}")
    print(f"    AD (X) = {noise['ad_x_stat']:.3f} (5% crit {noise['ad_x_critical_5pct']:.3f}), "
          f"AD (Y) = {noise['ad_y_stat']:.3f}")
    print(f"    SW p (X) = {noise['sw_x_pvalue']:.4f}, SW p (Y) = {noise['sw_y_pvalue']:.4f}")
    print(f"    Ljung-Box X@10/20 p = {noise['lb_x_lag10_pvalue']:.4f} / "
          f"{noise['lb_x_lag20_pvalue']:.4f}")

    # ---- 6. 系统偏差判定 (Q3 第一问) ----
    print(f"\n[6] 系统偏差假设检验")
    sb_test = system_bias_test(s1, s2, dt_hat, dx_hat, dy_hat, final_cost)
    print(f"    H0 (Δx=Δy=0): J*_0 = {sb_test['J_star_H0']:.4f}")
    print(f"    H1 (full):    J*_1 = {sb_test['J_star_H1']:.4f}")
    print(f"    ΔJ*  = {sb_test['delta_J_star']:.4f} ({sb_test['relative_improvement_pct']:.1f}% 改进)")
    print(f"    F 统计量 = {sb_test['F_statistic']:.2f}, "
          f"df=({sb_test['df_numerator']},{sb_test['df_denominator']})")
    print(f"    F 5% 临界 = {sb_test['F_critical_5pct']:.4f}, p = {sb_test['p_value']:.6e}")
    print(f"    → {sb_test['conclusion']}")

    # ---- 7. Bootstrap (per-path noise) ----
    print(f"\n[7] Bootstrap (B=80, σ_1={noise['sigma_1']:.3f}, σ_2={noise['sigma_2']:.3f})")
    boot = bootstrap_uncertainty(s1, s2, dt_hat, dx_hat, dy_hat,
                                 sigma_1=noise['sigma_1'], sigma_2=noise['sigma_2'],
                                 n_boot=80)
    print(f"    σ_dt = {boot['dt_std']:.4f},  CI95 = "
          f"[{boot['dt_ci95'][0]:.4f}, {boot['dt_ci95'][1]:.4f}]")
    print(f"    σ_dx = {boot['dx_std']:.4f},  CI95 = "
          f"[{boot['dx_ci95'][0]:.4f}, {boot['dx_ci95'][1]:.4f}]")
    print(f"    σ_dy = {boot['dy_std']:.4f},  CI95 = "
          f"[{boot['dy_ci95'][0]:.4f}, {boot['dy_ci95'][1]:.4f}]")
    contains_zero_dx = (boot['dx_ci95'][0] <= 0 <= boot['dx_ci95'][1])
    contains_zero_dy = (boot['dy_ci95'][0] <= 0 <= boot['dy_ci95'][1])
    print(f"    Δx CI95 包含 0? {contains_zero_dx}")
    print(f"    Δy CI95 包含 0? {contains_zero_dy}")

    # ---- 8. 不等方差 BLUE 静态融合 ----
    print(f"\n[8] BLUE 静态融合 (不等方差加权)")
    t_full, x_full, y_full, both, only1, only2, w1, w2, sigma_fused = fuse_10hz_unequal(
        s1, s2, dt_hat, dx_hat, dy_hat, noise['sigma_1'], noise['sigma_2'])
    t_int = t_full[both]
    x_int = x_full[both]
    y_int = y_full[both]
    print(f"    BLUE 权重: w_1 = {w1:.4f}, w_2 = {w2:.4f}")
    print(f"    融合后 σ = {sigma_fused:.4f} m  (vs 单路 σ_1={noise['sigma_1']:.3f}, σ_2={noise['sigma_2']:.3f})")
    print(f"    全覆盖 {len(t_full)} 点, 严格交集 {len(t_int)} 点, 物理时间 [{t_full[0]:.2f}, {t_full[-1]:.2f}] s")

    # ---- 9. KF + RTS 融合 (per-source R) ----
    print(f"\n[9] Kalman + RTS 融合")
    sigma_a = 1.5  # m/s², 车辆级机动 (Q2 是 0.5 机器人级)
    times_kf, sm_states, sm_covs, fwd_states, fwd_covs, nis = fuse_kf_rts(
        s1, s2, dt_hat, dx_hat, dy_hat,
        sigma_1=noise['sigma_1'], sigma_2=noise['sigma_2'],
        sigma_a=sigma_a)
    t_kf, x_kf, y_kf, vx_kf, vy_kf, var_x_kf, var_y_kf = resample_to_10hz(
        times_kf, sm_states, sm_covs)
    nis_mean = float(np.mean(nis[1:]))
    print(f"    σ_a (过程噪声) = {sigma_a} m/s² (车辆级机动)")
    print(f"    KF 观测数 = {len(times_kf)}, 10 Hz 点数 = {len(t_kf)}")
    print(f"    后验 σ²_x = {float(np.nanmean(var_x_kf)):.4f}, "
          f"σ²_y = {float(np.nanmean(var_y_kf)):.4f}  "
          f"(BLUE σ² = {sigma_fused**2:.4f})")
    print(f"    NIS 均值 = {nis_mean:.3f} (期望 2)")

    # ---- 10. 汇总 JSON ----
    summary = dict(
        attachment=name,
        feasible_domain=[dt_lo, dt_hi],
        dt_hat_seconds=dt_hat,
        dt_sigma_seconds_CR=sigma_dt_CR,
        dx_hat_meters=dx_hat,
        dy_hat_meters=dy_hat,
        joint_final_cost_m2=final_cost,
        coarse_dt0=dt0,
        candidates=[
            {"rank": k + 1, "J_star": J, "dt": dtv, "dx": dxv, "dy": dyv,
             "overlap_s": ov,
             "rejected_short_overlap": bool(ov < MIN_OVERLAP_S)}
            for k, (J, (dtv, dxv, dyv), _, ov) in enumerate(candidates_sorted)
        ],
        min_overlap_threshold_s=MIN_OVERLAP_S,
        noise=dict(
            sigma_1=noise['sigma_1'], sigma_1_x=noise['sigma_1_x'], sigma_1_y=noise['sigma_1_y'],
            sigma_2=noise['sigma_2'], sigma_2_x=noise['sigma_2_x'], sigma_2_y=noise['sigma_2_y'],
            sigma_diff_x=noise['sigma_diff_x'], sigma_diff_y=noise['sigma_diff_y'],
            sigma_sum_check_self=noise['sigma_sum_check'],
            sigma_diff_observed=noise['sigma_diff_observed'],
            cross_correlation_rho=noise['rho_xy'],
            cross_correlation_pvalue=noise['rho_xy_pvalue'],
            residual_mean_x=noise['residual_mean_x'],
            residual_mean_y=noise['residual_mean_y'],
        ),
        gaussian_diagnostics=dict(
            ks_x_pvalue=noise['ks_x_pvalue'],
            ks_y_pvalue=noise['ks_y_pvalue'],
            ad_x_stat=noise['ad_x_stat'], ad_x_critical_5pct=noise['ad_x_critical_5pct'],
            ad_y_stat=noise['ad_y_stat'], ad_y_critical_5pct=noise['ad_y_critical_5pct'],
            sw_x_pvalue=noise['sw_x_pvalue'],
            sw_y_pvalue=noise['sw_y_pvalue'],
        ),
        ljung_box=dict(
            x_lag10_pvalue=noise['lb_x_lag10_pvalue'],
            x_lag20_pvalue=noise['lb_x_lag20_pvalue'],
            y_lag10_pvalue=noise['lb_y_lag10_pvalue'],
            y_lag20_pvalue=noise['lb_y_lag20_pvalue'],
        ),
        system_bias_test=sb_test,
        bootstrap=dict(
            n_boot=boot['n_boot'],
            dt_mean=boot['dt_mean'], dt_std=boot['dt_std'], dt_ci95=boot['dt_ci95'],
            dx_mean=boot['dx_mean'], dx_std=boot['dx_std'], dx_ci95=boot['dx_ci95'],
            dy_mean=boot['dy_mean'], dy_std=boot['dy_std'], dy_ci95=boot['dy_ci95'],
            dx_ci95_contains_zero=bool(contains_zero_dx),
            dy_ci95_contains_zero=bool(contains_zero_dy),
        ),
        kalman=dict(
            sigma_a_process=sigma_a,
            n_observations=int(len(times_kf)),
            n_resampled_10hz=int(len(t_kf)),
            t_range=[float(t_kf[0]), float(t_kf[-1])],
            posterior_var_x_mean=float(np.nanmean(var_x_kf)),
            posterior_var_y_mean=float(np.nanmean(var_y_kf)),
            nis_mean=nis_mean,
            nis_consistency_2dof_target=2.0,
        ),
        weights_static=dict(w1=w1, w2=w2, sigma_fused_blue=sigma_fused),
        n_full_coverage_static=int(len(t_full)),
        n_strict_intersection_static=int(len(t_int)),
        n_only_method1=int(np.sum(only1)),
        n_only_method2=int(np.sum(only2)),
        t_full_range=[float(t_full[0]), float(t_full[-1])],
    )

    # ---- 11. 输出 Excel ----
    pd.DataFrame({"time_s": t_full, "X_m": x_full, "Y_m": y_full}).to_excel(
        OUT / "Q3_trajectory_10Hz.xlsx", index=False)
    pd.DataFrame({"time_s": t_int, "X_m": x_int, "Y_m": y_int}).to_excel(
        OUT / "Q3_trajectory_10Hz_strict.xlsx", index=False)
    pd.DataFrame({
        "time_s": t_kf, "X_m": x_kf, "Y_m": y_kf,
        "Vx_m_s": vx_kf, "Vy_m_s": vy_kf,
        "var_X": var_x_kf, "var_Y": var_y_kf,
    }).to_excel(OUT / "Q3_trajectory_10Hz_kalman.xlsx", index=False)
    print(f"\n[输出] Q3_trajectory_10Hz{{,_strict,_kalman}}.xlsx")

    # ---- 12. 出图 ----
    plot_all(s1, s2, dt_hat, dx_hat, dy_hat, grid, costs, candidates_sorted,
             noise, sb_test, boot, t_full, x_full, y_full, t_int, both,
             t_kf, x_kf, y_kf, vx_kf, vy_kf, var_x_kf, var_y_kf, nis,
             times_kf, fwd_covs, sm_covs, name)

    return summary


def plot_all(s1, s2, dt_hat, dx_hat, dy_hat, grid, costs, candidates_sorted,
             noise, sb_test, boot, t_full, x_full, y_full, t_int, both,
             t_kf, x_kf, y_kf, vx_kf, vy_kf, var_x_kf, var_y_kf, nis,
             times_kf, fwd_covs, sm_covs, name):
    fx2, fy2 = make_interp(s2)
    fx1, fy1 = make_interp(s1)

    # === 图 1: alignment ===
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    ax = axes[0, 0]
    ax.semilogy(grid, costs, lw=0.7, alpha=0.8)
    ax.axvline(dt_hat, color="r", ls="--", label=f"主解 Δt={dt_hat:.4f}")
    ax.set_xlabel("Δt (s)"); ax.set_ylabel("J(Δt, 0, 0) (m²)")
    ax.set_title(f"全局粗扫 J(Δt, 0, 0) — {name}")
    ax.legend(); ax.grid(alpha=0.3)

    ax = axes[0, 1]
    grid2 = np.linspace(dt_hat - 5, dt_hat + 5, 200)
    costs2 = [alignment_cost_dt(d, s1, s2, fx2, fy2, 4000) for d in grid2]
    ax.plot(grid2, costs2, 'b-', lw=1)
    ax.axvline(dt_hat, color='r', ls='--', label=f"Δt={dt_hat:.4f}")
    ax.set_xlabel("Δt (s)"); ax.set_ylabel("J (m²)")
    ax.set_title("精扫 (主 basin 邻域)")
    ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1, 0]
    t_lo = max(s1.t.min(), s2.t.min() + dt_hat)
    t_hi = min(s1.t.max(), s2.t.max() + dt_hat)
    g = np.linspace(t_lo, t_hi, 4000)
    ax.plot(g, fx1(g), 'b-', lw=0.6, alpha=0.7, label='方式1 X')
    ax.plot(g, fx2(g - dt_hat) + dx_hat, 'r-', lw=0.6, alpha=0.7, label='方式2 X (校正)')
    ax.set_xlabel("物理时间 τ (s)"); ax.set_ylabel("X (m)")
    ax.set_title("对齐后 X(τ) 重合")
    ax.legend(); ax.grid(alpha=0.3)

    ax = axes[1, 1]
    ax.plot(t_full, x_full, 'g-', lw=0.4, alpha=0.7, label='X 静态融合')
    ax.plot(t_full, y_full, 'orange', lw=0.4, alpha=0.7, label='Y 静态融合')
    ax.set_xlabel("τ (s)"); ax.set_ylabel("位置 (m)")
    ax.set_title(f"10 Hz 静态融合 (共 {len(t_full)} 点)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q3_alignment.png', dpi=200); plt.close()

    # === 图 2: residual_diag ===
    rx = noise['rx_diff']; ry = noise['ry_diff']
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    axes[0, 0].hist(rx, bins=80, density=True, alpha=0.7, color='b')
    xv = np.linspace(rx.min(), rx.max(), 200)
    sd = np.std(rx, ddof=1)
    axes[0, 0].plot(xv, np.exp(-0.5 * (xv / sd) ** 2) / (sd * np.sqrt(2 * np.pi)),
                    'r-', lw=1.5, label=f'N(0, {sd:.2f}²)')
    axes[0, 0].set_title(f'X 残差 (双路差分): σ={sd:.3f} m')
    axes[0, 0].legend(); axes[0, 0].grid(alpha=0.3)

    axes[0, 1].hist(ry, bins=80, density=True, alpha=0.7, color='r')
    yv = np.linspace(ry.min(), ry.max(), 200)
    sd = np.std(ry, ddof=1)
    axes[0, 1].plot(yv, np.exp(-0.5 * (yv / sd) ** 2) / (sd * np.sqrt(2 * np.pi)),
                    'b-', lw=1.5, label=f'N(0, {sd:.2f}²)')
    axes[0, 1].set_title(f'Y 残差: σ={sd:.3f} m')
    axes[0, 1].legend(); axes[0, 1].grid(alpha=0.3)

    from scipy.stats import probplot
    probplot((rx - rx.mean()) / np.std(rx, ddof=1), dist='norm', plot=axes[1, 0])
    axes[1, 0].set_title(f"Q-Q plot X (KS p={noise['ks_x_pvalue']:.3f}, AD={noise['ad_x_stat']:.2f})")
    axes[1, 0].grid(alpha=0.3)
    probplot((ry - ry.mean()) / np.std(ry, ddof=1), dist='norm', plot=axes[1, 1])
    axes[1, 1].set_title(f"Q-Q plot Y (KS p={noise['ks_y_pvalue']:.3f}, AD={noise['ad_y_stat']:.2f})")
    axes[1, 1].grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q3_residual_diag.png', dpi=200); plt.close()

    # === 图 3: bootstrap ===
    est = boot['estimates']
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, vals, name_ in zip(axes, [est[:, 0], est[:, 1], est[:, 2]],
                                ['Δt (s)', 'Δx (m)', 'Δy (m)']):
        ax.hist(vals, bins=20, color='steelblue', alpha=0.8)
        ax.axvline(np.mean(vals), color='r', ls='--',
                   label=f'mean={np.mean(vals):.3f}')
        ax.set_title(f'Bootstrap {name_} (B={boot["n_boot"]})')
        ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q3_bootstrap.png', dpi=200); plt.close()

    # === 图 4: KF vs static comparison + NIS ===
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    # (a) 整段轨迹 X(t)
    ax = axes[0, 0]
    ax.plot(t_full, x_full, 'gray', lw=0.4, alpha=0.6, label='静态融合')
    ax.plot(t_kf, x_kf, 'r-', lw=0.7, alpha=0.9, label='KF+RTS')
    ax.set_xlabel("τ (s)"); ax.set_ylabel("X (m)")
    ax.set_title("KF/RTS vs 静态融合 (全段)"); ax.legend(); ax.grid(alpha=0.3)
    # (b) 30s 窗
    t_mid = (t_kf[0] + t_kf[-1]) / 2
    mask_kf = (t_kf > t_mid - 15) & (t_kf < t_mid + 15)
    mask_full = (t_full > t_mid - 15) & (t_full < t_mid + 15)
    ax = axes[0, 1]
    ax.plot(t_full[mask_full], x_full[mask_full], color='gray', marker='.', ls='-',
            alpha=0.6, lw=0.5, label='静态')
    ax.plot(t_kf[mask_kf], x_kf[mask_kf], 'r-', lw=1, label='KF+RTS')
    ax.set_xlabel("τ (s)"); ax.set_ylabel("X (m)")
    ax.set_title("30 s 局部窗口对比"); ax.legend(); ax.grid(alpha=0.3)
    # (c) 后验方差
    ax = axes[1, 0]
    ax.plot(t_kf, var_x_kf, 'b-', lw=0.6, label='σ²_x')
    ax.plot(t_kf, var_y_kf, 'r-', lw=0.6, label='σ²_y')
    ax.axhline(0.5 * boot.get('dt_std', 0), color='gray', ls=':')
    ax.set_xlabel("τ (s)"); ax.set_ylabel("KF 后验方差 (m²)")
    ax.set_title(f"KF/RTS 后验方差时序")
    ax.legend(); ax.grid(alpha=0.3)
    # (d) NIS
    ax = axes[1, 1]
    ax.plot(times_kf, nis, 'b.', ms=1.2, alpha=0.5)
    ax.axhline(2.0, color='g', ls='--', label='期望 χ²(2) = 2')
    ax.axhline(np.mean(nis[1:]), color='r', ls='--',
               label=f"实测均值 = {np.mean(nis[1:]):.2f}")
    ax.set_xlabel("τ (s)"); ax.set_ylabel("NIS")
    ax.set_title("NIS 一致性诊断"); ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q3_kalman_compare.png', dpi=200); plt.close()

    # === 图 5: 系统偏差检验可视化 ===
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    # (a) ΔJ 改进
    ax = axes[0]
    bars = ax.bar(['H0: Δx=Δy=0', 'H1: full'],
                  [sb_test['J_star_H0'], sb_test['J_star_H1']],
                  color=['gray', 'green'], alpha=0.8)
    for bar, val in zip(bars, [sb_test['J_star_H0'], sb_test['J_star_H1']]):
        ax.text(bar.get_x() + bar.get_width() / 2, val * 1.02,
                f'{val:.3f}', ha='center')
    ax.set_ylabel("J* (m²)")
    ax.set_title(f"H0 vs H1 联合代价  (改进 {sb_test['relative_improvement_pct']:.1f}%)")
    ax.grid(alpha=0.3, axis='y')

    # (b) (Δx, Δy) Bootstrap CI
    ax = axes[1]
    ax.errorbar([0], [boot['dx_mean']],
                yerr=[[boot['dx_mean'] - boot['dx_ci95'][0]],
                      [boot['dx_ci95'][1] - boot['dx_mean']]],
                fmt='ro', capsize=8, label=f'Δx CI95')
    ax.errorbar([1], [boot['dy_mean']],
                yerr=[[boot['dy_mean'] - boot['dy_ci95'][0]],
                      [boot['dy_ci95'][1] - boot['dy_mean']]],
                fmt='go', capsize=8, label=f'Δy CI95')
    ax.axhline(0, color='black', lw=1, ls='--', alpha=0.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(['Δx', 'Δy'])
    ax.set_ylabel("空间偏差 (m)")
    ax.set_title(f"Bootstrap CI ({sb_test['conclusion'][:20]}...)")
    ax.legend(); ax.grid(alpha=0.3)
    plt.tight_layout(); plt.savefig(FIGS / 'Q3_system_bias_test.png', dpi=200); plt.close()


if __name__ == '__main__':
    np.random.seed(20260105)
    summary = solve_q3(DATA / "附件3.xlsx", "附件3")
    summary_no_arrays = {k: v for k, v in summary.items()
                         if not isinstance(v, np.ndarray)}
    (OUT / "Q3_summary.json").write_text(
        json.dumps(summary_no_arrays, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    print(f"\n[输出] Q3_summary.json")
