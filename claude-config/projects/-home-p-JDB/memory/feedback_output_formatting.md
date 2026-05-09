---
name: Output formatting — Unicode in terminal, LaTeX in documents
description: In terminal/chat replies use Unicode math symbols directly; reserve LaTeX syntax ($...$, \frac, etc.) for paper/markdown/HTML files
type: feedback
originSessionId: 13b09cd5-9478-446c-b286-6154852a9bee
---
In terminal/chat output, write math with Unicode characters directly (Δt, σ, ², ‖·‖, ∫, ≈, ×, …). Do NOT use LaTeX delimiters like `$\Delta t$` or `\hat{}` — they render as literal source in the terminal.

LaTeX (or KaTeX-flavored markdown) is only for files meant to be rendered: `xk/paper/*.md`, `*.html`, papers, slides.

**Why:** User explicitly corrected this after I wrote `$\hat{\Delta t}$` in a terminal summary — the terminal does not render LaTeX, so symbols come out as raw `$...$` source and look broken. Paper files have a KaTeX renderer (`xk/code/render_md.py`) that DOES render LaTeX, so keep using it there.

**How to apply:**
- Terminal/chat replies: `Δt̂ = −198.43 s`, `σ_Δt ≈ 67 μs`, `J* ≈ 1.74×10⁻¹¹ m²`, `‖p₁ − p₂‖²`
- Paper/markdown/HTML: `$\hat{\Delta t} = -198.43\,\mathrm s$`, `$\sigma_{\Delta t}$`, full `\frac`, `\boxed`, etc.
- Tables in terminal: keep math as Unicode in cells; tables in paper files: keep LaTeX.
