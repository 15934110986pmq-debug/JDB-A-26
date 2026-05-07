"""把 markdown 文件渲染为独立 HTML（含 KaTeX 公式渲染）。

用法:
    python render_md.py xk/paper/Q1.md
输出: 同目录下同名 .html
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<link rel="stylesheet"
      href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer
        src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body, {{
            delimiters: [
                {{left: '$$', right: '$$', display: true}},
                {{left: '$',  right: '$',  display: false}}
            ],
            throwOnError: false
        }});"></script>
<style>
body {{
  max-width: 880px; margin: 30px auto; padding: 0 24px;
  font-family: 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei',
               -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 16px; line-height: 1.75; color: #222;
}}
h1, h2, h3, h4 {{ color: #1a3a6e; margin-top: 1.6em; }}
h1 {{ border-bottom: 2px solid #1a3a6e; padding-bottom: .3em; }}
h2 {{ border-bottom: 1px solid #ccc; padding-bottom: .2em; }}
code {{
  background: #f4f6f8; padding: 2px 6px; border-radius: 3px;
  font-family: 'JetBrains Mono', Consolas, monospace; font-size: 0.92em;
}}
pre {{
  background: #f6f8fa; padding: 14px 16px; overflow-x: auto;
  border-radius: 6px; border: 1px solid #e1e4e8;
}}
pre code {{ background: transparent; padding: 0; }}
table {{
  border-collapse: collapse; margin: 1em 0; min-width: 60%;
}}
table th, table td {{
  border: 1px solid #d0d7de; padding: 8px 12px; text-align: left;
}}
table th {{ background: #f6f8fa; font-weight: 600; }}
blockquote {{
  border-left: 4px solid #1a3a6e; padding: 4px 16px;
  background: #eef3fb; color: #335; margin: 1em 0;
}}
.katex-display {{ margin: 1em 0; }}
hr {{ border: none; border-top: 1px solid #ddd; margin: 2em 0; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render(md_path: Path) -> Path:
    text = md_path.read_text(encoding="utf-8")
    # 提取首个 # 标题作为 title
    m = re.search(r"^#\s+(.+)$", text, flags=re.M)
    title = m.group(1) if m else md_path.stem
    md = markdown.Markdown(extensions=["extra", "tables", "fenced_code", "toc"])
    body = md.convert(text)
    html = HTML_TEMPLATE.format(title=title, body=body)
    out = md_path.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python render_md.py path/to/file.md [more.md ...]")
        sys.exit(1)
    for p in sys.argv[1:]:
        out = render(Path(p))
        print(f"OK -> {out}")
