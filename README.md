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
29 main + 42 subagent session files, 14431 calls; effort from message 14425, from history 6, unknown 0
effort  sessions  calls  calls/sess  ctx_p50  ctx_p90  total$    miss$     $/call  total/out$  think/out
medium  16        3566   222.9       111454   269793   222.9327  26.3348   0.0625  10.4        0.388
high    63        10490  166.5       113634   208452   479.2638  149.4992  0.0457  6.8         0.371
xhigh   5         132    26.4        73868    179732   4.5663    1.6367    0.0346  6.4         0.347
max     2         243    121.5       112794   180241   1.4292    1.0289    0.0059  18.5        0.652
TOTAL   71        14431  203.3       112612   223863   708.1920  178.4995  0.0491  7.6         0.377
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
- `think/out`: share of output tokens that were thinking.
- `sessions`: compare groups by this, not by `calls`. Calls in one session are not independent.

`--help` has the exact definitions.
