# 2026 金地杯数学建模竞赛 — A 题工作仓库

> 多源融合机器人定位 + 任务调度优化（4 小问 + result.xlsx）

## 目录结构

```
.
├── README.md                       # 本文件
├── 26金地杯赛题/2026金地杯/2026_A题/   # 官方题目与附件（原件，未改动）
│   ├── 2026_A题.docx
│   ├── 附件1.xlsx ~ 附件4.xlsx
│   └── result.xlsx                 # 提交模板
└── xk/                             # 解题主目录
    ├── README.md                   # 解题路线 + 约束速查
    ├── code/                       # 求解脚本
    │   ├── explore.py              # 数据画像
    │   └── q1_solve.py             # Q1: 时间对齐 + 10 Hz 轨迹
    ├── data/                       # 附件副本（与官方 md5 一致）
    ├── docs/                       # 题目原件 + 整理 markdown（含公式还原）
    ├── figures/                    # 论文用图
    └── output/                     # 结果 + summary.json
```

## 环境

```bash
# 用 uv（无需 sudo）准备环境
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python \
    numpy pandas scipy matplotlib openpyxl seaborn \
    jupyter ipykernel scikit-learn tqdm xlrd \
    cvxpy gurobipy mammoth python-docx
```

## 运行

```bash
.venv/bin/python xk/code/explore.py     # 数据画像
.venv/bin/python xk/code/q1_solve.py    # Q1 求解
```

## 当前进度

- [x] 环境搭建 + 中文字体配置
- [x] 题目整理（含公式 LaTeX 还原）
- [x] 数据画像
- [x] **Q1 — 时间对齐**（`Δt = -198.4317 s`，残差 1.7e-11 m²，确认无系统偏差）
- [ ] Q2 — 含噪 + 系统偏差融合
- [ ] Q3 — 实测数据系统偏差检验
- [ ] Q4 — 任务调度优化

## Q1 关键结果

| 项 | 值 |
|---|---|
| 时间偏差 $\hat{\Delta t}$ | $-198.4317009$ s |
| 不确定度 $\sigma_{\Delta t}$ | $6.7 \times 10^{-5}$ s ≈ 67 μs |
| 联合估计 $(\hat{\Delta x}, \hat{\Delta y})$ | $(2.2\times10^{-7}, 8.9\times10^{-9})$ m → 实证无系统偏差 |
| 最终残差 $J^*$ | $1.7\times10^{-11}$ m² (≈ 数值精度极限) |
| 双路 RMSE | 5.58 μm |
| 全覆盖 10 Hz 轨迹 | 8494 点，物理时间 [221.0, 1070.3] s |
| 严格交集 10 Hz 轨迹 | 7004 点，物理时间 [270.4, 970.7] s |
