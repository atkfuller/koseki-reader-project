"""Common shape for every OCR engine, so the benchmark can treat them alike."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass
class Line:
    """One recognised text region.

    `box` is (x, y, w, h) in pixels on the image that was fed to the engine --
    the review UI needs it to highlight the region on the original scan, and it
    is also what lets us reorder lines into proper vertical reading order.
    `conf` is per-line; `char_conf` is per-character where the engine exposes it
    (see the schema decision in the handoff: confidence must be persisted).
    """
    text: str
    box: tuple[int, int, int, int]
    conf: float | None = None
    char_conf: list[float] = field(default_factory=list)


@dataclass
class Result:
    engine: str
    lines: list[Line]
    seconds: float
    error: str | None = None

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)

    @property
    def chars(self) -> int:
        return sum(len(l.text) for l in self.lines)

    @property
    def mean_conf(self) -> float | None:
        cs = [l.conf for l in self.lines if l.conf is not None]
        return sum(cs) / len(cs) if cs else None


class Engine(Protocol):
    name: str

    def run(self, image_path: str) -> Result: ...


def reading_order_vertical(lines: Sequence[Line], col_tol: int = 40) -> list[Line]:
    """Sort lines for vertical Japanese: columns right-to-left, top-to-bottom.

    Engines that were trained on horizontal text return lines in raster order,
    which for a koseki is close to meaningless. Grouping by x-centre and walking
    from the right edge recovers the real order.
    """
    if not lines:
        return []
    ordered = sorted(lines, key=lambda l: -(l.box[0] + l.box[2] / 2))
    columns: list[list[Line]] = []
    for line in ordered:
        cx = line.box[0] + line.box[2] / 2
        if columns and abs((columns[-1][0].box[0] + columns[-1][0].box[2] / 2) - cx) <= col_tol:
            columns[-1].append(line)
        else:
            columns.append([line])
    out: list[Line] = []
    for col in columns:
        out.extend(sorted(col, key=lambda l: l.box[1]))
    return out


def reading_order_horizontal(lines: Sequence[Line], row_tol: int = 25) -> list[Line]:
    """Sort lines for horizontal text: rows top-to-bottom, left-to-right within a row.

    Grouping into rows before sorting by x matters for the computerised koseki,
    whose label column and value column sit side by side -- a naive sort by
    (y, x) interleaves them whenever the two boxes differ by a few pixels in y.
    """
    if not lines:
        return []
    out: list[Line] = []
    rows: list[list[Line]] = []
    for line in sorted(lines, key=lambda l: l.box[1] + l.box[3] / 2):
        cy = line.box[1] + line.box[3] / 2
        if rows and abs((rows[-1][0].box[1] + rows[-1][0].box[3] / 2) - cy) <= row_tol:
            rows[-1].append(line)
        else:
            rows.append([line])
    for row in rows:
        out.extend(sorted(row, key=lambda l: l.box[0]))
    return out


def reading_order(lines: Sequence[Line], vertical: bool | None = None) -> list[Line]:
    """Put lines into document reading order, choosing the axis automatically.

    This is not cosmetic. Measured on page 1 of the Takagi register, ndlocr-lite
    tiled scores CER 0.815 in the order the engine happens to return lines, and
    CER 0.110 after this sort -- same characters, same model, 7x the accuracy.
    Detection order is close to meaningless on a koseki, and every engine here
    returns it.

    `vertical` is inferred from the shape of the boxes when not given: a page of
    Japanese columns produces tall, narrow lines, a horizontal page wide ones.
    """
    if not lines:
        return []
    if vertical is None:
        tall = sum(1 for l in lines if l.box[3] > l.box[2] * 1.5)
        wide = sum(1 for l in lines if l.box[2] > l.box[3] * 1.5)
        vertical = tall > wide
    return reading_order_vertical(lines) if vertical else reading_order_horizontal(lines)
