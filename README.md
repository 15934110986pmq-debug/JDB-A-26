# 2026 数学建模竞赛 — A 题工作仓库（双队并行）

> 多源融合机器人定位 + 任务调度优化（4 小问 + result.xlsx）
>
> **状态：xk / xr 两支独立队伍均已完成 Q1–Q4 + 论文** （2026-05-10）

## 两支独立参赛队伍

本仓库下 **xk** 与 **xr** 是**两支独立的参赛队伍**，分别完成同一道 A 题但建模思路、代码、数据、论文文字**完全独立**，互不引用、互不借用。

| 队伍 | 工作区 | 论文交付包 | 风格定位 |
|---|---|---|---|
| **xk** | `xk/` | `submission/` | KF/RTS + 静态 BLUE + 多盆地诊断 + 分层目标 ILP；激进任务数（34 任务，29 射 + 5 拍） |
| **xr** | `xr_submission/{paper,code,figures,output}/` | `xr_submission/paper/` | 剖面 LS + SG 平滑 + 静态 BLUE + 三重证据稳健诊断 + 候选执行窗 + 0-1 ILP；稳健调度（35 任务，15 射 + 20 拍） |

**严格隔离规则**：xk 论文/代码只引 `xk/`；xr 论文/代码只引 `xr_submission/`；两边不得有内容交叉引用、相同段落、相同图命名规则、相同方法论术语借用，详见 `MEMORY.md` 与 `feedback_xk_xr_isolation.md`。

格式规范见根目录 `全国大学生数学建模竞赛论文格式规范（2026年修订稿）.pdf`，电子版六条硬性条件：≤20 MB、首页摘要、不要目录、附录强制源码、不出现身份信息、单文件不压缩。

## 目录结构

```
.
├── README.md                       # 本文件
├── CLAUDE.md                       # AI 协作上下文（项目类型/约定/决策沉淀）
├── 全国大学生数学建模竞赛论文格式规范（2026年修订稿）.pdf  # 国赛电子版规范（双队共用）
├── 26金地杯赛题/2026金地杯/2026_A题/   # 官方题目与附件（原件，未改动）
│   ├── 2026_A题.docx
│   ├── 附件1.xlsx ~ 附件4.xlsx
│   └── result.xlsx                 # 提交模板
│
├── xk/                             # 【xk 队】解题主目录
│   ├── README.md                   # 解题路线 + 约束速查
│   ├── code/                       # 求解脚本
│   │   ├── explore.py              # 数据画像
│   │   ├── q_utils.py              # 共享 LS 代价 / 插值 / fuse_10hz
│   │   ├── q1_solve.py             # Q1 省奖：单参数 Brent + 线性插值
│   │   ├── q1_kalman.py            # Q1 国奖 v2：6D CA + KF/RTS + EM + LRT
│   │   ├── q2_solve.py             # Q2：三参数联合估计 + 静态 BLUE + Bootstrap
│   │   ├── q2_kalman.py            # Q2：Kalman/RTS 融合 + NIS 一致性
│   │   ├── q2_validation.py        # Q2：创新 ACF / N_eff / RTS 减幅实测
│   │   ├── q2_basin_compare.py     # Q2：多盆地实证对比（红队回应）
│   │   ├── q2_dxdy_contour.py     # Q2：(Δx, Δy) 凸性诊断
│   │   ├── q3_solve.py             # Q3：不等方差 BLUE + F 检验 + KF/RTS
│   │   └── q4_solve.py             # Q4：滑动窗 + 分层目标 ILP + chance constraint
│   ├── data/                       # 附件副本（与官方 md5 一致）
│   ├── docs/                       # 题目原件 + 整理 markdown
│   ├── figures/                    # 论文用图（首字母大写命名）
│   ├── output/                     # 结果 + Q{1-4}_summary.json
│   └── paper/                      # 论文章节（CONVENTIONS / 三审清单 / v1 整合稿）
│
└── xr_submission/                  # 【xr 队】解题主目录（独立交付）
    ├── code/                       # 求解脚本（首字母小写命名）
    │   ├── program1.py             # Q1：CubicSpline/PCHIP 插值 + 1D 时间偏差最小二乘
    │   ├── program2.py             # Q2：剖面 LS + SG 平滑分离 + 静态 BLUE 协方差融合
    │   ├── program3.py             # Q3：Block Bootstrap + Newey-West HAC + N_eff BIC 三重证据
    │   ├── program4.py             # Q4：300 Hz 加密 + 候选执行窗 + 冲突图 + 两阶段 0-1 ILP
    │   └── build_docx.py           # md→docx 转换器（自写，按国赛 2026 规范）
    ├── figures/                    # 18 张诊断图
    ├── output/                     # q{1,2,3,3_final,4_second}_outputs/ 全部 csv + xlsx + png
    └── paper/
        ├── A题_XR第二版.md          # 论文 markdown 主稿
        └── A题_XR第二版.docx        # 国赛规范电子版（≤20 MB / 首页摘要 / 不要目录 / 附录全源码）
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

**xk 队脚本**：

```bash
.venv/bin/python xk/code/explore.py     # 数据画像
.venv/bin/python xk/code/q1_solve.py    # Q1 省奖
.venv/bin/python xk/code/q1_kalman.py   # Q1 国奖 v2 (KF/RTS+EM+LRT)
.venv/bin/python xk/code/q2_solve.py    # Q2 联合估计 + 静态融合 + Bootstrap
.venv/bin/python xk/code/q2_kalman.py   # Q2 KF/RTS 融合
.venv/bin/python xk/code/q3_solve.py    # Q3 不等方差 BLUE + F 检验
.venv/bin/python xk/code/q4_solve.py    # Q4 分层目标 ILP 调度
```

**xr 队脚本**（在 `xr_submission/code/` 下执行；需附件 1-4 同目录）：

```bash
cd xr_submission/code
python program1.py                       # Q1：时间偏差估计
python program2.py                       # Q2：剖面 LS + BLUE 融合
python program3.py                       # Q3：三重证据稳健诊断
python program4.py                       # Q4：300 Hz 加密 + 候选窗 + ILP 调度
python build_docx.py                     # md → docx（国赛规范输出）
```

## 当前进度

- [x] 环境搭建 + 中文字体配置
- [x] 题目整理（含公式 LaTeX 还原）
- [x] 数据画像
- [x] **跨章节符号统一**（`xk/paper/CONVENTIONS.md`：$\Delta t$ 全局约定、状态向量排列、过程噪声参数化、9 节模板、文风条款、docx patch 清单）
- [x] **Q1 — 时间对齐（双版本）**：省奖 Brent + 国奖 v2 KF/RTS+EM+LRT
- [x] **Q2 — 含噪 + 系统偏差融合**：联合估计 + 静态 BLUE + KF/RTS + 多盆地诊断 + Bootstrap
- [x] **Q3 — 实测数据系统偏差检验**：不等方差 BLUE + F 检验 + AIC/BIC + KF/RTS
- [x] **Q4 — 任务调度优化**：分层目标 ILP + chance constraint + 双解对照
- [x] **多 AI 红队三审验证**：Q2/Q3/Q4 经 ChatGPT + Gemini + DeepSeek + Claude + 豆包审查
- [x] **论文初版**：`xk/paper/A题论文_v1初版.md` 按 8 章框架整合

## Q1 关键结果

| 项 | 省奖 baseline | 国奖 v2 (KF/RTS+EM) |
|---|---|---|
| 时间偏差 $\hat{\Delta t}$ | $-198.4317009$ s | $-198.4317040$ s |
| 不确定度 $\sigma_{\Delta t}$ | $6.7 \times 10^{-5}$ s | （CRB 与 σ 同量级） |
| 漂移率 α 显著性 | — | LRT $p = 0.985$（不显著） |
| 联合估计 $(\hat{\Delta x}, \hat{\Delta y})$ | $(2.2\times10^{-7}, 8.9\times10^{-9})$ m | — |
| 10 Hz 输出 | 7004 点（位置） | 7004 点（位置 + 速度 + 加速度 + 协方差） |

## Q2 关键结果

> **2026-05-09 主解切换**：经 5 个独立 AI 红队验证，主解从 $\Delta t = -364.81$ s 切换至 $\Delta t = -50.29$ s（$J^*$ 最小 + 公共重叠最长 + 不出现负时间）。原 $-364.81$ 仍为合法周期 alias 备选，列入附录。详见 `xk/paper/Q2_三审综合.md`。

| 项 | 值（C1 主解） |
|---|---|
| 时间偏差 $\hat{\Delta t}$ | $-50.2949 \pm 0.29$ s（Bootstrap 95% CI $[-51.10, -49.92]$） |
| 系统偏差 $(\hat{\Delta x}, \hat{\Delta y})$ | $(-3.474, +1.831)$ m |
| 单路噪声 $\hat\sigma$ | $\hat\sigma_x = 0.662$ m，$\hat\sigma_y = 0.690$ m |
| 联合代价 $J^*$ | $1.827\,\mathrm m^2$（$2(\hat\sigma_x^2+\hat\sigma_y^2) = 1.828$，吻合 99.95%） |
| KF/RTS 融合方差 | $\overline P_{xx} \approx 0.019\,\mathrm m^2$（降噪 **71%**） |
| 一致性 $\overline{\mathrm{NIS}}$ | $2.89$（期望 2，越界已诚实记录） |
| 物理时间范围 | $[102.0, 951.4]$ s（**全为正**） |
| Alternative basin (附录) | $\Delta t = -364.81$ s（与 C1 同物理偏差错 1 个周期 314 s 的 alias） |

## Q3 关键结果

> **题面第一问结论：统计上不显著**（不写"不存在"，是诚实声明）。F 检验 + Bootstrap CI + AIC/BIC 三重证据下不拒绝 $H_0: (\Delta x, \Delta y) = 0$；同时保留 LS 点估计为输出。

| 项 | 值 |
|---|---|
| 时间偏差 $\hat{\Delta t}$ | $+367.93$ s |
| 系统偏差点估计 $(\hat{\Delta x}, \hat{\Delta y})$ | $(+0.14, +0.18)$ m |
| F 检验 p 值 | $0.133$（**不拒绝 $H_0$**） |
| 单路噪声 | $\hat\sigma_1 = 4.03$ m, $\hat\sigma_2 = 2.78$ m（不等方差） |
| BLUE 权重 | $w = (0.32, 0.68)$（按 $1/\sigma_k^2$ 加权） |
| KF $\overline{\mathrm{NIS}}$ | $2.20$（期望 2） |
| 10 Hz 轨迹输出 | `xk/output/Q3_trajectory_10Hz_kalman.xlsx`（含位置 / 速度 / 后验方差） |

## Q4 关键结果

> **拍照硬上限 = 5 / 18**（独立 ILP 验证）：题面 "$v \le 1.5$ + 视角差 60° + 持续 0.5 s" 与机器人轨迹（[445, 510] s 低速段）乘积所决定的物理上限。论文 §6.6.1 当成"诚实声明"而非缺陷。
>
> **2026-05-09 后期修正**：发现等权 $\max \sum x_i$ 给出失衡解（31 射击 + 4 拍照）；引入分层目标 ILP（覆盖优先权重 $M_p = 1000 \gg M_s = 100 \gg 1$）后仅减 1 任务即换得拍照覆盖 4 → 5（达物理上限）。详见 `xk/paper/Q4.md` §6.6.2。

| 项 | 标称解（**主交付**）| 鲁棒解（对照）|
|---|---|---|
| 入选任务总数 | **34** | 31 |
| 射击次数 / 覆盖目标 | 29 次 / 15 个 | 27 次 / 14 个 |
| 拍照次数 / 覆盖目标 | 5 次 / **5 个（达物理上限）** | 4 次 / 4 个 |
| 期望命中数 | $29 \times 0.85 = \mathbf{24.65}$ | $27 \times 0.85 = 22.95$ |
| 时间跨度 | $[445.00, 808.80]$ s | $[445.00, ...]$ s |
| 时段过渡 $\epsilon$ | $0$ | $0.1$ s |
| 鲁棒约束 | — | chance constraint $z = 1.645$（90% 单侧）|
| ILP 规模 | 323 候选 + 36 覆盖变量 + ~5000 时段冲突约束（亚秒级收敛）|

## xr 队四问关键结果（独立交付）

xr 队走"统计严谨 + 工程可执行"路线，与 xk 的"激进任务数"路线形成对比。

| 问 | 关键数值 | 备注 |
|---|---|---|
| Q1 | $\widehat{\tau}=198.4317$ s，RMSE $=3.62\times10^{-8}$ m，速度 RMSE $=6.05\times10^{-9}$ m/s | 三类一致性同时满足 |
| Q2 | $\widehat{\tau}=50.4429$ s，$\widehat{\mathbf{b}}=(3.475,\,-1.834)$ m，融合 95% 椭圆 12.5→**6.23** m² | SG 平滑分离 + 剖面 LS + 静态 BLUE |
| Q3 | $\widehat{\tau}=-368.17$ s，候选 $\|\widehat{\mathbf{b}}\|=0.244$ m；Bootstrap CI 含 0、HAC 长滞后不显著、$\Delta\mathrm{BIC}_\mathrm{eff}=+6.56$ | **三重证据均不支持固定偏差** |
| Q4 | **35 任务**（15 射 + 20 拍）；拍照 **18/18 全覆盖**；射击 15/18（与 $S_{13}/S_{17}/S_{18}$ 物理不可达上限一致）；期望命中 12.75 | 300 Hz 加密 + 角度分桶 + 冲突图 + 两阶段 ILP |

> xr 第四问拿到 18/18 拍照覆盖与 xk 红队"5/18 物理上限"结论存在差异，是两支独立队伍对同一题做出的不同建模选择，按"双队各自交付"处理；详 `xr_submission/paper/A题_XR第二版.md` §5.4.8 物理可达性诊断。

## 多 AI 红队验证范式

每个 Qx 完成后：
1. 写 `Qx_审查清单.md`（含 §0 项目背景 + 5 个 yes/no + 4 类问题 + 期望返回格式）
2. 用户贴给 ChatGPT / Gemini / DeepSeek / 独立 Claude / 豆包
3. 把回复贴回，写 `Qx_三审综合.md`（投票表 + 共识 + 分歧 + P0/P1/P2 处置清单）
4. 按 P0 修正代码 + 论文，P1 增强论文厚度，P2 选做

**红队发现**：
- Q2：原 NM 早停（C4 $J^*=3.139$ vs 真值 1.827）→ **主解切换**
- Q3：一致建议"不显著"非"不存在" + 保留点估计
- Q4：建议 chance constraint 鲁棒化（鲁棒解结构对照）+ 分层目标 ILP（覆盖均衡）
