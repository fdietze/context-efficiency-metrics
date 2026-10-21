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
33 main + 74 subagent session files, 16673 calls; effort from message 16667, from history 6, unknown 0
effort  calls  ctx_p50  ctx_p90  ctx_max  total$    $/call
medium  4033   110431   255326   401259   227.0410  0.0563
high    11780  110264   202044   777470   486.8957  0.0413
xhigh   497    83586    183525   228405   15.9987   0.0322
max     363    110741   180241   213238   1.7643    0.0049
TOTAL   16673  109531   208452   777470   731.6997  0.0439
```

Context is what the model read in one call: input + cache read + cache write tokens.
`ctx_p50`, `ctx_p90` and `ctx_max` are the median, the 90th percentile and the maximum over all calls.
Effort comes from the call itself, otherwise from the last thinking level change on its branch,
otherwise it is `unknown`.
