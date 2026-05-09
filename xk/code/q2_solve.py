"""Q2: Attachment-2 alignment + fusion (noise + system bias).

Pipeline:
    1) Joint estimation (dt, dx, dy) by least-squares
    2) Noise estimation from post-alignment two-path residual
       (assuming independent equal-variance Gaussian noise on each path)
    3) Gaussian residual diagnostics (QQ-plot, KS-test)
    4) Inverse-variance weighted 10 Hz fusion
    5) Outputs:
        output/Q2_summary.json
        output/Q2_trajectory_10Hz.xlsx          full coverage
        output/Q2_trajectory_10Hz_strict.xlsx   strict intersection
        figures/Q2_alignment.png
        figures/Q2_residual_diag.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import minimize, minimize_scalar
from scipy.stats import kstest, norm, probplot, anderson, shapiro, pearsonr
from statsmodels.stats.diagnostic import acorr_ljungbox

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "A"))
sys.path.insert(0, str(ROOT / "code"))
from plot_style import setup_plot_style  # noqa: E402
from q_utils import (  # noqa: E402
    load_xlsx, make_interp, feasible_domain,
    alignment_cost_dt, alignment_cost_joint,
    estimate_dt_uncertainty, coarse_search_dt, fuse_10hz,
)
from q2_kalman import fuse_kf_rts, resample_to_10hz  # noqa: E402

setup_plot_style()

DATA = ROOT / "data"
FIGS = ROOT / "figures"
OUT = ROOT / "output"


def estimate_noise_two_path(s1, s2, dt, dx, dy, n_grid: int = 8000):
    """Compute residual diff = p1(tau) - p2(tau-dt) - (dx, dy) on overlap.
    Under H0 of independent equal-variance Gaussian noise N(0, sigma^2) on each path,
        Var[diff_x] = Var[diff_y] = 2*sigma^2
    Returns: dict with sigma_per_path, diff arrays, KS p-values, etc.
    """
    fx1, fy1 = make_interp(s1)
    fx2, fy2 = make_interp(s2)
    t_lo = max(s1["t"].min(), s2["t"].min() + dt)
    t_hi = min(s1["t"].max(), s2["t"].max() + dt)
    grid = np.linspace(t_lo, t_hi, n_grid)
    rx = fx1(grid) - (fx2(grid - dt) + dx)
    ry = fy1(grid) - (fy2(grid - dt) + dy)
    rx = rx[~np.isnan(rx)]
    ry = ry[~np.isnan(ry)]

    var_diff_x = float(np.var(rx, ddof=1))
    var_diff_y = float(np.var(ry, ddof=1))
    sigma_per_path_x = float(np.sqrt(var_diff_x / 2))
    sigma_per_path_y = float(np.sqrt(var_diff_y / 2))
    sigma_per_path = float(np.sqrt((var_diff_x + var_diff_y) / 4))

    # KS test against N(mu, sigma_diff)
    sigma_diff_x = float(np.std(rx, ddof=1))
    sigma_diff_y = float(np.std(ry, ddof=1))
    ks_x = kstest((rx - rx.mean()) / sigma_diff_x, "norm")
    ks_y = kstest((ry - ry.mean()) / sigma_diff_y, "norm")

    # Anderson-Darling (more sensitive to tails)
    ad_x = anderson((rx - rx.mean()) / sigma_diff_x, dist="norm")
    ad_y = anderson((ry - ry.mean()) / sigma_diff_y, dist="norm")
    # Shapiro-Wilk (subsample if too long)
    rx_sw = rx if len(rx) <= 5000 else np.random.default_rng(0).choice(rx, 5000, replace=False)
    ry_sw = ry if len(ry) <= 5000 else np.random.default_rng(0).choice(ry, 5000, replace=False)
    sw_x = shapiro((rx_sw - rx_sw.mean()) / rx_sw.std(ddof=1))
    sw_y = shapiro((ry_sw - ry_sw.mean()) / ry_sw.std(ddof=1))
    # Cross-dimension correlation
    rho_xy, p_rho = pearsonr(rx, ry)
    # Ljung-Box for residual autocorrelation
    lb_x = acorr_ljungbox(rx, lags=[10, 20], return_df=True)
    lb_y = acorr_ljungbox(ry, lags=[10, 20], return_df=True)

    return dict(
        rx=rx, ry=ry,
        sigma_diff_x=sigma_diff_x,
        sigma_diff_y=sigma_diff_y,
        sigma_per_path_x=sigma_per_path_x,
        sigma_per_path_y=sigma_per_path_y,
        sigma_per_path=sigma_per_path,
        ks_x_stat=float(ks_x.statistic),
        ks_x_pvalue=float(ks_x.pvalue),
        ks_y_stat=float(ks_y.statistic),
        ks_y_pvalue=float(ks_y.pvalue),
        ad_x_stat=float(ad_x.statistic),
        ad_x_critical_5pct=float(ad_x.critical_values[2]),
        ad_y_stat=float(ad_y.statistic),
        ad_y_critical_5pct=float(ad_y.critical_values[2]),
        sw_x_stat=float(sw_x.statistic),
        sw_x_pvalue=float(sw_x.pvalue),
        sw_y_stat=float(sw_y.statistic),
        sw_y_pvalue=float(sw_y.pvalue),
        rho_xy=float(rho_xy),
        rho_xy_pvalue=float(p_rho),
        lb_x_lag10_stat=float(lb_x.iloc[0]["lb_stat"]),
        lb_x_lag10_pvalue=float(lb_x.iloc[0]["lb_pvalue"]),
        lb_x_lag20_stat=float(lb_x.iloc[1]["lb_stat"]),
        lb_x_lag20_pvalue=float(lb_x.iloc[1]["lb_pvalue"]),
        lb_y_lag10_stat=float(lb_y.iloc[0]["lb_stat"]),
        lb_y_lag10_pvalue=float(lb_y.iloc[0]["lb_pvalue"]),
        lb_y_lag20_stat=float(lb_y.iloc[1]["lb_stat"]),
        lb_y_lag20_pvalue=float(lb_y.iloc[1]["lb_pvalue"]),
        residual_mean_x=float(rx.mean()),
        residual_mean_y=float(ry.mean()),
    )


def bootstrap_uncertainty(s1, s2, dt_hat, dx_hat, dy_hat,
                          sigma_per_path: float,
                          n_boot: int = 80,
                          rng_seed: int = 42):
    """Parametric bootstrap (Gaussian residual) for (Δt, Δx, Δy).

    Resampling strategy:
      Method-1 sample positions are taken as ground-truth (within their own noise).
      For each iteration b:
        - Add fresh Gaussian noise with σ̂ to each method-1 sample → s1*
        - Add fresh Gaussian noise with σ̂ to each method-2 sample → s2*
        - Re-estimate (Δt, Δx, Δy) via local Nelder-Mead from (Δt̂, Δx̂, Δŷ)
      Return std + 95% CI of resulting parameter array.
    """
    rng = np.random.default_rng(rng_seed)
    estimates = np.zeros((n_boot, 3))

    for b in range(n_boot):
        s1b = s1.copy()
        s2b = s2.copy()
        s1b["x"] = s1b["x"].values + rng.normal(0, sigma_per_path, len(s1b))
        s1b["y"] = s1b["y"].values + rng.normal(0, sigma_per_path, len(s1b))
        s2b["x"] = s2b["x"].values + rng.normal(0, sigma_per_path, len(s2b))
        s2b["y"] = s2b["y"].values + rng.normal(0, sigma_per_path, len(s2b))
        fx2b, fy2b = make_interp(s2b)
        x0 = np.array([dt_hat, dx_hat, dy_hat])
        res = minimize(
            alignment_cost_joint,
            x0=x0,
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


def solve_q2(path: Path, name: str = "Attachment 2"):
    s1, s2 = load_xlsx(path)
    fx2, fy2 = make_interp(s2)

    # ---------- 1. Coarse search + multi-minimum local refinement ----------
    dt_lo, dt_hi = feasible_domain(s1, s2)
    print(f"[{name}] dt feasible: [{dt_lo:.2f}, {dt_hi:.2f}] s")
    grid, costs = coarse_search_dt(s1, s2, fx2, fy2, dt_lo, dt_hi, 1.0)

    # Find all local minima in the coarse cost (周期性可能导致多极小)
    is_local_min = np.r_[False,
                         (costs[1:-1] < costs[:-2]) & (costs[1:-1] < costs[2:]),
                         False]
    local_min_idx = np.where(is_local_min)[0]
    # Sort by cost ascending, pick top-K candidates
    K = min(10, len(local_min_idx))
    top_local = sorted(local_min_idx, key=lambda i: costs[i])[:K]
    print(f"[{name}] coarse local minima count={len(local_min_idx)}, top-{K} costs:")
    for i in top_local:
        print(f"    dt={grid[i]:.2f}, J={costs[i]:.4f}")

    # For each candidate, run TWO-STAGE Nelder-Mead, compare final J.
    # 单阶段 NM 在某些盆地里会卡在浅鞍点 (e.g. 原 C4 卡在 J=3.14, 真值 1.83);
    # 两阶段 NM (粗 + 细 + 加密积分网格) 大幅降低早停风险.
    best = None
    candidates = []
    for i in top_local:
        x0 = np.array([float(grid[i]), 0.0, 0.0])
        # Stage 1: rough convergence
        res1 = minimize(
            alignment_cost_joint,
            x0=x0,
            args=(s1, s2, fx2, fy2, 4000),
            method="Nelder-Mead",
            options={"xatol": 1e-7, "fatol": 1e-7, "maxiter": 5000},
        )
        # Stage 2: tight refinement on a denser grid, init = stage-1 solution
        res_i = minimize(
            alignment_cost_joint,
            x0=res1.x,
            args=(s1, s2, fx2, fy2, 8000),
            method="Nelder-Mead",
            options={"xatol": 1e-10, "fatol": 1e-12, "maxiter": 20000},
        )
        candidates.append((float(res_i.fun), tuple(map(float, res_i.x))))
        if best is None or res_i.fun < best[0]:
            best = (float(res_i.fun), tuple(map(float, res_i.x)), float(grid[i]))

    print(f"\n[{name}] candidates after joint refinement (sorted by J):")
    for J, (dt_, dx_, dy_) in sorted(candidates):
        print(f"    J={J:.4f}, dt={dt_:.4f}, dx={dx_:.4f}, dy={dy_:.4f}")

    final_cost, (dt_hat, dx_hat, dy_hat), dt0 = best
    print(f"\n[{name}] selected best: dt={dt_hat:.4f}, dx={dx_hat:.4f}, "
          f"dy={dy_hat:.4f}, J*={final_cost:.4f}")

    # For diagnostics: also do a fine scan around the chosen dt
    grid2, costs2 = coarse_search_dt(s1, s2, fx2, fy2, dt_hat - 1, dt_hat + 1, 0.01)

    # dt uncertainty (post-noise) from 2nd-order finite diff on joint cost as func of dt
    def J_dt(dt):
        return alignment_cost_joint([dt, dx_hat, dy_hat], s1, s2, fx2, fy2, 8000)
    h = 0.01
    J0_, Jp_, Jm_ = J_dt(dt_hat), J_dt(dt_hat + h), J_dt(dt_hat - h)
    J2 = (Jp_ - 2 * J0_ + Jm_) / (h ** 2)
    sigma_dt = float(np.sqrt(2 * J0_ / J2)) if J2 > 0 else float("nan")

    # ---------- 3. Noise estimation + Gaussian diagnostics ----------
    noise = estimate_noise_two_path(s1, s2, dt_hat, dx_hat, dy_hat)

    # ---------- 4. Inverse-variance weighting (here approx equal weight) ----------
    sx = noise["sigma_per_path_x"]
    sy = noise["sigma_per_path_y"]
    # If two paths have *equal* sigma, weights = 1/2 each. Here they're identical by assumption.
    w1, w2 = 0.5, 0.5

    t_full, x_full, y_full, mask_both, only1, only2 = fuse_10hz(
        s1, s2, dt_hat, dx_hat, dy_hat, w1, w2)
    t_int = t_full[mask_both]
    x_int = x_full[mask_both]
    y_int = y_full[mask_both]

    # ---------- 4b. Kalman + RTS Smoother fusion ----------
    print(f"[{name}] Running Kalman+RTS fusion ...")
    sigma_a = 0.5  # process noise (m/s^2). See sensitivity in summary.
    times_kf, sm_states, sm_covs, fwd_states, fwd_covs, nis = fuse_kf_rts(
        s1, s2, dt_hat, dx_hat, dy_hat, sx, sy, sigma_a=sigma_a)
    t_kf, x_kf, y_kf, vx_kf, vy_kf, var_x_kf, var_y_kf = resample_to_10hz(
        times_kf, sm_states, sm_covs)
    nis_mean = float(np.mean(nis[1:]))  # NIS ~ chi2(2), mean should be 2 if model correct

    # ---------- 4c. Bootstrap uncertainty ----------
    print(f"[{name}] Bootstrap (parametric, sigma={noise['sigma_per_path']:.3f} m) ...")
    boot = bootstrap_uncertainty(
        s1, s2, dt_hat, dx_hat, dy_hat,
        sigma_per_path=noise["sigma_per_path"],
        n_boot=80)
    print(f"  bootstrap σ_Δt = {boot['dt_std']:.4f} s "
          f"(CR-LB σ_Δt = {sigma_dt:.4f} s)")
    print(f"  bootstrap σ_Δx = {boot['dx_std']:.4f} m, σ_Δy = {boot['dy_std']:.4f} m")

    # Persist sorted candidate list for论文 §4.6 多盆地表
    candidates_sorted = sorted(candidates, key=lambda x: x[0])
    candidate_list = [
        {"rank": k + 1, "J_star": J, "dt": dtv, "dx": dxv, "dy": dyv}
        for k, (J, (dtv, dxv, dyv)) in enumerate(candidates_sorted)
    ]

    summary = dict(
        attachment=name,
        feasible_domain=[dt_lo, dt_hi],
        dt_hat_seconds=dt_hat,
        dt_sigma_seconds_CR=sigma_dt,
        dx_hat_meters=dx_hat,
        dy_hat_meters=dy_hat,
        joint_final_cost_m2=final_cost,
        coarse_dt0=dt0,
        candidates=candidate_list,
        noise=dict(
            sigma_diff_x_m=noise["sigma_diff_x"],
            sigma_diff_y_m=noise["sigma_diff_y"],
            sigma_per_path_x_m=noise["sigma_per_path_x"],
            sigma_per_path_y_m=noise["sigma_per_path_y"],
            sigma_per_path_m=noise["sigma_per_path"],
            residual_mean_x=noise["residual_mean_x"],
            residual_mean_y=noise["residual_mean_y"],
            cross_correlation_rho=noise["rho_xy"],
            cross_correlation_pvalue=noise["rho_xy_pvalue"],
        ),
        gaussian_diagnostics=dict(
            ks_x_pvalue=noise["ks_x_pvalue"],
            ks_y_pvalue=noise["ks_y_pvalue"],
            ad_x_stat=noise["ad_x_stat"],
            ad_x_critical_5pct=noise["ad_x_critical_5pct"],
            ad_y_stat=noise["ad_y_stat"],
            ad_y_critical_5pct=noise["ad_y_critical_5pct"],
            shapiro_x_pvalue=noise["sw_x_pvalue"],
            shapiro_y_pvalue=noise["sw_y_pvalue"],
        ),
        ljung_box=dict(
            x_lag10_pvalue=noise["lb_x_lag10_pvalue"],
            x_lag20_pvalue=noise["lb_x_lag20_pvalue"],
            y_lag10_pvalue=noise["lb_y_lag10_pvalue"],
            y_lag20_pvalue=noise["lb_y_lag20_pvalue"],
            interpretation=("p > 0.05 supports white-noise H0; "
                            "low p indicates serial correlation."),
        ),
        bootstrap=dict(
            n_boot=boot["n_boot"],
            dt_std=boot["dt_std"], dt_ci95=boot["dt_ci95"],
            dx_std=boot["dx_std"], dx_ci95=boot["dx_ci95"],
            dy_std=boot["dy_std"], dy_ci95=boot["dy_ci95"],
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
            interpretation=("NIS mean ≈ 2 means filter is consistent. "
                            "Posterior variance < single-path variance shows fusion gain."),
        ),
        weights_static=dict(w1=w1, w2=w2),
        n_full_coverage_static=int(len(t_full)),
        n_strict_intersection_static=int(len(t_int)),
        n_only_method1=int(np.sum(only1)),
        n_only_method2=int(np.sum(only2)),
        t_full_range=[float(t_full[0]), float(t_full[-1])],
    )

    pd.DataFrame({"time_s": t_full, "X_m": x_full, "Y_m": y_full}).to_excel(
        OUT / "Q2_trajectory_10Hz.xlsx", index=False)
    pd.DataFrame({"time_s": t_int, "X_m": x_int, "Y_m": y_int}).to_excel(
        OUT / "Q2_trajectory_10Hz_strict.xlsx", index=False)
    pd.DataFrame({
        "time_s": t_kf, "X_m": x_kf, "Y_m": y_kf,
        "Vx_m_s": vx_kf, "Vy_m_s": vy_kf,
        "var_X": var_x_kf, "var_Y": var_y_kf,
    }).to_excel(OUT / "Q2_trajectory_10Hz_kalman.xlsx", index=False)

    # ---------- 5. Plots ----------
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    ax = axes[0, 0]
    ax.plot(grid, costs, lw=0.7)
    ax.axvline(dt_hat, color="r", linestyle="--", label=f"$\\hat{{\\Delta t}}$={dt_hat:.4f} s")
    ax.set_yscale("log")
    ax.set_title("粗扫代价 $J(\\Delta t)$ — 附件2")
    ax.set_xlabel("$\\Delta t$ (s)")
    ax.set_ylabel("均方残差 ($m^2$)")
    ax.legend()

    ax = axes[0, 1]
    ax.plot(grid2, costs2, lw=0.7)
    ax.axvline(dt_hat, color="r", linestyle="--")
    ax.set_yscale("log")
    ax.set_title(f"精扫 $J(\\Delta t)$，0.01 s 步长")
    ax.set_xlabel("$\\Delta t$ (s)")
    ax.set_ylabel("均方残差 ($m^2$)")

    ax = axes[1, 0]
    ax.plot(s1["t"], s1["x"], lw=0.4, alpha=0.6, label="方式1 X 原始")
    ax.plot(s2["t"] + dt_hat, s2["x"] + dx_hat, lw=0.4, alpha=0.6,
            linestyle="--", label=f"方式2 X 已对齐+偏移 ($\\Delta t$={dt_hat:.3f}, $\\Delta x$={dx_hat:.3f})")
    ax.set_title(f"对齐 + 偏移修正后 X(t) 重合 — {name}")
    ax.set_xlabel("物理时间 t (s)")
    ax.set_ylabel("X (m)")
    ax.legend(fontsize=9)

    ax = axes[1, 1]
    ax.plot(t_full, x_full, lw=0.6, label="融合 X")
    ax.plot(t_full, y_full, lw=0.6, label="融合 Y")
    ax.set_title(f"10 Hz 加权融合轨迹 (w={w1:.2f}/{w2:.2f}, n={len(t_full)})")
    ax.set_xlabel("物理时间 t (s)")
    ax.set_ylabel("位置 (m)")
    ax.legend(fontsize=9)

    fig.tight_layout()
    fig.savefig(FIGS / "Q2_alignment.png")
    plt.close(fig)

    # ---------- 6. Residual diagnostics ----------
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    rx, ry = noise["rx"], noise["ry"]

    ax = axes[0, 0]
    ax.hist(rx, bins=80, density=True, alpha=0.7, label="实测 X 残差")
    xs = np.linspace(rx.min(), rx.max(), 200)
    ax.plot(xs, norm.pdf(xs, rx.mean(), rx.std()), "r", lw=1.5,
            label=f"$N({rx.mean():.3f}, {rx.std():.3f}^2)$")
    ax.set_title(f"X 残差分布 (KS p={noise['ks_x_pvalue']:.3f})")
    ax.set_xlabel("残差 (m)"); ax.set_ylabel("密度")
    ax.legend(fontsize=9)

    ax = axes[0, 1]
    ax.hist(ry, bins=80, density=True, alpha=0.7, color="C1", label="实测 Y 残差")
    ys = np.linspace(ry.min(), ry.max(), 200)
    ax.plot(ys, norm.pdf(ys, ry.mean(), ry.std()), "r", lw=1.5,
            label=f"$N({ry.mean():.3f}, {ry.std():.3f}^2)$")
    ax.set_title(f"Y 残差分布 (KS p={noise['ks_y_pvalue']:.3f})")
    ax.set_xlabel("残差 (m)"); ax.set_ylabel("密度")
    ax.legend(fontsize=9)

    ax = axes[1, 0]
    probplot(rx, dist="norm", plot=ax)
    ax.set_title("X 残差 QQ-plot")
    ax.get_lines()[1].set_color("r")

    ax = axes[1, 1]
    probplot(ry, dist="norm", plot=ax)
    ax.set_title("Y 残差 QQ-plot")
    ax.get_lines()[1].set_color("r")

    fig.suptitle(f"残差高斯诊断 — {name}", fontsize=12, y=1.0)
    fig.tight_layout()
    fig.savefig(FIGS / "Q2_residual_diag.png")
    plt.close(fig)

    # ---------- 7. Kalman vs Static-weighted comparison ----------
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    ax = axes[0, 0]
    ax.plot(t_full, x_full, lw=0.7, alpha=0.7, label="静态加权")
    ax.plot(t_kf, x_kf, lw=0.7, color="r", label="Kalman+RTS")
    ax.set_title("X(t) 融合方法对比")
    ax.set_xlabel("物理时间 t (s)"); ax.set_ylabel("X (m)")
    ax.legend(fontsize=9)

    ax = axes[0, 1]
    # zoom-in on a 30 s window to see noise difference
    mid = (t_full[0] + t_full[-1]) / 2
    mask_z = (t_full >= mid - 15) & (t_full <= mid + 15)
    mask_z_kf = (t_kf >= mid - 15) & (t_kf <= mid + 15)
    ax.plot(t_full[mask_z], x_full[mask_z], lw=0.8, alpha=0.7, label="静态加权")
    ax.plot(t_kf[mask_z_kf], x_kf[mask_z_kf], lw=1.0, color="r", label="Kalman+RTS")
    ax.set_title("X(t) 局部放大（30 s 窗口）")
    ax.set_xlabel("物理时间 t (s)"); ax.set_ylabel("X (m)")
    ax.legend(fontsize=9)

    ax = axes[1, 0]
    ax.plot(t_kf, vx_kf, lw=0.6, label="Kalman vx")
    ax.plot(t_kf, vy_kf, lw=0.6, label="Kalman vy", color="C1")
    ax.set_title("Kalman 估计速度（运动学先验副产物）")
    ax.set_xlabel("物理时间 t (s)"); ax.set_ylabel("速度 (m/s)")
    ax.legend(fontsize=9)

    ax = axes[1, 1]
    ax.plot(t_kf, np.sqrt(var_x_kf), lw=0.6, label="X 后验 σ")
    ax.plot(t_kf, np.sqrt(var_y_kf), lw=0.6, label="Y 后验 σ", color="C1")
    ax.axhline(noise["sigma_per_path"], color="gray", linestyle="--",
               label=f"单路 σ ≈ {noise['sigma_per_path']:.2f} m")
    ax.axhline(noise["sigma_per_path"] / np.sqrt(2), color="green", linestyle="--",
               label=f"等权融合 σ ≈ {noise['sigma_per_path']/np.sqrt(2):.2f} m")
    ax.set_title(f"Kalman 后验不确定度（NIS 均值={nis_mean:.2f}, 目标 2.0）")
    ax.set_xlabel("物理时间 t (s)"); ax.set_ylabel("后验 σ (m)")
    ax.legend(fontsize=9)

    fig.suptitle(f"Kalman+RTS 融合 vs 静态加权 — {name}", fontsize=12, y=1.0)
    fig.tight_layout()
    fig.savefig(FIGS / "Q2_kalman_compare.png")
    plt.close(fig)

    # ---------- 8. Bootstrap distribution figure ----------
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    ests = boot["estimates"]
    for i, (name_, vlim) in enumerate([("$\\Delta t$ (s)", "dt"),
                                        ("$\\Delta x$ (m)", "dx"),
                                        ("$\\Delta y$ (m)", "dy")]):
        ax = axes[i]
        ax.hist(ests[:, i], bins=20, density=True, alpha=0.7)
        ax.axvline(ests[:, i].mean(), color="r", linestyle="--",
                   label=f"均值 {ests[:, i].mean():.3f}")
        ax.set_xlabel(name_); ax.set_ylabel("密度")
        ax.set_title(f"Bootstrap 分布 ({name_})  n={boot['n_boot']}")
        ax.legend(fontsize=9)
    fig.suptitle(f"Bootstrap 参数分布 — {name}", fontsize=12, y=1.02)
    fig.tight_layout()
    fig.savefig(FIGS / "Q2_bootstrap.png")
    plt.close(fig)

    return summary


if __name__ == "__main__":
    summary = solve_q2(DATA / "附件2.xlsx", "附件2")
    (OUT / "Q2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
