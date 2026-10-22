# context-efficiency-metrics

Shows what your [Pi](https://github.com/badlogic/pi-mono) sessions would cost at API prices.
It reads the session logs in `~/.pi/agent/sessions` and groups the cost by model, thinking effort
and context size. It is one Python script without dependencies.

## Run with nix

```sh
nix run github:fdietze/context-efficiency-metrics -- --since 7d --all-projects
```

Pick the sessions with `--last N`, `--since 3d` or session files. Group with `--by`, for example
`--by model,effort` (default), `--by ctx` or `--by model,effort,ctx`.
Set the context ranges with `--ctx-edges 50k,100k,200k`. `--help` shows the rest.

## Install as flake input

```nix
{
  inputs.context-efficiency-metrics.url = "github:fdietze/context-efficiency-metrics";

  # then add it to your packages, e.g. in a NixOS config:
  # environment.systemPackages = [ inputs.context-efficiency-metrics.packages.${system}.default ];
}
```

## Example output

`context-efficiency-metrics --since 7d --all-projects --by effort` (shortened, there are more columns for cost parts and tokens):

```
27 main + 45 subagent session files, 15152 calls; effort from message 15130, from history 22, unknown 0
effort  sessions  calls  calls/sess  ctx_p50  ctx_p90  total$    miss$     miss%  $/call  total/out$  think/out  total$/Mvis
medium  16        3597   224.8       111200   269014   220.6096  24.5853   11.1   0.0613  10.2        0.389      238.61
high    58        10117  174.4       113097   210961   457.8480  156.5434  34.2   0.0453  6.6         0.375      124.62
xhigh   5         132    26.4        73868    179732   4.5663    1.6367    35.8   0.0346  6.4         0.347      98.66
max     8         1306   163.2       103688   149233   77.2697   11.3714   14.7   0.0592  2.6         0.659      142.24
TOTAL   72        15152  210.4       111379   216489   760.2935  194.1367  25.5   0.0502  6.3         0.427      146.57
```

- `ctx`: what the model read in one call: input + cache read + cache write tokens.
  `ctx_p50`, `ctx_p90`, `ctx_max` are median, 90th percentile and maximum.
- `effort`: comes from the call itself, otherwise from the last thinking level change on its branch,
  otherwise it is `unknown`.
- `total/out$`: dollars spent per dollar of written output. 10 means 90% of the money went into
  reading context. Lower is better.
- `miss$`: money spent on cache misses: context that was already cached, but had to be
  processed again, e.g. because the cache expired during a pause. Turn on Pi's `cacheWarming`
  or `PI_CACHE_RETENTION=long` to lower it.
- `miss%`: `miss$` as share of `total$`. This is the best number to optimize: it is pure waste,
  so lowering it never makes the real work worse. Watch `total$` too, so cost does not just move
  to another column.
- `think/out`: share of output tokens that were thinking.
- `total$/Mvis`: dollars per million visible output tokens (output without thinking).
  More thinking makes `total$/Mout` look better while you pay more; this one does not.
- `sessions`: compare groups by this, not by `calls`. Calls in one session are not independent.

`--help` has the exact definitions.
