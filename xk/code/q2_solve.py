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
from scipy.stats import kstest, norm, probplot

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "A"))
sys.path.insert(0, str(ROOT / "code"))
from plot_style import setup_plot_style  # noqa: E402
from q_utils import (  # noqa: E402
    load_xlsx, make_interp, feasible_domain,
    alignment_cost_dt, alignment_cost_joint,
    estimate_dt_uncertainty, coarse_search_dt, fuse_10hz,
)

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
        residual_mean_x=float(rx.mean()),
        residual_mean_y=float(ry.mean()),
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

    # For each candidate, run joint Nelder-Mead, compare final J
    best = None
    candidates = []
    for i in top_local:
        x0 = np.array([float(grid[i]), 0.0, 0.0])
        res_i = minimize(
            alignment_cost_joint,
            x0=x0,
            args=(s1, s2, fx2, fy2, 8000),
            method="Nelder-Mead",
            options={"xatol": 1e-7, "fatol": 1e-12, "maxiter": 20000},
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

    summary = dict(
        attachment=name,
        feasible_domain=[dt_lo, dt_hi],
        dt_hat_seconds=dt_hat,
        dt_sigma_seconds=sigma_dt,
        dx_hat_meters=dx_hat,
        dy_hat_meters=dy_hat,
        joint_final_cost_m2=final_cost,
        coarse_dt0=dt0,
        noise=dict(
            sigma_diff_x_m=noise["sigma_diff_x"],
            sigma_diff_y_m=noise["sigma_diff_y"],
            sigma_per_path_x_m=noise["sigma_per_path_x"],
            sigma_per_path_y_m=noise["sigma_per_path_y"],
            sigma_per_path_m=noise["sigma_per_path"],
            residual_mean_x=noise["residual_mean_x"],
            residual_mean_y=noise["residual_mean_y"],
        ),
        ks_test=dict(
            x_stat=noise["ks_x_stat"], x_pvalue=noise["ks_x_pvalue"],
            y_stat=noise["ks_y_stat"], y_pvalue=noise["ks_y_pvalue"],
            interpretation=("p > 0.05 supports Gaussian H0; "
                            "low p indicates non-Gaussian residual structure."),
        ),
        weights=dict(w1=w1, w2=w2),
        n_full_coverage=int(len(t_full)),
        n_strict_intersection=int(len(t_int)),
        n_only_method1=int(np.sum(only1)),
        n_only_method2=int(np.sum(only2)),
        t_full_range=[float(t_full[0]), float(t_full[-1])],
    )

    pd.DataFrame({"time_s": t_full, "X_m": x_full, "Y_m": y_full}).to_excel(
        OUT / "Q2_trajectory_10Hz.xlsx", index=False)
    pd.DataFrame({"time_s": t_int, "X_m": x_int, "Y_m": y_int}).to_excel(
        OUT / "Q2_trajectory_10Hz_strict.xlsx", index=False)

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

    return summary


if __name__ == "__main__":
    summary = solve_q2(DATA / "附件2.xlsx", "附件2")
    (OUT / "Q2_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
