# 金地杯 A 题 — 多源融合机器人定位与任务调度

## 项目类型
2026 金地杯（数模赛 A 题）。本科生建模竞赛交付物。仓库不是工程项目而是**论文 + 代码 + 数据**的研究资产，以"红队-验证-修正"循环为开发节奏。

## 仓库结构（认准 `xk/`）
```
xk/code/      Q1-Q4 求解脚本 + 共享 q_utils.py
xk/paper/     Qx.md 章节草稿 + Qx_审查清单/三审综合 + CONVENTIONS.md
xk/output/    Qx_summary.json + 中间 xlsx
xk/figures/   各章 PNG
xk/data/      附件 1-4.xlsx + result_template.xlsx (不要改)
A/            历史/旧版本（Q1-Q4 早期 baseline）— 默认不动
```

执行入口：`/home/p/JDB/.venv/bin/python xk/code/qN_solve.py`（不要 `python` 直接调用，系统无）。

## 关键技术决策（已沉淀，不要重做）
- **Δt 全局符号**：$t_{\mathrm{phys}} = t^{(2)} + \Delta t$，所有章节统一。
- **Q2 主解 = -50.29**（非原 -364.81）；J\* 最小盆地由 `q2_basin_compare.py` 两阶段 NM 验证。
- **Q3 系统偏差判定**：F 检验 + Bootstrap CI + AIC/BIC 三重证据 → "**统计上不显著**"（不写"不存在"）；保留 LS 点估计为输出。
- **Q4 主解 = 标称 34 任务 (29 射击 + 5 拍照)**，分层目标 ILP（拍照覆盖最优先）；拍照达物理上限 5/18。鲁棒解 31 任务为对照。
- **Q4 ILP**：scipy.optimize.milp + HiGHS，不要换 PuLP。
- **q_utils.py 的 feasible_domain 在 Q3 数据下符号反**：q3_solve.py 内 inline 修正。**不要修 q_utils.py**（影响 Q2）。

## 工作流偏好
- **诚实声明**：约束在最优解处不主动起作用、覆盖率受物理可达域限制等局限要在论文里**明确写**，不要藏。
- **多 AI 红队验证**：每个 Qx 完成后写 `Qx_审查清单.md`（含 §0 项目背景），用户贴给 ChatGPT/Gemini/DeepSeek/独立 Claude，回复汇总到 `Qx_三审综合.md`。
- **K 拐点 / J\* 最小盆地 / 双解对照**等已沉淀的范式继续使用。
- **段内密集 + ILP**优于"段内取唯一最优"启发式。
- **诊断 J\* 噪声底**：每个 LS 问题先估 σ_noise 给 J\* 一个量级参照。

## 代码/文档约定
- 论文中**Unicode 数学符号 + LaTeX `$...$`**（终端回复用 Unicode，paper/markdown 文件用 LaTeX）。
- 中文注释/标识符 OK，但变量名仍用英文（如 `shoot_candidates`、`coverage_weight`）。
- 修改 Qx 章节时**只动数学/数据/分析**，**不改章节编号、节标题格式**（合稿时统一处理）。
- 提交：`feat(QN): ...` / `fix(QN): ...` / `docs(QN): ...`，commit message 描述"为什么"。
- **不修改 `xk/data/`**（附件原始数据 + result_template）。

## 当前状态（2026-05-09）
Q1-Q4 全部完成 + 论文初版 `xk/paper/A题论文_v1初版.md`。最新工作：Q4 分层目标 ILP（commit 988e059）。
GitHub: https://github.com/15934110986pmq-debug/JDB-A-26
