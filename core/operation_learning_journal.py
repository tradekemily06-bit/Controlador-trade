from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import json
import os
import sqlite3
from pathlib import Path
from threading import Lock


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
    """Records post-operation learning and durably deduplicates verified observations.

    The journal is independent from execution authority. When a SQLite path is
    configured, verified learning notes survive restarts and the external-result
    identity becomes the idempotency key. Without a path, the journal keeps the
    original in-memory behavior.
    """

    def __init__(self, database_path: str | None = None) -> None:
        self.database_path = database_path if database_path is not None else os.environ.get("CONTROLADOR_LEARNING_DB")
        self._lock = Lock()
        if self.database_path:
            self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path or ":memory:", timeout=5)

    def _initialize(self) -> None:
        try:
            path = Path(self.database_path or "")
            if path.parent != Path("."):
                path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self._connect() as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS operation_learning_notes ("
                    "note_id TEXT PRIMARY KEY, dedupe_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)"
                )
        except (OSError, sqlite3.Error):
            self.database_path = None

    def persist_verified_note(self, note: OperationLearningNote, *, dedupe_key: str, evidence_identity: dict[str, object] | None = None) -> bool:
        """Persist one verified note exactly once; return False for the same evidence key."""
        if not isinstance(note, OperationLearningNote):
            raise ValueError("invalid operation learning note")
        self._required(dedupe_key, "dedupe_key")
        if not self.database_path:
            return True
        identity = dict(evidence_identity or {})
        payload = json.dumps({
            "note_id": note.note_id,
            "identity": identity,
            "outcome": note.outcome.value,
            "what_happened": note.what_happened,
            "why_assessment": note.why_assessment,
            "market_context": note.market_context,
            "evidence": list(note.evidence),
            "questions": [asdict(item) for item in note.questions],
            "lessons": list(note.lessons),
        }, ensure_ascii=False, sort_keys=True)
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    "INSERT INTO operation_learning_notes(note_id, dedupe_key, payload) VALUES (?, ?, ?)",
                    (note.note_id, dedupe_key.strip(), payload),
                )
            return True
        except sqlite3.IntegrityError:
            try:
                with self._lock, self._connect() as connection:
                    row = connection.execute(
                        "SELECT note_id, payload FROM operation_learning_notes WHERE dedupe_key = ?",
                        (dedupe_key.strip(),),
                    ).fetchone()
                    if row is None:
                        return False
                    current = json.loads(row[1])
                    current_identity = current.get("identity", {})
                    if not isinstance(current_identity, dict):
                        return False
                    if (
                        current_identity.get("cycle_id") != identity.get("cycle_id")
                        or current_identity.get("outcome") != identity.get("outcome")
                        or current_identity.get("financial_result") != identity.get("financial_result")
                    ):
                        return False
                    current_ids = set(current_identity.get("external_result_ids", ()))
                    incoming_ids = set(identity.get("external_result_ids", ()))
                    if not current_ids.issubset(incoming_ids) and not incoming_ids.issubset(current_ids):
                        return False
                    if current_identity.get("external_container_id") != identity.get("external_container_id"):
                        return False
                    if incoming_ids != current_ids:
                        current["identity"] = identity
                        current["evidence"] = list(note.evidence)
                        current["lessons"] = list(note.lessons)
                        current["what_happened"] = note.what_happened
                        current["why_assessment"] = note.why_assessment
                        connection.execute(
                            "UPDATE operation_learning_notes SET payload = ? WHERE dedupe_key = ?",
                            (json.dumps(current, ensure_ascii=False, sort_keys=True), dedupe_key.strip()),
                        )
                return True
            except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError, ValueError, KeyError):
                return False
        except sqlite3.Error:
            return False

    def verified_note(self, *, dedupe_key: str) -> OperationLearningNote | None:
        if not self.database_path:
            return None
        self._required(dedupe_key, "dedupe_key")
        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT payload FROM operation_learning_notes WHERE dedupe_key = ?",
                    (dedupe_key.strip(),),
                ).fetchone()
            if row is None:
                return None
            payload = json.loads(row[0])
            return OperationLearningNote(
                note_id=payload["note_id"], outcome=OperationOutcome(payload["outcome"]),
                what_happened=payload["what_happened"], why_assessment=payload["why_assessment"],
                market_context=payload["market_context"], evidence=tuple(payload.get("evidence", ())),
                questions=tuple(InvestigationQuestion(**item) for item in payload.get("questions", ())),
                lessons=tuple(payload.get("lessons", ())),
            )
        except (sqlite3.Error, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def verified_dedupe_key(snapshot) -> str:
        """Use operation identity, not a changing subset of external deal IDs."""
        cycle_id = getattr(snapshot, "cycle_id", None)
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            raise ValueError("verified result requires cycle_id")
        return f"cycle:{cycle_id.strip()}"

    @staticmethod
    def verified_evidence_identity(snapshot) -> dict[str, object]:
        cycle_id = getattr(snapshot, "cycle_id", None)
        ids = tuple(sorted(set(getattr(snapshot, "external_result_ids", ()) or ())))
        container = getattr(snapshot, "external_container_id", None)
        reference = getattr(snapshot, "external_reference", None)
        outcome = getattr(snapshot, "outcome", None)
        financial_result = getattr(snapshot, "financial_result", None)
        if not cycle_id or not ids or not container:
            raise ValueError("verified result requires cycle_id, external_container_id and external_result_ids")
        return {
            "cycle_id": cycle_id,
            "outcome": outcome,
            "financial_result": financial_result,
            "external_container_id": container,
            "external_reference": reference,
            "external_result_ids": list(ids),
        }

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
