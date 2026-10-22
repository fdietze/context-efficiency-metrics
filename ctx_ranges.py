"""Context-size ranges for --by ctx: parsing the boundaries and labelling the ranges."""
import argparse, re


def tokens(s: str) -> int:
    m = re.fullmatch(r"(\d+)([kKmM]?)", s)
    if not m:
        raise argparse.ArgumentTypeError("use e.g. 50k, 200000, 1m")
    return int(m[1]) * {"": 1, "k": 1000, "m": 1000000}[m[2].lower()]


def ctx_edges(s: str) -> list[int]:
    edges = [tokens(x) for x in s.split(",")]
    if edges != sorted(set(edges)) or edges[0] <= 0:
        raise argparse.ArgumentTypeError("edges must be positive and strictly increasing")
    return edges


def human(n: int) -> str:
    return f"{n // 1000000}m" if n % 1000000 == 0 else f"{n // 1000}k" if n % 1000 == 0 else str(n)


def ctx_label(edges: list[int], i: int) -> str:
    """Bin i is [edges[i-1], edges[i]); the first starts at 0, the last is open-ended."""
    if i == 0:
        return f"<{human(edges[0])}"
    if i == len(edges):
        return f">={human(edges[-1])}"
    return f"{human(edges[i - 1])}-{human(edges[i])}"
