"""PDF -> page images. Uses poppler's pdftoppm (installed via `brew install poppler`)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def render_pdf(pdf_path: str | Path, out_dir: str | Path, dpi: int = 300) -> list[Path]:
    """Render every page of `pdf_path` to PNG at `dpi`. Returns sorted page paths."""
    pdf_path, out_dir = Path(pdf_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), str(out_dir / "p")],
        check=True,
    )
    return sorted(out_dir.glob("p-*.png"))


def page_count(pdf_path: str | Path) -> int:
    out = subprocess.run(
        ["pdfinfo", str(pdf_path)], check=True, capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1])
    raise ValueError("no page count in pdfinfo output")
