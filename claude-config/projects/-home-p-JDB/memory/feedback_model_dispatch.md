---
name: Model dispatch policy — Opus orchestrates, Sonnet/Haiku do tactical work
description: User wants me to manually dispatch subagents via the Agent tool with explicit model overrides — main session stays on Opus, code/research/batch work goes to Sonnet or Haiku subagents
type: feedback
originSessionId: 13b09cd5-9478-446c-b286-6154852a9bee
---
User's directive: 你手动调代理. The user is paying for Opus 4.7 in the main session and wants tactical work offloaded to cheaper models via subagent dispatch — not by editing settings or agent frontmatter (no `~/.claude/agents/` dir exists on this machine; the names in `~/.claude/rules/common/agents.md` are conventions, not actual agent files).

**Why:** Cost + speed. Opus is for thinking (modeling,论文写作, sensitivity analysis, decisions). Sonnet/Haiku are for doing (code, plots, batch ops). Auto-routing by task type does not exist in Claude Code — the orchestrator (me, in Opus) must manually dispatch.

**How to apply:**

When the next step is **tactical** (write/edit code files, run experiments, generate plots, parse data, search docs, batch refactor), call the Agent tool with an explicit `model` override:

- `model: "sonnet"` — coding, debugging, experiment runs, figure generation, doc lookup with synthesis
- `model: "haiku"` — file renames, format conversion, simple greps, lightweight checks, repeated lookups

When the step is **strategic** (model design, choosing algorithms, writing论文 sections, sanity-checking assumptions, answering "为什么这样做"), keep it in the main Opus session — don't delegate.

Brief subagents thoroughly (file paths, line numbers, exact deliverables) since they don't see the conversation context. After the subagent returns, verify the diff myself — don't trust the summary blindly.

**Concrete project mapping (2026 金地杯 A 题, /home/p/JDB/xk):**

| Phase | Who |
|---|---|
| Q2/Q3/Q4 建模思路、算法选择、稳健性论证 | Opus (me) |
| 写 q2_solve.py / q3_solve.py / q4_solve.py | Sonnet subagent |
| 跑数、调参、生成 figures/*.png | Sonnet subagent |
| 论文章节起草 (Q2.md, Q3.md, Q4.md) 第一稿 | Sonnet subagent + Opus polish |
| 论文最终润色、评委视角自审 | Opus (me) |
| 批量改文件名、md→html 渲染、xlsx 合并 | Haiku subagent |
| 查 numpy/scipy/PuLP API | Haiku subagent (with documentation-lookup skill) |
