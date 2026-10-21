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
29 main + 41 subagent session files, 14261 calls; effort from message 14255, from history 6, unknown 0
effort  sessions  calls  calls/sess  ctx_p50  ctx_p90  total$    $/call  total/out$  think/out
medium  15        3523   234.9       112196   271058   221.8163  0.0630  10.5        0.388
high    63        10363  164.5       114026   209131   472.1766  0.0456  6.8         0.370
xhigh   5         132    26.4        73868    179732   4.5663    0.0346  6.4         0.347
max     2         243    121.5       112794   180241   1.4292    0.0059  18.5        0.652
TOTAL   70        14261  203.7       113117   225343   699.9884  0.0491  7.7         0.377
```

- `ctx`: what the model read in one call: input + cache read + cache write tokens.
  `ctx_p50`, `ctx_p90`, `ctx_max` are median, 90th percentile and maximum.
- `effort`: comes from the call itself, otherwise from the last thinking level change on its branch,
  otherwise it is `unknown`.
- `total/out$`: dollars spent per dollar of written output. 10 means 90% of the money went into
  reading context. Lower is better.
- `think/out`: share of output tokens that were thinking.
- `sessions`: compare groups by this, not by `calls`. Calls in one session are not independent.

`--help` has the exact definitions.
