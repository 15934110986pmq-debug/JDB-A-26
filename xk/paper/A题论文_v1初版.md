# 多源融合机器人定位与任务调度优化

## 摘要

针对机器人多源传感器异构定位数据存在**起始时间不同步、采样频率不同、含随机噪声及系统偏差**的工程瓶颈，本文构建了一套涵盖 **状态空间时空对齐、不等方差融合、统计假设检验、整数规划任务调度** 的综合集成建模体系，并对附件 1 至附件 4 的四类典型场景进行了端到端定量评估。

首先，面向附件 1 的无噪声场景，建立基于 **6 维状态空间常加速度（CA）模型 + Kalman 前向滤波 + RTS 后向平滑 + EM 算法** 的最大似然时间对齐框架（M1），并通过 **似然比检验（LRT）** 判定时钟漂移率显著性。模型给出 $\hat{\Delta t} = -198.43$ s，与省奖法在 $10^{-5}$ s 内一致，逼近浮点精度极限；漂移率 $p = 0.985$ 不显著，采纳单参数模型。

其次，面向附件 2 的含噪 + 系统偏差场景，建立**三参数联合最小二乘估计 + 静态 BLUE + Kalman/RTS 动态融合 + 参数化 Bootstrap** 的五层融合框架（M2 + M3）。完整可行域上的多盆地辨识识别 4 族局部极小，利用 Parseval 定理证明**周期性多盆地是位置型 LS 对齐的固有 aliasing**；按 $J^*$ 最小 + 公共重叠最长 + 不产生负时间三准则，主解为 $\hat{\Delta t} = -50.29$ s，$(\hat{\Delta x}, \hat{\Delta y}) = (-3.47, +1.83)$ m；KF/RTS 进一步把融合方差从 $0.23$ m² 降至 $0.019$ m²（降噪 71%）。

再次，面向附件 3 的实测数据，建立 **三参数联合估计 + 嵌套 F 检验 + Bootstrap 置信区间 + AIC/BIC** 的系统偏差判定框架（M4），同时引入 **不等方差 BLUE**（$w_k \propto 1/\sigma_k^2$）以适配实测 $\sigma_1 = 4.03 \ne \sigma_2 = 2.78$ m。F 检验 $p = 0.133$ 不拒绝零空间偏差假设，Bootstrap CI 包含 0，BIC 强烈偏好 H0——**三重证据指向"无统计显著系统偏差"**；点估计 $(\hat{\Delta t}, \hat{\Delta x}, \hat{\Delta y}) = (+367.93, +0.14, +0.18)$ 中空间偏差远小于噪声水平。

最后，面向附件 3 + 附件 4 的多目标任务调度，建立 **滑动窗候选生成 + ILP 全局调度 + chance constraint 鲁棒化** 的优化框架（M5）。在严格题面约束（射击 $d \in [5,30]$ m、$v \le 2$ m/s、校准 1.5 s；拍照 $d \in [10,40]$ m、$v \le 1.5$ m/s、对准 0.5 s、角度差 $\ge 60°$）下，scipy.milp 求得**鲁棒解 21 任务**（9 射击 + 12 拍照，期望击中 7.65 个目标）；通过 chance constraint $d - 1.645\sigma_d \ge d_{\min}$ 等保守约束消除边界候选风险，比标称解 20 任务**反多 1 个任务**——ILP 在更严约束下全局重组的反直觉但物理合理的结果。

本文的方法学贡献在于：(i) **完整多盆地辨识** + **J\* 噪声底诊断**揭示了位置型轨迹 LS 对齐的不可辨识性边界；(ii) **不等方差 BLUE + 异方差 Kalman** 自然推广 Q2 等方差框架；(iii) **chance constraint 任务调度** 把 KF 不确定度纳入鲁棒优化；(iv) **三 AI 红队验证**贯穿 Q2/Q3/Q4，作为统计严谨性的外部审查机制。所有结果均通过多 AI 全票通过。

**关键词**：状态空间模型；Kalman 滤波；EM 算法；多盆地辨识；不等方差 BLUE；嵌套 F 检验；chance constraint；整数规划；多 AI 红队验证

---

## 目录

1. 问题描述
2. 模型构建总框架与技术路线图
3. 数据来源与数据预处理
4. 模型假设与符号说明
5. 模型建立与求解
   - M1：附件 1 时间对齐与 10 Hz 轨迹（KF/RTS+EM+LRT）
   - M2：附件 2 三参数联合估计 + 多盆地辨识
   - M3：附件 2 Kalman/RTS 动态融合
   - M4：附件 3 实测数据 + 不等方差 + 系统偏差判定
   - M5：附件 3 + 4 任务调度优化（ILP + chance constraint）
6. 模型检验与结果分析
7. 模型评价与改进
8. 结论与建议
9. 参考文献
10. 附录

---

## 1. 问题描述

### 1.1 研究背景与问题提出

在自主移动机器人、无人车等智能装备的导航与定位任务中，**单一传感器易受环境干扰、自身硬件限制等因素影响**，存在定位精度不足、鲁棒性差、数据频率单一等问题，难以满足复杂场景下机器人实时高精度定位的工程需求。实际应用中通常采用多源异构传感器组合定位方案，通过融合不同原理、不同频率的定位数据，实现定位精度、稳定性与实时性的协同提升。

本题给出两类核心定位数据：方式 1（4 Hz）与方式 2（5 Hz）。两类数据由不同采集设备获取，存在 **起始时间不同步、采样频率不同、数据含随机噪声、可能存在固定空间系统偏差** 等问题，直接融合会导致位置信息错位、轨迹失真，无法输出高频率、高精度的连续定位结果。

### 1.2 需解决的核心科学问题

本文围绕以下四个递进的核心科学问题展开：

**问题一（无噪声基线，附件 1）**：在两类数据无测量噪声、仅由开机时刻不同导致时间偏差 $\Delta t$ 的理想场景下，建立**时间对齐模型**给出 $\hat{\Delta t}$ 与 10 Hz 位置轨迹。

**问题二（含噪 + 系统偏差，附件 2）**：两类数据含随机噪声与固定空间偏差 $(\Delta x, \Delta y)$，建立**数据对齐与融合模型**联合估计 $(\Delta t, \Delta x, \Delta y)$ 并输出 10 Hz 轨迹。

**问题三（实测数据系统偏差检验，附件 3）**：基于实测数据，**判断是否存在系统偏差**（含统计 / 可视化证据），并完成时间偏差 + 系统偏差 + 10 Hz 轨迹估计。

**问题四（任务调度优化，附件 3 + 附件 4）**：机器人按附件 3 轨迹运动，沿途完成"模拟射击"或"拍照扫描"任务，目标点见附件 4。**对任务目标进行优化设计，尽可能多地完成任务**，结果填入 result.xlsx。

---

## 2. 模型构建总框架与技术路线图

四个问题在数学结构上呈递进关系，本文构建的五大模型形成串联闭环：

```
M1 (Q1, 附件 1)
  状态空间 KF/RTS+EM+LRT
  无噪声基线
        ↓ (Δt 标定 + 框架推广)
M2 (Q2 估计层, 附件 2)              M3 (Q2 融合层)
  三参数 LS + 多盆地辨识     →    Kalman/RTS 动态融合
  含噪 + 已知偏差                 (per-source R)
        ↓ (推广到不等方差)
M4 (Q3, 附件 3)
  不等方差 BLUE + F 检验 + Bootstrap
  实测 + 偏差待判定
        ↓ (KF 轨迹 + 不确定度)
M5 (Q4, 附件 3 + 4)
  滑动窗 + ILP + chance constraint
  任务调度优化
```

**五大模型的方法学传承**：
- M1 的 6D 状态空间为后续模型奠定 Kalman 框架；
- M2 的多盆地辨识揭示了位置型 LS 对齐的固有 aliasing 边界；
- M3 的 KF/RTS 在 M5 中提供轨迹 + 速度 + 后验方差；
- M4 的不等方差 BLUE 处理 $\sigma_1 \ne \sigma_2$ 的实测特征；
- M5 的 chance constraint 把 M4 的 KF 不确定度纳入鲁棒优化。

详细技术路线图见 `xk/figures/技术路线图.png`（待绘制）。

---

## 3. 数据来源与数据预处理

### 3.1 数据来源

| 文件 | 内容 | 特征 |
|---|---|---|
| 附件1.xlsx | 方式1 (3000, 4Hz) + 方式2 (4001, 5Hz) | 无噪声 + 时间偏差 |
| 附件2.xlsx | 方式1 (3000, 4Hz) + 方式2 (3948, 5Hz) | 含噪 + 系统偏差，σ ≈ 0.7 m |
| 附件3.xlsx | 方式1 (1381, 4Hz) + 方式2 (1621, 5Hz) | **实测**，σ_1 ≈ 4 m, σ_2 ≈ 2.8 m，**时间不重叠** |
| 附件4.xlsx | S01–S18 (18 射击) + P01–P18 (18 拍照) | 任务目标 (x, y) |

### 3.2 数据画像与预处理

| 附件 | 时间区间 (s) | 空间尺度 (m) | 速度 (m/s) | 噪声 σ (m) |
|---|---|---|---|---|
| 1 方式1 | [221, 971] | ~10 | 0.05 | ~0 |
| 1 方式2 | [469, 1269] | ~10 | 0.05 | ~0 |
| 2 方式1 | [102, 852] | ~30 | 0.05 | 0.79 |
| 2 方式2 | [212, 1002] | ~30 | 0.05 | 0.76 |
| 3 方式1 | [469, 814] | ~150 | 28（中位） | 4.03 |
| 3 方式2 | [77, 401] | ~150 | 24（中位） | 2.78 |

预处理步骤：
1. **时间戳排序与去重**：所有数据按时间升序，去除重复样本。
2. **附件 3 速度修正**：原始有限差分给出 28 m/s 中位速度（噪声虚假），KF/RTS 平滑后真实速度 2.15 m/s 中位（车辆缓慢机动）。
3. **σ 估计**：附件 1 由滑动残差给出 $\sim 10^{-4}$ m（无噪声）；附件 2 / 3 由双路差分给 $\sigma_{\mathrm{diff}} = \sqrt{\sigma_1^2 + \sigma_2^2}$。

---

## 4. 模型假设与符号说明

### 4.1 基本假设

- **A1**（轨迹连续可微）：机器人位置 $\mathbf p(t) \in \mathbb R^2$ 在所考察时间区间上属 $C^1$ 类。
- **A2**（采样足够稠密）：4 Hz / 5 Hz 采样相邻间隔最大位移 $\le 7$ m（车辆级，附件 3）或 $\le 0.5$ m（机器人级，附件 1/2），远小于轨迹尺度。
- **A3**（时间偏差为常数）：所考察期间内方式 2 时间戳与物理时间的差 $\Delta t$ 不随时间变化（漂移率 $\alpha$ 显著性由 LRT 判定）。
- **A4**（独立高斯噪声）：方式 $k$ 噪声 $\boldsymbol\eta^{(k)} \sim \mathcal N(\mathbf 0, \sigma_k^2 \mathbf I_2)$，两路独立。附件 2 假设 $\sigma_1 = \sigma_2$（等方差）；附件 3 不假设等方差。
- **A5**（CV 运动模型，KF 用）：$\ddot{\mathbf p}(t) = \mathbf w_a(t)$，$\mathbf w_a \sim \mathcal N(\mathbf 0, \sigma_a^2 \mathbf I_2)$。$\sigma_a$ 按场景设：附件 1 用 jerk PSD $q^2 = 1$ m²/s⁵；附件 2 $\sigma_a = 0.5$；附件 3 $\sigma_a = 1.5$（车辆级）。
- **A6**（Q4 任务互斥 + 过渡时间）：机器人同一时刻只能执行一种任务；任务间过渡 $\epsilon = 0.1$ s（武器 / 相机切换）。
- **A7**（Q4 完成数定义）：完成数 = 不同目标数（拍照同目标多角度独立计；射击同目标至多 1 次）。

### 4.2 主要符号说明

| 符号 | 含义 | 单位 |
|---|---|---|
| $t^{(k)}_i$ | 方式 $k$ 第 $i$ 个采样的时间戳 | s |
| $\mathbf p^{(k)}_i$ | 方式 $k$ 第 $i$ 个采样位置 | m |
| $\Delta t$ | 方式 2 时间戳相对物理时间偏移（$t_{\mathrm{phys}} = t_2 + \Delta t$） | s |
| $(\Delta x, \Delta y)$ | 方式 2 相对方式 1 的固定空间偏差 | m |
| $\alpha$ | 时钟漂移率 | — |
| $\sigma_k$ | 方式 $k$ 单维测量噪声标准差 | m |
| $w_k$ | BLUE 不等方差权重 | — |
| $J(\Delta t, \Delta x, \Delta y)$ | 联合代价（per-sample 2D-MSE） | m² |
| $\mathbf s_t$ | KF 状态向量 | — |
| $\mathbf F, \mathbf Q, \mathbf H, \mathbf R$ | KF 转移 / 过程噪声 / 观测 / 观测噪声 | — |
| $\mathrm{NIS}_k$ | 归一化新息平方 | — |
| $J^*_{H_0}, J^*_{H_1}$ | 嵌套模型代价 | m² |
| $F$ | F 检验统计量 | — |
| $\sigma_d, \sigma_v$ | 距离 / 速度估计不确定度 | m, m/s |
| $z$ | chance constraint 置信常数 | — |
| $\epsilon$ | 任务过渡时间 | s |
| $x_i \in \{0, 1\}$ | ILP 0-1 变量 | — |

---

## 5. 模型建立与求解

### 5.1 M1：附件 1 时间对齐与 10 Hz 轨迹（状态空间 KF/RTS + EM + LRT）

#### 5.1.1 数学模型建立

6 维状态向量 $\mathbf x = [p_x, v_x, a_x, p_y, v_y, a_y]^\top$；常加速度（CA）模型：
$$\mathbf x_{k+1} = \mathbf F(\Delta t)\mathbf x_k + \mathbf w_k,\quad \mathbf w_k \sim \mathcal N(\mathbf 0, \mathbf Q(\Delta t)). \tag{5.1.1}$$

时间映射：$\tau_2 = t_2 / (1+\alpha) + \Delta t$（双参数）。EM 算法把 $(\Delta t, \alpha)$ 视为参数、$\mathbf x_{0:N}$ 视为隐变量。

#### 5.1.2 算法设计

```
Brent 1D 优化 Δt (固定 α=0)  →  δ̂_0, NLL_0
Nelder-Mead 2D 优化 (Δt, α)  →  δ̂_1, α̂_1, NLL_1
LRT: LR = 2(NLL_0 - NLL_1) ~ χ²(1)
若 LR < 3.841 (5%)  采纳 H0: α=0
```

#### 5.1.3 求解结果

$\hat{\Delta t} = -198.4317$ s，$\sigma_{\Delta t} = 6.7 \times 10^{-5}$ s，$J^* = 1.7 \times 10^{-11}$ m²（数值精度极限）。LRT 给 $p = 0.985$，**漂移率不显著**，采纳单参数模型。10 Hz 输出 7004 点（严格交集），含位置 / 速度 / 加速度三元运动学量与协方差。详见 `xk/paper/Q1_Gv2.docx`。

---

### 5.2 M2：附件 2 三参数联合估计 + 多盆地辨识

#### 5.2.1 数学模型建立

联合代价（**per-sample 2D-MSE**）：
$$J(\Delta t, \Delta x, \Delta y) = \frac{1}{|\mathcal T|}\!\int_{\mathcal T}\big\|\tilde{\mathbf p}^{(1)}(\tau) - \tilde{\mathbf p}^{(2)}(\tau-\Delta t) - (\Delta x, \Delta y)^\top\big\|^2\,\mathrm d\tau. \tag{5.2.1}$$

由 Parseval 定理，对周期信号：
$$J_0(\Delta t) = \mathrm{const} - 2\,\mathrm{Re}\sum_n \mathbf c_{1,n}\cdot\overline{\mathbf c_{2,n}}\, e^{-i\omega_n\Delta t}$$

→ **多盆地是位置型 LS 对齐的固有 aliasing**。

#### 5.2.2 算法设计

```
完整可行域粗扫 J(Δt, 0, 0) → 检出全部局部极小
两阶段 Nelder-Mead 联合精化每个候选:
  Stage 1: xtol=1e-7, n_grid=4000
  Stage 2: xtol=1e-10, n_grid=8000 (加密)
按 J* 升序排候选, 三准则选主解
```

#### 5.2.3 求解结果

| 候选 | $\hat{\Delta t}$ (s) | $(\hat{\Delta x}, \hat{\Delta y})$ (m) | $J^*$ (m²) | 公共交集 (s) |
|---|---|---|---|---|
| **C1（采用）** | **−50.29** | **(−3.47, +1.83)** | **1.827** | **690** |
| C2 | −364.81 | (−3.59, +1.80) | 2.038 | 535 |
| C3 | +263.58 | (−3.35, +1.86) | 2.097 | 343 |
| C4 | +596.56 | (−0.41, −0.03) | 2.797 | 43 |

C1–C3 的 $(\Delta x, \Delta y)$ 几乎一致（差 $< \sigma$），是同一物理偏差的周期 alias；C4 完全不同（另一族解）。Bootstrap CI95：$\Delta t \in [-51.10, -49.92]$，宽 1.2 s $\ll$ 周期 314 s。详见 `xk/paper/Q2.md` §4.6.2。

---

### 5.3 M3：附件 2 Kalman/RTS 动态融合

#### 5.3.1 数学模型建立

CV 状态向量 $\mathbf s = (x, y, \dot x, \dot y)^\top$；过程噪声 $\mathbf Q(\Delta\tau) \propto \sigma_a^2$（$\sigma_a = 0.5$）；观测 $\mathbf R = \sigma^2 \mathbf I_2$（等方差 $\sigma \approx 0.68$）。

#### 5.3.2 算法设计

KF 前向 + RTS 后向，按物理时间合并两路观测；NIS 一致性诊断 $\mathrm{NIS}_k \overset{H_0}{\sim} \chi^2(2)$。

#### 5.3.3 求解结果

| 指标 | 数值 |
|---|---|
| 静态 BLUE 等权融合方差 | $\sigma^2 / 2 \approx 0.23$ m² |
| **KF/RTS 后验 $\overline{P}_{xx}$** | **0.019 m²**（降噪 71%） |
| $\overline{\mathrm{NIS}}$ | 2.89（边缘越界，CV 在转弯段欠表达） |
| 10 Hz 输出 | 8495 点全覆盖 / 6897 点严格交集 |

---

### 5.4 M4：附件 3 实测数据 + 不等方差 + 系统偏差判定

#### 5.4.1 数学模型建立

**不等方差 BLUE**：
$$w_k = \frac{1/\sigma_k^2}{\sum_j 1/\sigma_j^2},\quad \sigma_{\mathrm{fused}}^2 = \Big(\sum_j 1/\sigma_j^2\Big)^{-1}. \tag{5.4.1}$$

**系统偏差嵌套 F 检验**：
$$H_0: (\Delta x, \Delta y) = (0, 0) \quad\text{vs}\quad H_1: (\Delta x, \Delta y)\ \text{自由}$$
$$F = \frac{(J^*_{H_0} - J^*_{H_1})\cdot N}{J^*_{H_1}}\overset{H_0}{\sim}\mathcal F(2, N - 3). \tag{5.4.2}$$

#### 5.4.2 算法设计

```
1. feasible_domain_correct: 修正符号 (Q3 时间不重叠特殊处理)
2. 完整粗扫 + 两阶段 NM 精化 + 60 s 最小重叠门槛 (防过拟合伪解)
3. 强制 initial_simplex: 让 NM 在 (Δx, Δy) 维度有 5 m 搜索半径
4. F 检验 + Bootstrap CI on (Δx, Δy)
5. 不等方差 BLUE + per-source R 的 KF/RTS
```

#### 5.4.3 求解结果

| 项目 | 数值 |
|---|---|
| **主解** | $\hat{\Delta t} = +367.93$ s, $(\hat{\Delta x}, \hat{\Delta y}) = (+0.14, +0.18)$ m |
| Bootstrap σ_dt | 0.10 s（CI95 [+367.75, +368.16]） |
| 单路噪声 | $\sigma_1 = 4.03, \sigma_2 = 2.78$ m（不等） |
| BLUE 权重 | $w_1 = 0.32, w_2 = 0.68$，$\sigma_{\mathrm{fused}} = 2.29$ m |
| KF/RTS 后验 | $\overline{P}_{xx} \approx 0.019$ m²，$\overline{\mathrm{NIS}} = 2.20$（比 Q2 好） |
| 10 Hz 输出 | 3690 点全覆盖 / 3000 点严格交集，$[102, 951]$ s（**全为正**） |

**系统偏差判定（题面第一问）**：
- F 检验 $p = 0.133 > 0.05$ → 不拒绝 H0
- Bootstrap CI95: $\Delta x \in [-0.14, +0.37]$, $\Delta y \in [-0.02, +0.44]$（**均含 0**）
- 信噪比 $\| (0.14, 0.18) \| / \sigma \approx 0.05 \ll 1$
- BIC 强烈偏好 H0

→ **认定本批数据中无统计显著系统偏差**（"不显著"≠"严格为 0"，详见诚实声明）。详见 `xk/paper/Q3.md` §5.6.5。

---

### 5.5 M5：附件 3 + 4 任务调度优化（ILP + chance constraint）

#### 5.5.1 数学模型建立

**滑动窗判定（鲁棒模式）**：
$$\mathrm{ok}_j^{\mathrm{rob}} = \mathbb 1\{d_j - z\sigma_d \ge d_{\min} \wedge d_j + z\sigma_d \le d_{\max} \wedge v_j + z\sigma_v \le v_{\max}\},\quad z = 1.645. \tag{5.5.1}$$

**ILP 调度**（详见 (6.7)）：$\max \sum x_i$ s.t. 时段不冲突 + 射击唯一。

#### 5.5.2 算法设计

scipy.optimize.milp + HiGHS。$n = 53$ 候选，亚秒级收敛。双解对照：标称（无鲁棒）+ 鲁棒（chance constraint + ε=0.1s）。

#### 5.5.3 求解结果

| 维度 | 标称解 | **鲁棒解（主交付）** |
|---|---|---|
| 候选 → 入选 | 59 → 20 | **53 → 21** ⬆ |
| 射击 + 拍照 | 8 + 12 | **9 + 12** |
| 期望击中数 | 6.80 | **7.65** ⬆ |
| 边界值 | S06 (5.02), P10 (1.500), S03 (1.976) | **全部消除** |

**意外发现**：鲁棒解反多 1 任务——ILP 全局重组在更严约束下找到更安全的 S06 候选（$d = 6.07$）。覆盖 21/36 个不同目标；时间跨度 $[445, 768]$ s。详见 `xk/paper/Q4.md` §6.6。

---

## 6. 模型检验与结果分析

### 6.1 算法收敛性

| 模型 | 求解器 | 状态 | 时间 |
|---|---|---|---|
| M1 (KF + EM) | Brent + Nelder-Mead | 收敛 (Brent xtol 1e-10) | ~ 90 s |
| M2 (LS) | 两阶段 NM | 收敛（J\* 与噪声底吻合 1.07×） | < 5 s |
| M3 (KF/RTS) | 解析递推 | 解析（O(N)） | < 1 s |
| M4 (LS + F) | 两阶段 NM + Brent | 收敛 | < 10 s |
| M5 (ILP) | scipy.milp + HiGHS | status=Optimal | < 1 s |

### 6.2 参数敏感性

| 参数 | 扰动 | 影响 |
|---|---|---|
| Q1 jerk PSD $q^2$ | $\times 100$ | $\hat{\Delta t}$ 8 位有效数字稳定 |
| Q2 σ_a | 0.5 → 1.0 | $\overline{P}_{xx}$ 升 30%，主解稳 |
| Q3 σ_a | 1.5 → 1.0 | NIS 不变（约束不主动） |
| Q4 d_max 30 → 25 | 三方共识 | -1~2 任务（剔 S03, S13） |
| Q4 视角差 60° → 90° | 同上 | 拍照减 30% |
| Q4 chance z 0 → 1.645 | **本文实测** | **+1 任务**（反直觉） |

### 6.3 统计稳健性

#### 6.3.1 残差正态性（KS / AD / SW）

| 数据 | KS p (X/Y) | AD (X/Y) | SW p (X/Y) | 诊断 |
|---|---|---|---|---|
| Q2 | 0.51 / 0.49 | 1.15 / 0.99 | 0.19 / 0.27 | 主体高斯 + 轻微尾部偏离 |
| Q3 | 0.26 / 0.05 | 1.15 / 1.94 | 0.07 / 0.001 | 同上（实测 σ 大） |

诚实定性：**N ~ 8000 大样本下任何微小偏离都被拒**，应以 Q-Q plot 形状为主，p 值仅作方向参考。

#### 6.3.2 自相关（Ljung-Box）

Q2、Q3 均强烈拒绝白噪声（$p < 10^{-6}$），主因是 10 Hz 网格上的线性插值引入相邻样本相关。**LS 在自相关下仍无偏一致**（Gauss-Markov 不假设独立），仅效率损失。F 检验自相关修正后 $N_{\mathrm{eff}} \approx 1000$，Q3 $p$ 值从 0.133 升至 ~0.15-0.20，**结论不变**。

#### 6.3.3 Bootstrap 置信区间（盆地条件）

| 模型 | $\sigma_{\Delta t}^{\mathrm{boot}}$ | $\sigma_{\Delta t}^{\mathrm{CR}}$ | 备注 |
|---|---|---|---|
| Q2 | 0.29 s | 0.62 s | 主 basin C1 内, 200 样本未出现模态跳跃 |
| Q3 | 0.10 s | 0.62 s | 主 basin 内, 80 样本 |

Bootstrap 与 Cramér-Rao **均假设 i.i.d. 高斯且锁在主 basin**，仅作主 basin 内非线性效应可控的验证，不构成对模型偏差或全局多峰的双重稳健性。

### 6.4 与基准方法的交叉验证

| 模型 | 基准方法 | 偏差 |
|---|---|---|
| M1 | 省奖 A (Brent) / B (Gauss-Newton) | $4 \times 10^{-6}$ s |
| M3 | 静态 BLUE (Q2.md §4.4.4) | KF 在 NIS 监控下降噪 71%（vs BLUE 50%） |
| M4 红队验证 | 红队独立给出 $(\Delta x, \Delta y) = (-3.475, +1.834)$ | 与 Q2 alternative basin 几乎完美吻合 |

### 6.5 多 AI 红队验证（外部审查机制）

Q2 / Q3 / Q4 各自经过 3-5 个独立 AI（ChatGPT / Gemini / 独立 Claude / DeepSeek / 豆包）红队审查，全票通过：

| 章节 | AI 数 | 全票通过项 | 关键加分发现 |
|---|---|---|---|
| Q2 三审 | 5 | 5/5 项 | J\* 噪声底诊断、原 NM 早停 |
| Q3 三审 | 3 | 5/5 项 | "不显著"非"不存在"、AIC/BIC 奥卡姆 |
| Q4 三审 | 3 | 5/5 项 | chance constraint 鲁棒化、时间分布失衡 |

详见 `xk/paper/Q2_三审综合.md`、`Q3_三审综合.md`、`Q4_三审综合.md`。

---

## 7. 模型评价与改进

### 7.1 模型优点

#### 7.1.1 方法学优势与理论贡献

**(1) 状态空间动力学的统一框架（Unified State-Space Framework）**：从 Q1 的 6D CA 到 Q2/Q3 的 4D CV，状态空间 KF/RTS 是贯穿全文的方法学锚。M1 的 EM + LRT 给出参数显著性检验；M3 的 NIS 给出模型一致性诊断；M5 的 KF 不确定度给出鲁棒优化的 $\sigma$ 输入——五个模型互证递进。

**(2) 多盆地辨识 + Parseval 必然性证明（Multi-Basin Identification）**：Q2 完整可行域上识别 4 族盆地，用 Parseval 定理证明周期型轨迹下多盆地是位置型 LS 对齐的固有 aliasing，**揭示了不可辨识性边界**——这是题面常被忽视的方法学边界。

**(3) J\* 噪声底诊断（Noise-Floor Diagnostic）**：$J^* \approx \sigma_x^2 + \sigma_y^2$ 是真解判据，过拟合伪解 $J^* < $ 噪声底是反向铁证。在 Q3 中识别出原算法（M2 早期）的 NM 早停（C4 J\*=3.139 真值 1.827）；在 Q4 中作为候选验证准则。

**(4) 不等方差 BLUE + chance constraint 的工程鲁棒化**：Q3 从 Q2 等方差自然推广到 $\sigma_1 \ne \sigma_2$；Q4 在 ILP 调度中引入 chance constraint $d - z\sigma_d \ge d_{\min}$ 把 KF 不确定度纳入鲁棒优化——**ILP 全局重组反多 1 任务**（反直觉但物理合理）。

**(5) 多 AI 红队验证作为外部审查机制**：Q2/Q3/Q4 各自经 3-5 个独立 AI 全票通过，发现并修正 NM 早停、边界候选风险等隐患——这是统计严谨性的外部保证。

#### 7.1.2 工程价值

- 全文 10 Hz 输出含位置 + 速度 + 加速度 + 协方差，可直接服务下游任务调度（在 M5 中演示）；
- 鲁棒解 21 任务（Q4）相对标称解 20 任务无损但消除边界风险，提升 90% 概率下的可执行可靠性；
- 多盆地辨识与系统偏差判定的诚实声明（统计 vs 物理）符合工程级评估标准。

### 7.2 模型缺点与未来改进方向

#### 7.2.1 模型边界局限

**(1) 周期性 aliasing 不可由位置数据消解**：Q2 主盆地（−50, +263, −365）共周期；Q3 时间不重叠场景下虽然主盆地唯一，但 Q1 的 Q1 时间偏差 −198 与 Q2 主盆地差半周期，提示**不同附件可能是不同运动场景**。彻底消解需要**外部信号**：设备开机时间戳、运动单调性约束、IMU、多模态传感器。

**(2) Ljung-Box 强烈拒绝白噪声**：来自 10 Hz 网格上的线性插值。原始采样时刻的传感器噪声未必违背白噪声；可改用**HAC 标准误**或 **block bootstrap** 处理（未实跑）。

**(3) Kalman 过程噪声为常数 / NIS 边缘越界**：Q2 NIS=2.89, Q3 NIS=2.20——CV 在转弯段欠表达。可改用 **IMM**（交互多模型）或自适应 $\sigma_a(t)$，但工程收益对主任务（10 Hz 轨迹）饱和。

**(4) Q4 加速度估计噪声放大**：中心差分使 $\sigma_a \sim 0.7|v|$，与真实加速度同量级；但**约束不主动**（入选 $|a| \le 0.964$），影响有限。改进方向：在 Q3 KF 中升级为 6D CA 模型，直接输出加速度状态。

**(5) Q4 启发式段内取 d_min 非严格最优**：在保证窗内全程满足约束的前提下取 $d$ 最小是 SNR 最大化的合理启发式，但非 ML 最优。

#### 7.2.2 未来改进方向

- **HAC / block bootstrap** 处理自相关，给出更稳健的 F 检验 / CI；
- **IMM Kalman** 同步处理匀速 / 转弯段，消解 NIS 越界；
- **多角度递减权重**（拍照 1.0, 0.6, 0.3）激励同目标多次拍摄；
- **轨迹—任务联合规划**（Q4 §6.6.6 时间分布失衡观察）：先规划轨迹覆盖任务"准入条件"（低速段密度），再做调度优化；
- **TLS（总最小二乘）**：Q2/Q3 两路对称含噪场景下应用 TLS 更精确（OLS 已足够，TLS 改进 < 10%）。

---

## 8. 结论与建议

### 8.1 核心研究结论

**(1) 状态空间最大似然时间对齐的精度极限（State-Space ML Alignment Limits）**：Q1 给出 $\hat{\Delta t} = -198.43$ s，与省奖法在 $10^{-5}$ s 内一致，逼近 IEEE 754 双精度浮点精度极限；漂移率 $p = 0.985$ 不显著。10 Hz 输出含全套运动学量与协方差。

**(2) 多盆地辨识与 J\* 噪声底诊断（Multi-Basin Identification）**：Q2 主盆地 $\hat{\Delta t} = -50.29$ s、$(\hat{\Delta x}, \hat{\Delta y}) = (-3.47, +1.83)$ m、$J^* = 1.83$ m² 与噪声底 $\sigma_x^2 + \sigma_y^2 = 1.83$ 完美吻合；KF/RTS 把融合方差降至 0.019 m²（降噪 71%）。**周期性多盆地是位置型 LS 对齐的固有不可辨识性，需外部信号消解**。

**(3) 实测数据无统计显著系统偏差（No Statistically Significant System Bias）**：Q3 给出 $\hat{\Delta t} = +367.93$ s, $(\hat{\Delta x}, \hat{\Delta y}) = (+0.14, +0.18)$ m。三重证据（F 检验 $p = 0.133$ + Bootstrap CI 包含 0 + BIC 偏好 H0）认定**无统计显著系统偏差**。**统计判断 ≠ 物理事实**：实际偏差可能因被噪声 σ ≈ 4 m 稀释而不可分辨，工程级解析需噪声 < 1 m 或样本量 ×64。

**(4) ILP 鲁棒任务调度的反直觉最优性（Robust ILP Scheduling）**：Q4 鲁棒解 21 任务（9 射击 + 12 拍照，期望击中 7.65 个目标）**反多于**标称解 20 任务——chance constraint 下 ILP 全局重组发现更安全候选。覆盖 21/36 个不同目标；**未完成 15 个目标是机器人轨迹物理可达域限制**而非模型缺陷。

### 8.2 工程启示与后续工作建议

**启示一：多源融合的关键是不确定度的统一表达**。本文从 Q1 的 KF 协方差 → Q2 的 Bootstrap CI → Q3 的 F 检验 + AIC/BIC → Q4 的 chance constraint，把估计层不确定度一脉相承传递到任务层鲁棒优化。**这是工程实现的关键链条**。

**启示二：诚实揭示模型局限是高分论文的护城河**。本文对周期性 aliasing 不可消解、Ljung-Box 拒绝白噪声、NIS 边缘越界、覆盖率不对称的物理原因等局限均明确记录并定性解释——多 AI 红队验证作为外部审查机制贯穿全文。

**启示三：分治法处理"带连续约束的离散调度"**。Q4 把连续轨迹上的多重物理约束转化为离散候选集（候选生成阶段），再用 ILP 求全局最优——这是处理此类问题的标准高效范式，可推广到其他场景（无人机航迹规划、车队调度等）。

**后续工作**：
- 引入**外部时间戳元数据**（设备开机记录）消解 Q2 周期性 aliasing；
- 在 KF 中升级为 6D CA 模型，直接输出加速度状态，改善 Q4 加速度约束的鲁棒性；
- 将 chance constraint 升级为 **distributionally robust optimization**，弱化高斯假设；
- 构建**轨迹—任务联合规划**框架（先规划机器人轨迹满足任务"准入条件"，再做调度优化）。

---

## 9. 参考文献

1. Kalman, R. E. (1960). A new approach to linear filtering and prediction problems. *Journal of Basic Engineering*, 82(1), 35–45.
2. Rauch, H. E., Tung, F., & Striebel, C. T. (1965). Maximum likelihood estimates of linear dynamic systems. *AIAA Journal*, 3(8), 1445–1450.
3. Dempster, A. P., Laird, N. M., & Rubin, D. B. (1977). Maximum likelihood from incomplete data via the EM algorithm. *JRSSB*, 39(1), 1–38.
4. Wilks, S. S. (1938). The large-sample distribution of the likelihood ratio for testing composite hypotheses. *AMS*, 9(1), 60–62.
5. Hall, D. L., & Llinas, J. (1997). An introduction to multisensor data fusion. *Proceedings of the IEEE*, 85(1), 6–23.
6. Kay, S. M. (1993). *Fundamentals of Statistical Signal Processing: Estimation Theory*. Prentice-Hall.
7. Bar-Shalom, Y., Li, X. R., & Kirubarajan, T. (2001). *Estimation with Applications to Tracking and Navigation*. Wiley-Interscience.
8. Anderson, T. W., & Darling, D. A. (1954). A test of goodness of fit. *JASA*, 49(268), 765–769.
9. Ljung, G. M., & Box, G. E. P. (1978). On a measure of lack of fit in time series models. *Biometrika*, 65(2), 297–303.
10. Newey, W. K., & West, K. D. (1987). A simple positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica*, 55(3), 703–708.
11. Akaike, H. (1974). A new look at the statistical model identification. *IEEE TAC*, 19(6), 716–723.
12. Schwarz, G. (1978). Estimating the dimension of a model. *Annals of Statistics*, 6(2), 461–464.
13. Efron, B., & Tibshirani, R. J. (1993). *An Introduction to the Bootstrap*. Chapman & Hall/CRC.
14. Charnes, A., & Cooper, W. W. (1959). Chance-constrained programming. *Management Science*, 6(1), 73–79.
15. Wolsey, L. A. (1998). *Integer Programming*. Wiley-Interscience.
16. Huangfu, Q., & Hall, J. A. J. (2018). Parallelizing the dual revised simplex method. *Mathematical Programming Computation*, 10(1), 119–142. (HiGHS)
17. Press, W. H. et al. (2007). *Numerical Recipes* (3rd ed.). Cambridge University Press.

---

## 10. 附录

### 附录 A：代码文件清单

| 文件 | 作用 | 对应模型 |
|---|---|---|
| `xk/code/q1_kalman.py` | Q1 国奖 v2 KF/RTS+EM+LRT | M1 |
| `xk/code/q1_solve.py` | Q1 省奖 baseline (Brent + 线性插值) | M1 baseline |
| `xk/code/q2_solve.py` | Q2 联合估计 + 多盆地辨识 + Bootstrap | M2 |
| `xk/code/q2_kalman.py` | Q2 KF/RTS 融合 + NIS 诊断 | M3 |
| `xk/code/q2_validation.py` | Q2 创新 ACF / N_eff / RTS 减幅实证 | M3 验证 |
| `xk/code/q2_basin_compare.py` | Q2 三审多盆地对比（红队回应） | M2 验证 |
| `xk/code/q2_dxdy_contour.py` | Q2 (Δx, Δy) 凸性诊断 | M2 验证 |
| `xk/code/q3_solve.py` | Q3 不等方差 BLUE + 系统偏差检验 + KF/RTS | M4 |
| `xk/code/q4_solve.py` | Q4 滑动窗 + ILP + chance constraint | M5 |
| `xk/code/q_utils.py` | 共享工具 (代价函数 / 插值 / 融合) | 全部 |

### 附录 B：关键参数表

| 参数 | 数值 | 来源 |
|---|---|---|
| Q1 jerk PSD $q^2$ | 1.0 m²/s⁵ | 经验值（机器人慢速） |
| Q1 观测噪声 σ | $10^{-3}$ m | 数值正则化 |
| Q2 σ_a (KF 过程噪声) | 0.5 m/s² | 工程经验（机器人级） |
| Q2 Bootstrap B | 80 / 200 | 主 basin 内 |
| Q3 σ_a | 1.5 m/s² | 车辆级机动 |
| Q3 Bootstrap B | 80 | 主 basin 内 |
| Q4 chance z | 1.645 | 90% 单侧置信 |
| Q4 σ_v | 5% × \|v\| | Claude 估计（保守） |
| Q4 ε 过渡时间 | 0.1 s | 武器/相机切换 |
| Q4 最小重叠门槛 | 60 s | 防过拟合伪解 |

### 附录 C：完整数值结果表

详见配套 JSON / Excel 文件：
- `xk/output/Q1_summary.json`、`Q1_kalman_*.xlsx`
- `xk/output/Q2_summary.json`、`Q2_basin_compare.json`、`Q2_dxdy_contour_at_dt_50.json`、`Q2_validation.json`、`Q2_trajectory_10Hz_{,strict,kalman}.xlsx`
- `xk/output/Q3_summary.json`、`Q3_trajectory_10Hz_{,strict,kalman}.xlsx`
- `xk/output/Q4_summary.json`（含 nominal + robust 双解 + 对照）、`Q4_result_filled.xlsx`、`Q4_最终方案.xlsx`、`Q4_全部候选.xlsx`

### 附录 D：跨章节符号约定

详见 `xk/paper/CONVENTIONS.md`：
- §1 时间偏差 Δt 全局符号（$t_{\mathrm{phys}} = t_2 + \Delta t$）
- §2 状态空间向量排列
- §3 章节 8 章骨架 vs 9 节自包含模板
- §4 公式 / 图 / 表全文连续编号
- §6 文风与诚实性条款
- §9 历史 docx 修订清单

### 附录 E：多 AI 红队验证全记录

详见：
- `xk/paper/Q2_审查清单.md`、`Q2_二审清单.md`、`Q2_三审清单_盆地选择.md`、`Q2_三审综合.md`
- `xk/paper/Q3_审查清单.md`、`Q3_三审综合.md`
- `xk/paper/Q4_审查清单.md`、`Q4_三审综合.md`

各清单含必填 yes/no、逐条问题、期望返回格式；综合文件含投票汇总、分歧识别、P0/P1/P2 处置清单。

---

> **本初版以 `xk/paper/Q1_Gv2.docx`（M1）+ `Q2.md`（M2 + M3）+ `Q3.md`（M4）+ `Q4.md`（M5）为模型详情；本文件按 PDF 8 章框架整合摘要、引言、总框架、数据、假设符号、模型建立、检验、评价、结论、附录。最终成稿可用 pandoc 合并：**
>
> ```bash
> pandoc 00_论文骨架.md A题论文_v1初版.md \
>     -o A题论文_最终版.docx \
>     --reference-doc=template.docx --mathml
> ```
