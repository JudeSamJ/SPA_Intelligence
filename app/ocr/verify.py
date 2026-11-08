"""Agreement between two independent readings of the same page (0..1)."""
from __future__ import annotations

import re

from rapidfuzz import fuzz


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", " ", (s or "").lower()).strip()


def agreement(a: str, b: str) -> float:
    """Word-order-tolerant similarity of two page transcriptions. Both empty counts as perfect agreement on 'nothing here'; one empty,
    the other not, is total disagreement."""
    na, nb = _norm(a), _norm(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return round(fuzz.token_sort_ratio(na, nb) / 100.0, 4)


_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers(text: str) -> set[str]:
    """Every number in the text, normalised (thousands commas removed). Digits are what OCR gets wrong most dangerously (6 vs 8,
    0 vs O), and a whole-page similarity score barely moves for one wrong digit, so numbers are compared on their own."""
    out = set()
    for m in _NUM.findall(text or ""):
        m = m.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", m) else m
        out.add(m.rstrip(".,"))
    return out


def number_differences(a: str, b: str) -> list[str]:
    """Numbers found by one reading but not the other, sorted."""
    return sorted(numbers(a) ^ numbers(b))
