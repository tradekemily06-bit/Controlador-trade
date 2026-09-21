from __future__ import annotations

from dataclasses import asdict
from typing import Any

from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize, summarize_breakdowns, summarize_periods
from core.p128_learning_professor import LearningProfessor
from core.professional_learning_question_engine import ProfessionalLearningQuestion
from core.scoped_professor_assessment import ScopedProfessorAssessment
from integration.production_data_plane import ProductionDataPlane
from security.http_identity import current_trusted_identity, saas_public_mode


class _ProductionLocalDecisionStoreBlock:
    """Fail-closed sentinel preventing legacy local decision persistence in production."""

    def load(self):
        raise RuntimeError("local decision store is unavailable for production-scoped service")

    def save(self, _record):
        raise RuntimeError("local decision store is unavailable for production-scoped service")

    def save_many(self, _records):
        raise RuntimeError("local decision store is unavailable for production-scoped service")


class _ProductionLocalLearningStateBlock:
    """Fail-closed sentinel preventing legacy process-local learning state in production."""

    def _blocked(self):
        raise RuntimeError("local learning state is unavailable for production-scoped service")

    def __contains__(self, _item):
        self._blocked()

    def __iter__(self):
        self._blocked()

    def __len__(self):
        self._blocked()

    def __getitem__(self, _item):
        self._blocked()

    def __setitem__(self, _item, _value):
        self._blocked()

    def __delitem__(self, _item):
        self._blocked()

    def append(self, _item):
        self._blocked()

    def values(self):
        self._blocked()


class ProductionScopedServiceMixin:
    """Replace process-global decision state with durable scoped state."""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # ConfiguredEcosystemService historically implemented these methods
        # directly. Replace those legacy class methods at class construction so
        # trusted tenant validation cannot be bypassed by an older override.
        if "generate_professor_activity" in cls.__dict__:
            cls.generate_professor_activity = ProductionScopedServiceMixin._scoped_generate_professor_activity
        if "generate_professional_questions" in cls.__dict__:
            cls.generate_professional_questions = ProductionScopedServiceMixin._scoped_generate_professional_questions

    def __init__(self, *args: Any, production_data_plane: ProductionDataPlane | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.production_data_plane = production_data_plane if production_data_plane is not None else ProductionDataPlane.from_config()
        if self.production_data_plane is not None:
            self.production_storage = self.production_data_plane.policy
            from security.production_operation_gate import ProductionOperationGate
            self.production_gate = ProductionOperationGate(self.production_storage)
            # The legacy DecisionStore is constructed by EcosystemService for
            # local/demo compatibility. Once a durable production data plane
            # exists it must not remain usable as a hidden fallback or source
            # of truth, even if a future inherited method accidentally touches
            # self.store. Also discard any local process snapshot loaded by the
            # legacy constructor so it cannot be read by a future bypass.
            self.store = _ProductionLocalDecisionStoreBlock()
            # Keep the legacy in-memory decision snapshot fail-closed as well.
            # A plain list here would let an inherited method accidentally read
            # process-local production state and bypass the durable data plane.
            local_learning_state = _ProductionLocalLearningStateBlock()
            self.memory = local_learning_state
            # Learning state had the same historical split: the configured
            # service now uses ScopedLearningState, while older inherited
            # methods can still reach the process-local dictionaries/lists.
            # Replace those containers with fail-closed sentinels so an
            # accidental fallback cannot create a second production source of
            # truth. DEMO/local mode is untouched because this branch runs only
            # when a production data plane exists.
            self.learning_sources = local_learning_state
            self.learning_resources = local_learning_state
            self.learning_observations = local_learning_state
            self.learning_activities = local_learning_state
            self.learning_attempts = local_learning_state

    def _production_scope_required(self) -> bool:
        return bool(self.production_data_plane is not None or saas_public_mode())

    @staticmethod
    def _require_trusted_owner(owner) -> None:
        identity = current_trusted_identity()
        if identity is None:
            raise PermissionError("trusted identity is required for production tenant state")
        if owner is None or owner.tenant_id != identity.tenant_id or owner.subject_id != identity.subject_id:
            raise PermissionError("requested tenant or subject does not match trusted identity")

    def _production_records(self, owner, *, limit: int | None = None) -> list[DecisionRecord]:
        if owner is None:
            if self._production_scope_required():
                raise PermissionError("trusted tenant and subject scope are required for production decision state")
            return list(self.memory)
        if self.production_data_plane is None:
            raise RuntimeError("production storage provider is required for owned decision state")
        self._require_trusted_owner(owner)
        return self.production_data_plane.list(tenant_id=owner.tenant_id, subject_id=owner.subject_id, limit=limit)

    def _scoped_memory(self, owner):
        if self.production_data_plane is not None or saas_public_mode():
            return self._production_records(owner)
        return super()._scoped_memory(owner)

    def _persist_records(self, records: list[DecisionRecord]) -> None:
        if not records:
            return
        owned = [record for record in records if record.subject_id is not None or record.tenant_id is not None]
        unowned = [record for record in records if record.subject_id is None and record.tenant_id is None]
        if self.production_data_plane is not None:
            if unowned:
                raise PermissionError("production decision records require tenant and subject ownership")
            identity = current_trusted_identity()
            if identity is None:
                raise PermissionError("trusted identity is required for production decision writes")
            for record in owned:
                if record.tenant_id != identity.tenant_id or record.subject_id != identity.subject_id:
                    raise PermissionError("decision record ownership does not match trusted identity")
                self.production_data_plane.save(record, tenant_id=record.tenant_id, subject_id=record.subject_id)
            return
        if saas_public_mode():
            raise RuntimeError("production storage provider is not configured; local decision fallback is disabled")
        super()._persist_records(records)

    def record_outcome(self, decision_id: str, outcome: str, *, subject_id: str | None = None, tenant_id: str | None = None) -> DecisionRecord:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        if self.production_data_plane is None and not saas_public_mode():
            return super().record_outcome(decision_id, outcome, subject_id=subject_id, tenant_id=tenant_id)
        if owner is None:
            raise PermissionError("trusted tenant and subject scope are required for production outcome updates")
        self._require_trusted_owner(owner)
        if self.production_data_plane is None:
            raise RuntimeError("production storage provider is not configured")
        record = self.production_data_plane.load(decision_id, tenant_id=owner.tenant_id, subject_id=owner.subject_id)
        if record is None:
            raise ValueError("decision_id não encontrado")
        updated = record.with_outcome(outcome)
        self.production_data_plane.save(updated, tenant_id=owner.tenant_id, subject_id=owner.subject_id)
        return updated

    def statistics(self, *, subject_id: str | None = None, tenant_id: str | None = None) -> dict[str, Any]:
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        if self.production_data_plane is None and not saas_public_mode():
            return super().statistics(subject_id=subject_id, tenant_id=tenant_id)
        scoped = self._production_records(owner, limit=None)
        breakdowns = summarize_breakdowns(scoped)
        return {**asdict(summarize(scoped)), "periods": summarize_periods(scoped), "breakdowns": {**breakdowns, "by_symbol": breakdowns["symbols"], "by_timeframe": breakdowns["timeframes"], "by_signal": breakdowns["signals"], "by_score_band": breakdowns["score_bands"]}}

    def memory_view(self, limit: int = 50, *, subject_id: str | None = None, tenant_id: str | None = None) -> list[dict[str, Any]]:
        if limit < 1:
            raise ValueError("limit deve ser maior que zero")
        owner = self._owner_context(subject_id=subject_id, tenant_id=tenant_id)
        if self.production_data_plane is None and not saas_public_mode():
            return super().memory_view(limit=limit, subject_id=subject_id, tenant_id=tenant_id)
        records = self._production_records(owner, limit=limit)
        return [item.to_dict() for item in records[:limit]]

    def _scoped_professor(self) -> ScopedProfessorAssessment | None:
        if not hasattr(self, "scoped_learning") or not hasattr(self, "_learning_scope"):
            return None
        professor = getattr(self, "learning_professor", None)
        return ScopedProfessorAssessment(professor if isinstance(professor, LearningProfessor) else LearningProfessor())

    def _scoped_generate_professor_activity(self, payload: dict[str, Any]):
        boundary = self._scoped_professor()
        if boundary is None:
            return super().generate_professor_activity(payload)
        scope = self._learning_scope()
        if scope is None:
            raise PermissionError("trusted tenant and subject scope are required for professor activity")
        knowledge_id = str(payload.get("knowledge_id", "")).strip()
        observation = boundary._validated_observation(scope, knowledge_id)
        from core.learning_content import LearningActivity
        from core.p128_learning_professor import ProfessorActivitySpec
        activity_id = str(payload.get("activity_id", "")).strip()
        if activity_id in scope.activities:
            raise ValueError("activity_id já cadastrado")
        activity = boundary.professor.build_activity(ProfessorActivitySpec(activity_id=activity_id, knowledge_id=knowledge_id, statement=observation.statement, concept=observation.concepts[0] if observation.concepts else "raciocínio de mercado", difficulty=str(payload.get("difficulty", "INTERMEDIATE"))), knowledge_validated=True)
        if not isinstance(activity, LearningActivity):
            raise RuntimeError("professor returned an invalid activity")
        scope.activities[activity.activity_id] = activity
        self._persist_learning_scope()
        return activity

    def _scoped_generate_professional_questions(self, payload: dict[str, Any]) -> tuple[ProfessionalLearningQuestion, ...]:
        boundary = self._scoped_professor()
        if boundary is None:
            return super().generate_professional_questions(payload)
        scope = self._learning_scope()
        if scope is None:
            raise PermissionError("trusted tenant and subject scope are required for professional questions")
        knowledge_id = str(payload.get("knowledge_id", "")).strip()
        observation = boundary._validated_observation(scope, knowledge_id)
        from core.p128_learning_professor import ProfessorActivitySpec
        spec = ProfessorActivitySpec(activity_id=str(payload.get("activity_id", "question-set")), knowledge_id=knowledge_id, statement=observation.statement, concept=observation.concepts[0] if observation.concepts else "raciocínio de mercado", difficulty=str(payload.get("difficulty", "ADVANCED")))
        return boundary.professor.build_professional_questions(spec, knowledge_validated=True, context=str(payload.get("context", "")))

    def generate_adaptive_professor_quiz(self, payload: dict[str, Any]):
        boundary = self._scoped_professor()
        if boundary is None:
            raise PermissionError("scoped professor boundary is required")
        scope = self._learning_scope()
        if scope is None:
            raise PermissionError("trusted tenant and subject scope are required for adaptive quiz")
        plan, questions = boundary.build_adaptive_quiz(scope, activity_id=str(payload.get("activity_id", "")), knowledge_id=str(payload.get("knowledge_id", "")), confidence=payload.get("confidence"), objective=str(payload.get("objective", "")))
        return {"plan": {"mode": plan.mode.value, "question_types": [item.value for item in plan.question_types], "question_count": plan.question_count, "rationale": list(plan.rationale), "completion_rule": plan.completion_rule}, "questions": [asdict(item) | {"question_type": item.question_type.value} for item in questions], "execution_allowed": False, "learning_authorizes_trading": False}

    def grade_professor_answer(self, payload: dict[str, Any], *, question: ProfessionalLearningQuestion) -> dict[str, Any]:
        boundary = self._scoped_professor()
        if boundary is None:
            raise PermissionError("scoped professor boundary is required")
        scope = self._learning_scope()
        if scope is None:
            raise PermissionError("trusted tenant and subject scope are required for professor grading")
        assessment = boundary.grade_and_record(scope, activity_id=str(payload.get("activity_id", "")), question=question, answer=str(payload.get("answer", "")))
        self._persist_learning_scope()
        return asdict(assessment) | {"execution_allowed": False, "learning_authorizes_trading": False}