"""Turn a model's CorrectionReport into corrections placed in the learner's message."""

import unicodedata
from dataclasses import dataclass

import structlog

from app.llm import LLM
from app.schemas.correction import CorrectionReport, LocatedCorrection

log = structlog.get_logger()


def normalize(text: str) -> str:
    """NFC, so that offsets and matching agree between server, model output and client."""
    return unicodedata.normalize("NFC", text)


def _find(message: str, fragment: str) -> int:
    index = message.find(fragment)
    if index >= 0:
        return index
    # Case-insensitive fallback. Only safe when lowering keeps every offset in place.
    lowered = message.lower()
    if len(lowered) == len(message):
        return lowered.find(fragment.lower())
    return -1


@dataclass
class Located:
    corrections: list[LocatedCorrection]
    dropped: int


def locate_corrections(message: str, report: CorrectionReport) -> Located:
    """Place each correction in `message`; drop any whose `original` isn't actually in it.

    Dropping doubles as the guard against invented errors. A repeated fragment resolves to its
    first occurrence. When spans overlap, the longer one wins.
    """
    message = normalize(message)
    placed: list[LocatedCorrection] = []
    dropped = 0
    for correction in report.corrections:
        original = normalize(correction.original)
        index = _find(message, original) if original.strip() else -1
        if index < 0:
            dropped += 1
            log.info("correction_dropped", reason="not_found", original_length=len(original))
            continue
        placed.append(
            LocatedCorrection(
                **correction.model_dump(exclude={"original"}),
                original=message[index : index + len(original)],
                start=index,
                end=index + len(original),
            )
        )

    kept: list[LocatedCorrection] = []
    for candidate in sorted(placed, key=lambda c: c.start - c.end):  # longest first
        if any(candidate.start < k.end and k.start < candidate.end for k in kept):
            dropped += 1
            log.info("correction_dropped", reason="overlap")
            continue
        kept.append(candidate)
    kept.sort(key=lambda c: c.start)
    return Located(kept, dropped)


async def check_message(llm: LLM, message: str, context: str | None = None) -> Located:
    """The production correction path: model call, then locate-and-validate. Also used by evals."""
    message = normalize(message)
    report = await llm.correct(message, context)
    return locate_corrections(message, report)
