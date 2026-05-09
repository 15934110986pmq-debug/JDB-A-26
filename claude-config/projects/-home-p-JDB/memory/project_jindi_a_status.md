---
name: 金地杯 A 题项目状态（2026-05-09）
description: A 题"多源融合机器人定位与任务调度"四问全部完成的当前状态、关键决策与文件结构
type: project
originSessionId: 5c82eef5-e5b4-4f85-8b31-8d603b6f0bf9
---
**Why**: 用户在 2026-05-09 这一长会话中完成了金地杯 A 题 Q1-Q4 全部建模 + 论文初版。后续会话需要快速恢复上下文，避免重新追溯所有历史决策。
**How to apply**: 接到关于 A 题的新请求时（修改、扩展、验证），先读本备忘 + 仓库 `xk/paper/CONVENTIONS.md`，再进入具体文件。

## 仓库结构（`/home/p/JDB`）

```
xk/
├── code/
│   ├── q1_solve.py             # Q1 省奖 baseline (Brent + 线性插值)
│   ├── q1_kalman.py            # Q1 国奖 v2 (6D CA + KF/RTS + EM + LRT)
│   ├── q2_solve.py             # Q2 联合 LS + Bootstrap + 多盆地 + KF/RTS 调度入口
│   ├── q2_kalman.py            # Q2 KF/RTS 融合（per-source R）
│   ├── q2_validation.py        # Q2 创新 ACF / N_eff / RTS 减幅实证
│   ├── q2_basin_compare.py     # Q2 多盆地实证对比（红队回应）
│   ├── q2_dxdy_contour.py      # Q2 (Δx, Δy) 凸性诊断
│   ├── q3_solve.py             # Q3 不等方差 BLUE + 系统偏差检验 + KF/RTS
│   ├── q4_solve.py             # Q4 滑动窗 + ILP + chance constraint
│   └── q_utils.py              # 共享 LS 代价函数 / 插值 / fuse_10hz
├── paper/
│   ├── CONVENTIONS.md          # 跨章节符号 + 8章模板 + docx patch 清单
│   ├── 00_论文骨架.md           # 8章顶层框架蓝图
│   ├── A题论文_v1初版.md        # 完整初版（按 8 章框架整合所有模型）
│   ├── Q1.md / Q1_Gv2.docx     # Q1 章节
│   ├── Q2.md                   # Q2 章节
│   ├── Q3.md                   # Q3 章节
│   ├── Q4.md                   # Q4 章节
│   ├── Q{2,3,4}_审查清单.md     # 多 AI 红队审查清单
│   └── Q{2,3,4}_三审综合.md     # 红队结果汇总 + P0/P1/P2 处置
├── data/                       # 附件1-4.xlsx + result_template.xlsx
├── output/                     # Q{1-4}_summary.json + 各 10Hz 轨迹 xlsx
└── figures/                    # 各章节诊断图
```

## 四问当前主交付（2026-05-09 状态）

| 问题 | 主交付 | 关键数值 | 备注 |
|---|---|---|---|
| Q1 | KF/RTS+EM+LRT 国奖 v2 | $\hat{\Delta t}=-198.43$ s, $J^*\sim 10^{-11}$, LRT $p=0.985$ | 双版本（省奖 baseline 在 Q1.md） |
| Q2 | $\hat{\Delta t}=-50.29$, $(\hat{\Delta x},\hat{\Delta y})=(-3.47,+1.83)$, $J^*=1.83$ | KF $\overline{P}_{xx}=0.019$（降噪 71%）, NIS=2.89 | **主解从 -364.81 切到 -50.29**（5 AI 红队全票），原 -364.81 保留为 alias 备选 |
| Q3 | $\hat{\Delta t}=+367.93$, $(\hat{\Delta x},\hat{\Delta y})=(+0.14,+0.18)$ m | F 检验 $p=0.133$ 不拒绝 H0；BLUE $w=(0.32,0.68)$；NIS=2.20 | **题面第一问结论：无统计显著系统偏差**；保留点估计输出 |
| Q4 | 标称 **34 任务 (29 射击 + 5 拍照)** / 鲁棒 31 任务 | 期望命中 24.65；K=3 拐点；分层目标 ILP（拍照覆盖优先）| 拍照达物理上限 5/18（题面 v≤1.5+视角差 60°+轨迹低速段乘积）；commit 988e059 |

## 关键技术决策（已沉淀，不要重做）

1. **Δt 全局符号约定**：$t_{\mathrm{phys}}=t^{(2)}+\Delta t$，所有章节统一为 Q2/Q3 同号；Q1 国奖 v2 docx 早期 $\delta$ 已弃用（patch 清单见 CONVENTIONS.md §9）。
2. **Q2 主解切换**：原始 -364.81 不是 J\* 最小盆地。`q2_basin_compare.py` 用两阶段 NM 重精化 -50 盆地 J\*=1.827（vs -364 的 2.038）。详见 `Q2_三审综合.md`。
3. **Q3 不等方差 BLUE**：$\sigma_1=4.03 \ne \sigma_2=2.78$，$w_k = 1/\sigma_k^2 / \Sigma$；KF 用 per-source R。
4. **Q3 系统偏差判定（题面第一问）**：F 检验 + Bootstrap CI + AIC/BIC 三重证据 → "**统计上不显著**"（不写"不存在"，是诚实声明）。保留 LS 点估计 (+0.14, +0.18) 为输出。
5. **Q4 K=3 选择**：单次 85% 命中累积 99.66% 是工程拐点；K=∞ 给 81 任务但 S12 单目标 25 次重复物理不合理。
6. **Q4 段内密集候选**：每段按 (T_aim+0) / (T_focus+0) 间隔放多个执行时刻候选，让 ILP 自由选；旧版"段内取 d_min 一个"是 P0 修正前。
7. **Q4 调度算法**：scipy.optimize.milp + HiGHS（n=275-323 候选亚秒级），不依赖 PuLP。
8. **Q4 分层目标 ILP（2026-05-09 后期修正）**：等权 max ∑x_i 因射击候选 295 vs 拍照 28 给出失衡解 (31 射击 + 4 拍照)；引入覆盖指示 y_g + 分层权重 M_p=1000 ≫ M_s=100 ≫ 1，强制拍照覆盖最优先。代价仅减 1 任务即让拍照覆盖 4 → 5（达物理上限）。
9. **Q4 拍照硬上限 = 5（独立 ILP 验证）**：题面"v≤1.5 + 视角差 60° + 持续 0.5s"叠加机器人轨迹（[445,510] s 低速段）→ 28 候选堆积在 5 个 t_exec 时段（445.5/479.9/480.4/493.4/508.3），每段最多选 1 个。这是物理硬上限，论文 §6.6.1 当成"诚实声明"而非缺陷。要再提升只能改轨迹（轨迹—任务联合规划，问题外延）。
8. **q_utils.py 的 feasible_domain bug**：在 Q3 数据下符号反，q3_solve 内 `feasible_domain_correct` inline 修正；不要动 q_utils.py 影响 Q2。

## 多 AI 红队验证范式（贯穿全文）

每个 Qx 完成后：
1. 写 `Q{x}_审查清单.md`（含 §0 项目背景 + 5 个 yes/no + 4 类问题 + 期望返回格式）
2. 用户贴给 ChatGPT / Gemini / 独立 Claude / DeepSeek / 豆包（ChatGPT 经常失败因长度）
3. 把回复贴回，写 `Q{x}_三审综合.md`（投票表 + 共识 + 分歧 + P0/P1/P2 处置清单）
4. 按 P0 修正代码 + 论文，P1 增强论文厚度，P2 选做

Q2 红队发现原 NM 早停（C4 J\*=3.139 真值 1.827）→ **主解切换**；
Q3 红队一致建议"不显著"非"不存在" + 保留点估计；
Q4 红队建议 chance constraint 鲁棒化（鲁棒解反多 1 任务）。

## 论文写作框架

8 章顶层骨架（参考 `xk/paper/PDF匿名版-山西低空经济...pdf`）：
1. 问题描述 / 2. 总框架 / 3. 数据预处理 / 4. 假设符号 / 5. 模型建立（M1-M5 三子节）/ 6. 模型检验 / 7. 评价 / 8. 结论 / 参考文献 / 附录

各 Qx.md 仍用 9 节自包含模板写草稿；合稿时按 `CONVENTIONS.md §3.3` 拆分到 8 章。完整初版已生成 `A题论文_v1初版.md`。

## GitHub

- 仓库：https://github.com/15934110986pmq-debug/JDB-A-26
- 已推到 main：所有四问 + 红队清单 + 综合 + 论文初版
- gh CLI 已装在 `~/.local/bin/gh`，已 auth 登录 token gho_***
- 当前 description 在 GitHub 上反映 Q1/Q2 完成 + Q3/Q4 待写状态（**已过时**，需要更新到 Q3/Q4 完成）
