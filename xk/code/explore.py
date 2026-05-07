"""数据画像：附件 1/2/3 两种定位方式的时空特性 + 噪声量级估计。

输出：
    figures/explore_overview.png    四宫格 × 三附件，鸟瞰
    figures/explore_dt_hist.png     采样间隔直方图
    figures/explore_noise_est.png   噪声量级估计（基于平滑残差）
    output/explore_report.md        文字报告
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent / "A"))  # 复用 plot_style
from plot_style import setup_plot_style  # noqa: E402

setup_plot_style()

DATA = ROOT / "data"
FIGS = ROOT / "figures"
OUT = ROOT / "output"
FIGS.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

ATTACHMENTS = [
    ("附件1", DATA / "附件1.xlsx", "无噪声 + 时间偏差"),
    ("附件2", DATA / "附件2.xlsx", "含噪声 + 系统偏差"),
    ("附件3", DATA / "附件3.xlsx", "实测数据"),
]


def load(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    xl = pd.ExcelFile(path)
    s1 = pd.read_excel(xl, "方式1(4Hz)")
    s2 = pd.read_excel(xl, "方式2(5Hz)")
    s1.columns = ["t", "x", "y"]
    s2.columns = ["t", "x", "y"]
    return s1.sort_values("t").reset_index(drop=True), s2.sort_values("t").reset_index(drop=True)


def basic_stats(df: pd.DataFrame) -> dict:
    dt = np.diff(df["t"].values)
    return dict(
        n=len(df),
        t0=float(df["t"].iloc[0]),
        t1=float(df["t"].iloc[-1]),
        dur=float(df["t"].iloc[-1] - df["t"].iloc[0]),
        dt_mean=float(np.mean(dt)),
        dt_std=float(np.std(dt)),
        dt_min=float(np.min(dt)),
        dt_max=float(np.max(dt)),
        x_range=(float(df["x"].min()), float(df["x"].max())),
        y_range=(float(df["y"].min()), float(df["y"].max())),
    )


def smooth_residual(df: pd.DataFrame, win: int = 9) -> tuple[np.ndarray, np.ndarray]:
    """用滑动平均做粗糙的"真值"，残差近似为噪声水平。"""
    x = df["x"].values
    y = df["y"].values
    k = np.ones(win) / win
    xs = np.convolve(x, k, mode="same")
    ys = np.convolve(y, k, mode="same")
    edge = win // 2
    rx = (x - xs)[edge:-edge]
    ry = (y - ys)[edge:-edge]
    return rx, ry


# ---------- 图 1：四列鸟瞰（每行一个附件） ----------
fig, axes = plt.subplots(3, 4, figsize=(16, 11))
report_lines = ["# 数据画像报告\n"]

for row, (name, path, desc) in enumerate(ATTACHMENTS):
    s1, s2 = load(path)
    st1, st2 = basic_stats(s1), basic_stats(s2)

    report_lines.append(f"## {name}（{desc}）\n")
    report_lines.append("| 方式 | 行数 | 起 (s) | 止 (s) | 时长 (s) | dt 均/标 (s) | x 范围 | y 范围 |")
    report_lines.append("|---|---:|---:|---:|---:|---|---|---|")
    for tag, st in [("方式1 (4Hz)", st1), ("方式2 (5Hz)", st2)]:
        report_lines.append(
            f"| {tag} | {st['n']} | {st['t0']:.3f} | {st['t1']:.3f} | {st['dur']:.2f}"
            f" | {st['dt_mean']:.4f}/{st['dt_std']:.5f}"
            f" | [{st['x_range'][0]:.2f}, {st['x_range'][1]:.2f}]"
            f" | [{st['y_range'][0]:.2f}, {st['y_range'][1]:.2f}] |"
        )

    overlap = (max(st1["t0"], st2["t0"]), min(st1["t1"], st2["t1"]))
    overlap_dur = max(0.0, overlap[1] - overlap[0])
    report_lines.append(
        f"\n**时间重叠区间**: [{overlap[0]:.2f}, {overlap[1]:.2f}] s,"
        f" 长度 {overlap_dur:.2f} s\n"
    )

    # 列1：xy 轨迹
    ax = axes[row, 0]
    ax.plot(s1["x"], s1["y"], lw=0.8, alpha=0.7, label="方式1 (4Hz)")
    ax.plot(s2["x"], s2["y"], lw=0.8, alpha=0.7, label="方式2 (5Hz)", linestyle="--")
    ax.set_title(f"{name} 轨迹叠加")
    ax.set_xlabel("X (m)")
    ax.set_ylabel("Y (m)")
    ax.legend(loc="best", fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")

    # 列2：x(t)
    ax = axes[row, 1]
    ax.plot(s1["t"], s1["x"], lw=0.6, label="方式1")
    ax.plot(s2["t"], s2["x"], lw=0.6, label="方式2")
    ax.set_title(f"{name} X 随时间")
    ax.set_xlabel("t (s)")
    ax.set_ylabel("X (m)")
    ax.legend(fontsize=9)

    # 列3：y(t)
    ax = axes[row, 2]
    ax.plot(s1["t"], s1["y"], lw=0.6, label="方式1")
    ax.plot(s2["t"], s2["y"], lw=0.6, label="方式2")
    ax.set_title(f"{name} Y 随时间")
    ax.set_xlabel("t (s)")
    ax.set_ylabel("Y (m)")
    ax.legend(fontsize=9)

    # 列4：dt 直方图
    ax = axes[row, 3]
    dt1 = np.diff(s1["t"].values)
    dt2 = np.diff(s2["t"].values)
    ax.hist(dt1, bins=40, alpha=0.6, label=f"方式1 μ={dt1.mean():.4f}")
    ax.hist(dt2, bins=40, alpha=0.6, label=f"方式2 μ={dt2.mean():.4f}")
    ax.set_title(f"{name} 采样间隔分布")
    ax.set_xlabel("Δt (s)")
    ax.set_ylabel("频次")
    ax.legend(fontsize=9)

fig.suptitle("数据画像 — 三附件鸟瞰", fontsize=13, y=1.0)
fig.tight_layout()
fig.savefig(FIGS / "explore_overview.png")
plt.close(fig)
report_lines.append("\n图：`figures/explore_overview.png`\n")


# ---------- 图 2：噪声量级估计（附件 2 / 3） ----------
fig, axes = plt.subplots(2, 4, figsize=(15, 7))
report_lines.append("\n## 噪声量级估计\n")
report_lines.append("> 方法：滑动平均 (window=9) 作为粗糙轨迹，残差作噪声近似。")
report_lines.append("> 附件 1 无噪声（残差≈0 仅反映轨迹曲率），附件 2/3 含噪。\n")
report_lines.append("| 附件 | 方式 | σx (m) | σy (m) |")
report_lines.append("|---|---|---:|---:|")

for col_pair, (name, path, _) in enumerate(ATTACHMENTS):
    if col_pair == 0:
        # 附件1 仍画一次作为对照
        pass
    s1, s2 = load(path)
    for ridx, (tag, df) in enumerate([("方式1", s1), ("方式2", s2)]):
        rx, ry = smooth_residual(df)
        sx, sy = float(np.std(rx)), float(np.std(ry))
        report_lines.append(f"| {name} | {tag} | {sx:.4f} | {sy:.4f} |")
        if name in ("附件2", "附件3"):
            ax = axes[ridx, 0 if name == "附件2" else 2]
            ax.plot(rx[:300], lw=0.6, label="残差 X")
            ax.set_title(f"{name} {tag} X 残差 (σ={sx:.3f})")
            ax.set_xlabel("样本序号")
            ax.set_ylabel("残差 (m)")
            ax = axes[ridx, 1 if name == "附件2" else 3]
            ax.plot(ry[:300], lw=0.6, color="C1", label="残差 Y")
            ax.set_title(f"{name} {tag} Y 残差 (σ={sy:.3f})")
            ax.set_xlabel("样本序号")
            ax.set_ylabel("残差 (m)")

fig.suptitle("噪声量级估计 — 滑动平均残差（附件2/3）", fontsize=12, y=1.0)
fig.tight_layout()
fig.savefig(FIGS / "explore_noise_est.png")
plt.close(fig)
report_lines.append("\n图：`figures/explore_noise_est.png`\n")


# ---------- 图 3：附件4 目标点空间分布 ----------
xl = pd.ExcelFile(DATA / "附件4.xlsx")
shoot = pd.read_excel(xl, "射击目标")
photo = pd.read_excel(xl, "拍照目标")
shoot.columns = ["id", "x", "y"]
photo.columns = ["id", "x", "y"]

# 叠在附件3轨迹上看可达性
s1, s2 = load(DATA / "附件3.xlsx")
fig, ax = plt.subplots(figsize=(9, 7))
ax.plot(s1["x"], s1["y"], lw=0.5, alpha=0.5, label="附件3 方式1")
ax.plot(s2["x"], s2["y"], lw=0.5, alpha=0.5, label="附件3 方式2", linestyle="--")
ax.scatter(shoot["x"], shoot["y"], marker="x", s=70, color="red", label="射击目标 (S01-S18)")
ax.scatter(photo["x"], photo["y"], marker="o", s=70,
           facecolors="none", edgecolors="green", linewidth=1.5, label="拍照目标 (P01-P18)")
for _, r in shoot.iterrows():
    ax.annotate(r["id"], (r["x"], r["y"]), fontsize=7, color="red", xytext=(3, 3), textcoords="offset points")
for _, r in photo.iterrows():
    ax.annotate(r["id"], (r["x"], r["y"]), fontsize=7, color="green", xytext=(3, 3), textcoords="offset points")
ax.set_title("附件3 轨迹 + 附件4 任务目标分布")
ax.set_xlabel("X (m)")
ax.set_ylabel("Y (m)")
ax.legend(loc="best", fontsize=9)
ax.set_aspect("equal", adjustable="datalim")
fig.tight_layout()
fig.savefig(FIGS / "explore_targets.png")
plt.close(fig)

x_traj_min = min(s1["x"].min(), s2["x"].min())
x_traj_max = max(s1["x"].max(), s2["x"].max())
y_traj_min = min(s1["y"].min(), s2["y"].min())
y_traj_max = max(s1["y"].max(), s2["y"].max())
report_lines.append("\n## 附件4 任务目标\n")
report_lines.append(f"- 射击目标 {len(shoot)} 个，X∈[{shoot['x'].min():.1f},{shoot['x'].max():.1f}]，Y∈[{shoot['y'].min():.1f},{shoot['y'].max():.1f}]")
report_lines.append(f"- 拍照目标 {len(photo)} 个，X∈[{photo['x'].min():.1f},{photo['x'].max():.1f}]，Y∈[{photo['y'].min():.1f},{photo['y'].max():.1f}]")
report_lines.append(f"- 附件3 轨迹包络 X∈[{x_traj_min:.1f},{x_traj_max:.1f}]，Y∈[{y_traj_min:.1f},{y_traj_max:.1f}]")
report_lines.append("\n图：`figures/explore_targets.png`\n")

(OUT / "explore_report.md").write_text("\n".join(report_lines), encoding="utf-8")
print("OK")
print(f"  figures: {FIGS}")
print(f"  report : {OUT/'explore_report.md'}")
