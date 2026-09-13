from __future__ import annotations

from dataclasses import dataclass

from core.integrated_market_reading import IntegratedMarketReading, ReadingStatus
from core.market_context import MarketContextResult
from core.models import AnalysisResult
from core.operation_learning_journal import OperationLearningNote
from core.p50_automation_result_snapshot import AutomationResultSnapshot
from core.p51_learning_ingestion import LearningEligibility, LearningIngestionBoundary
from core.p52_learning_evidence import LearningEvidence, LearningEvidenceBoundary
from core.p77_context_audit import ContextAudit
from core.p78_hypothesis_preparation import HypothesisPreparationBoundary, PreparedHypothesis
from core.p79_validation_admission import ValidationAdmission, ValidationAdmissionBoundary
from core.p80_validation_specification import ValidationSpecification, ValidationSpecificationBoundary
from core.p81_validation_run import ValidationRun, ValidationRunBoundary


@dataclass(frozen=True)
class OperationLearningHandoff:
    """Complete learning handoff for one operation cycle.

    An operation is never learned as an isolated WIN/LOSS. The handoff keeps the
    observed result together with the reading, market context and investigation
    record. Only reconciled evidence may cross into the learning-evidence layer.
    This artifact cannot authorize execution.
    """

    cycle_id: str
    note: OperationLearningNote
    analysis: AnalysisResult
    market_context: MarketContextResult
    evidence: LearningEvidence | None
    learning_eligible: bool
    execution_authorized: bool = False


@dataclass(frozen=True)
class IntegratedLearningCandidate:
    """A reading-derived hypothesis candidate with preserved provenance.

    This is deliberately a hypothesis, not knowledge and not an order signal.
    Supported readings may enter the existing P78-P81 validation path. Conflicting
    or insufficient readings remain investigation-only and cannot be admitted.
    """

    cycle_id: str
    reading_status: ReadingStatus
    statement: str
    source_observation_ids: tuple[str, ...]
    unanswered_questions: tuple[str, ...]
    hypothesis: PreparedHypothesis | None
    admission: ValidationAdmission | None
    specification: ValidationSpecification | None
    validation_run: ValidationRun | None
    execution_authorized: bool = False


class OperationLearningHandoffBoundary:
    """Connects result -> journal -> evidence without creating a parallel learner."""

    def build(
        self,
        *,
        snapshot: AutomationResultSnapshot,
        note: OperationLearningNote,
        analysis: AnalysisResult,
        market_context: MarketContextResult,
    ) -> OperationLearningHandoff:
        if not isinstance(snapshot, AutomationResultSnapshot):
            raise ValueError("invalid automation result snapshot")
        if not isinstance(note, OperationLearningNote):
            raise ValueError("invalid operation learning note")
        if not isinstance(analysis, AnalysisResult):
            raise ValueError("invalid analysis")
        if not isinstance(market_context, MarketContextResult):
            raise ValueError("invalid market context")
        if note.outcome.value != snapshot.outcome and note.outcome.value != "NOT_EXECUTED":
            raise ValueError("operation note outcome does not match result snapshot")

        ingestion = LearningIngestionBoundary().ingest(snapshot)
        evidence = None
        if ingestion.eligibility is LearningEligibility.VERIFIED:
            evidence = LearningEvidenceBoundary().build(ingestion)

        return OperationLearningHandoff(
            cycle_id=snapshot.cycle_id,
            note=note,
            analysis=analysis,
            market_context=market_context,
            evidence=evidence,
            learning_eligible=evidence is not None,
            execution_authorized=False,
        )


class IntegratedLearningValidationBoundary:
    """Route integrated market understanding into the existing validation chain."""

    def prepare(
        self,
        *,
        reading: IntegratedMarketReading,
        context_audit: ContextAudit,
        cycle_id: str,
        hypothesis_id: str,
        admission_id: str,
        test_id: str,
        run_id: str,
        statement: str | None = None,
        environment: str = "DEMO_VALIDATION",
        criteria: str = "Validar suporte, contradicoes, estabilidade contextual e capacidade de generalizacao sem autorizar execucao real.",
        sample_size: int = 1,
    ) -> IntegratedLearningCandidate:
        if not isinstance(reading, IntegratedMarketReading):
            raise ValueError("invalid integrated market reading")
        if not isinstance(context_audit, ContextAudit):
            raise ValueError("invalid context audit")
        if not isinstance(cycle_id, str) or not cycle_id.strip():
            raise ValueError("cycle_id is required")

        observations = tuple(o.observation_id for o in reading.observations)
        hypothesis_statement = (statement or self._default_statement(reading)).strip()
        if not hypothesis_statement:
            raise ValueError("hypothesis statement is required")

        # Conflict and insufficient evidence are preserved as investigation state;
        # they are never promoted into the operational validation path.
        if reading.status is not ReadingStatus.SUPPORTED:
            return IntegratedLearningCandidate(
                cycle_id=cycle_id.strip(),
                reading_status=reading.status,
                statement=hypothesis_statement,
                source_observation_ids=observations,
                unanswered_questions=reading.unanswered_questions,
                hypothesis=None,
                admission=None,
                specification=None,
                validation_run=None,
                execution_authorized=False,
            )

        hypothesis = HypothesisPreparationBoundary().prepare(
            context_audit,
            hypothesis_id=hypothesis_id,
            statement=hypothesis_statement,
        )
        admission = ValidationAdmissionBoundary().admit(
            hypothesis,
            admission_id=admission_id,
        )
        specification = ValidationSpecificationBoundary().specify(
            admission,
            test_id=test_id,
            environment=environment,
            criteria=criteria,
        )
        validation_run = ValidationRunBoundary().record(
            specification,
            run_id=run_id,
            sample_size=sample_size,
            observation=self._validation_observation(reading),
        )

        return IntegratedLearningCandidate(
            cycle_id=cycle_id.strip(),
            reading_status=reading.status,
            statement=hypothesis_statement,
            source_observation_ids=observations,
            unanswered_questions=reading.unanswered_questions,
            hypothesis=hypothesis,
            admission=admission,
            specification=specification,
            validation_run=validation_run,
            execution_authorized=False,
        )

    @staticmethod
    def _default_statement(reading: IntegratedMarketReading) -> str:
        directional = "; ".join(reading.supporting) or "evidencias integradas"
        return f"A leitura integrada encontrou suporte contextual suficiente para investigar a relacao entre {directional}."

    @staticmethod
    def _validation_observation(reading: IntegratedMarketReading) -> str:
        return (
            f"status={reading.status.value}; confluencias_independentes={reading.independent_confluences}; "
            f"observacoes={len(reading.observations)}; possivel_falso_rompimento={reading.possible_false_breakout}; "
            f"questoes={len(reading.unanswered_questions)}"
        )
