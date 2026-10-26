# Map

- `context-efficiency-metrics`: CLI entry (argparse only); the docstring holds the metric definitions shown by `--help`.
- `session_selection.py` -> `jsonl_entries.py` -> `calls.py`: pick session files, read them, parse them into `Call` records. Everything downstream uses only `Call`.
- `table.py`: terminal table. `html_report.py`: `--html`, one `chart_*.py` per chart (data function, Vega-Lite spec, `HELP` text).
- `model_windows.py`: context window per model from Pi's `models-store.json`, read by the CLI for `chart_nudge_limit.py`.
- `bayesian_bootstrap.py`: intervals; the resampling unit is the session tree (main session + its subagents).
- Tests: `test_*.py` (`python3 -B -m unittest`); `nix flake check` runs them. `test_support.py` builds `Call`s.
