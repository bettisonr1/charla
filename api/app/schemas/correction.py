"""The structured output we ask the model for when it reviews a learner's message.

This is the contract the eval harness, the UI and the learner-memory layer all depend on, so
change it deliberately.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class ErrorCategory(StrEnum):
    GRAMMAR = "grammar"
    VERB_TENSE = "verb_tense"
    GENDER_AGREEMENT = "gender_agreement"
    VOCABULARY = "vocabulary"
    PREPOSITION = "preposition"
    SER_ESTAR = "ser_estar"
    SUBJUNCTIVE = "subjunctive"
    WORD_ORDER = "word_order"
    REGISTER = "register"  # correct but unnatural or wrong formality
    SPELLING = "spelling"


class Correction(BaseModel):
    original: str = Field(description="The exact fragment the learner wrote.")
    corrected: str = Field(description="What a native speaker would say instead.")
    category: ErrorCategory
    explanation: str = Field(
        description="One or two sentences, in simple Spanish at the learner's level."
    )


class CorrectionReport(BaseModel):
    corrections: list[Correction] = Field(default_factory=list)
    natural_rewrite: str | None = Field(
        default=None, description="Optional more idiomatic version of the whole message."
    )


class LocatedCorrection(Correction):
    """A correction placed in the learner's message by the server.

    `start`/`end` are code-point offsets into the NFC-normalised message (end exclusive). The model
    never produces them: models count characters badly, so `CorrectionReport` stays offset-free.
    """

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class StoredCorrections(BaseModel):
    """What `messages.corrections` holds. A missing column means "not checked or check failed"."""

    corrections: list[LocatedCorrection] = Field(default_factory=list)
