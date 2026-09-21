#!/usr/bin/env python3
"""Render ANALYSIS.md / REPORT.md / HOW_TO_READ.md / FedLock notes into docs/."""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

CSS = r"""
:root {
  --bg: #f7f5f0;
  --paper: #ffffff;
  --text: #1a1a1a;
  --muted: #4a5568;
  --accent: #1a365d;
  --border: #d4cfc4;
  --pass: #276749;
  --serif: "Source Serif 4", "Palatino Linotype", Palatino, "Times New Roman", Times, serif;
  --sans: "IBM Plex Sans", "Helvetica Neue", Helvetica, Arial, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--serif);
  background: var(--bg);
  color: var(--text);
  line-height: 1.65;
  font-size: 17px;
}
header {
  background: var(--paper);
  border-bottom: 1px solid var(--border);
  padding: 2rem 1.5rem 1.25rem;
}
header .kicker {
  font-family: var(--sans);
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.5rem;
}
header h1 {
  font-family: var(--serif);
  font-weight: 600;
  font-size: 1.75rem;
  margin: 0 0 0.4rem;
  letter-spacing: -0.02em;
}
header p { margin: 0; color: var(--muted); font-size: 0.95rem; font-family: var(--sans); }
nav {
  display: flex; gap: 1.25rem; flex-wrap: wrap;
  padding: 0.65rem 1.5rem;
  background: var(--paper);
  border-bottom: 1px solid var(--border);
  font-family: var(--sans);
  font-size: 0.88rem;
}
nav a { color: var(--accent); text-decoration: none; }
nav a.active { font-weight: 600; border-bottom: 2px solid var(--accent); }
main {
  max-width: 42rem;
  margin: 0 auto;
  padding: 2rem 1.25rem 3rem;
  background: var(--paper);
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  min-height: 70vh;
}
body.wide main, body.wide footer { max-width: 48rem; }
h1.page { font-size: 1.45rem; margin: 0 0 1rem; font-weight: 600; }
h2 {
  font-size: 1.15rem;
  margin: 2rem 0 0.75rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}
h3 { font-size: 1.02rem; margin: 1.35rem 0 0.5rem; font-weight: 600; }
p { margin: 0.75rem 0; }
.abstract {
  background: #f0ebe3;
  border: 1px solid var(--border);
  padding: 1rem 1.15rem;
  margin: 0 0 1.5rem;
  font-size: 0.98rem;
}
.abstract .label {
  font-family: var(--sans);
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--muted);
  margin: 0 0 0.5rem;
}
.abstract p { margin: 0.55rem 0; }
.abstract p:last-child { margin-bottom: 0; }
table { width: 100%; border-collapse: collapse; font-size: 0.88rem; margin: 1rem 0; font-family: var(--sans); }
th, td { border: 1px solid var(--border); padding: 0.45rem 0.55rem; text-align: left; vertical-align: top; }
th { background: #f0ebe3; font-weight: 600; }
code, pre { font-family: var(--mono); font-size: 0.84rem; }
code { background: #f0ebe3; padding: 0.1em 0.3em; }
pre { background: #f0ebe3; padding: 1rem; overflow: auto; border: 1px solid var(--border); }
pre code { background: none; padding: 0; }
blockquote {
  margin: 1rem 0;
  padding: 0.35rem 1rem;
  border-left: 3px solid var(--accent);
  color: var(--muted);
}
.pass { color: var(--pass); font-weight: 600; font-family: var(--sans); }
ul, ol { padding-left: 1.25rem; }
li { margin: 0.35rem 0; }
footer {
  max-width: 42rem;
  margin: 0 auto;
  padding: 1.25rem;
  color: var(--muted);
  font-size: 0.82rem;
  font-family: var(--sans);
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  background: var(--paper);
}
a { color: var(--accent); }
.meta { font-family: var(--sans); font-size: 0.88rem; color: var(--muted); }
figure { margin: 1.5rem 0 1.75rem; }
figure img {
  width: 100%;
  height: auto;
  border: 1px solid var(--border);
  background: #ffffff;
  display: block;
}
figcaption {
  font-size: 0.88rem;
  color: var(--muted);
  margin: 0.5rem 0 0;
  line-height: 1.5;
}
"""

REPO = "https://github.com/maybern-tripp-smith/fedjev-bench"


PAGE_LINKS = {
    "ANALYSIS.md": "analysis.html",
    "REPORT.md": "report.html",
    "HOW_TO_READ.md": "how-to-read.html",
    "results/fedlock_fidelity.md": "fedlock.html",
    "results/fedlock_replica/FINDINGS.md": "fedlock-replica.html",
    "results/multiaxis/FINDINGS.md": "multiaxis.html",
    "CITATION": "https://github.com/maybern-tripp-smith/fedjev-bench/blob/main/CITATION",
}


def rewrite_href(url: str) -> str:
    if url in PAGE_LINKS:
        return PAGE_LINKS[url]
    if url.startswith("results/") or url.startswith("data/"):
        return f"https://github.com/maybern-tripp-smith/fedjev-bench/blob/main/{url}"
    return url


def rewrite_img_src(src: str) -> str:
    for prefix in (
        "results/multiaxis/figures/",
        "results/figures/",
        "docs/figures/",
    ):
        if src.startswith(prefix):
            return "figures/" + src[len(prefix) :]
    return src


def inline(text: str) -> str:
    """Convert a subset of Markdown inline syntax. Placeholders protect code spans."""
    codes: list[str] = []

    def stash_code(m: re.Match[str]) -> str:
        codes.append(html.escape(m.group(1)))
        return f"\x00C{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash_code, text)

    links: list[tuple[str, str]] = []

    def stash_link(m: re.Match[str]) -> str:
        label, url = m.group(1), rewrite_href(m.group(2))
        links.append((label, url))
        return f"\x00L{len(links) - 1}\x00"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", stash_link, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    text = text.replace("**PASS**", '<span class="pass">PASS</span>')
    text = re.sub(r"> \*\*PASS\*\*", r'> <span class="pass">PASS</span>', text)

    for i, (label, url) in enumerate(links):
        inner = inline_no_link(label)
        href = html.escape(url, quote=True)
        text = text.replace(f"\x00L{i}\x00", f'<a href="{href}">{inner}</a>')
    for i, code in enumerate(codes):
        text = text.replace(f"\x00C{i}\x00", f"<code>{code}</code>")
    text = text.replace("<strong>PASS</strong>", '<span class="pass">PASS</span>')
    return text


def inline_no_link(text: str) -> str:
    codes: list[str] = []

    def stash_code(m: re.Match[str]) -> str:
        codes.append(html.escape(m.group(1)))
        return f"\x00C{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash_code, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    for i, code in enumerate(codes):
        text = text.replace(f"\x00C{i}\x00", f"<code>{code}</code>")
    return text


def parse_table(lines: list[str]) -> str:
    rows = []
    for line in lines:
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cols)
    header, body = rows[0], rows[2:]
    out = ["<table><thead><tr>"]
    out.extend(f"<th>{inline(c)}</th>" for c in header)
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        out.extend(f"<td>{inline(c)}</td>" for c in row)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def md_to_html(
    md: str,
    *,
    drop_h1: bool = True,
    abstract_box: bool = False,
    box_headings: set[str] | None = None,
) -> str:
    boxes = set(box_headings or [])
    if abstract_box:
        boxes.add("Abstract")
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_abstract = False
    n = len(lines)
    skipped_h1 = False

    while i < n:
        line = lines[i]
        if line.strip() == "---":
            i += 1
            continue
        if line.startswith("```"):
            fence = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                fence.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(fence)) + "</code></pre>")
            continue
        if line.startswith("|") and i + 1 < n and re.match(r"^\|?\s*-+", lines[i + 1]):
            table_lines = [line]
            i += 1
            while i < n and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            out.append(parse_table(table_lines))
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if level == 1 and drop_h1 and not skipped_h1:
                skipped_h1 = True
                i += 1
                continue
            if title in boxes:
                if in_abstract:
                    out.append("</div>")
                    in_abstract = False
                out.append('<div class="abstract">')
                out.append(f'<p class="label">{inline(title)}</p>')
                in_abstract = True
                i += 1
                continue
            if in_abstract:
                out.append("</div>")
                in_abstract = False
            tag = f"h{level}"
            out.append(f"<{tag}>{inline(title)}</{tag}>")
            i += 1
            continue
        img = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", line)
        if img:
            alt, src = img.group(1), rewrite_img_src(img.group(2))
            cap = None
            j = i + 1
            if j < n and not lines[j].strip():
                j += 1
            if j < n and re.match(r"^\*.+\*\s*$", lines[j].strip()):
                cap = lines[j].strip()[1:-1].strip()
                i = j + 1
            else:
                i += 1
            block = ['<figure>']
            block.append(
                f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}">'
            )
            if cap:
                block.append(f"<figcaption>{inline(cap)}</figcaption>")
            block.append("</figure>")
            out.append("\n".join(block))
            continue
        if line.startswith("> "):
            quote = [line[2:]]
            i += 1
            while i < n and lines[i].startswith("> "):
                quote.append(lines[i][2:])
                i += 1
            out.append("<blockquote>" + inline(" ".join(quote)) + "</blockquote>")
            continue
        if re.match(r"^[-*]\s+", line):
            items = []
            while i < n and re.match(r"^[-*]\s+", lines[i]):
                items.append("<li>" + inline(re.sub(r"^[-*]\s+", "", lines[i])) + "</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i]):
                items.append("<li>" + inline(re.sub(r"^\d+\.\s+", "", lines[i])) + "</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue
        if not line.strip():
            i += 1
            continue
        para = [line]
        i += 1
        while i < n and lines[i].strip() and not re.match(r"^(#{1,3}\s+|```|\||---$|[-*]\s+|\d+\.\s+|> )", lines[i]):
            para.append(lines[i])
            i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")
        if in_abstract and i < n and re.match(r"^#{1,3}\s+", lines[i] if i < n else ""):
            out.append("</div>")
            in_abstract = False
    if in_abstract:
        out.append("</div>")
    return "\n".join(out)


def page(
    title: str,
    active: str,
    body: str,
    *,
    heading: str | None = None,
    wide: bool = False,
) -> str:
    nav = []
    for href, label, key in (
        ("index.html", "Overview", "index"),
        ("how-to-read.html", "How to read", "howto"),
        ("analysis.html", "Analysis", "analysis"),
        ("report.html", "Report", "report"),
        ("fedlock.html", "FedLock (Gate 7)", "fedlock"),
        ("fedlock-replica.html", "TrueSkill replica", "replica"),
        ("multiaxis.html", "Multi-axis", "multiaxis"),
    ):
        cls = ' class="active"' if key == active else ""
        nav.append(f'<a href="{href}"{cls}>{label}</a>')
    nav.append(f'<a href="{REPO}">GitHub</a>')
    h = f"<h1 class=\"page\">{html.escape(heading)}</h1>\n" if heading else ""
    body_cls = ' class="wide"' if wide else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Pre-registered evaluation of TypeSafe/Jev on FOMC chair openings (fedjev-2026-09-20).">
<meta http-equiv="Cache-Control" content="no-cache">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
{CSS}
</style>
</head>
<body{body_cls}>
<header>
<p class="kicker">Technical report · run fedjev-2026-09-20</p>
<h1>fedjev-bench</h1>
<p>Pairwise textual hawkishness scores for FOMC chair openings, evaluated against same-day funds-rate changes</p>
</header>
<nav>
{" ".join(nav)}
</nav>
<main>
{h}{body}
</main>
<footer>
Research instrumentation only. Not investment advice. No Federal Reserve endorsement implied. Companion repository:
<a href="{REPO}">maybern-tripp-smith/fedjev-bench</a>.

</footer>
</body>
</html>
"""


def index_body() -> str:
    return """
<div class="abstract">
<p class="label">Abstract</p>
<p>Same-day changes in the federal funds target are a convenient but incomplete label for the hawkishness of Federal Open Market Committee (FOMC) communication. Policy actions and textual stance often co-move on scheduled action days. They need not coincide when the Committee leaves the target unchanged.</p>
<p>This note reports a pre-registered evaluation of TypeSafe/Jev on chair press-conference openings under the fixed pairwise criterion <code>more hawkish about inflation</code>. Primary quantities include standard errors (s.e.) and bootstrap percentile confidence intervals. Gate 4 is a construct-validity result: same-day funds-rate changes are an incomplete label for textual hawkishness when the target is unchanged. Gate 7 is Spearman’s rank correlation with <a href="fedlock.html">FedLock</a> — an independent published text-scoring project — using that project’s published press-conference scores (raw TrueSkill mean <code>m</code>; era-adjusted <code>ma</code> as a sensitivity). Gate 7 reads those scores; it does not re-run FedLock’s tournament. A separate <a href="fedlock-replica.html">TrueSkill replica</a> on the 95 openings is a different claim.</p>
</div>

<h2>Measurement</h2>
<p>Two constructs are distinguished throughout. The behavioral measure is the same-day change in the funds target (<code>d_same</code> — hike, hold, or cut; identically zero on holds). The textual measure is the stance in the Chair’s opening remarks, recovered by dual-order Choice and Bradley–Terry aggregation (a pairwise strength model on a fixed gold-pair graph), with a secondary Score pass. FedLock’s published scores are a second text measure, not a behavioral label.</p>
<p>Gates 1, 3, 4, and 6 are pre-registered pass/fail tests. Gates 2, 5, and 7 are report-only or secondary. Gate 7 is not a TrueSkill replication. The exercise does not identify a causal effect of communication on rates. A <a href="how-to-read.html">plain-language scoreboard guide</a> explains what each gate answers and how to read inversion rates, rank correlations, Score gaps, and cost.</p>

<h2>Selected estimates</h2>
<table>
<thead><tr><th>Gate</th><th>Estimate</th></tr></thead>
<tbody>
<tr><td>1 Easy-pair inversion</td><td><span class="pass">PASS</span> — 0.000 (n=40, STE=0.000)</td></tr>
<tr><td>3 Action-day Spearman (BT vs <code>d_same</code>)</td><td><span class="pass">PASS</span> — +0.851 (n=24, STE=0.074)</td></tr>
<tr><td>4 Holds − cuts (BT mean gap)</td><td><span class="pass">PASS</span> — +0.519 (STE=0.368)</td></tr>
<tr><td>6 Name/order stability</td><td><span class="pass">PASS</span> — Δ inversion = 0.000</td></tr>
<tr><td>7 FedLock consistency (<code>score_jev</code> vs published raw <code>m</code>; not a TrueSkill replication)</td><td>report — Spearman +0.944 (n=90, s.e.=0.016)</td></tr>
</tbody>
</table>

<h2>Selected figures</h2>
<figure>
<img src="figures/score_vs_d_same.svg" alt="Text scores versus same-day target change">
<figcaption>Figure 6. BT (n=46) and <code>score_jev</code> (n=93) against <code>d_same</code>. Holds stack at zero. Spearman ρ and bootstrap STE are the Gate 3 all-scheduled estimates.</figcaption>
</figure>
<figure>
<img src="figures/gate4_means.svg" alt="Mean scores for holds, cuts, and hikes">
<figcaption>Figure 8. Mean text scores by same-day action, ± STE. Holds sit above cuts on both the BT and Score axes.</figcaption>
</figure>

<h2>Documents</h2>
<ul>
<li><a href="how-to-read.html">How to read the results</a> — scoreboard guide (not a second analysis)</li>
<li><a href="analysis.html">Analysis</a> — methods, results, figures, limitations</li>
<li><a href="report.html">Report</a> — gate tables, cost, and artifacts</li>
<li><a href="fedlock.html">FedLock (Gate 7)</a> — published-score agreement; how to rebuild the match</li>
<li><a href="fedlock-replica.html">TrueSkill replica</a> — separate FedLock-faithful tournament on 95 openings</li>
<li><a href="multiaxis.html">Multi-axis</a> — seven frozen criteria on the same 95 openings (text-only and macro-conditional)</li>
<li>Machine-readable: <code>results/gates.json</code>, <code>results/interpretation.json</code>, <code>results/fedlock_replica/agreement.json</code>, <code>results/multiaxis/gates.json</code></li>
</ul>
"""


def main() -> None:
    analysis_md = (ROOT / "ANALYSIS.md").read_text()
    report_md = (ROOT / "REPORT.md").read_text()
    howto_md = (ROOT / "HOW_TO_READ.md").read_text()
    fidelity_md = (ROOT / "results/fedlock_fidelity.md").read_text()
    replica_md = (ROOT / "results/fedlock_replica/FINDINGS.md").read_text()
    multiaxis_path = ROOT / "results/multiaxis/FINDINGS.md"
    multiaxis_md = multiaxis_path.read_text() if multiaxis_path.exists() else "# Multi-axis\n\n_Pending run._\n"
    analysis_html = md_to_html(analysis_md, drop_h1=True, abstract_box=True)
    report_html = md_to_html(report_md, drop_h1=True, abstract_box=True)
    howto_html = md_to_html(
        howto_md,
        drop_h1=True,
        box_headings={"If you only look at three numbers"},
    )
    fidelity_html = md_to_html(fidelity_md, drop_h1=True, abstract_box=False)
    replica_html = md_to_html(replica_md, drop_h1=True, abstract_box=False)
    multiaxis_html = md_to_html(multiaxis_md, drop_h1=True, abstract_box=True)

    (DOCS / "index.html").write_text(
        page("fedjev-bench — Overview", "index", index_body().strip())
    )
    (DOCS / "how-to-read.html").write_text(
        page(
            "fedjev-bench — How to read the results",
            "howto",
            howto_html,
            heading="How to read the results",
        )
    )
    (DOCS / "analysis.html").write_text(
        page(
            "fedjev-bench — Analysis",
            "analysis",
            analysis_html,
            heading="Analysis",
        )
    )
    (DOCS / "report.html").write_text(
        page(
            "fedjev-bench — Report",
            "report",
            report_html,
            heading="Report",
        )
    )
    (DOCS / "fedlock.html").write_text(
        page(
            "fedjev-bench — FedLock Gate 7",
            "fedlock",
            fidelity_html,
            heading="FedLock (Gate 7)",
        )
    )
    (DOCS / "fedlock-replica.html").write_text(
        page(
            "fedjev-bench — FedLock TrueSkill replica",
            "replica",
            replica_html,
            heading="FedLock-faithful TrueSkill replica",
        )
    )
    (DOCS / "multiaxis.html").write_text(
        page(
            "fedjev-bench — Seven criteria on chair openings",
            "multiaxis",
            multiaxis_html,
            heading="Seven criteria on chair openings",
            wide=True,
        )
    )
    print(
        "wrote docs/index.html docs/how-to-read.html docs/analysis.html "
        "docs/report.html docs/fedlock.html docs/fedlock-replica.html docs/multiaxis.html"
    )


if __name__ == "__main__":
    main()
