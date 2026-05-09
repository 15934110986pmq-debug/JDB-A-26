# -*- coding: utf-8 -*-
"""
第三问修改版：实测轨迹时基校准、固定残差成分识别、第四问专用扩展轨迹输出

新增重点：
1. 原 q3_outputs 仍输出第三问论文用公共区间 10Hz 融合轨迹；
2. 额外输出 q3_final_outputs/q3_10Hz_extended_trajectory_for_q4.csv；
3. 第四问应优先使用该扩展轨迹，避免只用公共区间轨迹导致任务数偏低；
4. 第三问固定系统偏差判定逻辑不变：若未检出显著固定偏差，则不剥离空间偏差。

运行：
    cd /d E:\数模A
    python program3.py
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.interpolate import PchipInterpolator, CubicSpline, Akima1DInterpolator
from scipy.optimize import minimize_scalar
from scipy.signal import savgol_filter
from scipy.stats import chi2


# ============================================================
# 0. 参数区
# ============================================================

BASE_DIR = Path.cwd()
OUT_DIR = BASE_DIR / "q3_outputs"
FINAL_OUT_DIR = BASE_DIR / "q3_final_outputs"

ATTACHMENT_CANDIDATES = [
    BASE_DIR / "附件3.xlsx",
    BASE_DIR / "附件3：实际测量数据.xlsx",
    BASE_DIR / "附件3_实际测量数据.xlsx",
    BASE_DIR / "attachment3.xlsx",
]

TARGET_HZ = 10.0
TARGET_DT = 1.0 / TARGET_HZ

# 第三问时间偏差搜索范围
TAU_LEFT = -370.0
TAU_RIGHT = -366.0
COARSE_STEP = 0.01
REFINE_RADIUS = 0.6

# 防止短公共区间伪匹配
MIN_OVERLAP_POINTS = 600
MIN_OVERLAP_SECONDS = 300.0

# 平滑参数
SMOOTH_WINDOW = 61
SMOOTH_POLY = 3

# 固定残差成分识别参数
BOOT_TIMES = 1000
BOOT_BLOCK_SECONDS = 8.0
RANDOM_SEED = 2026
HAC_LAGS = [2, 4, 6, 8, 12, 18, 24]
ALPHA = 0.05

COV_REG = 1e-8


# ============================================================
# 1. 数据读取与预处理
# ============================================================

def setup_plot() -> None:
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]


def prepare_output_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_OUT_DIR.mkdir(parents=True, exist_ok=True)


def std_name(x) -> str:
    return (
        str(x)
        .strip()
        .replace(" ", "")
        .replace("\n", "")
        .replace("\r", "")
        .replace("（", "(")
        .replace("）", ")")
        .lower()
    )


def locate_attachment() -> Path:
    for p in ATTACHMENT_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "未找到附件3，请将附件3放在当前工作目录下。可识别文件名包括：\n"
        + "\n".join(str(p) for p in ATTACHMENT_CANDIDATES)
    )


def choose_column(df: pd.DataFrame, aliases: list[str]) -> str:
    col_map = {std_name(c): c for c in df.columns}
    alias_norm = [std_name(a) for a in aliases]

    for a in alias_norm:
        if a in col_map:
            return col_map[a]

    for k, raw in col_map.items():
        for a in alias_norm:
            if a in k or k in a:
                return raw

    raise KeyError(f"找不到列 {aliases}，当前列为 {list(df.columns)}")


def clean_position_table(raw: pd.DataFrame) -> pd.DataFrame:
    time_col = choose_column(raw, ["时间", "时刻", "t", "time", "time(s)", "t(s)", "时间(s)"])
    x_col = choose_column(raw, ["x", "x坐标", "x坐标(m)", "X坐标(m)", "X/m", "x/m"])
    y_col = choose_column(raw, ["y", "y坐标", "y坐标(m)", "Y坐标(m)", "Y/m", "y/m"])

    df = pd.DataFrame({
        "time": pd.to_numeric(raw[time_col], errors="coerce"),
        "x": pd.to_numeric(raw[x_col], errors="coerce"),
        "y": pd.to_numeric(raw[y_col], errors="coerce"),
    })

    df = (
        df.dropna(subset=["time", "x", "y"])
        .sort_values("time")
        .drop_duplicates(subset=["time"], keep="first")
        .reset_index(drop=True)
    )

    if len(df) < 20:
        raise ValueError("附件3中有效轨迹点过少，请检查表格格式。")

    return df


def read_attachment3(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None)
    names = list(sheets.keys())

    if len(names) < 2:
        raise ValueError("附件3至少应包含两个工作表，分别对应方式一和方式二。")

    sheet1 = None
    sheet2 = None

    for name in names:
        n = std_name(name)
        if "方式一" in n or "方法一" in n or "定位一" in n:
            sheet1 = name
        if "方式二" in n or "方法二" in n or "定位二" in n:
            sheet2 = name

    if sheet1 is None or sheet2 is None:
        sheet1, sheet2 = names[0], names[1]

    return clean_position_table(sheets[sheet1]), clean_position_table(sheets[sheet2])


def valid_savgol_window(n: int, target: int, poly: int) -> int:
    w = min(n, target)
    if w % 2 == 0:
        w -= 1

    min_w = poly + 3
    if min_w % 2 == 0:
        min_w += 1

    if w < min_w:
        w = min_w
    if w > n:
        w = n if n % 2 == 1 else n - 1

    return max(3, w)


def add_smooth_and_noise(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    n = len(out)

    if n <= SMOOTH_POLY + 4:
        out["x_smooth"] = out["x"]
        out["y_smooth"] = out["y"]
        out["noise_x"] = 0.0
        out["noise_y"] = 0.0
        return out

    window = valid_savgol_window(n, SMOOTH_WINDOW, SMOOTH_POLY)

    out["x_smooth"] = savgol_filter(
        out["x"].to_numpy(float),
        window_length=window,
        polyorder=SMOOTH_POLY,
        mode="interp",
    )
    out["y_smooth"] = savgol_filter(
        out["y"].to_numpy(float),
        window_length=window,
        polyorder=SMOOTH_POLY,
        mode="interp",
    )

    out["noise_x"] = out["x"] - out["x_smooth"]
    out["noise_y"] = out["y"] - out["y_smooth"]

    return out


def make_curve(df: pd.DataFrame, kind: str = "pchip", x_col: str = "x_smooth", y_col: str = "y_smooth"):
    t = df["time"].to_numpy(float)
    x = df[x_col].to_numpy(float)
    y = df[y_col].to_numpy(float)

    if kind == "pchip":
        fx = PchipInterpolator(t, x, extrapolate=False)
        fy = PchipInterpolator(t, y, extrapolate=False)
    elif kind == "cubic":
        fx = CubicSpline(t, x, bc_type="natural", extrapolate=False)
        fy = CubicSpline(t, y, bc_type="natural", extrapolate=False)
    elif kind == "akima":
        fx = Akima1DInterpolator(t, x)
        fy = Akima1DInterpolator(t, y)
    else:
        raise ValueError(f"未知插值方法：{kind}")

    return fx, fy


# ============================================================
# 2. 时间偏差估计：去中心化轨迹差异准则
# ============================================================

def overlap_mask(t1: np.ndarray, t2_min: float, t2_max: float, tau: float) -> np.ndarray:
    return (t1 + tau >= t2_min) & (t1 + tau <= t2_max)


def residual_table_at_tau(tau: float, df1: pd.DataFrame, df2: pd.DataFrame, kind: str = "pchip") -> pd.DataFrame:
    t1 = df1["time"].to_numpy(float)
    x1 = df1["x_smooth"].to_numpy(float)
    y1 = df1["y_smooth"].to_numpy(float)

    t2 = df2["time"].to_numpy(float)
    mask = overlap_mask(t1, float(t2.min()), float(t2.max()), tau)

    if mask.sum() < MIN_OVERLAP_POINTS:
        return pd.DataFrame()

    t_common = t1[mask]
    if float(t_common.max() - t_common.min()) < MIN_OVERLAP_SECONDS:
        return pd.DataFrame()

    fx2, fy2 = make_curve(df2, kind=kind, x_col="x_smooth", y_col="y_smooth")

    tq = t1[mask] + tau
    x2 = fx2(tq)
    y2 = fy2(tq)

    valid = np.isfinite(x2) & np.isfinite(y2)
    if valid.sum() < MIN_OVERLAP_POINTS:
        return pd.DataFrame()

    time = t1[mask][valid]
    x1v = x1[mask][valid]
    y1v = y1[mask][valid]
    x2v = x2[valid]
    y2v = y2[valid]

    dx = x2v - x1v
    dy = y2v - y1v

    out = pd.DataFrame({
        "time": time,
        "x_ref": x1v,
        "y_ref": y1v,
        "x_shifted": x2v,
        "y_shifted": y2v,
        "dx": dx,
        "dy": dy,
    })
    out["dist"] = np.sqrt(out["dx"] ** 2 + out["dy"] ** 2)
    return out


def centered_residual_score(tau: float, df1: pd.DataFrame, df2: pd.DataFrame, kind: str = "pchip") -> float:
    table = residual_table_at_tau(tau, df1, df2, kind)
    if table.empty:
        return np.inf

    dx = table["dx"].to_numpy(float)
    dy = table["dy"].to_numpy(float)

    dx0 = dx - dx.mean()
    dy0 = dy - dy.mean()

    score = float(np.mean(dx0 ** 2 + dy0 ** 2))
    duration = float(table["time"].max() - table["time"].min())
    score += 1e-4 / max(duration, 1.0)
    return score


def solve_time_shift(df1: pd.DataFrame, df2: pd.DataFrame, kind: str = "pchip") -> tuple[float, float, pd.DataFrame]:
    grid = np.arange(TAU_LEFT, TAU_RIGHT + COARSE_STEP, COARSE_STEP)

    values = np.array([
        centered_residual_score(tau, df1, df2, kind)
        for tau in grid
    ])

    if not np.any(np.isfinite(values)):
        raise RuntimeError("当前时间偏差搜索范围内没有满足公共区间约束的候选解。")

    tau0 = float(grid[int(np.nanargmin(values))])
    left = max(TAU_LEFT, tau0 - REFINE_RADIUS)
    right = min(TAU_RIGHT, tau0 + REFINE_RADIUS)

    opt = minimize_scalar(
        lambda z: centered_residual_score(z, df1, df2, kind),
        bounds=(left, right),
        method="bounded",
        options={"xatol": 1e-12, "maxiter": 1000},
    )

    if not opt.success:
        warnings.warn(f"时间偏差优化未完全收敛：{opt.message}")

    tau_hat = float(opt.x)
    score_min = float(opt.fun)
    aligned = residual_table_at_tau(tau_hat, df1, df2, kind)
    return tau_hat, score_min, aligned


# ============================================================
# 3. 固定残差成分识别
# ============================================================

def block_bootstrap_means(residual: np.ndarray, dt: float, block_seconds: float, n_boot: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = residual.shape[0]

    block_len = max(2, int(round(block_seconds / dt)))
    block_len = min(block_len, max(2, n // 3))

    starts = np.arange(0, n - block_len + 1)
    n_blocks = int(math.ceil(n / block_len))

    means = []
    for _ in range(n_boot):
        selected = rng.choice(starts, size=n_blocks, replace=True)
        sample = np.vstack([residual[s:s + block_len] for s in selected])[:n]
        means.append(sample.mean(axis=0))

    means = np.asarray(means)
    return pd.DataFrame({
        "mu_x_boot": means[:, 0],
        "mu_y_boot": means[:, 1],
        "mu_norm_boot": np.sqrt(means[:, 0] ** 2 + means[:, 1] ** 2),
    })


def newey_west_cov_of_mean(residual: np.ndarray, lag: int) -> np.ndarray:
    x = np.asarray(residual, dtype=float)
    n, d = x.shape

    z = x - x.mean(axis=0)
    gamma0 = (z.T @ z) / n
    hac = gamma0.copy()

    for k in range(1, lag + 1):
        w = 1.0 - k / (lag + 1.0)
        gk = (z[k:].T @ z[:-k]) / n
        hac += w * (gk + gk.T)

    return hac / n + COV_REG * np.eye(d)


def hac_lag_scan(residual: np.ndarray) -> pd.DataFrame:
    mu = residual.mean(axis=0)
    rows = []

    for lag in HAC_LAGS:
        cov_mu = newey_west_cov_of_mean(residual, lag)
        try:
            stat = float(mu.T @ np.linalg.inv(cov_mu) @ mu)
            p_val = float(1.0 - chi2.cdf(stat, df=2))
        except np.linalg.LinAlgError:
            stat = np.nan
            p_val = np.nan

        rows.append({
            "lag": lag,
            "T2": stat,
            "p_value": p_val,
            "significant_0.05": int(np.isfinite(p_val) and p_val < ALPHA),
        })

    return pd.DataFrame(rows)


def effective_n_from_autocorr(series: np.ndarray, max_lag: int = 80) -> float:
    x = np.asarray(series, dtype=float)
    n = len(x)
    if n < 5:
        return float(n)

    x = x - x.mean()
    denom = float(np.dot(x, x))
    if denom <= 1e-12:
        return float(n)

    total = 0.0
    max_lag = min(max_lag, n - 2)

    for k in range(1, max_lag + 1):
        rho = float(np.dot(x[k:], x[:-k]) / denom)
        if rho <= 0:
            break
        total += rho

    n_eff = n / (1.0 + 2.0 * total)
    return float(max(2.0, min(float(n), n_eff)))


def bic_eff_screen(residual: np.ndarray) -> dict[str, float]:
    n = residual.shape[0]
    mu = residual.mean(axis=0)

    sse0 = float(np.sum(residual[:, 0] ** 2 + residual[:, 1] ** 2))
    centered = residual - mu
    sse1 = float(np.sum(centered[:, 0] ** 2 + centered[:, 1] ** 2))

    dist = np.sqrt(residual[:, 0] ** 2 + residual[:, 1] ** 2)
    n_eff = effective_n_from_autocorr(dist)

    bic0 = n_eff * math.log(max(sse0 / n, 1e-12))
    bic1 = n_eff * math.log(max(sse1 / n, 1e-12)) + 2 * math.log(n_eff)

    return {
        "SSE_no_fixed_component": sse0,
        "SSE_with_fixed_component": sse1,
        "N": float(n),
        "N_eff": n_eff,
        "BIC_eff_no_fixed_component": bic0,
        "BIC_eff_with_fixed_component": bic1,
        "Delta_BIC_eff": bic1 - bic0,
    }


def identify_fixed_component(aligned: pd.DataFrame):
    residual = aligned[["dx", "dy"]].to_numpy(float)
    t = aligned["time"].to_numpy(float)

    dt = float(np.median(np.diff(t)))
    mu = residual.mean(axis=0)
    mu_norm = float(np.linalg.norm(mu))

    boot = block_bootstrap_means(
        residual=residual,
        dt=dt,
        block_seconds=BOOT_BLOCK_SECONDS,
        n_boot=BOOT_TIMES,
        seed=RANDOM_SEED,
    )

    x_ci = np.quantile(boot["mu_x_boot"], [0.025, 0.975])
    y_ci = np.quantile(boot["mu_y_boot"], [0.025, 0.975])
    norm_ci = np.quantile(boot["mu_norm_boot"], [0.025, 0.975])

    x_cover_zero = bool(x_ci[0] <= 0 <= x_ci[1])
    y_cover_zero = bool(y_ci[0] <= 0 <= y_ci[1])

    hac = hac_lag_scan(residual)
    bic = bic_eff_screen(residual)

    bootstrap_support = (not x_cover_zero) or (not y_cover_zero)
    short_hac_support = bool(hac[hac["lag"] <= 8]["significant_0.05"].any())
    long_hac_support = bool(hac[hac["lag"] >= 12]["significant_0.05"].any())
    bic_support = bool(bic["Delta_BIC_eff"] < 0)

    detected = bool(bootstrap_support and long_hac_support and bic_support)

    diagnosis = pd.DataFrame([
        ["候选固定成分X/m", mu[0]],
        ["候选固定成分Y/m", mu[1]],
        ["候选固定成分模长/m", mu_norm],
        ["Bootstrap_X_95CI_lower", x_ci[0]],
        ["Bootstrap_X_95CI_upper", x_ci[1]],
        ["Bootstrap_Y_95CI_lower", y_ci[0]],
        ["Bootstrap_Y_95CI_upper", y_ci[1]],
        ["Bootstrap_norm_95CI_lower", norm_ci[0]],
        ["Bootstrap_norm_95CI_upper", norm_ci[1]],
        ["X方向置信区间是否覆盖0", int(x_cover_zero)],
        ["Y方向置信区间是否覆盖0", int(y_cover_zero)],
        ["Bootstrap是否支持固定成分", int(bootstrap_support)],
        ["短滞后HAC是否显著", int(short_hac_support)],
        ["长滞后HAC是否显著", int(long_hac_support)],
        ["BIC_eff是否支持固定成分", int(bic_support)],
        ["是否认定为需剥离固定系统偏差", int(detected)],
    ], columns=["指标", "数值"])

    bic_df = pd.DataFrame([
        ["SSE_no_fixed_component", bic["SSE_no_fixed_component"]],
        ["SSE_with_fixed_component", bic["SSE_with_fixed_component"]],
        ["N", bic["N"]],
        ["N_eff", bic["N_eff"]],
        ["BIC_eff_no_fixed_component", bic["BIC_eff_no_fixed_component"]],
        ["BIC_eff_with_fixed_component", bic["BIC_eff_with_fixed_component"]],
        ["Delta_BIC_eff", bic["Delta_BIC_eff"]],
    ], columns=["指标", "数值"])

    evidence = pd.DataFrame([
        ["候选成分量级", f"{mu_norm:.6f} m", "偏弱" if mu_norm < 0.5 else "较明显"],
        ["区间稳定性", "两个方向95%CI均覆盖0" if x_cover_zero and y_cover_zero else "至少一个方向95%CI不覆盖0", "不支持" if not bootstrap_support else "支持"],
        ["相关性稳健性", "短滞后显著、长滞后不稳定" if short_hac_support and not long_hac_support else "长滞后仍显著" if long_hac_support else "不显著", "支持不足" if not long_hac_support else "支持"],
        ["模型收益", f"Delta_BIC_eff={bic['Delta_BIC_eff']:.6f}", "不支持" if not bic_support else "支持"],
    ], columns=["判别依据", "结果", "对固定系统偏差的支持情况"])

    return diagnosis, boot, hac, bic_df, evidence, mu, detected


# ============================================================
# 4. 协方差融合与轨迹输出
# ============================================================

def cov2d(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    c = np.cov(np.vstack([x, y]), bias=False)
    c = np.asarray(c, dtype=float)
    if c.shape != (2, 2) or not np.all(np.isfinite(c)):
        c = np.eye(2)
    return c + COV_REG * np.eye(2)


def estimate_covariances(df1: pd.DataFrame, df2: pd.DataFrame):
    cov1 = cov2d(df1["noise_x"].to_numpy(float), df1["noise_y"].to_numpy(float))
    cov2 = cov2d(df2["noise_x"].to_numpy(float), df2["noise_y"].to_numpy(float))
    inv1 = np.linalg.inv(cov1)
    inv2 = np.linalg.inv(cov2)
    cov_f = np.linalg.inv(inv1 + inv2)
    return cov1, cov2, cov_f


def fuse_two_points(p1: np.ndarray, p2: np.ndarray, cov1: np.ndarray, cov2: np.ndarray) -> np.ndarray:
    inv1 = np.linalg.inv(cov1)
    inv2 = np.linalg.inv(cov2)
    cov_f = np.linalg.inv(inv1 + inv2)
    return cov_f @ (inv1 @ p1 + inv2 @ p2)


def build_common_10hz_track(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    tau: float,
    cov1: np.ndarray,
    cov2: np.ndarray,
    remove_fixed: bool,
    fixed_component: np.ndarray,
    kind: str = "pchip",
) -> pd.DataFrame:
    """第三问论文用：公共区间双源融合轨迹。"""
    t1_min, t1_max = float(df1["time"].min()), float(df1["time"].max())
    t2_min, t2_max = float(df2["time"].min()), float(df2["time"].max())

    start = max(t1_min, t2_min - tau)
    end = min(t1_max, t2_max - tau)

    start = math.ceil(start * TARGET_HZ) / TARGET_HZ
    end = math.floor(end * TARGET_HZ) / TARGET_HZ

    t_new = np.arange(start, end + 0.5 * TARGET_DT, TARGET_DT)

    fx1, fy1 = make_curve(df1, kind=kind, x_col="x_smooth", y_col="y_smooth")
    fx2, fy2 = make_curve(df2, kind=kind, x_col="x_smooth", y_col="y_smooth")

    x1 = fx1(t_new)
    y1 = fy1(t_new)
    x2 = fx2(t_new + tau)
    y2 = fy2(t_new + tau)

    if remove_fixed:
        x2 = x2 - fixed_component[0]
        y2 = y2 - fixed_component[1]

    valid = np.isfinite(x1) & np.isfinite(y1) & np.isfinite(x2) & np.isfinite(y2)

    rows = []
    for t, a1, b1, a2, b2 in zip(t_new[valid], x1[valid], y1[valid], x2[valid], y2[valid]):
        p = fuse_two_points(np.array([a1, b1]), np.array([a2, b2]), cov1, cov2)
        rows.append({
            "time": float(t),
            "x": float(p[0]),
            "y": float(p[1]),
            "x_way1_smooth": float(a1),
            "y_way1_smooth": float(b1),
            "x_way2_time_aligned": float(a2),
            "y_way2_time_aligned": float(b2),
            "fixed_component_removed": int(remove_fixed),
            "source": "双源融合",
        })

    return pd.DataFrame(rows)


def build_extended_10hz_for_q4(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    tau: float,
    cov1: np.ndarray,
    cov2: np.ndarray,
    remove_fixed: bool,
    fixed_component: np.ndarray,
    kind: str = "pchip",
) -> pd.DataFrame:
    """
    第四问专用扩展轨迹：
    1. 在方式一轨迹和方式二校正后轨迹的并集时间范围内输出；
    2. 公共区间采用双源协方差融合；
    3. 非公共区间保留可用单源轨迹；
    4. 这样第四问不会只局限在第三问公共区间。
    """
    t1_min, t1_max = float(df1["time"].min()), float(df1["time"].max())
    t2_min, t2_max = float(df2["time"].min()), float(df2["time"].max())

    # 方式二校正到方式一时间轴后，其可用时间为 [t2_min - tau, t2_max - tau]
    t2c_min = t2_min - tau
    t2c_max = t2_max - tau

    start = min(t1_min, t2c_min)
    end = max(t1_max, t2c_max)

    start = math.ceil(start * TARGET_HZ) / TARGET_HZ
    end = math.floor(end * TARGET_HZ) / TARGET_HZ

    t_new = np.arange(start, end + 0.5 * TARGET_DT, TARGET_DT)

    fx1, fy1 = make_curve(df1, kind=kind, x_col="x_smooth", y_col="y_smooth")
    fx2, fy2 = make_curve(df2, kind=kind, x_col="x_smooth", y_col="y_smooth")

    x1 = fx1(t_new)
    y1 = fy1(t_new)

    # t_new 是方式一时间轴；查询方式二原始时间为 t_new + tau
    x2 = fx2(t_new + tau)
    y2 = fy2(t_new + tau)

    if remove_fixed:
        x2 = x2 - fixed_component[0]
        y2 = y2 - fixed_component[1]

    valid1 = np.isfinite(x1) & np.isfinite(y1)
    valid2 = np.isfinite(x2) & np.isfinite(y2)

    rows = []
    for i, t in enumerate(t_new):
        if valid1[i] and valid2[i]:
            p = fuse_two_points(np.array([x1[i], y1[i]]), np.array([x2[i], y2[i]]), cov1, cov2)
            source = "双源融合"
        elif valid1[i]:
            p = np.array([x1[i], y1[i]], dtype=float)
            source = "仅方式一"
        elif valid2[i]:
            p = np.array([x2[i], y2[i]], dtype=float)
            source = "仅方式二时间校正"
        else:
            continue

        rows.append({
            "time": float(t),
            "x": float(p[0]),
            "y": float(p[1]),
            "x_way1_smooth": float(x1[i]) if valid1[i] else np.nan,
            "y_way1_smooth": float(y1[i]) if valid1[i] else np.nan,
            "x_way2_time_aligned": float(x2[i]) if valid2[i] else np.nan,
            "y_way2_time_aligned": float(y2[i]) if valid2[i] else np.nan,
            "fixed_component_removed": int(remove_fixed),
            "source": source,
        })

    return pd.DataFrame(rows)


# ============================================================
# 5. 作图
# ============================================================

def plot_time_score(df1: pd.DataFrame, df2: pd.DataFrame, tau: float) -> None:
    taus = np.linspace(TAU_LEFT, TAU_RIGHT, 600)
    vals = np.array([centered_residual_score(z, df1, df2, "pchip") for z in taus])

    plt.figure(figsize=(10, 5))
    plt.plot(taus, vals)
    plt.axvline(tau, linestyle="--", label=f"最优偏差={tau:.6f}s")
    plt.xlabel("方式二相对方式一时间偏差/s")
    plt.ylabel("去均值残差目标函数")
    plt.title("第三问时间偏差目标函数")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q3_time_objective.png", dpi=300)
    plt.close()


def plot_fixed_ci(diagnosis: pd.DataFrame) -> None:
    def val(name: str) -> float:
        return float(diagnosis.loc[diagnosis["指标"] == name, "数值"].iloc[0])

    mx = val("候选固定成分X/m")
    my = val("候选固定成分Y/m")
    xl = val("Bootstrap_X_95CI_lower")
    xu = val("Bootstrap_X_95CI_upper")
    yl = val("Bootstrap_Y_95CI_lower")
    yu = val("Bootstrap_Y_95CI_upper")

    centers = np.array([mx, my])
    lows = np.array([xl, yl])
    highs = np.array([xu, yu])
    xerr = np.vstack([centers - lows, highs - centers])

    plt.figure(figsize=(9, 5))
    plt.errorbar(
        centers,
        [0, 1],
        xerr=xerr,
        fmt="o",
        capsize=6,
        linewidth=2,
        label="Block Bootstrap 95%置信区间",
    )
    plt.axvline(0, linestyle="--", label="零偏移")
    plt.yticks([0, 1], ["X方向", "Y方向"])
    plt.xlabel("候选固定成分/m")
    plt.title("第三问固定残差成分诊断")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q3_bias_bootstrap_ci.png", dpi=300)
    plt.close()


def plot_hac(hac: pd.DataFrame) -> None:
    plt.figure(figsize=(9, 5))
    plt.plot(hac["lag"], hac["p_value"], marker="o")
    plt.axhline(ALPHA, linestyle="--", label="0.05显著性水平")
    plt.xlabel("Newey-West 截断滞后")
    plt.ylabel("二维联合检验 p 值")
    plt.title("第三问HAC稳健检验敏感性")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q3_hac_sensitivity.png", dpi=300)
    plt.close()


def plot_ecdf(aligned: pd.DataFrame) -> None:
    r = np.sort(aligned["dist"].to_numpy(float))
    y = np.arange(1, len(r) + 1) / len(r)

    q95 = float(np.quantile(r, 0.95))
    q99 = float(np.quantile(r, 0.99))

    plt.figure(figsize=(9, 5))
    plt.plot(r, y)
    plt.axvline(q95, linestyle="--", label=f"95%分位={q95:.3f}m")
    plt.axvline(q99, linestyle=":", label=f"99%分位={q99:.3f}m")
    plt.xlabel("时间校正后空间残差/m")
    plt.ylabel("经验累计概率")
    plt.title("第三问时间校正后空间残差分布")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q3_residual_ecdf.png", dpi=300)
    plt.close()


def plot_track(aligned: pd.DataFrame, common_traj: pd.DataFrame, extended_traj: pd.DataFrame) -> None:
    plt.figure(figsize=(9, 7))
    plt.scatter(aligned["x_ref"], aligned["y_ref"], s=5, alpha=0.25, label="方式一平滑点")
    plt.scatter(aligned["x_shifted"], aligned["y_shifted"], s=5, alpha=0.25, label="方式二时间校正点")
    plt.plot(common_traj["x"], common_traj["y"], linewidth=2, label="公共区间10Hz融合轨迹")
    plt.axis("equal")
    plt.xlabel("X坐标/m")
    plt.ylabel("Y坐标/m")
    plt.title("第三问时间校正后的双源轨迹与公共区间输出")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q3_10hz_fused_trajectory.png", dpi=300)
    plt.close()

    plt.figure(figsize=(9, 7))
    plt.plot(extended_traj["x"], extended_traj["y"], linewidth=2)
    plt.axis("equal")
    plt.xlabel("X坐标/m")
    plt.ylabel("Y坐标/m")
    plt.title("第四问专用扩展10Hz轨迹")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FINAL_OUT_DIR / "q3_extended_trajectory_for_q4.png", dpi=300)
    plt.close()


# ============================================================
# 6. 主程序
# ============================================================

def main() -> None:
    setup_plot()
    prepare_output_dir()

    attachment = locate_attachment()

    print("=" * 76)
    print("第三问：时间校准、固定残差成分识别、第四问扩展轨迹输出")
    print("=" * 76)
    print(f"读取文件：{attachment}")

    df1_raw, df2_raw = read_attachment3(attachment)
    df1 = add_smooth_and_noise(df1_raw)
    df2 = add_smooth_and_noise(df2_raw)

    print(f"方式一点数：{len(df1)}")
    print(f"方式二点数：{len(df2)}")
    print(f"方式一时间范围：{df1['time'].min():.6f} — {df1['time'].max():.6f} s")
    print(f"方式二时间范围：{df2['time'].min():.6f} — {df2['time'].max():.6f} s")
    print(f"时间偏差搜索区间：[{TAU_LEFT}, {TAU_RIGHT}] s")

    tau_hat, score_min, aligned = solve_time_shift(df1, df2, kind="pchip")
    tau_cubic, score_cubic, _ = solve_time_shift(df1, df2, kind="cubic")
    tau_akima, score_akima, _ = solve_time_shift(df1, df2, kind="akima")

    diagnosis, boot, hac, bic, evidence, fixed_mu, detected = identify_fixed_component(aligned)

    cov1, cov2, cov_f = estimate_covariances(df1, df2)

    # 第三问论文用公共区间轨迹
    common_traj = build_common_10hz_track(
        df1=df1,
        df2=df2,
        tau=tau_hat,
        cov1=cov1,
        cov2=cov2,
        remove_fixed=detected,
        fixed_component=fixed_mu,
        kind="pchip",
    )

    # 第四问专用扩展轨迹
    extended_traj = build_extended_10hz_for_q4(
        df1=df1,
        df2=df2,
        tau=tau_hat,
        cov1=cov1,
        cov2=cov2,
        remove_fixed=detected,
        fixed_component=fixed_mu,
        kind="pchip",
    )

    robustness = pd.DataFrame({
        "插值方法": ["PCHIP", "自然三次样条", "Akima"],
        "时间偏差/s": [tau_hat, tau_cubic, tau_akima],
        "目标函数最小值": [score_min, score_cubic, score_akima],
    })

    summary = pd.DataFrame([
        ["方式一时间偏差/s", 0.0],
        ["方式二相对方式一时间偏差/s", tau_hat],
        ["时间偏差目标函数最小值", score_min],
        ["候选固定成分X/m", fixed_mu[0]],
        ["候选固定成分Y/m", fixed_mu[1]],
        ["候选固定成分模长/m", float(np.linalg.norm(fixed_mu))],
        ["是否认定为需剥离固定系统偏差", int(detected)],
        ["公共区间样本数", len(aligned)],
        ["公共区间10Hz轨迹点数", len(common_traj)],
        ["第四问扩展10Hz轨迹点数", len(extended_traj)],
        ["残差RMSE/m", float(np.sqrt(np.mean(aligned["dist"].to_numpy(float) ** 2)))],
        ["残差95%分位/m", float(np.quantile(aligned["dist"], 0.95))],
        ["残差99%分位/m", float(np.quantile(aligned["dist"], 0.99))],
    ], columns=["指标", "数值"])

    cov_table = pd.DataFrame({
        "矩阵": [
            "方式一协方差", "方式一协方差",
            "方式二协方差", "方式二协方差",
            "融合后协方差", "融合后协方差",
        ],
        "行": ["X", "Y", "X", "Y", "X", "Y"],
        "X": [cov1[0, 0], cov1[1, 0], cov2[0, 0], cov2[1, 0], cov_f[0, 0], cov_f[1, 0]],
        "Y": [cov1[0, 1], cov1[1, 1], cov2[0, 1], cov2[1, 1], cov_f[0, 1], cov_f[1, 1]],
    })

    # q3_outputs：第三问论文用输出
    summary.to_csv(OUT_DIR / "q3_summary.csv", index=False, encoding="utf-8-sig")
    diagnosis.to_csv(OUT_DIR / "q3_bias_diagnosis.csv", index=False, encoding="utf-8-sig")
    evidence.to_csv(OUT_DIR / "q3_evidence_table.csv", index=False, encoding="utf-8-sig")
    hac.to_csv(OUT_DIR / "q3_hac_tests.csv", index=False, encoding="utf-8-sig")
    bic.to_csv(OUT_DIR / "q3_bic_eff.csv", index=False, encoding="utf-8-sig")
    robustness.to_csv(OUT_DIR / "q3_interpolation_robustness.csv", index=False, encoding="utf-8-sig")
    cov_table.to_csv(OUT_DIR / "q3_covariances.csv", index=False, encoding="utf-8-sig")
    aligned.to_csv(OUT_DIR / "q3_alignment_residuals.csv", index=False, encoding="utf-8-sig")
    boot.to_csv(OUT_DIR / "q3_bootstrap_samples.csv", index=False, encoding="utf-8-sig")
    common_traj.to_csv(OUT_DIR / "q3_10hz_trajectory.csv", index=False, encoding="utf-8-sig")

    # q3_final_outputs：第四问优先读取输出
    extended_path1 = FINAL_OUT_DIR / "q3_10Hz_extended_trajectory_for_q4.csv"
    extended_path2 = FINAL_OUT_DIR / "q3_extended_10hz_trajectory.csv"
    extended_path3 = FINAL_OUT_DIR / "q3_for_q4_10hz_trajectory.csv"
    extended_traj.to_csv(extended_path1, index=False, encoding="utf-8-sig")
    extended_traj.to_csv(extended_path2, index=False, encoding="utf-8-sig")
    extended_traj.to_csv(extended_path3, index=False, encoding="utf-8-sig")

    summary.to_csv(FINAL_OUT_DIR / "q3_summary.csv", index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(OUT_DIR / "q3_results.xlsx", engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="结果汇总", index=False)
        diagnosis.to_excel(writer, sheet_name="固定成分诊断", index=False)
        evidence.to_excel(writer, sheet_name="证据汇总", index=False)
        hac.to_excel(writer, sheet_name="HAC检验", index=False)
        bic.to_excel(writer, sheet_name="BIC_eff", index=False)
        robustness.to_excel(writer, sheet_name="插值稳健性", index=False)
        cov_table.to_excel(writer, sheet_name="协方差矩阵", index=False)
        common_traj.to_excel(writer, sheet_name="公共区间10Hz轨迹", index=False)
        extended_traj.to_excel(writer, sheet_name="第四问扩展轨迹", index=False)
        aligned.to_excel(writer, sheet_name="时间校正残差", index=False)

    plot_time_score(df1, df2, tau_hat)
    plot_fixed_ci(diagnosis)
    plot_hac(hac)
    plot_ecdf(aligned)
    plot_track(aligned, common_traj, extended_traj)

    print("\n求解完成。")
    print("-" * 76)
    print(f"方式一时间偏差：0.000000 s")
    print(f"方式二相对方式一时间偏差：{tau_hat:.6f} s")
    print(f"候选固定成分：({fixed_mu[0]:.6f}, {fixed_mu[1]:.6f}) m")
    print(f"候选固定成分模长：{np.linalg.norm(fixed_mu):.6f} m")
    print(f"是否认定为需剥离固定系统偏差：{'是' if detected else '否'}")
    print(f"公共区间样本数：{len(aligned)}")
    print(f"公共区间10Hz轨迹点数：{len(common_traj)}")
    print(f"第四问扩展10Hz轨迹点数：{len(extended_traj)}")
    print(f"残差RMSE：{float(np.sqrt(np.mean(aligned['dist'].to_numpy(float) ** 2))):.6f} m")
    print(f"残差95%分位：{float(np.quantile(aligned['dist'], 0.95)):.6f} m")
    print(f"残差99%分位：{float(np.quantile(aligned['dist'], 0.99)):.6f} m")

    print("\n第四问应优先读取：")
    print(extended_path1)

    print("\n证据汇总：")
    print(evidence.to_string(index=False))

    print("\nBIC_eff：")
    print(bic.to_string(index=False))

    print("\nHAC稳健检验：")
    print(hac.to_string(index=False))

    print("\n插值稳健性：")
    print(robustness.to_string(index=False))

    print("\n输出目录：")
    print(OUT_DIR)
    print(FINAL_OUT_DIR)


if __name__ == "__main__":
    main()
