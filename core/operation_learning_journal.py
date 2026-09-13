from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperationOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    DRAW = "DRAW"
    OPEN = "OPEN"
    VOID = "VOID"
    NOT_EXECUTED = "NOT_EXECUTED"


@dataclass(frozen=True)
class InvestigationQuestion:
    question_id: str
    category: str
    question: str


@dataclass(frozen=True)
class OperationLearningNote:
    note_id: str
    outcome: OperationOutcome
    what_happened: str
    why_assessment: str
    market_context: str
    evidence: tuple[str, ...]
    questions: tuple[InvestigationQuestion, ...]
    lessons: tuple[str, ...]


class OperationLearningJournal:
    """Records what happened after an operation and creates questions for later validation.

    This is an observation/learning record, not a strategy rule. Both favorable and
    unfavorable outcomes are retained so the ecosystem can study success and failure,
    challenge its own interpretation, and reduce repeat errors. A note never grants
    execution authority.
    """

    def create_note(
        self,
        *,
        note_id: str,
        outcome: OperationOutcome,
        what_happened: str,
        why_assessment: str,
        market_context: str,
        evidence: tuple[str, ...] = (),
        questions: tuple[InvestigationQuestion, ...] = (),
        lessons: tuple[str, ...] = (),
    ) -> OperationLearningNote:
        self._required(note_id, "note_id")
        self._required(what_happened, "what_happened")
        self._required(why_assessment, "why_assessment")
        self._required(market_context, "market_context")
        if not isinstance(outcome, OperationOutcome):
            raise ValueError("invalid operation outcome")
        self._strings(evidence, "evidence")
        self._questions(questions)
        self._strings(lessons, "lessons")
        return OperationLearningNote(
            note_id=note_id.strip(), outcome=outcome,
            what_happened=what_happened.strip(), why_assessment=why_assessment.strip(),
            market_context=market_context.strip(), evidence=tuple(x.strip() for x in evidence),
            questions=questions, lessons=tuple(x.strip() for x in lessons),
        )

    def default_questions(self, outcome: OperationOutcome) -> tuple[InvestigationQuestion, ...]:
        if not isinstance(outcome, OperationOutcome):
            raise ValueError("invalid operation outcome")
        prefix = "win" if outcome is OperationOutcome.WIN else "loss" if outcome is OperationOutcome.LOSS else "result"
        return (
            InvestigationQuestion(f"{prefix}-what", "what", "O que aconteceu no mercado antes, durante e depois da operação?"),
            InvestigationQuestion(f"{prefix}-why", "why", "Por que a leitura parece ter funcionado ou falhado?"),
            InvestigationQuestion(f"{prefix}-context", "context", "Qual contexto de mercado sustentou ou contrariou a leitura?"),
            InvestigationQuestion(f"{prefix}-evidence", "evidence", "Quais evidências sustentam a interpretação e quais a contradizem?"),
            InvestigationQuestion(f"{prefix}-repeat", "reassessment", "O que precisaria ser diferente para evitar repetir este resultado no futuro?"),
        )

    @staticmethod
    def _required(value: str, name: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")

    @staticmethod
    def _strings(values: tuple[str, ...], name: str) -> None:
        if not isinstance(values, tuple) or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValueError(f"invalid {name}")

    @staticmethod
    def _questions(values: tuple[InvestigationQuestion, ...]) -> None:
        if not isinstance(values, tuple) or any(not isinstance(v, InvestigationQuestion) for v in values):
            raise ValueError("invalid questions")
