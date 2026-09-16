"""Load NeMo models from a one-time extracted copy.

A `.nemo` file is a tar; NeMo normally unpacks it to /tmp on every load
(2+ GB for Parakeet). We unpack once under SETU_MODEL_DIR/extracted and
point NeMo's SaveRestoreConnector at that folder.
"""

from __future__ import annotations

import tarfile
from pathlib import Path

from ...config import get_settings


def nemo_file(repo: str) -> Path:
    """Local cache first (works offline); the network is only used if missing."""
    snap = get_settings().model_dir / "hf" / "hub" / f"models--{repo.replace('/', '--')}" / "snapshots"
    found = sorted(snap.glob("*/*.nemo"))
    if found:
        return found[-1]
    from huggingface_hub import HfApi, hf_hub_download

    name = next(f for f in HfApi().list_repo_files(repo) if f.endswith(".nemo"))
    return Path(hf_hub_download(repo, name))


def extracted_dir(repo: str) -> tuple[Path, Path]:
    src = nemo_file(repo)
    dst = get_settings().model_dir / "extracted" / repo.replace("/", "--")
    marker = dst / ".complete"
    if not marker.exists():
        dst.mkdir(parents=True, exist_ok=True)
        with tarfile.open(src, "r:*") as tar:
            tar.extractall(dst, filter="data")
        marker.write_text(src.name)
    return src, dst


def restore(cls, repo: str, device: str):
    from nemo.core.connectors.save_restore_connector import SaveRestoreConnector

    src, dst = extracted_dir(repo)
    conn = SaveRestoreConnector()
    conn.model_extracted_dir = str(dst)
    return cls.restore_from(restore_path=str(src), map_location=device, save_restore_connector=conn)
