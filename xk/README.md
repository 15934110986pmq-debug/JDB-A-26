# 2026 金地杯 A 题工作目录

> 多源融合机器人定位 + 任务调度优化

## 目录结构

```
xk/
├── README.md             # 本文件
├── docs/
│   ├── 2026_A题.docx     # 官方题目（原件）
│   └── 题目.md           # 整理后的 Markdown 题面（含 LaTeX 还原的约束）
├── data/
│   ├── 附件1.xlsx        # 无噪声，仅时间偏差
│   ├── 附件2.xlsx        # 含噪声 + 系统偏差
│   ├── 附件3.xlsx        # 实测数据
│   ├── 附件4.xlsx        # 射击/拍照目标
│   └── result_template.xlsx
├── figures/              # 论文用图（待生成）
└── output/               # 中间结果与最终 result.xlsx
```

## 环境

- Python 3.12 venv 在 `/home/p/JDB/.venv`
- VSCode：选择该解释器即可
- 中文字体配置：`/home/p/JDB/A/plot_style.py`（也适用于本目录）

## 解题路线（建议顺序）

| 阶段 | 内容 | 输出 |
|---|---|---|
| Q1 | 时间对齐（互相关 / 最大公共时段） | `output/Q1_轨迹_10Hz.xlsx` |
| Q2 | 含噪 + 系统偏差融合（Kalman / WLS） | `output/Q2_轨迹_10Hz.xlsx` |
| Q3 | 系统偏差检验（卡方 / Bootstrap） + 同 Q2 | `output/Q3_轨迹_10Hz.xlsx` |
| Q4 | 任务调度优化（贪心 + MILP） | `output/result.xlsx`，`figures/Q4_*.png` |

## 关键约束速查

- 射击：$d\in[5,30]\mathrm m$、$v\le 2\,\mathrm{m/s}$、$|a|\le 1.5\,\mathrm{m/s^2}$，校准 1.5 s
- 拍照：$d\in[10,40]\mathrm m$、角度差 $\ge 60°$、$v\le 1.5\,\mathrm{m/s}$、$|a|\le 1.5\,\mathrm{m/s^2}$，对准 0.5 s
