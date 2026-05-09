# -*- coding: utf-8 -*-
"""
第一问：无噪声异频定位数据的时间偏差估计与10Hz轨迹重建

功能：
1. 读取附件1中两种定位方式的数据；
2. 估计方式二相对方式一的时间偏差；
3. 检验时间校正后的空间残差、速度一致性、方向角一致性；
4. 输出统一10Hz轨迹；
5. 生成论文可用图件和结果表。

运行：
    cd /d E:\数模A
    python program1.py
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


# ============================================================
# 0. 路径与参数
# ============================================================

BASE_DIR = Path.cwd()
OUT_DIR = BASE_DIR / "q1_outputs"

ATTACHMENT_CANDIDATES = [
    BASE_DIR / "附件1.xlsx",
    BASE_DIR / "附件1：异频定位数据.xlsx",
    BASE_DIR / "附件1_异频定位数据.xlsx",
    BASE_DIR / "attachment1.xlsx",
]

TARGET_HZ = 10.0
TARGET_DT = 1.0 / TARGET_HZ

# 粗搜索步长，越小越稳但越慢
COARSE_STEP = 0.05

# 精化搜索半宽
REFINE_HALF_WIDTH = 2.0

# 候选偏差搜索范围；若附件时间跨度正常，此范围足够覆盖第一问
SEARCH_MARGIN = 5.0


# ============================================================
# 1. 工具函数
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
        "未找到附件1文件。请确认当前目录存在以下文件之一：\n"
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

    if len(df) < 5:
        raise ValueError("有效轨迹点过少，请检查附件1格式。")

    return df


def read_attachment1(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    sheets = pd.read_excel(path, sheet_name=None)

    if len(sheets) < 2:
        raise ValueError("附件1至少应包含两个工作表，分别对应方式一和方式二。")

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


def make_interpolator(df: pd.DataFrame, kind: str):
    t = df["time"].to_numpy(float)
    x = df["x"].to_numpy(float)
    y = df["y"].to_numpy(float)

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
    采用定义：
        方式二校正后位置 = p2(t + tau)

    因此，方式一时刻 t 能比较的条件是：
        t + tau 位于方式二原始时间范围内。
    """
    return (t1 + tau >= t2_min) & (t1 + tau <= t2_max)


def objective_time_shift(
    tau: float,
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    interp_kind: str = "cubic",
) -> float:
    t1 = df1["time"].to_numpy(float)
    x1 = df1["x"].to_numpy(float)
    y1 = df1["y"].to_numpy(float)

    t2 = df2["time"].to_numpy(float)
    t2_min, t2_max = float(t2.min()), float(t2.max())

    mask = common_time_mask(t1, t2_min, t2_max, tau)
    if mask.sum() < 5:
        return np.inf

    fx2, fy2 = make_interpolator(df2, interp_kind)

    tq = t1[mask] + tau
    x2q = fx2(tq)
    y2q = fy2(tq)

    valid = np.isfinite(x2q) & np.isfinite(y2q)
    if valid.sum() < 5:
        return np.inf

    dx = x1[mask][valid] - x2q[valid]
    dy = y1[mask][valid] - y2q[valid]

    return float(np.mean(dx * dx + dy * dy))


def estimate_time_shift(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    interp_kind: str = "cubic",
) -> tuple[float, float]:
    t1 = df1["time"].to_numpy(float)
    t2 = df2["time"].to_numpy(float)

    # 使两条轨迹至少存在交集的偏差范围
    tau_min = float(t2.min() - t1.max()) + SEARCH_MARGIN
    tau_max = float(t2.max() - t1.min()) - SEARCH_MARGIN

    if tau_min >= tau_max:
        raise ValueError("两组数据时间范围异常，无法构造公共区间。")

    grid = np.arange(tau_min, tau_max + COARSE_STEP, COARSE_STEP)
    vals = np.array([
        objective_time_shift(tau, df1, df2, interp_kind=interp_kind)
        for tau in grid
    ])

    best_idx = int(np.nanargmin(vals))
    coarse_tau = float(grid[best_idx])

    left = max(tau_min, coarse_tau - REFINE_HALF_WIDTH)
    right = min(tau_max, coarse_tau + REFINE_HALF_WIDTH)

    res = minimize_scalar(
        lambda z: objective_time_shift(z, df1, df2, interp_kind=interp_kind),
        bounds=(left, right),
        method="bounded",
        options={"xatol": 1e-12, "maxiter": 1000},
    )

    if not res.success:
        warnings.warn(f"一维优化未完全收敛：{res.message}")

    best_tau = float(res.x)
    best_obj = float(res.fun)

    return best_tau, best_obj


def residual_after_alignment(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    tau: float,
    interp_kind: str = "cubic",
) -> pd.DataFrame:
    t1 = df1["time"].to_numpy(float)
    x1 = df1["x"].to_numpy(float)
    y1 = df1["y"].to_numpy(float)

    t2 = df2["time"].to_numpy(float)
    mask = common_time_mask(t1, float(t2.min()), float(t2.max()), tau)

    fx2, fy2 = make_interpolator(df2, interp_kind)

    tq = t1[mask] + tau
    x2q = fx2(tq)
    y2q = fy2(tq)

    valid = np.isfinite(x2q) & np.isfinite(y2q)

    out = pd.DataFrame({
        "time": t1[mask][valid],
        "x1": x1[mask][valid],
        "y1": y1[mask][valid],
        "x2_aligned": x2q[valid],
        "y2_aligned": y2q[valid],
    })

    out["rx"] = out["x2_aligned"] - out["x1"]
    out["ry"] = out["y2_aligned"] - out["y1"]
    out["r_norm"] = np.sqrt(out["rx"] ** 2 + out["ry"] ** 2)

    return out


def angle_deg(vx: np.ndarray, vy: np.ndarray) -> np.ndarray:
    return np.degrees(np.arctan2(vy, vx))


def circular_angle_diff_deg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = np.abs(a - b) % 360.0
    return np.minimum(d, 360.0 - d)


def consistency_check(residual_df: pd.DataFrame) -> dict[str, float]:
    t = residual_df["time"].to_numpy(float)

    x1 = residual_df["x1"].to_numpy(float)
    y1 = residual_df["y1"].to_numpy(float)
    x2 = residual_df["x2_aligned"].to_numpy(float)
    y2 = residual_df["y2_aligned"].to_numpy(float)

    # 为避免非均匀时间间隔问题，使用 gradient(t)
    vx1 = np.gradient(x1, t)
    vy1 = np.gradient(y1, t)
    vx2 = np.gradient(x2, t)
    vy2 = np.gradient(y2, t)

    v1 = np.sqrt(vx1 ** 2 + vy1 ** 2)
    v2 = np.sqrt(vx2 ** 2 + vy2 ** 2)

    theta1 = angle_deg(vx1, vy1)
    theta2 = angle_deg(vx2, vy2)
    theta_diff = circular_angle_diff_deg(theta1, theta2)

    return {
        "残差RMSE_m": float(np.sqrt(np.mean(residual_df["r_norm"].to_numpy(float) ** 2))),
        "最大残差_m": float(np.max(residual_df["r_norm"].to_numpy(float))),
        "平均残差_m": float(np.mean(residual_df["r_norm"].to_numpy(float))),
        "速度RMSE_mps": float(np.sqrt(np.mean((v2 - v1) ** 2))),
        "最大方向角差_deg": float(np.max(theta_diff)),
        "平均方向角差_deg": float(np.mean(theta_diff)),
    }


def reconstruct_10hz(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    tau: float,
    interp_kind: str = "cubic",
) -> pd.DataFrame:
    """
    第一问无噪声，校正后两种方式理论一致。
    为减小插值端点误差，输出公共区间内两者均值轨迹。
    """
    t1_min, t1_max = float(df1["time"].min()), float(df1["time"].max())
    t2_min, t2_max = float(df2["time"].min()), float(df2["time"].max())

    start = max(t1_min, t2_min - tau)
    end = min(t1_max, t2_max - tau)

    start = math.ceil(start * TARGET_HZ) / TARGET_HZ
    end = math.floor(end * TARGET_HZ) / TARGET_HZ

    t_new = np.arange(start, end + 0.5 * TARGET_DT, TARGET_DT)

    fx1, fy1 = make_interpolator(df1, interp_kind)
    fx2, fy2 = make_interpolator(df2, interp_kind)

    x1 = fx1(t_new)
    y1 = fy1(t_new)

    x2 = fx2(t_new + tau)
    y2 = fy2(t_new + tau)

    valid = (
        np.isfinite(x1)
        & np.isfinite(y1)
        & np.isfinite(x2)
        & np.isfinite(y2)
    )

    x_hat = 0.5 * (x1[valid] + x2[valid])
    y_hat = 0.5 * (y1[valid] + y2[valid])

    out = pd.DataFrame({
        "time": t_new[valid],
        "x": x_hat,
        "y": y_hat,
        "x_way1": x1[valid],
        "y_way1": y1[valid],
        "x_way2_aligned": x2[valid],
        "y_way2_aligned": y2[valid],
    })

    return out


# ============================================================
# 2. 作图
# ============================================================

def plot_objective(df1: pd.DataFrame, df2: pd.DataFrame, best_tau: float) -> None:
    t1 = df1["time"].to_numpy(float)
    t2 = df2["time"].to_numpy(float)

    tau_min = float(t2.min() - t1.max()) + SEARCH_MARGIN
    tau_max = float(t2.max() - t1.min()) - SEARCH_MARGIN

    # 只画最优值附近，论文更清晰
    left = max(tau_min, best_tau - 4.0)
    right = min(tau_max, best_tau + 4.0)

    taus = np.linspace(left, right, 500)
    vals = np.array([
        objective_time_shift(tau, df1, df2, interp_kind="cubic")
        for tau in taus
    ])

    plt.figure(figsize=(10, 5))
    plt.plot(taus, vals)
    plt.axvline(best_tau, linestyle="--", label=f"最优偏差={best_tau:.6f}s")
    plt.xlabel("方式二相对方式一时间偏差/s")
    plt.ylabel("平均平方距离目标函数")
    plt.title("第一问时间偏差目标函数极小值搜索")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q1_time_shift_objective.png", dpi=300)
    plt.close()


def plot_alignment(residual_df: pd.DataFrame) -> None:
    plt.figure(figsize=(9, 7))
    plt.plot(residual_df["x1"], residual_df["y1"], label="方式一轨迹", linewidth=2)
    plt.plot(
        residual_df["x2_aligned"],
        residual_df["y2_aligned"],
        linestyle="--",
        label="方式二时间校正后轨迹",
        linewidth=2,
    )
    plt.axis("equal")
    plt.xlabel("X坐标/m")
    plt.ylabel("Y坐标/m")
    plt.title("第一问时间校正后的轨迹重合效果")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q1_aligned_trajectory.png", dpi=300)
    plt.close()


def plot_residual(residual_df: pd.DataFrame) -> None:
    plt.figure(figsize=(10, 5))
    plt.plot(residual_df["time"], residual_df["r_norm"])
    plt.xlabel("时间/s")
    plt.ylabel("空间残差/m")
    plt.title("第一问时间校正后的空间残差")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q1_alignment_residual.png", dpi=300)
    plt.close()


def plot_10hz(trajectory_10hz: pd.DataFrame) -> None:
    plt.figure(figsize=(9, 7))
    plt.plot(trajectory_10hz["x"], trajectory_10hz["y"], linewidth=2)
    plt.axis("equal")
    plt.xlabel("X坐标/m")
    plt.ylabel("Y坐标/m")
    plt.title("第一问重构得到的10Hz轨迹")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(OUT_DIR / "q1_10hz_trajectory.png", dpi=300)
    plt.close()


# ============================================================
# 3. 主程序
# ============================================================

def main() -> None:
    setup_chinese_font()
    ensure_out_dir()

    attachment_path = find_existing_file(ATTACHMENT_CANDIDATES)

    print("=" * 70)
    print("第一问：无噪声异频定位数据时间同步与10Hz轨迹重建")
    print("=" * 70)
    print(f"读取文件：{attachment_path}")

    df1, df2 = read_attachment1(attachment_path)

    print(f"方式一点数：{len(df1)}")
    print(f"方式二点数：{len(df2)}")
    print(f"方式一时间范围：{df1['time'].min():.6f} — {df1['time'].max():.6f} s")
    print(f"方式二时间范围：{df2['time'].min():.6f} — {df2['time'].max():.6f} s")

    # 主结果：自然三次样条
    best_tau, best_obj = estimate_time_shift(df1, df2, interp_kind="cubic")

    # 稳健性：PCHIP 与 Akima
    tau_pchip, obj_pchip = estimate_time_shift(df1, df2, interp_kind="pchip")
    tau_akima, obj_akima = estimate_time_shift(df1, df2, interp_kind="akima")

    residual_df = residual_after_alignment(df1, df2, best_tau, interp_kind="cubic")
    checks = consistency_check(residual_df)

    traj_10hz = reconstruct_10hz(df1, df2, best_tau, interp_kind="cubic")

    summary_rows = [
        ["方式一时间偏差/s", 0.0],
        ["方式二相对方式一时间偏差/s", best_tau],
        ["最小目标函数值", best_obj],
        ["校正后公共区间点数", len(residual_df)],
        ["10Hz轨迹点数", len(traj_10hz)],
    ]

    for k, v in checks.items():
        summary_rows.append([k, v])

    summary_df = pd.DataFrame(summary_rows, columns=["指标", "数值"])

    robust_df = pd.DataFrame({
        "插值方法": ["自然三次样条", "PCHIP", "Akima"],
        "时间偏差/s": [best_tau, tau_pchip, tau_akima],
        "目标函数最小值": [best_obj, obj_pchip, obj_akima],
    })

    residual_df.to_csv(OUT_DIR / "q1_alignment_residuals.csv", index=False, encoding="utf-8-sig")
    traj_10hz.to_csv(OUT_DIR / "q1_10hz_trajectory.csv", index=False, encoding="utf-8-sig")
    summary_df.to_csv(OUT_DIR / "q1_summary.csv", index=False, encoding="utf-8-sig")
    robust_df.to_csv(OUT_DIR / "q1_interpolation_robustness.csv", index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(OUT_DIR / "q1_results.xlsx", engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="结果汇总", index=False)
        robust_df.to_excel(writer, sheet_name="插值稳健性", index=False)
        traj_10hz.to_excel(writer, sheet_name="10Hz轨迹", index=False)
        residual_df.to_excel(writer, sheet_name="校正残差", index=False)

    plot_objective(df1, df2, best_tau)
    plot_alignment(residual_df)
    plot_residual(residual_df)
    plot_10hz(traj_10hz)

    print("\n求解完成。")
    print("-" * 70)
    print(f"方式一时间偏差：0.000000 s")
    print(f"方式二相对方式一时间偏差：{best_tau:.6f} s")
    print(f"最小目标函数值：{best_obj:.6e}")
    print(f"校正后残差RMSE：{checks['残差RMSE_m']:.6e} m")
    print(f"最大空间残差：{checks['最大残差_m']:.6e} m")
    print(f"最大方向角差：{checks['最大方向角差_deg']:.6e} °")
    print(f"10Hz轨迹点数：{len(traj_10hz)}")

    print("\n插值稳健性：")
    print(robust_df.to_string(index=False))

    print("\n输出目录：")
    print(OUT_DIR)
    print("\n主要输出文件：")
    print(OUT_DIR / "q1_results.xlsx")
    print(OUT_DIR / "q1_10hz_trajectory.csv")
    print(OUT_DIR / "q1_summary.csv")
    print(OUT_DIR / "q1_time_shift_objective.png")
    print(OUT_DIR / "q1_aligned_trajectory.png")


if __name__ == "__main__":
    main()