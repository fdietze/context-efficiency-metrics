"""Which session files to read: main sessions picked by the CLI, plus their subagents."""
import argparse, os, re, sys, time
from pathlib import Path

from jsonl_entries import entries

ROOT = Path.home() / ".pi/agent/sessions"


def project_dir(cwd: str) -> Path:
    return ROOT / ("--" + cwd.strip("/").replace("/", "-") + "--")


def duration(s: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)([mhdw])", s)
    if not m:
        raise argparse.ArgumentTypeError("use e.g. 90m, 12h, 3d, 2w")
    return float(m[1]) * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[m[2]]


def select_main(a) -> list[Path]:
    if a.files:
        return [Path(f) for f in a.files]
    if a.last is None and a.since is None:
        env = os.environ.get("PI_SESSION_FILE")
        if not env:
            sys.exit("pass session files, --last N or --since D (or run inside Pi)")
        return [Path(env)]
    dirs = [d for d in ROOT.iterdir() if d.is_dir()] if a.all_projects else [project_dir(a.cwd)]
    files = sorted((f for d in dirs for f in d.glob("*.jsonl")), key=lambda f: f.stat().st_mtime, reverse=True)
    if a.since is not None:
        cutoff = time.time() - a.since
        files = [f for f in files if f.stat().st_mtime >= cutoff]
    return files[: a.last] if a.last is not None else files


def subagent_files(main: Path) -> list[Path]:
    """Actor-subagent sessions live in <session dir>/subagents/<main session id>/*.jsonl."""
    sid = next((e.get("id", "") for e in entries(main, [])), "")
    return sorted((main.parent / "subagents" / sid).glob("*.jsonl")) if sid else []
