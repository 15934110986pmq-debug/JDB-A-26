"""Q2 二审 Round-2 实证验证（P0 #1, #2, #3, #4）.

目的：把"二审 Round-2"5 个 P0 中需要数据兜底的 4 项跑出真实数字，更新论文：
  P0 #1: 创新序列自相关 → 真实 ESS  (替换 N_eff~50 启发式)
  P0 #2: forward vs RTS P_xx 实测比例 (替换"减半"经验法则)
  P0 #3: Bootstrap 三参数协方差矩阵 (确认/否定边际 CI 是否低估联合不确定度)
  P0 #4: Bootstrap Δt 直方图 + basin 跳模检查

输出：
  xk/output/Q2_validation.json
  xk/figures/Q2_bootstrap_basin.png
  xk/figures/Q2_innovation_acf.png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from statsmodels.tsa.stattools import acf

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "code"))

from q_utils import alignment_cost_joint, make_interp  # noqa: E402
from q2_kalman import collect_observations, kf_forward, rts_backward  # noqa: E402

DATA = ROOT / "data"
OUT = ROOT / "output"
FIG = ROOT / "figures"


def load_attachment2():
    """Returns s1 (4Hz), s2 (5Hz) as DataFrames with columns t, x, y."""
    xls = pd.ExcelFile(DATA / "附件2.xlsx")
    s1 = pd.read_excel(xls, sheet_name=0)
    s2 = pd.read_excel(xls, sheet_name=1)
    s1.columns = ["t", "x", "y"]
    s2.columns = ["t", "x", "y"]
    return s1, s2


def real_ess_from_innovation(nis_series: np.ndarray, max_lag: int = 100) -> dict:
    """Compute real ESS from innovation NIS autocorrelation.

    For a stationary series, N_eff = N / (1 + 2*sum_{k>=1} rho_k).
    """
    nis_centered = nis_series - nis_series.mean()
    rho, _ = acf(nis_centered, nlags=max_lag, fft=True, alpha=0.05)
    rho_pos = rho[1:]
    cum_rho = np.cumsum(rho_pos)
    first_neg = np.where(rho_pos < 0)[0]
    L = int(first_neg[0]) if len(first_neg) else max_lag
    sum_rho = float(cum_rho[L - 1]) if L > 0 else 0.0
    N = len(nis_series)
    n_eff = N / (1 + 2 * sum_rho)
    return dict(
        N=int(N),
        sum_rho_first_negative_truncation=sum_rho,
        first_negative_lag=L,
        n_eff=float(n_eff),
        rho_first_5=[float(r) for r in rho_pos[:5]],
        nis_mean=float(nis_series.mean()),
    )


def rts_vs_forward_ratio(forward_covs: np.ndarray, rts_covs: np.ndarray) -> dict:
    """Real RTS / forward variance ratio for position dimensions."""
    P_xx_fwd = forward_covs[:, 0, 0]
    P_yy_fwd = forward_covs[:, 1, 1]
    P_xx_rts = rts_covs[:, 0, 0]
    P_yy_rts = rts_covs[:, 1, 1]
    return dict(
        forward_Pxx_mean=float(P_xx_fwd.mean()),
        forward_Pyy_mean=float(P_yy_fwd.mean()),
        rts_Pxx_mean=float(P_xx_rts.mean()),
        rts_Pyy_mean=float(P_yy_rts.mean()),
        rts_over_forward_xx=float(P_xx_rts.mean() / P_xx_fwd.mean()),
        rts_over_forward_yy=float(P_yy_rts.mean() / P_yy_fwd.mean()),
    )


def bootstrap_with_full_estimates(s1, s2, dt_hat, dx_hat, dy_hat,
                                  sigma_per_path: float, n_boot: int = 200,
                                  rng_seed: int = 42):
    """Re-run parametric Bootstrap, this time saving every estimate.
    Increased B=200 for tighter joint covariance + clearer histogram.
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
        if (b + 1) % 50 == 0:
            print(f"  bootstrap {b+1}/{n_boot}")
    return estimates


def joint_covariance_diagnosis(estimates: np.ndarray) -> dict:
    cov = np.cov(estimates, rowvar=False, ddof=1)
    std = np.sqrt(np.diag(cov))
    corr = cov / np.outer(std, std)
    n = len(estimates)
    return dict(
        n_boot=int(n),
        std_dt=float(std[0]),
        std_dx=float(std[1]),
        std_dy=float(std[2]),
        corr_dt_dx=float(corr[0, 1]),
        corr_dt_dy=float(corr[0, 2]),
        corr_dx_dy=float(corr[1, 2]),
        cov_matrix=cov.tolist(),
        corr_matrix=corr.tolist(),
    )


def basin_check(estimates: np.ndarray, dt_main: float = -364.8094,
                period_T: float = 628.3) -> dict:
    """How many bootstrap iterations strayed away from C1 main basin?"""
    dt_samples = estimates[:, 0]
    deviations = np.abs(dt_samples - dt_main)
    in_main_basin = (deviations < period_T / 4)
    n_main = int(in_main_basin.sum())
    return dict(
        n_total=len(dt_samples),
        n_in_main_basin=n_main,
        fraction_in_main_basin=float(n_main / len(dt_samples)),
        max_abs_deviation_s=float(deviations.max()),
        dt_min=float(dt_samples.min()),
        dt_max=float(dt_samples.max()),
    )


def plot_innovation_acf(nis_series: np.ndarray, save_to: Path, max_lag: int = 50):
    nis_c = nis_series - nis_series.mean()
    rho, ci = acf(nis_c, nlags=max_lag, fft=True, alpha=0.05)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(range(len(rho)), rho, width=0.5, color="steelblue", alpha=0.7)
    ax.axhline(0, color="k", lw=0.5)
    ax.fill_between(range(len(rho)), ci[:, 0] - rho, ci[:, 1] - rho,
                    alpha=0.2, color="grey", label="95% CI under H0")
    ax.set_xlabel("Lag")
    ax.set_ylabel(r"NIS autocorrelation $\rho_k$")
    ax.set_title(f"KF innovation NIS autocorrelation (N={len(nis_series)})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(save_to, dpi=150)
    plt.close(fig)


def plot_bootstrap_basin(estimates: np.ndarray, dt_main: float, period_T: float,
                         save_to: Path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(estimates[:, 0], bins=30, color="steelblue", edgecolor="k", alpha=0.7)
    axes[0].axvline(dt_main, color="red", lw=2, label=f"C1 main solution = {dt_main:.2f} s")
    axes[0].axvline(dt_main + period_T, color="orange", ls="--", lw=1.5,
                    label=f"C2 = C1 + T = {dt_main + period_T:.2f} s")
    axes[0].axvline(dt_main - period_T, color="orange", ls="--", lw=1.5,
                    label=f"C0 = C1 - T = {dt_main - period_T:.2f} s")
    axes[0].set_xlabel(r"$\Delta t^{(b)}$ (s)")
    axes[0].set_ylabel("Bootstrap count")
    axes[0].set_title(rf"Bootstrap $\Delta t$ distribution (B={len(estimates)})")
    axes[0].legend(fontsize=8)

    axes[1].scatter(estimates[:, 1], estimates[:, 2], s=15, alpha=0.6, color="steelblue")
    axes[1].set_xlabel(r"$\Delta x^{(b)}$ (m)")
    axes[1].set_ylabel(r"$\Delta y^{(b)}$ (m)")
    axes[1].set_title("Bootstrap (Δx, Δy) joint scatter")
    axes[1].axis("equal")

    fig.tight_layout()
    fig.savefig(save_to, dpi=150)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)

    s1, s2 = load_attachment2()
    print(f"Loaded: s1 N={len(s1)}, s2 N={len(s2)}")

    dt_hat = -364.8094
    dx_hat, dy_hat = -3.587, 1.796
    sigma_per_path = 0.71315
    sigma_1 = 0.730
    sigma_2 = 0.697
    sigma_a = 0.5

    # P0 #1, #2: KF + RTS, get innovation series and covariance series
    print("\n[P0 #1, #2] Running KF + RTS...")
    obs = collect_observations(s1, s2, dt_hat, dx_hat, dy_hat, sigma_1, sigma_2)
    states, covs, pred_states, pred_covs, nis = kf_forward(obs, sigma_a)
    sm_states, sm_covs = rts_backward(states, covs, pred_states, pred_covs, obs, sigma_a)

    ess_result = real_ess_from_innovation(nis)
    print(f"  Real ESS: N_eff = {ess_result['n_eff']:.1f}")
    print(f"  rho_1..5 = {ess_result['rho_first_5']}")

    # 95% upper bound at this real ESS
    n_eff = ess_result["n_eff"]
    bound_at_real_ess = 2.0 + 1.645 * np.sqrt(4.0 / n_eff)
    print(f"  95% upper bound at N_eff={n_eff:.1f}: {bound_at_real_ess:.4f}")
    print(f"  Reported NIS = {nis.mean():.4f} (越界 {(nis.mean() - bound_at_real_ess) / np.sqrt(4/n_eff):.2f}σ)")

    rts_ratio = rts_vs_forward_ratio(covs, sm_covs)
    print(f"\n  RTS/forward Pxx ratio: {rts_ratio['rts_over_forward_xx']:.4f}")
    print(f"  RTS/forward Pyy ratio: {rts_ratio['rts_over_forward_yy']:.4f}")
    print(f"  Forward mean(Pxx) = {rts_ratio['forward_Pxx_mean']:.4f} m²")
    print(f"  RTS     mean(Pxx) = {rts_ratio['rts_Pxx_mean']:.4f} m²")

    # P0 #3, #4: Bootstrap with all estimates saved
    print("\n[P0 #3, #4] Running parametric bootstrap (B=200)...")
    estimates = bootstrap_with_full_estimates(
        s1, s2, dt_hat, dx_hat, dy_hat, sigma_per_path, n_boot=200)
    joint = joint_covariance_diagnosis(estimates)
    basin = basin_check(estimates)
    print(f"\n  Joint covariance diagnosis:")
    print(f"    σ_dt={joint['std_dt']:.4f}, σ_dx={joint['std_dx']:.4f}, σ_dy={joint['std_dy']:.4f}")
    print(f"    corr(dt, dx) = {joint['corr_dt_dx']:.3f}")
    print(f"    corr(dt, dy) = {joint['corr_dt_dy']:.3f}")
    print(f"    corr(dx, dy) = {joint['corr_dx_dy']:.3f}")
    print(f"\n  Basin check:")
    print(f"    n_in_main_basin = {basin['n_in_main_basin']} / {basin['n_total']}")
    print(f"    max |Δt - main| = {basin['max_abs_deviation_s']:.4f} s")

    # Plots
    plot_innovation_acf(nis, FIG / "Q2_innovation_acf.png")
    plot_bootstrap_basin(estimates, dt_hat, 628.3, FIG / "Q2_bootstrap_basin.png")
    print(f"\n  Saved: {FIG / 'Q2_innovation_acf.png'}")
    print(f"  Saved: {FIG / 'Q2_bootstrap_basin.png'}")

    # Save JSON
    out = dict(
        ess=ess_result,
        rts_vs_forward=rts_ratio,
        bootstrap_joint=joint,
        bootstrap_basin=basin,
        nis_mean=float(nis.mean()),
        nis_n=len(nis),
        bound_95_at_real_ess=float(bound_at_real_ess),
        deviation_in_sigma_units=float(
            (nis.mean() - 2.0) / np.sqrt(4.0 / n_eff)
        ),
    )
    with open(OUT / "Q2_validation.json", "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {OUT / 'Q2_validation.json'}")


if __name__ == "__main__":
    main()
