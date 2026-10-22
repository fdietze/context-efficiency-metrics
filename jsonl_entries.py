"""Tolerant reader for Pi session .jsonl files."""
import json, re
from pathlib import Path


def entries(path: Path, bad: list):
    """Yield parsed JSONL entries. A line torn by a failed write (e.g. disk full) is
    lost, but Pi's next entry may be glued to its tail: recover it by retrying from each
    later '{"type":"'. Lines with nothing recoverable are recorded in `bad`."""
    with path.open(errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            try:
                yield json.loads(line)
                continue
            except json.JSONDecodeError:
                pass
            for m in re.finditer(r'\{"type":"', line):
                if m.start() == 0:
                    continue
                try:
                    e = json.loads(line[m.start():])
                except json.JSONDecodeError:
                    continue
                if isinstance(e, dict) and "id" in e:  # skips nested {"type":"text"} blocks
                    yield e
                    break
            else:
                bad.append((path, n))
                continue
            bad.append((path, n))  # the torn head of this line is still lost
