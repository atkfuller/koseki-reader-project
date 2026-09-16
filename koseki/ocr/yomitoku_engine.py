"""yomitoku adapter.

Also isolated (venvs/yomitoku) -- it wants torch plus newer networkx and
reportlab than ndlocr-lite's pins allow. Unlike ndlocr-lite it does layout
analysis and reading-order resolution itself, and it has an explicit
`--reading_order right2left` mode, which is the correct setting for a vertical
Japanese register and worth having in the comparison.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path

from .base import Line, Result

BIN = Path(__file__).resolve().parents[2] / "venvs" / "yomitoku" / "bin" / "yomitoku"


class YomitokuEngine:
    def __init__(self, reading_order: str = "right2left", lite: bool = False,
                 binary: Path = BIN, timeout: int = 1800):
        self.reading_order, self.lite = reading_order, lite
        self.binary, self.timeout = Path(binary), timeout

    @property
    def name(self) -> str:
        return f"yomitoku{'-lite' if self.lite else ''}/{self.reading_order}"

    def run(self, image_path: str) -> Result:
        t = time.time()
        if not self.binary.exists():
            return Result(self.name, [], 0.0, error=f"missing binary {self.binary}")
        with tempfile.TemporaryDirectory() as td:
            cmd = [str(self.binary), str(image_path), "-f", "json", "-o", td,
                   "-d", "cpu", "--reading_order", self.reading_order, "--ignore_meta"]
            if self.lite:
                cmd.append("-l")
            try:
                subprocess.run(cmd, check=True, capture_output=True, timeout=self.timeout)
            except subprocess.CalledProcessError as e:
                return Result(self.name, [], time.time() - t,
                              error=f"exit {e.returncode}: {(e.stderr or b'').decode()[-300:]}")
            except subprocess.TimeoutExpired:
                return Result(self.name, [], time.time() - t, error="timeout")

            files = list(Path(td).rglob("*.json"))
            if not files:
                return Result(self.name, [], time.time() - t, error="no json produced")
            data = json.loads(files[0].read_text(encoding="utf-8"))

        lines: list[Line] = []
        for w in data.get("words", []):
            text = w.get("content") or ""
            if not text:
                continue
            pts = w.get("points") or []
            if pts:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                box = (int(min(xs)), int(min(ys)), int(max(xs) - min(xs)), int(max(ys) - min(ys)))
            else:
                box = (0, 0, 0, 0)
            lines.append(Line(text=text, box=box, conf=w.get("rec_score")))
        return Result(self.name, lines, time.time() - t)
