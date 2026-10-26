"""Context window per model, from Pi's model store (<agent dir>/models-store.json).

Session logs do not record the window, but the reminder limit of the infinite-context
extension depends on it (chart_nudge_limit.py). Fail-open: a missing or unreadable store
yields no windows, and charts leave out what they cannot place.
"""
import json
from pathlib import Path


def model_windows(store: Path) -> dict[str, int]:
    """"provider/model id" -> context window in tokens."""
    try:
        data = json.loads(store.read_text())
    except (OSError, ValueError):
        return {}
    windows = {}
    for provider, entry in data.items() if isinstance(data, dict) else ():
        for m in (entry.get("models") or []) if isinstance(entry, dict) else ():
            if isinstance(m, dict) and isinstance(m.get("contextWindow"), int):
                windows[f"{provider}/{m.get('id')}"] = m["contextWindow"]
    return windows
