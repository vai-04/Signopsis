"""Per-user memory: taught sign prototypes + jargon (resolved ambiguities).

Default backend is local files (works offline, no services):
    data/users/<user>/prototypes.npz   taught samples (K x D each)
    data/users/<user>/prototypes.json  labels, durations, created time
    data/users/<user>/jargon.json      repair choices, keyed by context

Set SIGNOPSIS_QDRANT_URL (or SIGNOPSIS_QDRANT=":memory:") to also mirror prototypes
into Qdrant for fast shortlisting at scale; DTW re-ranking stays local.
Everything is scoped per user: one person's name sign never leaks into
another person's recognizer.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

from signopsis.perceive.recognizer import Proto

DATA_ROOT = Path(os.getenv("SIGNOPSIS_DATA", Path(__file__).resolve().parents[2] / "data"))
_SAFE = re.compile(r"[^a-zA-Z0-9_.-]")


def safe_user(user: str) -> str:
    u = _SAFE.sub("_", user or "default")[:64]
    return u or "default"


class MemoryStore:
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else DATA_ROOT
        self._lock = threading.Lock()
        self._qdrant = _maybe_qdrant()

    def _dir(self, user: str) -> Path:
        d = self.root / "users" / safe_user(user)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ------------------------------------------------------------ prototypes
    def load_prototypes(self, user: str) -> list[Proto]:
        d = self._dir(user)
        meta_p, arr_p = d / "prototypes.json", d / "prototypes.npz"
        if not meta_p.exists() or not arr_p.exists():
            return []
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        arrs = np.load(arr_p)
        out = []
        for i, m in enumerate(meta):
            key = f"p{i}"
            if key in arrs:
                out.append(Proto(m["label"], m.get("kind", "sign"), arrs[key], float(m["dur_ms"]), owner=user))
        return out

    def _save(self, user: str, protos: list[Proto], meta_extra: list[dict]):
        d = self._dir(user)
        np.savez_compressed(d / "prototypes.npz", **{f"p{i}": p.T for i, p in enumerate(protos)})
        meta = [{"label": p.label, "kind": p.kind, "dur_ms": p.dur_ms, **e} for p, e in zip(protos, meta_extra)]
        (d / "prototypes.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")

    def _meta(self, user: str) -> list[dict]:
        p = self._dir(user) / "prototypes.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def add_sign(self, user: str, label: str, samples: list[np.ndarray], durs: list[float],
                 display: Optional[str] = None, extra: Optional[dict] = None) -> int:
        """Store the taught samples plus their mean. Returns how many prototypes now carry this label."""
        with self._lock:
            protos = self.load_prototypes(user)
            meta = self._meta(user)
            now = time.time()
            mean = np.mean(np.stack(samples), axis=0)
            new = [(s, d) for s, d in zip(samples, durs)] + [(mean, float(np.mean(durs)))]
            for T, d in new:
                protos.append(Proto(label, "sign", T, d, owner=user))
                meta.append({"created": now, "display": display or label, **(extra or {})})
            self._save(user, protos, meta[: len(protos)])
            if self._qdrant:
                self._qdrant.upsert(user, label, [T for T, _ in new])
            return sum(1 for p in protos if p.label == label)

    def delete_sign(self, user: str, label: str) -> int:
        with self._lock:
            protos = self.load_prototypes(user)
            meta = self._meta(user)
            keep = [(p, m) for p, m in zip(protos, meta) if p.label != label]
            self._save(user, [p for p, _ in keep], [m for _, m in keep])
            if self._qdrant:
                self._qdrant.delete(user, label)
            return len(protos) - len(keep)

    def list_signs(self, user: str) -> list[dict]:
        meta = self._meta(user)
        out: dict[str, dict] = {}
        for m in meta:
            e = out.setdefault(m["label"], {"label": m["label"], "display": m.get("display", m["label"]),
                                           "samples": 0, "created": m.get("created"),
                                           "kind": m.get("kind", "name"), "scope": m.get("scope", "me")})
            e["samples"] += 1
        for e in out.values():
            e["samples"] = max(0, e["samples"] - 1)   # don't count the stored mean
        return sorted(out.values(), key=lambda e: e["label"])

    # ------------------------------------------------------------ jargon
    def _jargon(self, user: str) -> dict:
        p = self._dir(user) / "jargon.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"ctx": {}, "any": {}}

    @staticmethod
    def _keys(cands: list[str], left: Optional[str], right: Optional[str]) -> tuple[str, str]:
        c = "|".join(sorted(cands[:2]))
        return f"{c}@{left or '^'}_{right or '$'}", c

    def record_choice(self, user: str, cands: list[str], chosen: str,
                      left: Optional[str], right: Optional[str]):
        with self._lock:
            j = self._jargon(user)
            k_ctx, k_any = self._keys(cands, left, right)
            j["ctx"].setdefault(k_ctx, {})
            j["ctx"][k_ctx][chosen] = j["ctx"][k_ctx].get(chosen, 0) + 1
            j["any"].setdefault(k_any, {})
            j["any"][k_any][chosen] = j["any"][k_any].get(chosen, 0) + 1
            (self._dir(user) / "jargon.json").write_text(json.dumps(j, indent=1), encoding="utf-8")

    def jargon_bonus(self, user: str, cands: list[str], left: Optional[str], right: Optional[str]) -> dict[str, float]:
        """Log-score bonus per candidate from this user's past choices."""
        j = self._jargon(user)
        k_ctx, k_any = self._keys(cands, left, right)
        bonus: dict[str, float] = {}
        for g, n in j["ctx"].get(k_ctx, {}).items():
            bonus[g] = bonus.get(g, 0.0) + 2.0 * min(n, 3) / 3 + 1.0
        for g, n in j["any"].get(k_any, {}).items():
            bonus[g] = bonus.get(g, 0.0) + 0.5 * min(n, 4) / 4
        return bonus

    def forget_user(self, user: str):
        with self._lock:
            d = self._dir(user)
            for f in d.iterdir():
                f.unlink()


class _QdrantMirror:
    """Optional: mirrors prototypes into Qdrant (collection per deployment, filtered by user)."""

    def __init__(self, client):
        from qdrant_client.http import models as qm
        self.c, self.qm = client, qm
        self.col = "signopsis_prototypes"
        names = [x.name for x in client.get_collections().collections]
        if self.col not in names:
            client.create_collection(self.col, vectors_config=qm.VectorParams(size=16 * 84, distance=qm.Distance.COSINE))

    def upsert(self, user, label, arrays):
        import uuid
        pts = [self.qm.PointStruct(id=str(uuid.uuid4()), vector=np.asarray(a, dtype=float).ravel().tolist(),
                                   payload={"user": user, "label": label}) for a in arrays]
        self.c.upsert(self.col, points=pts)

    def delete(self, user, label):
        qm = self.qm
        self.c.delete(self.col, points_selector=qm.FilterSelector(filter=qm.Filter(must=[
            qm.FieldCondition(key="user", match=qm.MatchValue(value=user)),
            qm.FieldCondition(key="label", match=qm.MatchValue(value=label))])))

    def search(self, user, vec, limit=10):
        qm = self.qm
        flt = qm.Filter(must=[qm.FieldCondition(key="user", match=qm.MatchValue(value=user))])
        res = self.c.query_points(self.col, query=np.asarray(vec, dtype=float).ravel().tolist(),
                                  query_filter=flt, limit=limit)
        return [(p.payload["label"], p.score) for p in res.points]


def _maybe_qdrant():
    url = os.getenv("SIGNOPSIS_QDRANT_URL") or os.getenv("SIGNOPSIS_QDRANT")
    if not url:
        return None
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(location=":memory:") if url == ":memory:" else QdrantClient(url=url)
        return _QdrantMirror(client)
    except Exception:
        return None
