"""p50 / p95 per stage from JSONL traces.

    python -m setu.eval.latency_report [trace_dir_or_file ...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from ..config import get_settings
from ..tracing import _pct


def load(paths: list[Path]) -> dict[str, list[float]]:
    stages: dict[str, list[float]] = defaultdict(list)
    for p in paths:
        files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                if rec.get("kind") == "latency":
                    stages[rec["stage"]].append(float(rec["ms"]))
    return stages


def main(argv: list[str]) -> None:
    paths = [Path(a) for a in argv] or [get_settings().trace_dir]
    stages = load(paths)
    if not stages:
        print("not measured yet")
        return
    print(f"{'stage':<26}{'n':>6}{'p50 ms':>10}{'p95 ms':>10}")
    for stage, vals in sorted(stages.items()):
        vals.sort()
        print(f"{stage:<26}{len(vals):>6}{_pct(vals, 50):>10.1f}{_pct(vals, 95):>10.1f}")


if __name__ == "__main__":
    main(sys.argv[1:])
