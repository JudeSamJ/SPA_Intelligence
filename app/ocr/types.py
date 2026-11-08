"""Shared shapes for OCR. Coordinates are PDF points with the origin at the TOP-LEFT of the page (PyMuPDF's convention)."""
from __future__ import annotations

from dataclasses import dataclass, field


class OcrError(RuntimeError):
    """A readable reason OCR could not run or finished with nothing usable (never contains document text)."""


@dataclass
class OcrLine:
    text: str
    bbox: tuple[float, float, float, float]          # x0, y0, x1, y1


@dataclass
class OcrPage:
    page: int                                        # 1-based
    width: float                                     # page size the boxes refer to, in points
    height: float
    lines: list[OcrLine] = field(default_factory=list)
    engine: str = ""
    coarse: bool = False                             # True when the engine gave text but no usable positions

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)


class OcrEngine:
    name = "base"

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def read_pages(self, pdf_bytes: bytes, pages: list[int]) -> dict[int, OcrPage]:
        """Read the given 1-based pages. Pages the engine could not read are simply absent from the result."""
        raise NotImplementedError
