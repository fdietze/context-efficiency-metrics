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
Set the context ranges with `--ctx-edges 50k,100k,200k`. `--wide` shows all columns. `--help` shows the rest.

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
27 main + 45 subagent session files, 15163 calls; effort from message 15141, from history 22, unknown 0
effort  total$    miss%  total$/Mvis  ctx_p50  think/out  sessions  calls
medium  220.6096  11.1   238.61       111200   0.389      16        3597
high    458.1421  34.2   124.56       113049   0.374      58        10123
xhigh   4.5663    35.8   98.66        73868    0.347      5         132
max     77.8796   14.6   143.15       103749   0.662      8         1311
TOTAL   761.1975  25.5   146.61       111378   0.428      72        15163
```

- `miss%`: share of `total$` spent on cache misses: context that was already cached, but had
  to be processed again, e.g. because the cache expired during a pause. This is the best number
  to optimize: it is pure waste, so lowering it never makes the real work worse. Watch `total$`
  too, so cost does not just move to another column. Pi's `cacheWarming` and
  `PI_CACHE_RETENTION=long` lower it.
- `total$/Mvis`: dollars per million visible output tokens (output without thinking).
- `ctx_p50`: median context: what the model read in one call (input + cache read + cache write).
- `think/out`: share of output tokens that were thinking.
- `sessions`: compare groups by this, not by `calls`. Calls in one session are not independent.
- `effort`: comes from the call itself, otherwise from the last thinking level change on its branch,
  otherwise it is `unknown`.

`--help` has the exact definitions.
