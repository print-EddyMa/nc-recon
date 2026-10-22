"""The frozen ResNet-18 encoder file: find it locally, or fetch it once.

    python -m terratriage.ops.model.fetch_encoder      # on a networked machine, once

Groma never downloads model weights while assessing: on an offline laptop a
hidden download would stall or fail late. `encoder_path()` only looks on disk
($TORCH_HOME/hub/checkpoints, else ~/.cache/torch/hub/checkpoints) and checks
the file's sha256; this command is the one place that fetches it (torchvision's
published ImageNet ResNet-18, BSD-3-Clause code). To stage an offline laptop,
copy the file into the same folder there.
"""
from __future__ import annotations

import hashlib
import os

FILE = "resnet18-f37072fd.pth"
SHA256 = "f37072fd47e89c5e827621c5baffa7500819f7896bbacec160b1a16c560e07ec"
URL = "https://download.pytorch.org/models/resnet18-f37072fd.pth"


def checkpoints_dir() -> str:
    home = os.environ.get("TORCH_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "torch")
    return os.path.join(home, "hub", "checkpoints")


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def encoder_path(verify: bool = True) -> str:
    """Local path of the encoder weights; FileNotFoundError when absent or wrong."""
    p = os.path.join(checkpoints_dir(), FILE)
    if not os.path.exists(p):
        raise FileNotFoundError("resnet18 encoder weights not on this machine "
                                f"(expected {p}; run python -m terratriage.ops.model.fetch_encoder)")
    if verify and _sha(p) != SHA256:
        raise FileNotFoundError(f"resnet18 encoder weights at {p} do not match sha256 {SHA256}")
    return p


def main() -> None:
    import urllib.request

    d = checkpoints_dir()
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, FILE)
    if os.path.exists(p) and _sha(p) == SHA256:
        print(f"already present and verified: {p}")
        return
    tmp = p + ".part"
    urllib.request.urlretrieve(URL, tmp)  # noqa: S310 - fixed https URL, checked below
    if _sha(tmp) != SHA256:
        os.remove(tmp)
        raise SystemExit("downloaded file does not match the expected sha256; not installed")
    os.replace(tmp, p)
    print(f"installed and verified: {p}")


if __name__ == "__main__":
    main()
