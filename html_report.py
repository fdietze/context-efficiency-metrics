"""One HTML file with the per-chart aggregates embedded as Vega-Lite specs.

The page loads Vega from a CDN at pinned versions with Subresource Integrity hashes, so
the browser refuses any changed script. Only aggregates are embedded, never prompts,
paths or per-call records (smaller file, nothing sensitive to leak when shared).
"""
import html, json
from datetime import datetime

from calls import Call
from chart_ctx_spend import ctx_spend_data, ctx_spend_spec
from chart_daily_spend import daily_spend_data, daily_spend_spec
from chart_forest import forest_data, forest_spec
from chart_miss_vs_gap import miss_vs_gap_data, miss_vs_gap_spec

SCRIPTS = (
    ("https://cdn.jsdelivr.net/npm/vega@6.4.0/build/vega.min.js",
     "sha384-VKdcJr3ZaBIJMbVcopTAI/JEuUkSY6qnwVu9iLuw0DnQ9gQ1JjsfZJhXFQAgNi43"),
    ("https://cdn.jsdelivr.net/npm/vega-lite@6.5.0/build/vega-lite.min.js",
     "sha384-pV2l7nzmyxZh02knvUH7N8zvtyCYsYiGt+SsE/emG/dFiBI6G0YJZFZ2FzEX72P3"),
    ("https://cdn.jsdelivr.net/npm/vega-embed@7.3.0/build/vega-embed.min.js",
     "sha384-Muy1QRxYFeNrA1zShc1KtN4OfipkR/61gt+HWqN57c1Zxu3Oe16TsilsruVVjfKL"),
)


def _json(spec: dict) -> str:
    # "</" inside a <script> block would end it early; JSON allows escaping the slash.
    return json.dumps(spec, separators=(",", ":")).replace("</", "<\\/")


def render_html(calls: list[Call], table: str, cutoff: float | None) -> str:
    specs = [
        daily_spend_spec(daily_spend_data(calls, cutoff)),
        forest_spec(forest_data(calls)),
        miss_vs_gap_spec(miss_vs_gap_data(calls)),
        ctx_spend_spec(ctx_spend_data(calls)),
    ]
    scripts = "\n".join(f'<script src="{u}" integrity="{h}" crossorigin="anonymous"></script>'
                        for u, h in SCRIPTS)
    divs = "\n".join(f'<div id="chart{i}" class="chart"></div>' for i in range(len(specs)))
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>context-efficiency-metrics</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2em; color: #222; }}
.chart {{ margin: 2em 0; }}
pre {{ font-size: 12px; overflow-x: auto; }}
#fallback {{ color: #b00; }}
</style>
{scripts}
</head><body>
<h1>context-efficiency-metrics</h1>
<p>Created {created}. API-equivalent cost of Pi sessions.</p>
<p id="fallback">Charts need the pinned Vega scripts from cdn.jsdelivr.net. If you read this, they did not load.</p>
{divs}
<h2>Table</h2>
<pre>{html.escape(table)}</pre>
<script>
const specs = [{",".join(_json(s) for s in specs)}];
if (window.vegaEmbed) {{
  document.getElementById("fallback").remove();
  specs.forEach((s, i) => vegaEmbed("#chart" + i, {{"$schema": "https://vega.github.io/schema/vega-lite/v6.json", ...s}}, {{actions: false}}));
}}
</script>
</body></html>
"""
