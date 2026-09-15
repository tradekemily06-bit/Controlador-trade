from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .learning_content import LearningActivity
from .professional_learning_question_engine import (
    ProfessionalLearningQuestion,
    ProfessionalLearningQuestionEngine,
    QuestionType,
)


class QuizMode(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    CONSOLIDATION = "CONSOLIDATION"
    REMEDIATION = "REMEDIATION"
    MASTERy = "MASTERY"
    MATERIAL_REVIEW = "MATERIAL_REVIEW"


@dataclass(frozen=True)
class ProfessorActivitySpec:
    """Educational activity generated only from validated knowledge."""

    activity_id: str
    knowledge_id: str
    statement: str
    concept: str
    difficulty: str = "INTERMEDIATE"

    def __post_init__(self) -> None:
        if not self.activity_id.strip() or not self.knowledge_id.strip():
            raise ValueError("activity_id and knowledge_id are required")
        if not self.statement.strip() or not self.concept.strip():
            raise ValueError("statement and concept are required")


@dataclass(frozen=True)
class QuizPlan:
    """Evidence-driven plan for the current assessment session.

    The count is deliberately dynamic. It is not a storage/history limit and
    does not cap the learner's future assessments or learning material.
    """

    mode: QuizMode
    question_types: tuple[QuestionType, ...]
    question_count: int
    rationale: tuple[str, ...]
    completion_rule: str


@dataclass(frozen=True)
class AnswerAssessment:
    """Professional assessment of one answer; never an execution decision."""

    result: str
    score: float
    covered_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    strengths: tuple[str, ...]
    gaps: tuple[str, ...]
    feedback: str
    trading_authorized: bool = False


class LearningProfessor:
    """Senior-teacher boundary for validated market knowledge.

    The professor may explain validated knowledge, choose an appropriate
    assessment depth, and grade reasoning. It never treats a lesson, quiz, or
    user score as authorization to trade.
    """

    def __init__(self, question_engine: ProfessionalLearningQuestionEngine | None = None) -> None:
        self.question_engine = question_engine or ProfessionalLearningQuestionEngine()

    def build_activity(self, spec: ProfessorActivitySpec, *, knowledge_validated: bool) -> LearningActivity:
        if not isinstance(spec, ProfessorActivitySpec):
            raise ValueError("invalid professor activity specification")
        if not knowledge_validated:
            raise ValueError("only validated knowledge can generate operational teaching activities")
        return LearningActivity(
            activity_id=spec.activity_id,
            prompt=(
                f"Analise a afirmação validada a seguir e explique em qual contexto ela faz sentido, "
                f"quais evidências a sustentam e quais evidências poderiam contradizê-la: {spec.statement}"
            ),
            expected_concepts=(spec.concept, spec.knowledge_id),
            difficulty=spec.difficulty,
        )

    def build_professional_questions(
        self,
        spec: ProfessorActivitySpec,
        *,
        knowledge_validated: bool,
        context: str = "",
        question_types: tuple[QuestionType, ...] | None = None,
    ) -> tuple[ProfessionalLearningQuestion, ...]:
        if not isinstance(spec, ProfessorActivitySpec):
            raise ValueError("invalid professor activity specification")
        if not knowledge_validated:
            raise ValueError("only validated knowledge can generate professional questions")
        return self.question_engine.build(
            knowledge_id=spec.knowledge_id,
            concept=spec.concept,
            statement=spec.statement,
            context=context,
            question_types=question_types,
        )

    def plan_quiz(
        self,
        spec: ProfessorActivitySpec,
        *,
        knowledge_validated: bool,
        prior_attempts: int = 0,
        recent_gap_count: int = 0,
        confidence: float | None = None,
        material_reviewed: bool = False,
        material_contradictions: int = 0,
        objective: str = "",
    ) -> QuizPlan:
        if not isinstance(spec, ProfessorActivitySpec):
            raise ValueError("invalid professor activity specification")
        if not knowledge_validated:
            raise ValueError("only validated knowledge can be assessed")
        if prior_attempts < 0 or recent_gap_count < 0 or material_contradictions < 0:
            raise ValueError("attempt and gap counts must be non-negative")
        if confidence is not None and not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

        reasons: list[str] = []
        if recent_gap_count > 0:
            mode = QuizMode.REMEDIATION
            reasons.append("há lacunas recentes que precisam ser testadas novamente")
        elif material_reviewed and material_contradictions > 0:
            mode = QuizMode.MATERIAL_REVIEW
            reasons.append("o material validado contém pontos que exigem confronto crítico")
        elif prior_attempts == 0:
            mode = QuizMode.DIAGNOSTIC
            reasons.append("é a primeira avaliação deste conhecimento")
        elif confidence is not None and confidence >= 0.85:
            mode = QuizMode.MASTERY
            reasons.append("a confiança declarada é alta e exige validação, não aceitação automática")
        else:
            mode = QuizMode.CONSOLIDATION
            reasons.append("o conhecimento já foi estudado e precisa de consolidação")

        types = list((
            QuestionType.CONTEXT,
            QuestionType.SCENARIO,
            QuestionType.EVIDENCE,
            QuestionType.COUNTERFACTUAL,
            QuestionType.RISK,
            QuestionType.STATISTICAL_VALIDATION,
            QuestionType.MARKET_STRUCTURE,
            QuestionType.SELF_CRITIQUE,
            QuestionType.EXECUTION_DISCIPLINE,
        ))
        if mode == QuizMode.DIAGNOSTIC:
            selected = types[:5]
        elif mode == QuizMode.REMEDIATION:
            selected = [QuestionType.CONTEXT, QuestionType.EVIDENCE, QuestionType.COUNTERFACTUAL, QuestionType.RISK, QuestionType.SELF_CRITIQUE]
            if recent_gap_count >= 3:
                selected += [QuestionType.STATISTICAL_VALIDATION, QuestionType.MARKET_STRUCTURE]
        elif mode == QuizMode.MATERIAL_REVIEW:
            selected = [QuestionType.EVIDENCE, QuestionType.COUNTERFACTUAL, QuestionType.STATISTICAL_VALIDATION, QuestionType.SELF_CRITIQUE, QuestionType.RISK]
        elif mode == QuizMode.MASTERY:
            selected = types
        else:
            selected = types[:6]

        if objective:
            reasons.append(f"objetivo atual: {objective.strip()}")
        if recent_gap_count:
            reasons.append(f"a profundidade foi ajustada às {recent_gap_count} lacunas observadas")
        if confidence is not None:
            reasons.append("a confiança foi usada como sinal diagnóstico, nunca como prova de domínio")
        if material_reviewed:
            reasons.append("o material externo só influencia a avaliação porque já foi marcado como revisado/validado")

        return QuizPlan(
            mode=mode,
            question_types=tuple(selected),
            question_count=len(selected),
            rationale=tuple(reasons),
            completion_rule=(
                "Concluir quando as dimensões necessárias estiverem suficientemente demonstradas; "
                "se surgirem lacunas relevantes, gerar avaliação complementar em vez de aceitar por quantidade fixa."
            ),
        )

    def build_adaptive_quiz(
        self,
        spec: ProfessorActivitySpec,
        *,
        knowledge_validated: bool,
        prior_attempts: int = 0,
        recent_gap_count: int = 0,
        confidence: float | None = None,
        material_reviewed: bool = False,
        material_contradictions: int = 0,
        objective: str = "",
        context: str = "",
    ) -> tuple[QuizPlan, tuple[ProfessionalLearningQuestion, ...]]:
        plan = self.plan_quiz(
            spec,
            knowledge_validated=knowledge_validated,
            prior_attempts=prior_attempts,
            recent_gap_count=recent_gap_count,
            confidence=confidence,
            material_reviewed=material_reviewed,
            material_contradictions=material_contradictions,
            objective=objective,
        )
        questions = self.build_professional_questions(
            spec,
            knowledge_validated=knowledge_validated,
            context=context,
            question_types=plan.question_types,
        )
        return plan, questions

    @staticmethod
    def grade_answer(*, question: ProfessionalLearningQuestion, answer: str) -> AnswerAssessment:
        if not isinstance(question, ProfessionalLearningQuestion):
            raise ValueError("invalid professional question")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("answer is required")

        normalized = " ".join(answer.lower().split())
        covered: list[str] = []
        missing: list[str] = []
        for evidence in question.expected_evidence:
            terms = [term for term in evidence.lower().split() if len(term) > 3]
            if terms and any(term in normalized for term in terms):
                covered.append(evidence)
            else:
                missing.append(evidence)

        total = len(question.expected_evidence)
        coverage = len(covered) / total if total else 0.0
        if len(answer.strip()) < 30:
            result = "INSUFFICIENT"
        elif coverage >= 0.75:
            result = "STRONG"
        elif coverage >= 0.4:
            result = "PARTIAL"
        else:
            result = "WEAK"

        strengths = tuple(covered)
        gaps = tuple(missing)
        if result == "STRONG":
            feedback = "Boa cobertura dos critérios esperados. Ainda revise qualquer evidência ausente antes de considerar o domínio consolidado."
        elif result == "PARTIAL":
            feedback = "A resposta demonstra parte do raciocínio, mas ainda faltam critérios importantes; a próxima avaliação deve explorar essas lacunas."
        elif result == "INSUFFICIENT":
            feedback = "A resposta é curta demais para demonstrar raciocínio profissional; explique contexto, evidências, invalidação e limites."
        else:
            feedback = "A resposta não demonstrou evidência suficiente. Refaça o raciocínio separando hipótese, evidência, contraevidência e risco."

        return AnswerAssessment(
            result=result,
            score=round(coverage * 100, 2),
            covered_evidence=strengths,
            missing_evidence=gaps,
            strengths=strengths,
            gaps=gaps,
            feedback=feedback,
            trading_authorized=False,
        )

    @staticmethod
    def grade_attempt(*, activity: LearningActivity, answer: str, evidence_based: bool) -> tuple[bool | None, str]:
        """Backward-compatible grading surface; legacy flag is only a signal."""
        if not isinstance(activity, LearningActivity):
            raise ValueError("invalid learning activity")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("answer is required")
        if evidence_based and len(answer.strip()) >= 30:
            return True, "Resposta preliminar aceita; a avaliação profissional deve verificar contexto, evidências e contraevidências."
        return False, "Reveja contexto, evidências favoráveis, contraevidências e critérios de invalidação."
