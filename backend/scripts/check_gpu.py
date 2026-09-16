"""Phase 0 check: driver, CUDA, torch device, onnxruntime providers, llama.cpp.

Exits non-zero if the RTX 50-series GPU is not usable, instead of silently
falling back to CPU (hard rule 10).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ok = True


def line(name: str, value: str, good: bool | None = True) -> None:
    global ok
    mark = {True: "OK  ", False: "FAIL", None: "--  "}[good]
    if good is False:
        ok = False
    print(f"[{mark}] {name:<22} {value}")


def main() -> int:
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, check=True).stdout.strip()
        line("nvidia-smi", out)
        cuda = next((l for l in subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout.splitlines()
                     if "CUDA Version" in l), "")
        line("driver CUDA", cuda.split("CUDA Version:")[-1].strip(" |") if cuda else "unknown")
    except Exception as e:
        line("nvidia-smi", repr(e), False)

    try:
        import torch

        avail = torch.cuda.is_available()
        line("torch", f"{torch.__version__} (built for CUDA {torch.version.cuda})", avail)
        if avail:
            name = torch.cuda.get_device_name(0)
            cap = torch.cuda.get_device_capability(0)
            arches = torch.cuda.get_arch_list()
            sm = f"sm_{cap[0]}{cap[1]}"
            line("torch device", f"{name} ({sm})", sm in arches)
            if sm not in arches:
                print(f"       this torch build supports {arches}; install a cu128+ build")
            x = torch.randn(512, 512, device="cuda", dtype=torch.float16)
            line("torch fp16 matmul", f"{float((x @ x).float().abs().mean()):.3f}")
    except ImportError:
        line("torch", "not installed (make setup)", False)
    except Exception as e:
        line("torch", repr(e), False)

    try:
        import onnxruntime as ort

        provs = ort.get_available_providers()
        line("onnxruntime", f"{ort.__version__} {provs}", "CUDAExecutionProvider" in provs)
    except ImportError:
        line("onnxruntime", "not installed (make setup)", False)

    try:
        import nemo

        line("nemo", nemo.__version__)
    except ImportError:
        line("nemo", "not installed (make setup)", False)

    server = ROOT / "third_party/llama.cpp/build/bin/llama-server"
    found = server if server.exists() else shutil.which("llama-server")
    # llama.cpp is needed from Phase 3 (resolver); report but do not fail the speech layer.
    line("llama.cpp", str(found) if found else "not built yet (Phase 3: bash backend/scripts/build_llamacpp.sh)",
         True if found else None)
    print("\nGPU stack OK" if ok else "\nGPU stack NOT ready — see FAIL lines above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
