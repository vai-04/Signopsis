"""Export Pydantic contracts as JSON Schema for the web app.

Writes app/web/src/types/contracts.schema.json. When the React app is set up
(later layer) `pnpm dlx json-schema-to-typescript` turns it into contracts.ts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic.json_schema import models_json_schema  # noqa: E402

from setu.schemas import PerceptEvent, RenderPlan, SemanticFrame  # noqa: E402
from setu.schemas import ws  # noqa: E402

MODELS = [PerceptEvent, SemanticFrame, RenderPlan] + [
    getattr(ws, n) for n in dir(ws)
    if isinstance(getattr(ws, n), type) and getattr(getattr(ws, n), "__module__", "") == ws.__name__
    and hasattr(getattr(ws, n), "model_fields")
]


def main() -> None:
    _, schema = models_json_schema([(m, "serialization") for m in MODELS], title="SETU contracts")
    out = ROOT / "app/web/src/types/contracts.schema.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} ({len(schema.get('$defs', {}))} definitions)")


if __name__ == "__main__":
    main()
