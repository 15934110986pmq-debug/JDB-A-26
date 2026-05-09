# 论文章节工作目录

> 边解边写。每完成一问立即落成一个章节文件，最终拼接为完整论文。

## 章节清单

| 章节 | 文件 | 状态 |
|---|---|---|
| **统一约定** | **`CONVENTIONS.md`** | ✅ 符号、章节结构、文风、docx patch 清单 |
| 第一章 摘要与关键词 | `00_摘要.md` | 待写 |
| 第二章 问题重述与思路 | `01_问题重述.md` | 待写 |
| **第三章 问题一（省奖基线）** | `Q1.md` | ✅ 单参数 Brent + 线性插值（baseline）；代码 `code/q1_solve.py` |
| **第三章 问题一（国奖 v2）** | `Q1_Gv2.docx` + `code/q1_kalman.py` | ✅ KF/RTS+EM+LRT；**符号已在代码中切换为 Δt 约定，docx 待按 CONVENTIONS §9 patch 后重生** |
| 第四章 问题二 | `Q2.md` | ✅ 完成（三参数联合估计 + KF/RTS + Bootstrap + 多重诊断） |
| 第五章 问题三 | `Q3.md` | 待写 |
| 第六章 问题四 | `Q4.md` | 待写 |
| 第七章 模型评价与改进 | `90_模型评价.md` | 待写 |
| 附录 | `99_附录.md` | 代码/输出文件清单 |

> 跨章节符号（特别是时间偏差 $\Delta t$ 的符号约定）以 `CONVENTIONS.md` 为准。新增章节前先读 §1–§7。

## 风格约定

- **学术中文**：避免口语，使用"建立"、"实证"、"等价"、"约定"等学术词汇
- **公式 LaTeX**：行内 `$...$`，行间 `$$...$$`；编号 `\tag{x.y}`
- **图表**：图标题中文，引用如"图 3.1"；与代码生成的 PNG 同步
- **参考文献**：每章末尾分别列出（建议最后再统一去重）
- **符号一致**：跨章节维护一份符号表，符号尽量沿用

## 渲染与导出

VSCode 装 `Markdown Preview Enhanced` 插件，公式自动 KaTeX 渲染。

最终导出为 Word：

```bash
# 假设已装 pandoc
pandoc Q1.md Q2.md Q3.md Q4.md \
  -o A题论文_v1.docx \
  --metadata title="2026 金地杯 A 题：多源融合机器人定位与任务调度优化" \
  --metadata author="xk" \
  --reference-doc=template.docx \
  --mathml
```

或用 `python-docx` + `build_paper.py` 程序化生成（参考 `A/build_paper.py`）。
