# -*- coding: utf-8 -*-
"""
第二问：剖面最小二乘—系统偏差剥离—协方差融合模型

修正版要点：
1. 避免短公共区间伪极小值；
2. 时间偏差搜索限制在第二问合理区间；
3. 用平滑轨迹估计时间偏差和系统偏差；
4. 用原始观测相对平滑轨迹的残差估计噪声协方差；
5. 在公共有效区间输出10Hz融合轨迹。

运行：
    cd /d E:\数模A
    python program2.py
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.interpolate import CubicSpline, PchipInterpolator, Akima1DInterpolator
from scipy.optimize import minimize_scalar
from scipy.signal import savgol_filter


# ============================================================
# 0. 路径与参数
# ============================================================

BASE_DIR = Path.cwd()
OUT_DIR = BASE_DIR / "q2_outputs"

ATTACHMENT_CANDIDATES = [
    BASE_DIR / "附件2.xlsx",
    BASE_DIR / "附件2：异频定位数据.xlsx",
    BASE_DIR / "附件2_异频定位数据.xlsx",
    BASE_DIR / "attachment2.xlsx",
]

TARGET_HZ = 10.0
TARGET_DT = 1.0 / TARGET_HZ

# 第二问合理时间偏差搜索区间。
# 这不是放宽条件，而是防止全局搜索误选只有几十个公共点的伪极小值。
TAU_SEARCH_MIN = 40.0
TAU_SEARCH_MAX = 60.0

COARSE_STEP = 0.02
REFINE_HALF_WIDTH = 1.0

# 公共区间门槛，避免短片段伪匹配
MIN_COMMON_POINTS = 600
MIN_COMMON_DURATION = 300.0

# 平滑参数
SMOOTH_WINDOW = 61
SMOOTH_POLY = 3

# 协方差正则项
COV_REG = 1e-8


# ============================================================
# 1. 基础工具
# ============================================================

def setup_chinese_font() -> None:
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.sans-serif"] = [
        "SimHei",
        "Microsoft YaHei",
        "Noto Sans CJK SC",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]


def ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def norm_name(x) -> str:
    if x is None:
        return ""
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


def find_existing_file(candidates: list[Path]) -> Path:
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "未找到附件2文件。请确认当前目录存在以下文件之一：\n"
        + "\n".join(str(p) for p in candidates)
    )


def pick_col(df: pd.DataFrame, aliases: list[str]) -> str:
    col_map = {norm_name(c): c for c in df.columns}
    alias_norm = [norm_name(a) for a in aliases]

    for a in alias_norm:
        if a in col_map:
            return col_map[a]

    for key, raw in col_map.items():
        for a in alias_norm:
            if a in key or key in a:
                return raw

    raise KeyError(f"找不到列：{aliases}，当前列为：{list(df.columns)}")


def clean_track_df(raw: pd.DataFrame) -> pd.DataFrame:
    time_col = pick_col(raw, ["时间", "时刻", "t", "time", "time(s)", "t(s)", "时间(s)"])
    x_col = pick_col(raw, ["x", "x坐标", "x坐标(m)", "X坐标(m)", "X/m", "x/m"])
    y_col = pick_col(raw, ["y", "y坐标", "y坐标(m)", "Y坐标(m)", "Y/m", "y/m"])

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
        raise ValueError("有效轨迹点过少，请检查附件2格式。")

    return df


def read_attachment2(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None)

    if len(sheets) < 2:
        raise ValueError("附件2至少应包含两个工作表，分别对应方式一和方式二。")

    sheet_names = list(sheets.keys())

    sheet1 = None
    sheet2 = None

    for name in sheet_names:
        n = norm_name(name)
        if "方式一" in n or "方法一" in n or "定位一" in n:
            sheet1 = name
        if "方式二" in n or "方法二" in n or "定位二" in n:
            sheet2 = name

    if sheet1 is None or sheet2 is None:
        sheet1, sheet2 = sheet_names[0], sheet_names[1]

    df1 = clean_track_df(sheets[sheet1])
    df2 = clean_track_df(sheets[sheet2])

    return df1, df2


def choose_savgol_window(n: int, wanted: int, poly: int) -> int:
    w = min(wanted, n)
    if w % 2 == 0:
        w -= 1
    min_w = poly + 3
    if min_w % 2 == 0:
        min_w += 1
    if w < min_w:
        w = min_w
    if w > n:
        w = n if n % 2 == 1 else n - 1
    return max(w, 3)


def add_smooth_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    n = len(out)

    if n <= SMOOTH_POLY + 4:
        out["x_smooth"] = out["x"]
        out["y_smooth"] = out["y"]
        out["noise_x"] = 0.0
        out["noise_y"] = 0.0
        return out

    window = choose_savgol_window(n, SMOOTH_WINDOW, SMOOTH_POLY)

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


def make_interpolator(
    df: pd.DataFrame,
    kind: str = "pchip",
    x_col: str = "x_smooth",
    y_col: str = "y_smooth",
):
    t = df["time"].to_numpy(float)
    x = df[x_col].to_numpy(float)
    y = df[y_col].to_numpy(float)

    if kind == "cubic":
        fx = CubicSpline(t, x, bc_type="natural", extrapolate=False)
        fy = CubicSpline(t, y, bc_type="natural", extrapolate=False)
    elif kind == "pchip":
        fx = PchipInterpolator(t, x, extrapolate=False)
        fy = PchipInterpolator(t, y, extrapolate=False)
    elif kind == "akima":
        fx = Akima1DInterpolator(t, x)
        fy = Akima1DInterpolator(t, y)
    else:
        raise ValueError(f"未知插值方法：{kind}")

    return fx, fy


def common_time_mask(t1: np.ndarray, t2_min: float, t2_max: float, tau: float) -> np.ndarray:
    """
    定义：
        方式二校正到方式一时间轴：p2(t + tau)

    条件：
        t + tau 必须位于方式二原始时间范围内。
    """
    return (t1 + tau >= t2_min) & (t1 + tau <= t2_max)


def covariance_matrix(rx: np.ndarray, ry: np.ndarray) -> np.ndarray:
    arr = np.vstack([rx, ry])
    cov = np.cov(arr, bias=False)
    cov = np.asarray(cov, dtype=float)

    if cov.shape != (2, 2) or not np.all(np.isfinite(cov)):
        cov = np.eye(2)

    cov = cov + COV_REG * np.eye(2)
    return cov


def ellipse_area_95(cov: np.ndarray) -> float:
    chi2_95 = 5.991
    det = max(float(np.linalg.det(cov)), 0.0)
    return float(math.pi * chi2_95 * math.sqrt(det))


# ============================================================
# 2. 剖面最小二乘：时间偏差与系统偏差估计
# ============================================================

def profiled_bias_and_residual(
    tau: float,
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    interp_kind: str = "pchip",
) -> tuple[np.ndarray, pd.DataFrame]:
    """
    对给定 tau：
    1. 将方式二平滑轨迹插值到方式一时间轴；
    2. 计算 delta = p2(t+tau) - p1(t)；
    3. 解析估计系统偏差 b(tau)=mean(delta)；
    4. 计算剥离偏差后的残差。
    """
    t1 = df1["time"].to_numpy(float)
    x1_s = df1["x_smooth"].to_numpy(float)
    y1_s = df1["y_smooth"].to_numpy(float)

    t2 = df2["time"].to_numpy(float)
    t2_min, t2_max = float(t2.min()), float(t2.max())

    mask = common_time_mask(t1, t2_min, t2_max, tau)

    if mask.sum() < MIN_COMMON_POINTS:
        return np.array([np.nan, np.nan]), pd.DataFrame()

    common_t = t1[mask]
    if float(common_t.max() - common_t.min()) < MIN_COMMON_DURATION:
        return np.array([np.nan, np.nan]), pd.DataFrame()

    fx2_s, fy2_s = make_interpolator(
        df2,
        kind=interp_kind,
        x_col="x_smooth",
        y_col="y_smooth",
    )

    tq = t1[mask] + tau
    x2_s = fx2_s(tq)
    y2_s = fy2_s(tq)

    valid = np.isfinite(x2_s) & np.isfinite(y2_s)

    if valid.sum() < MIN_COMMON_POINTS:
        return np.array([np.nan, np.nan]), pd.DataFrame()

    time = t1[mask][valid]
    x1v = x1_s[mask][valid]
    y1v = y1_s[mask][valid]
    x2v = x2_s[valid]
    y2v = y2_s[valid]

    dx = x2v - x1v
    dy = y2v - y1v

    bx = float(np.mean(dx))
    by = float(np.mean(dy))
    b = np.array([bx, by], dtype=float)

    ex = dx - bx
    ey = dy - by
    e_norm = np.sqrt(ex * ex + ey * ey)

    out = pd.DataFrame({
        "time": time,
        "x1_smooth": x1v,
        "y1_smooth": y1v,
        "x2_smooth_time_aligned": x2v,
        "y2_smooth_time_aligned": y2v,
        "x2_smooth_corrected": x2v - bx,
        "y2_smooth_corrected": y2v - by,
        "delta_x_before_bias": dx,
        "delta_y_before_bias": dy,
        "residual_x_after_bias": ex,
        "residual_y_after_bias": ey,
        "residual_norm_after_bias": e_norm,
    })

    return b, out


def objective_profiled_tau(
    tau: float,
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    interp_kind: str = "pchip",
) -> float:
    b, residual_df = profiled_bias_and_residual(tau, df1, df2, interp_kind)

    if residual_df.empty or not np.all(np.isfinite(b)):
        return np.inf

    ex = residual_df["residual_x_after_bias"].to_numpy(float)
    ey = residual_df["residual_y_after_bias"].to_numpy(float)

    # 使用均方残差作为剖面目标函数
    mse = float(np.mean(ex * ex + ey * ey))

    # 极轻微惩罚短公共区间，进一步抑制伪极小值
    duration = float(residual_df["time"].max() - residual_df["time"].min())
    penalty = 1e-4 / max(duration, 1.0)

    return mse + penalty


def estimate_time_and_bias(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    interp_kind: str = "pchip",
) -> tuple[float, np.ndarray, float, pd.DataFrame]:
    tau_min = TAU_SEARCH_MIN
    tau_max = TAU_SEARCH_MAX

    grid = np.arange(tau_min, tau_max + COARSE_STEP, COARSE_STEP)

    vals = np.array([
        objective_profiled_tau(tau, df1, df2, interp_kind=interp_kind)
        for tau in grid
    ])

    if not np.any(np.isfinite(vals)):
        raise RuntimeError(
            "在当前时间偏差搜索区间内没有满足公共区间约束的候选值。"
            "请检查附件2时间列或适当调整 TAU_SEARCH_MIN / TAU_SEARCH_MAX。"
        )

    best_idx = int(np.nanargmin(vals))
    coarse_tau = float(grid[best_idx])

    left = max(tau_min, coarse_tau - REFINE_HALF_WIDTH)
    right = min(tau_max, coarse_tau + REFINE_HALF_WIDTH)

    res = minimize_scalar(
        lambda z: objective_profiled_tau(z, df1, df2, interp_kind=interp_kind),
        bounds=(left, right),
        method="bounded",
        options={"xatol": 1e-12, "maxiter": 1000},
    )

    if not res.success:
        warnings.warn(f"时间偏差优化未完全收敛：{res.message}")

    tau_hat = float(res.x)
    obj_min = float(res.fun)

    b_hat, residual_df = profiled_bias_and_residual(
        tau_hat,
        df1,
        df2,
        interp_kind=interp_kind,
    )

    return tau_hat, b_hat, obj_min, residual_df


# ============================================================
# 3. 原始观测残差诊断与协方差估计
# ============================================================

def raw_residual_after_correction(
    tau: float,
    b: np.ndarray,
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    interp_kind: str = "pchip",
) -> pd.DataFrame:
    t1 = df1["time"].to_numpy(float)
    x1 = df1["x"].to_numpy(float)
    y1 = df1["y"].to_numpy(float)

    t2 = df2["time"].to_numpy(float)
    mask = common_time_mask(t1, float(t2.min()), float(t2.max()), tau)

    fx2_raw, fy2_raw = make_interpolator(
        df2,
        kind=interp_kind,
        x_col="x",
        y_col="y",
    )

    tq = t1[mask] + tau
    x2 = fx2_raw(tq)
    y2 = fy2_raw(tq)

    valid = np.isfinite(x2) & np.isfinite(y2)

    out = pd.DataFrame({
        "time": t1[mask][valid],
        "x1_raw": x1[mask][valid],
        "y1_raw": y1[mask][valid],
        "x2_raw_time_aligned": x2[valid],
        "y2_raw_time_aligned": y2[valid],
        "x2_raw_corrected": x2[valid] - b[0],
        "y2_raw_corrected": y2[valid] - b[1],
    })

    out["raw_residual_x"] = out["x2_raw_corrected"] - out["x1_raw"]
    out["raw_residual_y"] = out["y2_raw_corrected"] - out["y1_raw"]
    out["raw_residual_norm"] = np.sqrt(
        out["raw_residual_x"] ** 2 + out["raw_residual_y"] ** 2
    )

    return out


def estimate_noise_covariances(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    由原始观测减去平滑轨迹的残差估计两种定位方式噪声协方差。
    """
    cov1 = covariance_matrix(
        df1["noise_x"].to_numpy(float),
        df1["noise_y"].to_numpy(float),
    )
    cov2 = covariance_matrix(
        df2["noise_x"].to_numpy(float),
        df2["noise_y"].to_numpy(float),
    )

    inv1 = np.linalg.inv(cov1)
    inv2 = np.linalg.inv(cov2)
    cov_fused = np.linalg.inv(inv1 + inv2)

    return cov1, cov2, cov_fused


# ============================================================
# 4. 10Hz协方差融合轨迹
# ============================================================

def reconstruct_fused_10hz(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    tau_hat: float,
    b_hat: np.ndarray,
    cov1: np.ndarray,
    cov2: np.ndarray,
    interp_kind: str = "pchip",
) -> pd.DataFrame:
    """
    第二问输出公共区间内的10Hz融合轨迹。
    这样可避免方式二时间平移后在非公共区间产生异常长轨迹。
    """
    t1_min, t1_max = float(df1["time"].min()), float(df1["time"].max())
    t2_min, t2_max = float(df2["time"].min()), float(df2["time"].max())

    start = max(t1_min, t2_min - tau_hat)
    end = min(t1_max, t2_max - tau_hat)

    start = math.ceil(start * TARGET_HZ) / TARGET_HZ
    end = math.floor(end * TARGET_HZ) / TARGET_HZ

    t_new = np.arange(start, end + 0.5 * TARGET_DT, TARGET_DT)

    fx1, fy1 = make_interpolator(
        df1,
        kind=interp_kind,
        x_col="x_smooth",
        y_col="y_smooth",
    )
    fx2, fy2 = make_interpolator(
        df2,
        kind=interp_kind,
        x_col="x_smooth",
        y_col="y_smooth",
    )

    x1 = fx1(t_new)
    y1 = fy1(t_new)

    x2 = fx2(t_new + tau_hat) - b_hat[0]
    y2 = fy2(t_new + tau_hat) - b_hat[1]

    valid = (
        np.isfinite(x1)
        & np.isfinite(y1)
        & np.isfinite(x2)
        & np.isfinite(y2)
    )

    t_new = t_new[valid]
    x1 = x1[valid]
    y1 = y1[valid]
    x2 = x2[valid]
    y2 = y2[valid]

    inv1 = np.linalg.inv(cov1)
    inv2 = np.linalg.inv(cov2)
    cov_f = np.linalg.inv(inv1 + inv2)

    fused = []
    for k in range(len(t_new)):
        p1 = np.array([x1[k], y1[k]], dtype=float)
        p2 = np.array([x2[k], y2[k]], dtype=float)
        pf = cov_f @ (inv1 @ p1 + inv2 @ p2)
        fused.append(pf)

    fused = np.asarray(fused)

    out = pd.DataFrame({
        "time": t_new,
        "x": fused[:, 0],
        "y": fused[:, 1],
        "x_way1_smooth": x1,
        "y_way1_smooth": y1,
        "x_way2_corrected_smooth": x2,
        "y_way2_corrected_smooth": y2,
    })

    return out


# ============================================================
# 5. 指标计算
# ============================================================

def residual_metrics(
    smooth_residual_df: pd.DataFrame,
    raw_residual_df: pd.DataFrame,
) -> dict[str, float]:
    smooth_r = smooth_residual_df["residual_norm_after_bias"].to_numpy(float)
    raw_r = raw_residual_df["raw_residual_norm"].to_numpy(float)

    before = np.sqrt(
        smooth_residual_df["delta_x_before_bias"].to_numpy(float) ** 2
        + smooth_residual_df["delta_y_before_bias"].to_numpy(float) ** 2
    )

    return {
        "仅时间校正平滑RMSE_m": float(np.sqrt(np.mean(before ** 2))),
        "时间和系统偏差校正后平滑RMSE_m": float(np.sqrt(np.mean(smooth_r ** 2))),
        "时间和系统偏差校正后平滑平均残差_m": float(np.mean(smooth_r)),
        "时间和系统偏差校正后平滑最大残差_m": float(np.max(smooth_r)),
        "时间和系统偏差校正后原始RMSE_m": float(np.sqrt(np.mean(raw_r ** 2))),
        "时间和系统偏差校正后原始平均残差_m": float(np.mean(raw_r)),
        "时间和系统偏差校正后原始最大残差_m": float(np.max(raw_r)),
        "公共区间样本数": int(len(smooth_residual_df)),
    }


# ============================================================
# 6. 作图
# ============================================================

def plot_objective(df1: pd.DataFrame, df2: pd.DataFrame, tau_hat: float) -> None:
    taus = np.linspace(TAU_SEARCH_MIN, TAU_SEARCH_MAX, 600)
    vals = np.array([
        objective_profiled_tau(tau, df1, df2, interp_kind="pchip")
        for tau in taus
    ])

    plt.figure(figsize=(10, 5))
    plt.plot(taus, vals)
    plt.axvline(tau_hat, linestyle="--", label=f"最优偏差={tau_hat:.6f}s")
    plt.xlabel("方式二相对方式一时间偏差/s")
    plt.ylabel("剥离系统偏差后的目标函数")
    plt.title("第二问剖面最小二乘目标函数")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q2_profile_objective.png", dpi=300)
    plt.close()


def plot_alignment(smooth_residual_df: pd.DataFrame) -> None:
    plt.figure(figsize=(9, 7))
    plt.scatter(
        smooth_residual_df["x1_smooth"],
        smooth_residual_df["y1_smooth"],
        s=8,
        alpha=0.35,
        label="方式一平滑轨迹点",
    )
    plt.scatter(
        smooth_residual_df["x2_smooth_time_aligned"],
        smooth_residual_df["y2_smooth_time_aligned"],
        s=8,
        alpha=0.25,
        label="方式二仅时间校正",
    )
    plt.plot(
        smooth_residual_df["x2_smooth_corrected"],
        smooth_residual_df["y2_smooth_corrected"],
        linewidth=2,
        label="方式二时间+系统偏差校正",
    )
    plt.axis("equal")
    plt.xlabel("X坐标/m")
    plt.ylabel("Y坐标/m")
    plt.title("第二问系统偏差剥离前后的空间轨迹对比")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q2_bias_removed_alignment.png", dpi=300)
    plt.close()


def plot_residual(smooth_residual_df: pd.DataFrame) -> None:
    plt.figure(figsize=(10, 5))
    plt.plot(
        smooth_residual_df["time"],
        smooth_residual_df["residual_norm_after_bias"],
    )
    plt.xlabel("时间/s")
    plt.ylabel("校正后空间残差/m")
    plt.title("第二问时间校正与系统偏差剥离后的空间残差")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q2_residual_after_bias.png", dpi=300)
    plt.close()


def plot_residual_ecdf(smooth_residual_df: pd.DataFrame) -> None:
    r = np.sort(smooth_residual_df["residual_norm_after_bias"].to_numpy(float))
    y = np.arange(1, len(r) + 1) / len(r)

    q95 = float(np.quantile(r, 0.95))
    q99 = float(np.quantile(r, 0.99))

    plt.figure(figsize=(9, 5))
    plt.plot(r, y)
    plt.axvline(q95, linestyle="--", label=f"95%分位={q95:.3f}m")
    plt.axvline(q99, linestyle=":", label=f"99%分位={q99:.3f}m")
    plt.xlabel("空间残差/m")
    plt.ylabel("经验累计概率")
    plt.title("第二问校正后空间残差经验分布")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q2_residual_ecdf.png", dpi=300)
    plt.close()


def plot_covariance_bars(cov1: np.ndarray, cov2: np.ndarray, covf: np.ndarray) -> None:
    labels = ["X方差", "Y方差", "95%椭圆面积"]

    vals1 = [cov1[0, 0], cov1[1, 1], ellipse_area_95(cov1)]
    vals2 = [cov2[0, 0], cov2[1, 1], ellipse_area_95(cov2)]
    valsf = [covf[0, 0], covf[1, 1], ellipse_area_95(covf)]

    x = np.arange(len(labels))
    width = 0.25

    plt.figure(figsize=(10, 5))
    plt.bar(x - width, vals1, width, label="方式一")
    plt.bar(x, vals2, width, label="方式二")
    plt.bar(x + width, valsf, width, label="融合后")
    plt.xticks(x, labels)
    plt.ylabel("数值")
    plt.title("第二问融合前后不确定性对比")
    plt.grid(True, axis="y", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q2_covariance_comparison.png", dpi=300)
    plt.close()


def plot_fused_trajectory(traj_10hz: pd.DataFrame) -> None:
    plt.figure(figsize=(9, 7))
    plt.plot(traj_10hz["x"], traj_10hz["y"], linewidth=2)
    plt.axis("equal")
    plt.xlabel("X坐标/m")
    plt.ylabel("Y坐标/m")
    plt.title("第二问协方差融合后的10Hz轨迹")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q2_fused_10hz_trajectory.png", dpi=300)
    plt.close()


# ============================================================
# 7. 主程序
# ============================================================

def main() -> None:
    setup_chinese_font()
    ensure_out_dir()

    attachment_path = find_existing_file(ATTACHMENT_CANDIDATES)

    print("=" * 72)
    print("第二问：剖面最小二乘—系统偏差剥离—协方差融合")
    print("=" * 72)
    print(f"读取文件：{attachment_path}")

    df1_raw, df2_raw = read_attachment2(attachment_path)

    df1 = add_smooth_columns(df1_raw)
    df2 = add_smooth_columns(df2_raw)

    print(f"方式一点数：{len(df1)}")
    print(f"方式二点数：{len(df2)}")
    print(f"方式一时间范围：{df1['time'].min():.6f} — {df1['time'].max():.6f} s")
    print(f"方式二时间范围：{df2['time'].min():.6f} — {df2['time'].max():.6f} s")
    print(f"时间偏差搜索区间：[{TAU_SEARCH_MIN}, {TAU_SEARCH_MAX}] s")

    tau_hat, b_hat, obj_min, smooth_residual_df = estimate_time_and_bias(
        df1,
        df2,
        interp_kind="pchip",
    )

    tau_cubic, b_cubic, obj_cubic, _ = estimate_time_and_bias(
        df1,
        df2,
        interp_kind="cubic",
    )

    tau_akima, b_akima, obj_akima, _ = estimate_time_and_bias(
        df1,
        df2,
        interp_kind="akima",
    )

    raw_residual_df = raw_residual_after_correction(
        tau_hat,
        b_hat,
        df1,
        df2,
        interp_kind="pchip",
    )

    cov1, cov2, covf = estimate_noise_covariances(df1, df2)

    traj_10hz = reconstruct_fused_10hz(
        df1=df1,
        df2=df2,
        tau_hat=tau_hat,
        b_hat=b_hat,
        cov1=cov1,
        cov2=cov2,
        interp_kind="pchip",
    )

    metrics = residual_metrics(smooth_residual_df, raw_residual_df)

    summary_rows = [
        ["方式一时间偏差/s", 0.0],
        ["方式二相对方式一时间偏差/s", tau_hat],
        ["方式一系统偏差X/m", 0.0],
        ["方式一系统偏差Y/m", 0.0],
        ["方式二系统偏差X/m", b_hat[0]],
        ["方式二系统偏差Y/m", b_hat[1]],
        ["剖面目标函数最小值", obj_min],
        ["仅时间校正平滑RMSE/m", metrics["仅时间校正平滑RMSE_m"]],
        ["时间+系统偏差校正平滑RMSE/m", metrics["时间和系统偏差校正后平滑RMSE_m"]],
        ["时间+系统偏差校正平滑最大残差/m", metrics["时间和系统偏差校正后平滑最大残差_m"]],
        ["时间+系统偏差校正原始RMSE/m", metrics["时间和系统偏差校正后原始RMSE_m"]],
        ["公共区间样本数", metrics["公共区间样本数"]],
        ["10Hz融合轨迹点数", len(traj_10hz)],
        ["方式一95%置信椭圆面积/m2", ellipse_area_95(cov1)],
        ["方式二95%置信椭圆面积/m2", ellipse_area_95(cov2)],
        ["融合后95%置信椭圆面积/m2", ellipse_area_95(covf)],
    ]

    summary_df = pd.DataFrame(summary_rows, columns=["指标", "数值"])

    robustness_df = pd.DataFrame({
        "插值方法": ["PCHIP", "自然三次样条", "Akima"],
        "时间偏差/s": [tau_hat, tau_cubic, tau_akima],
        "系统偏差X/m": [b_hat[0], b_cubic[0], b_akima[0]],
        "系统偏差Y/m": [b_hat[1], b_cubic[1], b_akima[1]],
        "目标函数最小值": [obj_min, obj_cubic, obj_akima],
    })

    covariance_df = pd.DataFrame({
        "矩阵": [
            "方式一协方差", "方式一协方差",
            "方式二协方差", "方式二协方差",
            "融合后协方差", "融合后协方差",
        ],
        "行": ["X", "Y", "X", "Y", "X", "Y"],
        "X": [
            cov1[0, 0], cov1[1, 0],
            cov2[0, 0], cov2[1, 0],
            covf[0, 0], covf[1, 0],
        ],
        "Y": [
            cov1[0, 1], cov1[1, 1],
            cov2[0, 1], cov2[1, 1],
            covf[0, 1], covf[1, 1],
        ],
    })

    smooth_residual_df.to_csv(
        OUT_DIR / "q2_alignment_residuals_smooth.csv",
        index=False,
        encoding="utf-8-sig",
    )
    raw_residual_df.to_csv(
        OUT_DIR / "q2_alignment_residuals_raw.csv",
        index=False,
        encoding="utf-8-sig",
    )
    traj_10hz.to_csv(
        OUT_DIR / "q2_10hz_fused_trajectory.csv",
        index=False,
        encoding="utf-8-sig",
    )
    summary_df.to_csv(
        OUT_DIR / "q2_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    robustness_df.to_csv(
        OUT_DIR / "q2_interpolation_robustness.csv",
        index=False,
        encoding="utf-8-sig",
    )
    covariance_df.to_csv(
        OUT_DIR / "q2_covariances.csv",
        index=False,
        encoding="utf-8-sig",
    )

    with pd.ExcelWriter(OUT_DIR / "q2_results.xlsx", engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="结果汇总", index=False)
        robustness_df.to_excel(writer, sheet_name="插值稳健性", index=False)
        covariance_df.to_excel(writer, sheet_name="协方差矩阵", index=False)
        traj_10hz.to_excel(writer, sheet_name="10Hz融合轨迹", index=False)
        smooth_residual_df.to_excel(writer, sheet_name="平滑校正残差", index=False)
        raw_residual_df.to_excel(writer, sheet_name="原始校正残差", index=False)

    plot_objective(df1, df2, tau_hat)
    plot_alignment(smooth_residual_df)
    plot_residual(smooth_residual_df)
    plot_residual_ecdf(smooth_residual_df)
    plot_covariance_bars(cov1, cov2, covf)
    plot_fused_trajectory(traj_10hz)

    print("\n求解完成。")
    print("-" * 72)
    print(f"方式一时间偏差：0.000000 s")
    print(f"方式二相对方式一时间偏差：{tau_hat:.6f} s")
    print(f"方式一系统偏差：(0.000000, 0.000000) m")
    print(f"方式二系统偏差：({b_hat[0]:.6f}, {b_hat[1]:.6f}) m")
    print(f"仅时间校正平滑RMSE：{metrics['仅时间校正平滑RMSE_m']:.6f} m")
    print(f"时间+系统偏差校正平滑RMSE：{metrics['时间和系统偏差校正后平滑RMSE_m']:.6f} m")
    print(f"时间+系统偏差校正原始RMSE：{metrics['时间和系统偏差校正后原始RMSE_m']:.6f} m")
    print(f"公共区间样本数：{metrics['公共区间样本数']}")
    print(f"10Hz融合轨迹点数：{len(traj_10hz)}")

    print("\n协方差矩阵：")
    print("方式一：")
    print(cov1)
    print("方式二：")
    print(cov2)
    print("融合后：")
    print(covf)

    print("\n95%置信椭圆面积：")
    print(f"方式一：{ellipse_area_95(cov1):.6f} m²")
    print(f"方式二：{ellipse_area_95(cov2):.6f} m²")
    print(f"融合后：{ellipse_area_95(covf):.6f} m²")

    print("\n插值稳健性：")
    print(robustness_df.to_string(index=False))

    print("\n输出目录：")
    print(OUT_DIR)
    print("\n主要输出文件：")
    print(OUT_DIR / "q2_results.xlsx")
    print(OUT_DIR / "q2_10hz_fused_trajectory.csv")
    print(OUT_DIR / "q2_summary.csv")
    print(OUT_DIR / "q2_profile_objective.png")
    print(OUT_DIR / "q2_bias_removed_alignment.png")
    print(OUT_DIR / "q2_fused_10hz_trajectory.png")


if __name__ == "__main__":
    main()