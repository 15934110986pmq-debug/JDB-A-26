# 面向异频定位轨迹融合与严格约束任务调度的稳健建模方法

## 摘要

针对地面无人平台异频定位与多目标任务调度问题，本文以"时间校正—稳健残差诊断—协方差融合—严格约束任务调度"为统一建模主线，建立四层次模型，强调统计严谨性与工程可执行性。

**第一问** 针对附件1无噪声异频数据，建立基于轨迹空间残差最小化的时间偏差估计模型。以方式一为时间基准，对方式二采用 PCHIP/Cubic Spline 插值重建轨迹，构造目标函数 $\min_{\tau} \mathrm{MSE}(\tau)=\frac{1}{N}\sum_{k}\|\mathbf{p}_1(t_k)-\mathbf{p}_2(t_k+\tau)\|^2$，采用 0.05 s 步长粗搜索 + 黄金分割精细优化，得 $\widehat{\tau}=198.4317\,\mathrm{s}$，校正后空间残差 RMSE $=3.62\times10^{-8}\,\mathrm{m}$，速度差 RMSE $=6.05\times10^{-9}\,\mathrm{m/s}$，最大方向角差 $0.0096^\circ$，三维一致性同时满足。

**第二问** 针对附件2存在固定系统偏差与随机噪声，建立 *剖面最小二乘 + Savitzky-Golay 平滑分离 + BLUE 协方差融合* 三段模型：先用 SG 滤波（窗长 61，3 阶）剥离主运动轨迹与高频随机分量，再在剖面参数化下解析估计偏差 $\widehat{\mathbf{b}}(\tau)=\mathrm{mean}[\mathbf{p}_2(t+\tau)-\mathbf{p}_1(t)]$ 并把它代回得到一维剖面目标 $\min_{\tau} \mathrm{MSE}_e(\tau)$，求得 $\widehat{\tau}=50.4429\,\mathrm{s}$、$\widehat{\mathbf{b}}=(3.475,\,-1.834)^\top\,\mathrm{m}$。最后基于残差协方差 $\Sigma_1,\Sigma_2$ 对两路观测做最优线性无偏融合 $\widehat{\mathbf{p}}=(\Sigma_1^{-1}+\Sigma_2^{-1})^{-1}(\Sigma_1^{-1}\mathbf{p}_1+\Sigma_2^{-1}\mathbf{p}_2)$。融合后 95% 置信椭圆面积由 $12.5\,\mathrm{m}^2$ 降至 $6.23\,\mathrm{m}^2$，剥离偏差后平滑残差 RMSE 由 $3.94\,\mathrm{m}$ 降至 $0.328\,\mathrm{m}$。

**第三问** 针对附件3，重点不在剥离偏差，而在判别"固定残差成分是否真实存在"。建立 $\mathbf{r}(t)=\mathbf{b}+\boldsymbol{\varepsilon}(t)$，构造 *Block Bootstrap 区间 + Newey-West HAC 协方差检验 + 有效样本 BIC* 三重证据：候选偏差 $\|\widehat{\mathbf{b}}\|=0.244\,\mathrm{m}$，块自助法 95%CI 在 $X,Y$ 方向均覆盖 0；HAC-Hotelling $T^2$ 检验仅在短滞后（lag $\le8$）显著、长滞后（lag $\ge12$）不显著，提示残差时间相关引致的伪显著；BIC$_\mathrm{eff}$ 比较给出 $\Delta\mathrm{BIC}=+6.56$，模型复杂度并未带来收益。三重证据一致：**固定系统偏差统计上不显著**。后续不再剥离空间偏移，仅保留时间校正与协方差融合，并把 10 Hz 融合轨迹按需扩展为第四问输入（共 3687 点）。

**第四问** 在严格物理约束下完成任务调度。把第三问 10 Hz 融合轨迹经 Savitzky-Golay 平滑后用 PCHIP 插值加密至 $300\,\mathrm{Hz}$（$\Delta t=1/300\,\mathrm{s}$），用 `all_true_in_previous_window` 严格检查每个执行时刻前 0.5 s（拍照）或 1.5 s（射击）的全部 150/450 步连续可执行。每目标按 5° 方向角分桶生成至多 520 个拍照候选 / 220 个射击候选，构造冲突图：同射击目标 $\le 1$、同拍照目标任意两次方位角差 $\ge 60^\circ$、准备占用区间互不重叠，然后用 `scipy.optimize.milp`（HiGHS）求两阶段 0–1 整数规划：阶段一最大化任务总数，阶段二在不降低总数的前提下按词典序优化"拍照覆盖 → 射击次数 → 平均质量 → 早完成"。诊断显示射击目标 $S_{13},S_{17},S_{18}$ 因距离/速度联合约束在全轨迹上找不到任何可行点，构成物理不可达；故最终方案为 **35 项任务（15 射击 + 20 拍照）**：覆盖 15/18 射击目标（与可达上限相等）、18/18 拍照目标全覆盖、$P_{01},P_{02}$ 各被两次方向差 $137.8^\circ/171.5^\circ$ 的拍照覆盖。射击命中率 $0.85$，期望命中数 $12.75$。

本文方法的核心定位是**面向真实无人平台约束条件的稳健轨迹融合与任务调度模型**，强调：(1) 统计严谨——第三问以三重证据替代单一显著性检验，避免时间相关残差引致的伪结论；(2) 工程可执行——第四问以候选执行窗 + 冲突图建模，把所有物理约束硬化为 0–1 ILP 不等式，可执行性优先于任务数量。

**关键词** 异频轨迹时间校正；剖面最小二乘；BLUE 协方差融合；HAC 稳健检验；候选执行窗；0–1 整数规划；冲突图

---

## 1. 问题重述

地面无人平台同时携带两种定位方式，二者数据率不同、时间基不同步，且因传感器特性差异可能存在固定系统偏差与随机测量噪声。需要研究：

- **问题一**：附件 1 给出无噪声但时间不同步的两路定位轨迹，要求估计两种方式之间的时间偏差，给出 $10\,\mathrm{Hz}$ 校正后统一轨迹。
- **问题二**：附件 2 在时间偏差之外引入了固定系统偏差与随机噪声，要求把两类误差分离开来，对系统偏差进行参数估计，并在此基础上给出 $10\,\mathrm{Hz}$ 融合轨迹。
- **问题三**：附件 3 的固定偏差是否真实存在尚不确定，要求在残差时间相关条件下做出统计学严谨的判别，并把诊断后的融合轨迹输出供第四问使用。
- **问题四**：基于第三问轨迹与附件 4 的 18 个射击目标 + 18 个拍照目标，在严格的距离/速度/加速度/准备时间/视角差等物理约束下设计任务调度方案，使任务执行尽可能多、覆盖尽可能完整、且全部约束严格满足。

---

## 2. 问题分析

四个问题构成递进式建模链条：

1. **轨迹时间配准**是后续一切建模的前提。两路异频数据若不进行时间对齐，则空间残差中既包含真正的测量误差，又包含时间错位带来的位置错位，导致后续的偏差估计、噪声协方差估计全部失真。
2. **误差分解**是问题二与问题三的核心。误差至少由三部分组成：(i) 时间错位误差 $\to$ 由问题一的 $\widehat{\tau}$ 校正；(ii) 固定系统偏差 $\mathbf{b}$ $\to$ 通过剖面参数化解析估计；(iii) 随机零均值噪声 $\boldsymbol\varepsilon(t)$ $\to$ 由协方差融合处理。
3. **偏差显著性判别**是问题三相对问题二的本质升级。直接套用问题二的 $\widehat{\mathbf{b}}$ 作为修正量是有风险的：当残差短期相关（无人平台轨迹本身平滑，相邻误差强相关）时，常规独立样本检验会得到伪显著结果。必须用稳健工具区分"统计上显著"与"在有效样本意义下显著"。
4. **任务调度**本质是带组合约束的资源分配。直接对原 $10\,\mathrm{Hz}$ 轨迹做调度会因时间分辨率不足而漏掉可行候选；过度放宽约束又会丢失工程可信度。本文采用**先严格约束生成候选执行窗、再用 ILP 在冲突图上选最优组合**的两步分解策略。

---

## 3. 模型假设

1. 两路定位输出的位置量纲一致，时间戳精度足够分辨 $10^{-3}\,\mathrm{s}$ 量级的时间偏差；
2. 在公共有效区间内，定位噪声为零均值二维高斯过程，协方差时变部分远小于平稳部分（用样本协方差近似总体协方差）；
3. 第三问中固定偏差 $\mathbf{b}$ 若存在，则在记录时间内是常向量（不随时间漂移）；
4. 第四问中无人平台轨迹由第三问的融合轨迹刻画，平滑且可用 PCHIP 插值无穷加密；运动学量速度、加速度由数值微分给出；
5. 射击命中率 $p_h=0.85$ 与目标无关，单次行动相互独立；
6. 准备时间内平台必须连续满足该目标的所有空间约束，准备完成后立即执行（执行瞬时占用结束）；
7. 同一射击目标至多被打击一次，同一拍照目标可被多次拍照但任两张照片的视角差必须 $\ge 60^\circ$。

---

## 4. 符号说明

| 符号 | 含义 |
|---|---|
| $\mathbf{p}_1(t),\,\mathbf{p}_2(t)$ | 方式一/方式二在时刻 $t$ 的二维位置向量 |
| $\tau$ | 方式二相对方式一的时间偏差，使 $\mathbf{p}_2(t+\tau)\approx \mathbf{p}_1(t)+\mathbf{b}+\boldsymbol\varepsilon(t)$ |
| $\mathbf{b}=(b_x,b_y)^\top$ | 二维固定系统偏差向量 |
| $\boldsymbol\varepsilon(t)$ | 二维零均值随机误差过程 |
| $\Sigma_1,\Sigma_2,\Sigma_f$ | 方式一/方式二/融合后的 $2\times 2$ 噪声协方差矩阵 |
| $J(\tau)$ | 第一问目标函数 $\frac{1}{N}\sum_k\|\mathbf{p}_1(t_k)-\mathbf{p}_2(t_k+\tau)\|^2$ |
| $J_e(\tau)$ | 第二问剖面目标函数（剥离 $\widehat{\mathbf{b}}(\tau)$ 后的 MSE） |
| $T^2_\mathrm{HAC}(L)$ | 在带宽 $L$ 下 Newey-West HAC 协方差对应的 Hotelling $T^2$ 统计量 |
| $N_\mathrm{eff}$ | 由自相关结构估出的有效样本量 |
| $W_i$ | 第 $i$ 个候选执行窗（含目标编号、准备区间、执行时刻、运动学量、视角） |
| $E$ | 冲突图边集 |
| $x_i\in\{0,1\}$ | 候选窗 $i$ 是否被选中 |
| $y_g\in\{0,1\}$ | 拍照目标 $g$ 是否被覆盖（至少一次） |

---

## 5. 模型建立与求解

### 5.1 第一问：异频轨迹时间偏差估计模型

#### 5.1.1 模型建立

附件 1 中两条轨迹无噪声，但时间基不同步。约定方式一为时间基准，方式二实际物理时间 $=t+\tau$。在方式一时刻 $\{t_k\}_{k=1}^{N_1}$ 上构造误差泛函：

$$J(\tau)=\frac{1}{|M(\tau)|}\sum_{k\in M(\tau)} \big\|\mathbf{p}_1(t_k)-\widehat{\mathbf{p}}_2(t_k+\tau)\big\|^2,$$

其中 $\widehat{\mathbf{p}}_2$ 由方式二原始离散观测经三次样条/PCHIP/Akima 插值得到，$M(\tau)=\{k:\,t_k+\tau\in[t_2^{\min},\,t_2^{\max}]\}$ 是公共有效掩码。

#### 5.1.2 求解算法

**步骤 1（公共区间界定）**：构造 $\tau$ 的可行域

$$[\,\tau_{\min},\tau_{\max}\,]=[\,t_2^{\min}-t_1^{\max}+\delta,\,\ t_2^{\max}-t_1^{\min}-\delta\,],\quad \delta=5\,\mathrm{s}.$$

**步骤 2（粗搜索）**：以步长 $\Delta=0.05\,\mathrm{s}$ 在 $[\tau_{\min},\tau_{\max}]$ 上扫描 $J(\tau)$，得粗最优 $\tau_0$。

**步骤 3（精化）**：在 $[\tau_0-2,\tau_0+2]$ 上用 SciPy `minimize_scalar(method="bounded")`（黄金分割 + 二次插值），收敛容差 $10^{-12}$。

#### 5.1.3 求解结果

| 指标 | 数值 |
|---|---|
| $\widehat{\tau}$ | $198.4317\,\mathrm{s}$ |
| $J(\widehat{\tau})$ | $1.31\times10^{-15}\,\mathrm{m}^2$ |
| 公共区间样本数 | 2 802 |
| 校正后空间 RMSE | $3.62\times10^{-8}\,\mathrm{m}$ |
| 校正后最大残差 | $1.89\times10^{-6}\,\mathrm{m}$ |
| 速度差 RMSE | $6.05\times10^{-9}\,\mathrm{m/s}$ |
| 最大方向角差 | $0.0096^\circ$ |
| $10\,\mathrm{Hz}$ 轨迹点数 | 7 003 |

数值上目标函数已降至浮点精度量级，验证了附件 1 在恰当时间校正下两路轨迹空间一致。最后取两路平均得到 $10\,\mathrm{Hz}$ 统一轨迹（图 5.1）。

#### 5.1.4 一致性多维度验证

仅用空间残差最小化作为目标可能存在过拟合风险，故在估计完成后对**速度** $v=\|\dot{\mathbf{p}}\|$ 和**方向角** $\theta=\mathrm{atan2}(\dot y,\dot x)$ 同步做差异核验，速度 RMSE $=6.05\times10^{-9}\,\mathrm{m/s}$、最大方向角差 $0.0096^\circ$，均处于浮点误差量级，说明问题一的时间校正同时满足三类一致性。

---

### 5.2 第二问：剖面最小二乘—系统偏差剥离—协方差融合模型

#### 5.2.1 误差模型

附件 2 同时含时间偏差 $\tau$、固定偏差 $\mathbf{b}$、随机噪声 $\boldsymbol\varepsilon(t)$：

$$\mathbf{p}_2(t+\tau)=\mathbf{p}_1(t)+\mathbf{b}+\boldsymbol\varepsilon(t),\quad \mathbb{E}[\boldsymbol\varepsilon(t)]=\mathbf{0},\ \mathrm{Cov}[\boldsymbol\varepsilon(t)]=\Sigma_2-\Sigma_1\ne\mathbf{0}.$$

直接做 $\min J(\tau)$ 会同时受偏差与噪声两方面污染，故先剥离 $\mathbf{b}$、再剖面优化 $\tau$。

#### 5.2.2 Savitzky-Golay 平滑轨迹分离

为降低高频随机扰动对偏差估计的污染，先对两路原始观测分别做 Savitzky-Golay 滤波（窗长 $W=61$，自动按奇数边界裁剪；多项式阶 $p=3$）得到平滑轨迹 $\bar{\mathbf{p}}_1(t),\,\bar{\mathbf{p}}_2(t)$，并定义噪声分量

$$\boldsymbol{\eta}_i(t)=\mathbf{p}_i(t)-\bar{\mathbf{p}}_i(t),\quad i=1,2.$$

平滑轨迹用于 $\tau,\mathbf{b}$ 估计，噪声分量用于 $\Sigma_i$ 估计。

#### 5.2.3 剖面最小二乘

给定 $\tau$，定义跨路位置差

$$\boldsymbol{\delta}(t;\tau)=\bar{\mathbf{p}}_2(t+\tau)-\bar{\mathbf{p}}_1(t),$$

固定偏差最小二乘解析解为 $\widehat{\mathbf{b}}(\tau)=\mathrm{mean}_t[\boldsymbol{\delta}(t;\tau)]$。代回得到剖面目标

$$J_e(\tau)=\mathrm{mean}_t\big\|\boldsymbol{\delta}(t;\tau)-\widehat{\mathbf{b}}(\tau)\big\|^2 + \lambda\cdot\frac{1}{T(\tau)},\quad \lambda=10^{-4},$$

其中第二项为短公共区间惩罚（$T(\tau)$ 为公共区间时长），用以抑制公共点过少时出现的伪极小值。在公共区间长度 $\ge 300\,\mathrm{s}$ 且公共点数 $\ge 600$ 的硬筛选下，对 $\tau\in[40,60]\,\mathrm{s}$ 以步长 $0.02\,\mathrm{s}$ 粗搜，再以 `minimize_scalar(bounded, xatol=1e-12)` 精化。

#### 5.2.4 BLUE 协方差融合

由噪声分量样本协方差

$$\widehat\Sigma_i=\mathrm{Cov}(\boldsymbol{\eta}_i)+\rho I,\quad \rho=10^{-8}\ (\text{正则}),\ i=1,2,$$

构造时刻 $t$ 的最优线性无偏估计（BLUE）

$$\boxed{\widehat{\mathbf{p}}(t)=(\widehat\Sigma_1^{-1}+\widehat\Sigma_2^{-1})^{-1}\big(\widehat\Sigma_1^{-1}\bar{\mathbf{p}}_1(t)+\widehat\Sigma_2^{-1}(\bar{\mathbf{p}}_2(t+\widehat\tau)-\widehat{\mathbf{b}})\big)}.$$

后验融合协方差为 $\widehat\Sigma_f=(\widehat\Sigma_1^{-1}+\widehat\Sigma_2^{-1})^{-1}$，对应 95% 置信椭圆面积 $A_{95}=\pi\,\chi^2_{2,0.95}\sqrt{\det\widehat\Sigma_f}$。

#### 5.2.5 求解结果

| 指标 | 数值 |
|---|---|
| 时间偏差 $\widehat\tau$ | $50.4429\,\mathrm{s}$ |
| 系统偏差 $\widehat b_x$ | $3.475\,\mathrm{m}$ |
| 系统偏差 $\widehat b_y$ | $-1.834\,\mathrm{m}$ |
| 剖面目标 $J_e(\widehat\tau)$ | $0.107\,\mathrm{m}^2$ |
| 仅时间校正平滑 RMSE | $3.943\,\mathrm{m}$ |
| 时间 + 偏差校正平滑 RMSE | $0.328\,\mathrm{m}$ |
| 时间 + 偏差校正平滑最大残差 | $1.643\,\mathrm{m}$ |
| 时间 + 偏差校正原始 RMSE | $1.555\,\mathrm{m}$ |
| 公共区间样本数 | 2 760 |
| 方式一 95% 椭圆面积 | $12.538\,\mathrm{m}^2$ |
| 方式二 95% 椭圆面积 | $12.390\,\mathrm{m}^2$ |
| 融合后 95% 椭圆面积 | $\mathbf{6.226\,\mathrm{m}^2}$ |
| $10\,\mathrm{Hz}$ 融合轨迹点数 | 6 899 |

融合后置信椭圆面积比单路减小约 50%，验证了协方差加权融合相对单路与等权平均的统计优势。

#### 5.2.6 关键说明

> "融合并非简单平均，而是基于噪声统计特性的最优加权融合。" 当两路噪声各向异性或方差差异显著时，BLUE 与 1:1 等权融合在样本均值意义下虽接近，但**在协方差意义下** BLUE 是同类无偏估计中后验方差最小的。本文以椭圆面积量化这一收益。

---

### 5.3 第三问：固定残差成分稳健诊断模型

#### 5.3.1 问题升级

附件 3 的问题不是"$\mathbf{b}$ 等于多少"，而是"$\mathbf{b}$ 是否真的存在"。常规做法（直接套问题二的 $\widehat{\mathbf{b}}$）忽略了一个关键事实：**无人平台轨迹本身平滑，相邻时刻误差强相关**，在自相关条件下做独立样本均值检验会得到伪显著结论。本节建立 *Block Bootstrap + HAC 稳健协方差 + 有效样本 BIC* 三重证据机制做联合判别。

#### 5.3.2 残差产生

沿用问题二的 SG 平滑轨迹 + 剖面最小二乘流程，先定 $\widehat\tau$，得到对齐残差表

$$r_x(t_k)=\bar p_{2,x}(t_k+\widehat\tau)-\bar p_{1,x}(t_k),\quad r_y(t_k)=\bar p_{2,y}(t_k+\widehat\tau)-\bar p_{1,y}(t_k).$$

附件 3 上得 $\widehat\tau=-368.17\,\mathrm{s}$、候选偏差 $\widehat{\mathbf{b}}=(-0.081,\,-0.230)^\top\,\mathrm{m}$、$\|\widehat{\mathbf{b}}\|=0.244\,\mathrm{m}$。该数值偏小，是否需要剥离尚需诊断。

#### 5.3.3 三重证据

**(A) Block Bootstrap 稳健均值区间**：取块长 $L_b=10\,\mathrm{s}$（$\Delta t=0.1\,\mathrm{s}$ 对应 100 步），按块独立有放回重采样 $B=2\,000$ 次，得 $\widehat{\mathbf{b}}^{(b)}$ 经验分布。算 $X,Y$ 方向 95% 分位区间：

| 方向 | 95%CI |
|---|---|
| $X$ | $[-0.450,\ +0.228]\,\mathrm{m}$ |
| $Y$ | $[-0.471,\ +0.056]\,\mathrm{m}$ |
| $\|\widehat{\mathbf{b}}\|$ | $[0.059,\ 0.561]\,\mathrm{m}$ |

$X,Y$ 方向区间均覆盖 0 → **Bootstrap 不支持存在固定偏差**。

**(B) HAC（Newey-West）稳健协方差检验**：对残差均值 $\bar{\mathbf{r}}$ 构造 $T^2_\mathrm{HAC}(L)=\bar{\mathbf{r}}^\top \widehat\Sigma_{\bar{\mathbf{r}},\,\mathrm{HAC}}^{-1}(L)\bar{\mathbf{r}}$，其中

$$\widehat\Sigma_{\bar{\mathbf{r}},\,\mathrm{HAC}}=\frac{1}{N}\Big(\widehat\Gamma_0+\sum_{k=1}^{L}\big(1-\tfrac{k}{L+1}\big)(\widehat\Gamma_k+\widehat\Gamma_k^\top)\Big),$$

$\widehat\Gamma_k$ 为残差的 $k$ 阶样本自协方差，权重采用 Bartlett 核。对 $L\in\{2,4,6,8,12,18,24\}$ 做 lag-scan：

| lag $L$ | $T^2$ | $p$ | $\alpha=0.05$ 显著 |
|---|---|---|---|
| 2 | 21.29 | $2.4\times10^{-5}$ | ✓ |
| 4 | 13.02 | 0.0015 | ✓ |
| 6 | 9.50 | 0.0086 | ✓ |
| 8 | 7.57 | 0.023 | ✓ |
| **12** | **5.52** | **0.063** | ✗ |
| **18** | **4.14** | **0.126** | ✗ |
| **24** | **3.49** | **0.175** | ✗ |

短滞后显著（自相关被低估）但长滞后不显著的模式是**典型短期相关伪显著信号**，并非真实固定偏差。HAC 不支持存在固定偏差。

**(C) 有效样本 BIC**：用残差模长一阶自相关结构估有效样本量

$$N_\mathrm{eff}=\frac{N}{1+2\sum_{k=1}^{K^*}\widehat\rho_k},\qquad K^*=\min\{k:\widehat\rho_k\le 0\}-1,$$

得 $N=1\,202,\ N_\mathrm{eff}=45.15$。比较两模型 BIC：

$$\mathrm{BIC}_\mathrm{eff}^{(0)}=N_\mathrm{eff}\log\big(\mathrm{SSE}_0/N\big),\quad \mathrm{BIC}_\mathrm{eff}^{(1)}=N_\mathrm{eff}\log\big(\mathrm{SSE}_1/N\big)+2\log N_\mathrm{eff}.$$

| 量 | 值 |
|---|---|
| $\mathrm{SSE}_0$（不含偏差） | $3\,065.88$ |
| $\mathrm{SSE}_1$（含偏差） | $2\,994.53$ |
| $\mathrm{BIC}_\mathrm{eff}^{(0)}$ | $42.276$ |
| $\mathrm{BIC}_\mathrm{eff}^{(1)}$ | $48.833$ |
| $\Delta\mathrm{BIC}_\mathrm{eff}$ | $\mathbf{+6.557}$ |

$\Delta\mathrm{BIC}>0$ → 加偏差参数后模型反而变差。BIC$_\mathrm{eff}$ 不支持存在固定偏差。

#### 5.3.4 综合判定

| 判别依据 | 结果 | 支持情况 |
|---|---|---|
| 候选成分量级 | $\|\widehat{\mathbf{b}}\|=0.244\,\mathrm{m}$ | 偏弱 |
| 区间稳定性 | 两个方向 95%CI 均覆盖 0 | 不支持 |
| 相关性稳健性 | 短滞后显著、长滞后不稳定 | 支持不足 |
| 模型收益 | $\Delta\mathrm{BIC}_\mathrm{eff}=+6.56$ | 不支持 |

**结论**：附件 3 残差中**未发现长期稳定显著固定偏差成分**。后续不再剥离空间偏移，仅以问题二节流程的协方差融合产出 $10\,\mathrm{Hz}$ 轨迹（公共区间 3 003 点，扩展给问题四 3 687 点），残差 RMSE $1.60\,\mathrm{m}$、$95\%$ 分位 $2.67\,\mathrm{m}$、$99\%$ 分位 $3.01\,\mathrm{m}$。

#### 5.3.5 协方差融合复用

仍采用 BLUE：

| 矩阵 | $\Sigma_{XX}$ | $\Sigma_{XY}$ | $\Sigma_{YY}$ |
|---|---|---|---|
| 方式一 | $17.66$ | $0.40$ | $17.67$ |
| 方式二 | $8.48$ | $0.12$ | $8.03$ |
| 融合 | $\mathbf{5.73}$ | $0.10$ | $\mathbf{5.52}$ |

融合后 $X,Y$ 方差较单路最小者 ($\Sigma_{2,XX}=8.48$) 仍下降 $\sim 32\%$。

---

### 5.4 第四问：候选执行窗—冲突图—整数规划任务调度模型

#### 5.4.1 总体架构

第四问采用四步串联结构（不追求激进任务数，而是把所有约束硬化为 ILP 不等式）：

$$\fbox{$10\,\mathrm{Hz}$ 融合轨迹}\ \to\ \fbox{$300\,\mathrm{Hz}$ 加密}\ \to\ \fbox{候选执行窗}\ \to\ \fbox{冲突图}\ \to\ \fbox{两阶段 0-1 ILP}.$$

#### 5.4.2 高频轨迹扩展

直接对第三问 $10\,\mathrm{Hz}$ 轨迹（3 687 点）做调度时，$0.1\,\mathrm{s}$ 网格不足以分辨准备时间约束（$0.5\,\mathrm{s}$ 拍照、$1.5\,\mathrm{s}$ 射击）的进入/退出时刻，会漏掉大量短可行段。本文先用 SG 滤波（窗 21）在原 $10\,\mathrm{Hz}$ 上去高频抖动，再用 PCHIP 加密到 $300\,\mathrm{Hz}$（$\Delta t=1/300\,\mathrm{s}$），最后再对加密结果做窗长 61 的二次 SG 平滑。速度与加速度由数值微分得到：

$$v(t_k)=\|\nabla \mathbf{p}(t_k)\|,\quad a(t_k)=|\nabla v(t_k)|.$$

#### 5.4.3 基础可行性掩码

设目标 $g$ 位于 $(t_x,t_y)$，类型 $\kappa\in\{\text{shoot},\text{photo}\}$，距离 $d(t)=\|\mathbf{p}(t)-(t_x,t_y)\|$。基础掩码为

$$M_g(t)=\mathbb{1}\{d_\kappa^{\min}\le d(t)\le d_\kappa^{\max},\ v(t)\le v_\kappa^{\max},\ a(t)\le a_\kappa^{\max}\}.$$

| 任务类型 | $d^{\min}$ | $d^{\max}$ | $v^{\max}$ | $a^{\max}$ | 准备时间 |
|---|---|---|---|---|---|
| 射击 | $5\,\mathrm{m}$ | $30\,\mathrm{m}$ | $2\,\mathrm{m/s}$ | $1.5\,\mathrm{m/s}^2$ | $1.5\,\mathrm{s}$ |
| 拍照 | $10\,\mathrm{m}$ | $40\,\mathrm{m}$ | $1.5\,\mathrm{m/s}$ | $1.5\,\mathrm{m/s}^2$ | $0.5\,\mathrm{s}$ |

#### 5.4.4 准备窗严格连续约束

执行时刻 $t_e$ 可行的充要条件是**在前 $T_\mathrm{prep}$ 秒（$N_\mathrm{prep}=T_\mathrm{prep}\cdot 300$ 步）内基础掩码连续为真**：

$$R_g(t_e)=\bigwedge_{k=t_e-N_\mathrm{prep}+1}^{t_e} M_g(t_k).$$

由 `all_true_in_previous_window(M, N)` 实现，等价于对掩码做长度 $N_\mathrm{prep}$ 的滚动 AND。这一条件比"准备瞬时可行"严格得多，确保整个准备过程中目标可见性不被打断。

#### 5.4.5 候选执行窗压缩

对每个目标 $g$，把 $R_g$ 为真的样点按角度分桶后压缩。射击使用纯运动学评分

$$Q_\mathrm{shoot}(d,v,a)=0.45\Big(1-\frac{|d-d_\mathrm{mid}|}{d_\mathrm{half}}\Big)+0.35\Big(1-\frac{v}{v^{\max}}\Big)+0.20\Big(1-\frac{a}{a^{\max}}\Big),$$

每个射击目标按时间步距 $0.03\,\mathrm{s}$ 抽样后取评分前 220 个候选；拍照目标在此基础上按方位角 $\theta_g(t)=\mathrm{atan2}(t_y-y(t),\,t_x-x(t))$ 以 $5^\circ$ 为分桶宽度，每桶取前 3 名 + 全局前 520 名，最终去重保留至多 520 个候选。这一分桶机制是 $18/18$ 拍照覆盖的关键：避免同目标候选堆在同一方向角而被 $60^\circ$ 视角差约束相互排斥。

#### 5.4.6 冲突图建模

对每对候选窗 $(W_i,W_j)$，定义冲突关系 $C(W_i,W_j)$：

$$C(W_i,W_j)=\begin{cases}
\mathrm{True}, & \text{同射击目标}\ \&\ g_i=g_j;\\
\mathrm{True}, & \text{同拍照目标}\ \&\ |\theta_i-\theta_j|_{\bmod 360^\circ}<60^\circ;\\
\mathrm{True}, & [\,t_i^\mathrm{prep},t_i^\mathrm{exec}]\cap[\,t_j^\mathrm{prep},t_j^\mathrm{exec}]\ne\emptyset;\\
\mathrm{False}, & \text{其它}.
\end{cases}$$

冲突图 $G=(V,E)$，$V$ 为候选窗集合，$E=\{(i,j):C(W_i,W_j)\}$。本场实例 $|V|\sim 5\,000$，$|E|\sim 10^5$ 量级。

#### 5.4.7 两阶段 0-1 整数规划

引入决策变量 $x_i\in\{0,1\}$（窗 $i$ 是否被选）和拍照覆盖辅助变量 $y_g\in\{0,1\}$（拍照目标 $g$ 是否被覆盖）。线性约束：

$$\begin{aligned}
&x_i+x_j\le 1, & \forall (i,j)\in E,\\
&y_g\le \sum_{i:\,g_i=g,\,\kappa=\text{photo}} x_i\le M_g\cdot y_g, & \forall \text{ 拍照目标}\,g.
\end{aligned}$$

**阶段一**（最大化任务数）：

$$\max\ \sum_i x_i\quad \text{s.t. 上述约束}.$$

解出 $K^\star$ 后，添加约束 $\sum_i x_i\ge K^\star$ 进入阶段二。

**阶段二**（在不降低任务数前提下做词典序优化）：

$$\max\ W_\mathrm{total}\sum_i x_i+W_\mathrm{photo}\sum_g y_g+W_\mathrm{shoot}\sum_{i:\kappa_i=\mathrm{shoot}} x_i+W_q\sum_i Q_i x_i-W_\mathrm{e}\sum_i \tilde t_i x_i$$

权重按数量级硬分层：

$$W_\mathrm{total}=10^9\gg W_\mathrm{photo}=10^7\gg W_\mathrm{shoot}=2\times10^6\gg W_q=10^3\gg W_\mathrm{e}=10^{-3}.$$

求解器：`scipy.optimize.milp`（HiGHS），`mip_rel_gap=0`，时限 $1\,200\,\mathrm{s}$。最后再以 *局部贪心补插 + 1 换 2 邻域改进* 兜底，提升至局部不可改进。

#### 5.4.8 物理可达性诊断（重要）

候选生成阶段先做诊断（`q4_target_diagnosis_second.csv`），列出每个目标的可行段数、累计可行时长、最小距离：

| 目标 | 可行段数 | 累计可行时长 (s) | 最小距离 (m) | 可达 |
|---|---|---|---|---|
| $S_{13}$ | $\mathbf{0}$ | $0$ | $3.26$ | ✗（速度/加速度不达） |
| $S_{17}$ | $\mathbf{0}$ | $0$ | $22.75$ | ✗ |
| $S_{18}$ | $\mathbf{0}$ | $0$ | $32.09$ | ✗ |
| 其余 15 个射击目标 | 1–17 | $3.39\sim 55.32$ | — | ✓ |
| 全部 18 个拍照目标 | 1–7 | $1.98\sim 21.65$ | — | ✓ |

**$S_{13}/S_{17}/S_{18}$ 在全场轨迹上不存在任何同时满足距离/速度/加速度的 1.5 s 连续段**，构成物理不可达。所以射击覆盖的物理上限就是 15/18，**不是算法弱**。这一诊断在论文中明确声明，避免与"任务总数最大化"目标冲突时被误读。

#### 5.4.9 求解结果

| 指标 | 值 |
|---|---|
| 候选窗总数 | $\sim 4\,800$ |
| 冲突边数 | $\sim 1.1\times 10^5$ |
| **总任务数** | **35** |
| 射击次数 | 15 |
| 完成射击目标 | 15 / 18（与可达上限一致） |
| 射击期望命中数 | $0.85\times15 = \mathbf{12.75}$ |
| 拍照次数 | 20 |
| 拍照覆盖目标 | $\mathbf{18\,/\,18}$ |
| 多角度拍照目标 | $P_{01}$（$137.79^\circ$ 角差）、$P_{02}$（$171.52^\circ$ 角差） |
| 全部约束 | 距离 / 速度 / 加速度 / 1.5 s（射击）/ 0.5 s（拍照）连续准备 / 视角差 全部硬满足 |

#### 5.4.10 任务时间线（节选）

| # | 目标 | 类型 | 准备 (s) | 执行 (s) | $d$ (m) | $v$ (m/s) | $a$ (m/s$^2$) | 视角 (°) |
|---|---|---|---|---|---|---|---|---|
| 1 | $S_{05}$ | 射击 | 445.757 | 447.257 | 15.66 | 0.265 | 0.281 | 219.81 |
| 2 | $P_{17}$ | 拍照 | 447.257 | 447.757 | 28.28 | 0.154 | 0.142 | 329.10 |
| 3 | $P_{18}$ | 拍照 | 447.767 | 448.267 | 31.35 | 0.141 | 0.083 | 349.38 |
| 4 | $P_{13}$ | 拍照 | 448.277 | 448.777 | 12.93 | 0.205 | 0.140 | 216.44 |
| 5 | $P_{08}$ | 拍照 | 448.787 | 449.287 | 32.32 | 0.274 | 0.122 | 69.88 |
| 6 | $P_{14}$ | 拍照 | 449.297 | 449.797 | 20.38 | 0.326 | 0.083 | 264.54 |
| 7 | $S_{07}$ | 射击 | 449.807 | 451.307 | 15.10 | 0.061 | 0.090 | 281.11 |
| ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ |
| 23 | $P_{01}$ | 拍照 | 479.053 | 479.553 | 23.43 | 1.322 | 0.239 | 141.97 |
| 28 | $P_{01}$ | 拍照 | 508.623 | 509.123 | 32.96 | 1.329 | 0.128 | 279.77 |
| ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ | ⋯ |
| 35 | $S_{12}$ | 射击 | 805.857 | 807.357 | 24.05 | 0.209 | 0.028 | 348.01 |

完整时间线见附录与 `q4_task_schedule_second.csv`。

#### 5.4.11 第二版相对激进调度的取舍

第二版任务总数（35）显著低于"最大化任务数 + 放松准备时间连续约束"的激进方案，但**所有约束硬满足**：

1. 轨迹空间覆盖有限（图 5.4.b），平台高速运行时段 $\sim 250$ s 拍照速度上限不可用；
2. 准备窗连续约束直接消除 $\sim 70\%$ 候选；
3. 多角度 $60^\circ$ 拍照约束排除掉 $\ge 80\%$ 同目标候选；
4. 物理不可达目标 $\{S_{13},S_{17},S_{18}\}$ 直接锁定射击覆盖上限。

**论文核心定位**：**可执行性优先于任务数量**。

---

## 6. 模型分析与评价

### 6.1 模型创新点

1. **异频轨迹时间配准模型**：以空间残差最小化为目标，配合粗 + 精两阶段优化，在第一问无噪声场景下可压到浮点精度。
2. **剖面最小二乘 + BLUE 协方差融合**：把"$\tau,\mathbf{b}$ 联合估计"分解为内层解析估计 + 外层一维优化，把高维问题降为一维；融合阶段以椭圆面积量化协方差收益。
3. **三重证据稳健诊断框架**：用 Block Bootstrap + HAC + BIC$_\mathrm{eff}$ 联合判别，避免在自相关残差上做独立样本检验得到伪显著结论。
4. **候选执行窗调度框架**：以"基础掩码 → 滚动 AND 准备窗 → 角度分桶压缩"三步生成 ILP 候选，把所有物理约束硬化为 0-1 不等式。
5. **冲突图 + 两阶段 ILP**：阶段一锁住任务总数，阶段二做词典序结构优化（拍照覆盖 → 射击次数 → 平均质量 → 早完成），可重现、可证明、可调权重。
6. **多角度拍照视角差正式纳入调度**：把 $60^\circ$ 视角差作为同目标 pairwise 硬约束写入 ILP，通过角度分桶机制保证候选多样性，是 18/18 拍照覆盖的关键。

### 6.2 模型优点

- **统计严谨**：第三问以三重证据替代单一显著性检验；
- **物理可信**：第四问所有约束硬满足，准备窗连续性、视角差、距离/速度/加速度全部体现；
- **可复现**：所有最优化采用确定性算法（粗搜索 + 黄金分割 + HiGHS MILP），无随机种子相关结果；
- **诊断完备**：每问输出 `summary.csv` + 诊断图（$J(\tau)$ 曲线、残差 ECDF、HAC lag-scan、Bootstrap 直方图、轨迹图、任务甘特图、目标可达性诊断表）。

### 6.3 模型局限与诚实声明

1. 协方差融合假设两路噪声独立、平稳。若两路定位共享公共干扰源（例如同一 GNSS 接收机的多路径误差），$\Sigma_1,\Sigma_2$ 不再独立，BLUE 失去最优性。
2. 第三问 BIC$_\mathrm{eff}$ 以模长一阶自相关近似 $N_\mathrm{eff}$，对长程相关结构（如分形噪声）敏感性不足。
3. 第四问准备时间内运动学约束的硬连续假设较强，未建模平台姿态切换的动力学过渡过程。
4. 射击命中率 $0.85$ 与目标无关，未考虑视线遮挡、目标抖动等外因。
5. **物理不可达目标 $S_{13},S_{17},S_{18}$** 在论文与代码诊断中明确声明，避免被解读为算法不力。

### 6.4 模型推广

该框架可直接推广至以下场景：

- 多源 GNSS / UWB / 视觉里程计的异频轨迹融合；
- 卫星轨迹与地面观测的时间对齐与残差检验；
- 含有非零零均值噪声的自动驾驶感知系统；
- 任务密集型无人机集群的多目标巡查 / 拍照调度；
- 工业检测中带准备时间和视角约束的扫描路径规划。

---

## 7. 参考文献

[1] Newey W K, West K D. *A Simple, Positive Semi-definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix*. Econometrica, 1987, 55(3): 703-708.

[2] Künsch H R. *The Jackknife and the Bootstrap for General Stationary Observations*. Annals of Statistics, 1989, 17(3): 1217-1241.

[3] Savitzky A, Golay M J E. *Smoothing and Differentiation of Data by Simplified Least Squares Procedures*. Analytical Chemistry, 1964, 36(8): 1627-1639.

[4] Schwarz G. *Estimating the Dimension of a Model*. Annals of Statistics, 1978, 6(2): 461-464.

[5] Huber P J, Ronchetti E M. *Robust Statistics*. 2nd Edition. Wiley, 2009.

[6] Huang B, Hofmann B et al. *HiGHS: high-performance parallel linear optimization software*. Mathematical Programming Computation, 2018.

[7] Virtanen P, Gommers R et al. *SciPy 1.0: Fundamental Algorithms for Scientific Computing in Python*. Nature Methods, 2020, 17: 261-272.

[8] Aitken A C. *On Least Squares and Linear Combination of Observations*. Proceedings of the Royal Society of Edinburgh, 1935, 55: 42-48. (BLUE 加权最小二乘融合的经典出处)

[9] Wolsey L A. *Integer Programming*. 2nd Edition. Wiley, 2020.

---

## 8. 附录

### 8.1 文件清单

| 子目录 | 文件 | 说明 |
|---|---|---|
| `code/` | `program1.py` | 第一问：异频轨迹时间偏差估计 |
| `code/` | `program2.py` | 第二问：剖面 LS + BLUE 协方差融合 |
| `code/` | `program3.py` | 第三问：Block Bootstrap + HAC + BIC$_\mathrm{eff}$ 三重诊断 |
| `code/` | `program4.py` | 第四问：候选执行窗 + 冲突图 + 两阶段 0-1 ILP |
| `output/q1_outputs/` | `q1_summary.csv`, `q1_10hz_trajectory.csv`, ... | 第一问输出表 |
| `output/q2_outputs/` | `q2_summary.csv`, `q2_covariances.csv`, ... | 第二问输出表 |
| `output/q3_outputs/` | `q3_summary.csv`, `q3_evidence_table.csv`, `q3_hac_tests.csv`, `q3_bic_eff.csv`, ... | 第三问输出表 |
| `output/q3_final_outputs/` | `q3_10Hz_extended_trajectory_for_q4.csv`, ... | 给问题四的扩展轨迹 |
| `output/q4_second_outputs/` | `q4_summary_second.csv`, `q4_task_schedule_second.csv`, `q4_target_diagnosis_second.csv`, `q4_photo_angle_check_second.csv`, `result.xlsx` | 第四问最终交付 |
| `figures/` | `q[1-4]_*.png` | 各问诊断图与轨迹图 |

### 8.2 复现命令

```bash
# 在仓库 xr_submission/code/ 下放置附件 1-4 后依次运行
python program1.py
python program2.py
python program3.py
python program4.py
```

### 8.3 关键超参数

| 阶段 | 超参 | 值 |
|---|---|---|
| 第一问 | 粗搜索步长 / 精化半宽 | $0.05\,\mathrm{s}$ / $2\,\mathrm{s}$ |
| 第二问 | SG 窗长 / 阶 | $61$ / $3$ |
| 第二问 | $\tau$ 搜索区间 | $[40,60]\,\mathrm{s}$ |
| 第二问 | 公共点 / 时长门槛 | $\ge 600$ / $\ge 300\,\mathrm{s}$ |
| 第三问 | Block Bootstrap | 块长 $10\,\mathrm{s}$，$B=2\,000$ |
| 第三问 | HAC lag 扫描 | $\{2,4,6,8,12,18,24\}$ |
| 第四问 | 加密频率 | $300\,\mathrm{Hz}$ |
| 第四问 | 拍照角度桶宽 | $5^\circ$ |
| 第四问 | 单目标候选上限 | 220（射击）/ 520（拍照） |
| 第四问 | ILP 时限 / gap | $1\,200\,\mathrm{s}$ / $0$ |
| 第四问 | 阶段二权重 | $W_\mathrm{total}=10^9,\ W_\mathrm{photo}=10^7,\ W_\mathrm{shoot}=2\times10^6,\ W_q=10^3,\ W_\mathrm{e}=10^{-3}$ |

### 8.4 关键诊断图索引

- 图 5.1 — 附件 1 时间偏差目标函数 $J(\tau)$ 曲线 → `figures/q1_time_shift_objective.png`
- 图 5.2 — 附件 2 剖面目标函数 $J_e(\tau)$ 曲线 → `figures/q2_profile_objective.png`
- 图 5.3 — 附件 2 残差 ECDF（剥离偏差前后） → `figures/q2_residual_ecdf.png`
- 图 5.4 — 附件 2 三种轨迹的 95% 椭圆面积比较 → `figures/q2_covariance_comparison.png`
- 图 5.5 — 附件 3 Bootstrap 候选偏差 95%CI → `figures/q3_bias_bootstrap_ci.png`
- 图 5.6 — 附件 3 HAC lag-scan p 值曲线 → `figures/q3_hac_sensitivity.png`
- 图 5.7 — 第三问扩展 $10\,\mathrm{Hz}$ 轨迹（供第四问使用） → `figures/q3_extended_trajectory_for_q4.png`
- 图 5.8 — 第四问轨迹与目标点叠加图 → `figures/q4_trajectory_targets_second.png`
- 图 5.9 — 第四问拍照覆盖统计柱状图 → `figures/q4_photo_counts_second.png`

### 8.5 第四问完整任务调度

详见 `output/q4_second_outputs/q4_task_schedule_second.csv` 与 `output/q4_second_outputs/result.xlsx`，共 35 行任务记录，按执行时刻升序排列。

### 8.6 第四问验证表

`output/q4_second_outputs/q4_photo_angle_check_second.csv` — 18 个拍照目标的视角差校核表，全部 `pass=True`。

`output/q4_second_outputs/q4_target_diagnosis_second.csv` — 36 个目标的物理可达性诊断表，标识 $S_{13},S_{17},S_{18}$ 为不可达。

