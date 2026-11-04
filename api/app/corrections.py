"""Turn the model's CorrectionReport into corrections with offsets, dropping unplaceable ones."""

import unicodedata
from dataclasses import dataclass

import structlog

from app.schemas.correction import CorrectionReport, LocatedCorrection

log = structlog.get_logger()


@dataclass
class LocateResult:
    located: list[LocatedCorrection]
    dropped: int  # reported by the model but not found in the message


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def locate_corrections(message: str, report: CorrectionReport) -> LocateResult:
    """Place each correction in `message` (NFC). Exact match first, then case-insensitive.

    Unplaceable corrections are dropped (this also guards against invented errors). A repeated
    fragment matches its first occurrence. Of two overlapping spans, the longer one is kept.
    """
    message = normalize(message)
    lowered = message.lower()
    # str.lower() can change length for a few characters; fall back to exact only then.
    can_fold = len(lowered) == len(message)
    found: list[LocatedCorrection] = []
    dropped = 0
    for c in report.corrections:
        original = normalize(c.original)
        start = message.find(original) if original else -1
        if start < 0 and original and can_fold:
            start = lowered.find(original.lower())
        if start < 0:
            dropped += 1
            log.info("correction_dropped", original_length=len(c.original))
            continue
        found.append(
            LocatedCorrection(
                **c.model_dump(exclude={"original"}),
                original=message[start : start + len(original)],
                start=start,
                end=start + len(original),
            )
        )
    found.sort(key=lambda c: (-(c.end - c.start), c.start))
    kept: list[LocatedCorrection] = []
    for c in found:
        if any(c.start < k.end and k.start < c.end for k in kept):
            dropped += 1
            continue
        kept.append(c)
    kept.sort(key=lambda c: c.start)
    return LocateResult(located=kept, dropped=dropped)
