"""Render docs/CAPSTONE_REPORT.md into a styled, print-ready HTML page.

Chrome prints the result to PDF (see scripts/print_report_pdf.mjs). No extra
Python dependencies: the small Markdown subset used by the report is handled
here so the build works offline in the project venv. The intermediate HTML is
written to the system temp folder, not into the repository.
"""
from __future__ import annotations

import html
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "CAPSTONE_REPORT.md"
OUTPUT = Path(os.environ.get("REPORT_HTML") or Path(tempfile.gettempdir()) / "autoguard_report.html")

METRICS = [
    ("68.48%", "Exact plate match"),
    ("9.72%", "Character error rate"),
    ("0.81", "Frozen review gate"),
    ("58.18%", "Test coverage"),
    ("92.71%", "Selective accuracy"),
]

CSS = """
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;font-family:"Segoe UI","Inter",system-ui,sans-serif;font-size:10.4pt;line-height:1.62;color:#1f2430;orphans:3;widows:3}
.cover{min-height:9.2in;display:flex;flex-direction:column;padding-top:1.1in;break-after:page}
.cover .brand{display:flex;align-items:center;gap:10px;font-weight:800;letter-spacing:.16em;font-size:9pt;color:#4338ca;text-transform:uppercase}
.cover .mark{width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,#4338ca,#0e7490);display:flex;align-items:center;justify-content:center;color:#fff;font-size:12pt;font-weight:800}
.cover h1{font-size:30pt;line-height:1.12;margin:.75in 0 .18in;color:#151a3d;letter-spacing:-.01em}
.cover .subtitle{font-size:14.5pt;line-height:1.4;font-weight:500;color:#3b3f55;margin:0 0 .5in;max-width:6in}
.cover .kind{font-size:10pt;color:#5b6070;letter-spacing:.06em;text-transform:uppercase;border-top:1px solid #d9dceb;padding-top:.16in;width:3.4in}
.cover .meta{margin-top:auto;padding-bottom:.2in;font-size:9.5pt;color:#5b6070;display:flex;justify-content:space-between;border-bottom:3px solid #4338ca;padding-top:.14in}
.metrics{display:grid;grid-template-columns:repeat(5,1fr);gap:7px;margin:.45in 0 0}
.metrics div{background:#f4f5fb;border:1px solid #e3e6f2;border-radius:9px;padding:9px 10px}
.metrics b{display:block;font-size:12.6pt;color:#1e1b4b;line-height:1.2}
.metrics span{font-size:6.9pt;color:#5b6070;text-transform:uppercase;letter-spacing:.04em;line-height:1.3;display:block;margin-top:2px}
.cover .caption{margin-top:9px;font-size:8.4pt;color:#7a7f93}
main{max-width:100%}
h2{font-size:16pt;color:#1e1b4b;margin:26px 0 10px;padding-bottom:6px;border-bottom:1.5px solid #dfe2f0;break-after:avoid}
h2.first{margin-top:0}
.keep+ul,.keep+ol{break-inside:avoid}
h3{font-size:11.6pt;color:#312e81;margin:18px 0 6px;break-after:avoid}
p{margin:0 0 9px}
strong{color:#151a3d}
code{font-family:"Cascadia Mono","Consolas",monospace;font-size:8.8pt;background:#f1f2f9;border:1px solid #e3e6f2;border-radius:4px;padding:1px 4px;color:#312e81}
blockquote{margin:12px 0;padding:10px 14px;border-left:3px solid #4338ca;background:#f6f7fd;color:#2b2f45}
blockquote p{margin:0}
ul,ol{margin:0 0 10px;padding-left:20px}
li{margin:0 0 4px}
hr{display:none}
table{width:100%;border-collapse:collapse;margin:10px 0 14px;font-size:9.4pt;break-inside:auto}
thead{display:table-header-group}
tr{break-inside:avoid}
th{background:#eef1fb;color:#1e1b4b;text-align:left;font-weight:600;border:1px solid #d9ddec;padding:6px 8px}
td{border:1px solid #dfe2f0;padding:6px 8px;vertical-align:top}
tbody tr:nth-child(even) td{background:#fafbff}
td.r,th.r{text-align:right}
.task{list-style:none;padding-left:0}
.task li{padding-left:20px;position:relative}
.task li:before{content:"";position:absolute;left:0;top:3px;width:10px;height:10px;border:1.4px solid #4338ca;border-radius:3px}
.task li.done:before{background:#4338ca}
.task li.done:after{content:"";position:absolute;left:3px;top:5px;width:5px;height:3px;border-left:1.6px solid #fff;border-bottom:1.6px solid #fff;transform:rotate(-45deg)}
a{color:#4338ca;text-decoration:none}
"""

INLINE = re.compile(r"`([^`]+)`|\*\*([^*]+)\*\*|\*([^*]+)\*|\[([^\]]+)\]\(([^)]+)\)")


def inline(text: str) -> str:
    out, pos = [], 0
    for match in INLINE.finditer(text):
        out.append(html.escape(text[pos:match.start()]))
        code, bold, italic, label, href = match.groups()
        if code is not None:
            out.append(f"<code>{html.escape(code)}</code>")
        elif bold is not None:
            out.append(f"<strong>{html.escape(bold)}</strong>")
        elif italic is not None:
            out.append(f"<em>{html.escape(italic)}</em>")
        else:
            out.append(f'<a href="{html.escape(href)}">{html.escape(label)}</a>')
        pos = match.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    i, first_h2, list_kind = 0, True, None
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if list_kind:
                out.append(f"</{list_kind}>")
                list_kind = None
            i += 1
            continue
        if stripped == "---":
            i += 1
            continue
        heading = re.match(r"^(#{2,3})\s+(.+)$", stripped)
        if heading:
            if list_kind:
                out.append(f"</{list_kind}>")
                list_kind = None
            level = len(heading.group(1))
            title_text = heading.group(2)
            classes = []
            if level == 2 and first_h2:
                classes.append("first")
            if title_text.startswith(("Appendix", "References")):
                classes.append("keep")
            first_h2 = False
            cls = f' class="{" ".join(classes)}"' if classes else ""
            out.append(f"<h{level}{cls}>{inline(title_text)}</h{level}>")
            i += 1
            continue
        if stripped.startswith("|"):
            if list_kind:
                out.append(f"</{list_kind}>")
                list_kind = None
            header = split_row(stripped)
            aligns = split_row(lines[i + 1].strip())
            right = [a.endswith(":") for a in aligns]
            rows = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(split_row(lines[j].strip()))
                j += 1
            head = "".join(
                f'<th class="{ "r" if right[k] else "" }">{inline(cell)}</th>'
                for k, cell in enumerate(header)
            )
            cells = "".join(
                "<tr>" + "".join(
                    f'<td class="{ "r" if right[k] else "" }">{inline(cell)}</td>'
                    for k, cell in enumerate(row)
                ) + "</tr>"
                for row in rows
            )
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{cells}</tbody></table>")
            i = j
            continue
        if stripped.startswith(">"):
            if list_kind:
                out.append(f"</{list_kind}>")
                list_kind = None
            out.append(f"<blockquote><p>{inline(stripped[1:].strip())}</p></blockquote>")
            i += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if bullet or ordered:
            kind = "ul" if bullet else "ol"
            if list_kind != kind:
                if list_kind:
                    out.append(f"</{list_kind}>")
                cls = ""
                if bullet:
                    if re.match(r"^- \[[x ]\]", stripped):
                        cls = ' class="task"'
                out.append(f"<{kind}{cls}>")
                list_kind = kind
            item = (bullet or ordered).group(1)
            if item.startswith("[x] ") or item.startswith("[ ] "):
                done = item.startswith("[x]")
                item = item[4:]
                out.append(f'<li class="{ "done" if done else "" }">{inline(item)}</li>')
            else:
                out.append(f"<li>{inline(item)}</li>")
            i += 1
            continue
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None
        paragraph = [stripped]
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if not nxt or nxt.startswith(("|", ">", "#", "- ", "* ", "---")) or re.match(r"^\d+\. ", nxt):
                break
            paragraph.append(nxt)
            j += 1
        out.append(f"<p>{inline(' '.join(paragraph))}</p>")
        i = j
    if list_kind:
        out.append(f"</{list_kind}>")
    return "\n".join(out)


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = lines[0].lstrip("# ").strip()
    subtitle = lines[2].lstrip("# ").strip()
    body_start = next(i for i, line in enumerate(lines) if line.strip() == "---") + 1
    metrics = "".join(f"<div><b>{value}</b><span>{label}</span></div>" for value, label in METRICS)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)} — Capstone report</title>
<style>{CSS}</style></head><body>
<section class="cover">
  <div class="brand"><span class="mark">A</span>AutoGuard AI · Capstone Project</div>
  <h1>{html.escape(title)}</h1>
  <p class="subtitle">{html.escape(subtitle)}</p>
  <div class="kind">Capstone project report</div>
  <div class="metrics">{metrics}</div>
  <p class="caption">Internal 165-crop held-out split · shipped detector and OCR checkpoints · gate calibrated on validation only.</p>
  <div class="meta"><span>Department project · Computer Science &amp; Engineering</span><span>2026</span></div>
</section>
<main>{render(chr(10).join(lines[body_start:]))}</main>
</body></html>"""
    OUTPUT.write_text(page, encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    sys.exit(main())
