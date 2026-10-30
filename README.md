# context-efficiency-metrics

Shows what your [Pi](https://github.com/badlogic/pi-mono) sessions would cost at API prices.
It reads the session logs in `~/.pi/agent/sessions` and groups the cost by model, thinking effort
and context size, and can write an HTML report with charts. Plain Python, no dependencies.

## Run with nix

```sh
nix run github:fdietze/context-efficiency-metrics -- --since 7d --all-projects
```

Pick the sessions with `--last N`, `--since 3d` or session files. Group with `--by`, for example
`--by kind,model,effort` (default), `--by ctx` or `--by model,effort,ctx`.
Set the context ranges with `--ctx-edges 50k,100k,200k`. `--wide` shows all columns. `--help` shows the rest.

`--html report.html` also writes a report: daily spend and overhead (cache misses, cache
warming, context folding), cost and thinking per effort level, cache-miss probability versus
pause length, spend by context size, the payoff of a fold against the share of context it
freed (the dollars it saves later per dollar it costs), and the reminder-limit experiment of
[pi-infinite-context](https://github.com/fdietze/pi-infinite-context) (`nudgeAtTokens` as a range: cost
per prompt against the randomly assigned limit, with the cheapest limit and its uncertainty;
context windows come from Pi's `models-store.json`). Each chart says how to read it. The file embeds only aggregates (no prompts or paths) and loads Vega from a CDN at
pinned, hash-checked versions.

## Install as flake input

```nix
{
  inputs.context-efficiency-metrics.url = "github:fdietze/context-efficiency-metrics";

  # then add it to your packages, e.g. in a NixOS config:
  # environment.systemPackages = [ inputs.context-efficiency-metrics.packages.${system}.default ];
}
```

## Example output

`context-efficiency-metrics --since 7d --all-projects --by effort`:

```
55 main + 75 subagent session files, 17956 calls; effort from message 16729, from history 995, unknown 232
effort   total$    miss%  fold%  total$/Mvis  ctx_p50  think/out  sessions  calls
low      2.1820    0.0    0.0    47.39        26827    0.077      16        180
medium   44.1576   40.2   3.5    129.74       83820    0.354      11        990
high     799.4247  37.8   9.3    160.72       98156    0.402      101       14626
xhigh    5.6379    30.8   45.5   132.31       103500   0.548      2         84
max      133.2639  16.8   24.3   155.74       114550   0.650      6         1844
unknown  5.4173    0.0    0.0    23350.24     125538   0.000      6         232
TOTAL    990.0834  34.7   11.2   158.19       99120    0.453      130       17956
```

- `miss%`: share of `total$` spent on cache misses: context that was already cached, but had
  to be processed again, e.g. because the cache expired during a pause. This is the best number
  to optimize: it is pure waste, so lowering it never makes the real work worse. Watch `total$`
  too, so cost does not just move to another column. Pi's `cacheWarming` and
  `PI_CACHE_RETENTION=long` lower it.
- `fold%`: share of `total$` spent on context folding (the infinite-context extension): turns
  that call `context_fold`, `context_map`, `context_search` or `context_peek`, plus the cache
  miss each fold causes (that miss is in `miss%` too). Only the cost side: the savings of
  smaller later contexts are not measured.
- `total$/Mvis`: dollars per million visible output tokens (output without thinking).
- `ctx_p50`: median context: what the model read in one call (input + cache read + cache write).
- `think/out`: share of output tokens that were thinking.
- `sessions`: compare groups by this, not by `calls`. Calls in one session are not independent.
- `kind`: `assistant` (model turns), `cache_warm` (Pi's keep-alive pings during pauses) or `side`
  (tool summaries, compaction). Kept apart so cheap pings do not distort the real turns.
- `effort`: comes from the call itself, otherwise from the last thinking level change on its branch,
  otherwise it is `unknown`.

`--help` has the exact definitions.
