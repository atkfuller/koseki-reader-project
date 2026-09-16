"""NDLkotenOCR-Lite adapter.

Runs in its own virtualenv (venvs/ndl) because the package hard-pins numpy,
opencv, PyYAML and networkx to versions that conflict with PaddleOCR. We shell
out to its CLI and read the JSON back, which keeps the dependency walls intact
and costs one process spawn per page.

Worth knowing about the bundled weights: the recogniser ONNX files are named
`parseq-ndl-*-tegaki3-*` -- *tegaki* is 手書き, handwriting. This model was
trained on handwritten historical Japanese, which is exactly the hard half of a
koseki, and the weights ship inside the wheel, so there is nothing to download.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from .base import Line, Result

VENV_PY = Path(__file__).resolve().parents[2] / "venvs" / "ndl" / "bin" / "ndlocr-lite"


class NdlEngine:
    name = "ndlocr-lite"

    def __init__(self, binary: Path = VENV_PY, timeout: int = 600):
        self.binary = Path(binary)
        self.timeout = timeout

    def run(self, image_path: str) -> Result:
        t = time.time()
        if not self.binary.exists():
            return Result(self.name, [], 0.0, error=f"missing binary {self.binary}")
        with tempfile.TemporaryDirectory() as td:
            try:
                subprocess.run(
                    [str(self.binary), "--sourceimg", str(image_path),
                     "--output", td, "--json-only"],
                    check=True, capture_output=True, timeout=self.timeout,
                )
            except subprocess.CalledProcessError as e:
                msg = (e.stderr or b"").decode()[-300:]
                return Result(self.name, [], time.time() - t, error=f"exit {e.returncode}: {msg}")
            except subprocess.TimeoutExpired:
                return Result(self.name, [], time.time() - t, error="timeout")

            found = list(Path(td).glob("*.json"))
            if not found:
                return Result(self.name, [], time.time() - t, error="no json produced")
            data = json.loads(found[0].read_text(encoding="utf-8"))

        lines: list[Line] = []
        for page in data.get("contents", []):
            for item in page:
                if item.get("isTextline") not in ("true", True):
                    continue
                text = item.get("text") or ""
                if not text:
                    continue
                pts = item.get("boundingBox") or []
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    box = (int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))
                else:
                    box = (0, 0, 0, 0)
                lines.append(Line(text=text, box=box, conf=item.get("confidence")))
        return Result(self.name, lines, time.time() - t)
