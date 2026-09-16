"""Print model sizes, ask, then download (hard rule 5).

    python backend/scripts/download_models.py            # layer 1 (speech -> text)
    python backend/scripts/download_models.py --fallback # + faster-whisper small (CPU)
    python backend/scripts/download_models.py --yes      # no prompt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from setu import config  # noqa: E402  (sets HF_HOME)

LAYER1 = [
    (config.PARAKEET_MODEL, "ASR English (CC-BY-4.0)"),
    (config.SORTFORMER_MODEL, "diarization, 4 speakers (see model card)"),
]
FALLBACK = [("Systran/faster-whisper-small", "CPU fallback ASR (MIT)")]


def repo_size(api, repo: str) -> int:
    info = api.model_info(repo, files_metadata=True)
    return sum((s.size or 0) for s in info.siblings)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fallback", action="store_true")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()

    from huggingface_hub import HfApi, snapshot_download

    api = HfApi()
    repos = LAYER1 + (FALLBACK if args.fallback else [])
    total = 0
    print(f"Download target: {config.get_settings().model_dir / 'hf'}\n")
    for repo, why in repos:
        size = repo_size(api, repo)
        total += size
        print(f"  {repo:<48} {size / 2**30:6.2f} GB   {why}")
    print(f"  {'total':<48} {total / 2**30:6.2f} GB")
    print("  (Silero VAD ships inside the silero-vad pip package — no download.)\n")

    if not args.yes and input("Download now? [y/N] ").strip().lower() != "y":
        print("Skipped.")
        return 1
    for repo, _ in repos:
        print(f"-> {repo}")
        if "faster-whisper" in repo:
            snapshot_download(repo, cache_dir=str(config.get_settings().model_dir / "whisper"))
        else:
            snapshot_download(repo)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
