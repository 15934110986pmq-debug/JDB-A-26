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
    │   ├── q1_solve.py             # Q1 省奖：单参数 Brent + 线性插值
    │   ├── q1_kalman.py            # Q1 国奖 v2：6D CA + KF/RTS + EM + LRT
    │   ├── q2_solve.py             # Q2：三参数联合估计 + 静态 BLUE + Bootstrap
    │   ├── q2_kalman.py            # Q2：Kalman/RTS 融合 + NIS 一致性
    │   └── q2_validation.py        # Q2：创新 ACF / N_eff / RTS 减幅实测
    ├── data/                       # 附件副本（与官方 md5 一致）
    ├── docs/                       # 题目原件 + 整理 markdown（含公式还原）
    ├── figures/                    # 论文用图
    ├── output/                     # 结果 + summary.json
    └── paper/                      # 论文章节
        ├── CONVENTIONS.md          # 跨章节符号 / 章节模板 / docx patch 清单
        ├── Q1.md                   # 省奖基线
        ├── Q1_Gv2.docx             # 国奖 v2 deliverable（待 patch 重生）
        └── Q2.md                   # 含完整诚实性诊断
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
.venv/bin/python xk/code/q1_solve.py    # Q1 省奖
.venv/bin/python xk/code/q1_kalman.py   # Q1 国奖 v2 (KF/RTS+EM+LRT)
.venv/bin/python xk/code/q2_solve.py    # Q2 联合估计 + 静态融合 + Bootstrap
.venv/bin/python xk/code/q2_kalman.py   # Q2 KF/RTS 融合
```

## 当前进度

- [x] 环境搭建 + 中文字体配置
- [x] 题目整理（含公式 LaTeX 还原）
- [x] 数据画像
- [x] **跨章节符号统一**（`xk/paper/CONVENTIONS.md`：$\Delta t$ 全局约定、状态向量排列、过程噪声参数化、9 节模板、文风条款、docx patch 清单）
- [x] **Q1 — 时间对齐（双版本）**
  - 省奖 baseline：单参数 Brent + 线性插值 → $\hat{\Delta t} = -198.4317009$ s，$J^* \approx 1.7 \times 10^{-11}\,\mathrm m^2$
  - 国奖 v2：6D CA 状态空间 + KF + RTS + EM + LRT(α) → $\hat{\Delta t} = -198.4317040$ s，漂移率不显著（p = 0.985），10 Hz 输出含位置/速度/加速度三元运动学量与协方差
- [x] **Q2 — 含噪 + 系统偏差融合**
  - 三参数联合估计 (Δt, Δx, Δy)：$\hat{\Delta t} = -364.81$ s，$(\hat{\Delta x},\hat{\Delta y}) = (-3.59, +1.80)$ m
  - 静态 BLUE + Kalman/RTS 双轨融合：方差 $0.50 \to 0.25 \to 0.025$ m²（KF 后再降一个数量级）
  - 多重诊断：KS / AD / SW / Ljung-Box / NIS / 创新 ACF
  - 不确定度互核：Cramér-Rao + 参数化 Bootstrap (B=200, basin-conditional)
  - 已知缺陷诚实记录：$\overline{\mathrm{NIS}} = 2.70$ 越界 $\sim 27\sigma$（CV 在转弯段欠表达）
- [ ] Q3 — 实测数据系统偏差检验
- [ ] Q4 — 任务调度优化

## Q1 关键结果

| 项 | 省奖 baseline | 国奖 v2 (KF/RTS+EM) |
|---|---|---|
| 时间偏差 $\hat{\Delta t}$ | $-198.4317009$ s | $-198.4317040$ s |
| 不确定度 $\sigma_{\Delta t}$ | $6.7 \times 10^{-5}$ s | （CRB 与 σ 同量级） |
| 漂移率 α 显著性 | — | LRT $p = 0.985$（不显著） |
| 联合估计 $(\hat{\Delta x}, \hat{\Delta y})$ | $(2.2\times10^{-7}, 8.9\times10^{-9})$ m | — |
| 10 Hz 输出 | 7004 点（位置） | 7004 点（位置 + 速度 + 加速度 + 协方差） |

## Q2 关键结果

| 项 | 值 |
|---|---|
| 时间偏差 $\hat{\Delta t}$ | $-364.8094 \pm 0.40$ s（Bootstrap 95% CI 主 basin 内） |
| 系统偏差 $(\hat{\Delta x}, \hat{\Delta y})$ | $(-3.587, +1.796)$ m |
| 单路噪声 $\hat\sigma$ | $\hat\sigma_x = 0.730$ m，$\hat\sigma_y = 0.697$ m |
| 静态 BLUE 融合方差 | $\overline P_{xx} \approx 0.25\,\mathrm m^2$ |
| KF/RTS 融合方差 | $\overline P_{xx} \approx 0.025\,\mathrm m^2$（降噪 68%） |
| 一致性 $\overline{\mathrm{NIS}}$ | $2.70$（期望 2，越界已诚实记录） |
