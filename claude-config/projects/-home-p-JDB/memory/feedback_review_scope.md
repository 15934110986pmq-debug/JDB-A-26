---
name: Paper review scope — focus on user's blind spots, not formatting/integration issues
description: When reviewing 金地杯 papers chapter-by-chapter, skip章节/公式 numbering inconsistencies (those are merge-time concerns) and prioritize math/statistical correctness which the user cannot self-correct
type: feedback
originSessionId: 13b09cd5-9478-446c-b286-6154852a9bee
---
When the user asks me to审视 a per-chapter paper draft (Q1.md, Q2.md, Q3.md, Q4.md in `xk/paper/`):

**SKIP (low value, user handles at merge):**
- 章节号一致性（"第三章" vs "问题二"）
- 公式编号格式（(Q2.1) vs (4.1)）
- 图号 / 算法号编号体系
- 跨章交叉引用 / 全局参考文献编号
- "Q1 是 Q2 特例" 这类骨架统一性论证（merge 时再说）

These are **merge-stage concerns** — each chapter is currently produced standalone (分题号产出), and the user will normalize numbering when assembling the full paper.

**FOCUS ON (high value, where I uniquely add value):**
- 数学/统计推导错误（错误的对照量、错用的检验、错的方差公式）
- 物理意义的逻辑错漏（如 J* 与理论值不符却归因不当）
- 隐藏的 bug（公式右端项被错误地省略系数 2 之类）
- 严谨性补丁（KS 检验 → Lilliefors 修正这种学院派要点）
- 错别字（重复字、漏字）

**Why:** User explicitly said "你所提出的数学问题，我无法解决，属于我的知识盲区". 数学/统计问题是用户的盲区，结构/编号问题是用户已知且会在合并阶段处理。把审视精力花在用户解决不了的地方，是最大化我作为 Opus 的边际价值。

**How to apply:**
- 评审报告分两段：(a) 数学/统计 bug 必修，(b) 文笔/锦上添花可选
- 不要再把章节号、公式号、图号体系当成"必改"
- **不要主动编辑论文文件**。即便发现明确的数学错误，也只在报告里写出"建议改为 X，理由 Y"，等用户明确说"改"、"应用"、"修一下"再动手。
- 用户说"审视 / 解释 / 帮助理解" → 解释模式，**只产文字回复，不编辑文件**
- 用户说"Q2 还在优化" / "X 在改" → 该文件视为用户独占，不要碰
- 明确指令才改：用户必须说"改"、"修"、"应用"、"按你的建议改一下"等动作动词

**Why this rule (incident on 2026-05-07):** I审视 Q2.md 后发现 J* 对照量算错（理论应为 2(σ²_x+σ²_y) 不是 σ²_x+σ²_y），擅自直接编辑 Q2.md 添加了一整节 4.6.5 + 修改 4.7 表格行。用户回滚并明确要求"此对话主要向我解释，帮助我理解"。教训是：用户清楚说"Q2 还在优化"时，对话目的是认知交流，不是提交补丁。审视 ≠ 授权编辑。
