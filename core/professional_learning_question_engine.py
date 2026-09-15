from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QuestionType(str, Enum):
    CONTEXT = "CONTEXT"
    SCENARIO = "SCENARIO"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    EVIDENCE = "EVIDENCE"
    RISK = "RISK"
    EXECUTION_DISCIPLINE = "EXECUTION_DISCIPLINE"
    STATISTICAL_VALIDATION = "STATISTICAL_VALIDATION"
    MARKET_STRUCTURE = "MARKET_STRUCTURE"
    SELF_CRITIQUE = "SELF_CRITIQUE"


@dataclass(frozen=True)
class ProfessionalQuestion:
    question_id: str
    question_type: QuestionType
    prompt: str
    objective: str
    expected_evidence: tuple[str, ...] = ()
    difficulty: str = "ADVANCED"
    source_basis: tuple[str, ...] = ()


class ProfessionalLearningQuestionEngine:
    """Generates senior-level educational questions from validated knowledge.

    Questions are deliberately broader than recall. They test context, competing
    hypotheses, evidence quality, risk, execution discipline and statistical
    validation. The engine teaches and evaluates; it never produces a trading
    authorization.
    """

    def build(self, *, knowledge_id: str, concept: str, statement: str, context: str = "", question_types: tuple[QuestionType, ...] | None = None) -> tuple[ProfessionalQuestion, ...]:
        if not knowledge_id.strip() or not concept.strip() or not statement.strip():
            raise ValueError("knowledge_id, concept and statement are required")
        types = question_types or tuple(QuestionType)
        basis = (knowledge_id, concept)
        context_text = context.strip() or "o contexto de mercado fornecido"
        templates = {
            QuestionType.CONTEXT: (
                f"Antes de aplicar '{concept}', quais condições de mercado precisam estar presentes em {context_text} e quais condições fariam você considerar a aplicação inadequada?",
                "Avaliar contexto e limites de validade, não memorizar uma regra.",
                ("estrutura de mercado", "regime", "condições que invalidam a hipótese"),
            ),
            QuestionType.SCENARIO: (
                f"Considere um cenário em que '{statement}'. Quais evidências você procuraria antes, durante e no fechamento do movimento para distinguir uma oportunidade válida de uma aparência semelhante?",
                "Testar leitura sequencial e confirmação por evidência.",
                ("evidência anterior", "confirmação", "evidência de invalidação"),
            ),
            QuestionType.COUNTERFACTUAL: (
                f"Se a hipótese '{statement}' estiver correta, o que você esperaria observar? E se ela estiver errada, qual observação contrariaria a hipótese? Explique como diferenciaria os dois casos.",
                "Desenvolver raciocínio por hipóteses concorrentes.",
                ("hipótese", "contraevidência", "critério de invalidação"),
            ),
            QuestionType.EVIDENCE: (
                f"Quais evidências são realmente necessárias para sustentar a afirmação '{statement}', quais seriam apenas indícios e quais poderiam ser confundidas com confirmação por viés de seleção?",
                "Separar evidência, indício e narrativa.",
                ("qualidade da evidência", "viés de seleção", "contraevidência"),
            ),
            QuestionType.RISK: (
                f"Mesmo que '{concept}' pareça presente, quais riscos de contexto, execução, liquidez, tamanho da posição e invalidação precisam ser avaliados antes de considerar uma operação?",
                "Impedir que uma leitura técnica seja confundida com controle de risco.",
                ("risco máximo", "invalidação", "exposição", "custos"),
            ),
            QuestionType.EXECUTION_DISCIPLINE: (
                f"Se a leitura de '{concept}' estiver correta, quais condições objetivas devem permanecer verdadeiras até a execução e quais mudanças exigiriam aguardar ou abandonar a hipótese?",
                "Testar disciplina de execução sem transformar o professor em executor.",
                ("gatilho", "invalidação", "disciplina", "não operar"),
            ),
            QuestionType.STATISTICAL_VALIDATION: (
                f"Como você testaria se '{concept}' realmente apresenta vantagem além do acaso? Defina amostra, período, critérios de entrada e saída, custos, drawdown, resultados negativos e condições em que a vantagem desaparece.",
                "Separar uma estratégia demonstrada de uma estratégia apenas alegada.",
                ("amostra", "custos", "drawdown", "out-of-sample", "robustez"),
            ),
            QuestionType.MARKET_STRUCTURE: (
                f"Como '{concept}' se relaciona com tendência, topos e fundos, suporte/resistência, rompimento, pullback e pressão compradora/vendedora? Quais relações são causais, quais são apenas contextuais e quais não podem ser assumidas sem evidência?",
                "Avaliar relações entre componentes do mercado sem inventar causalidade.",
                ("estrutura", "relações", "causalidade", "evidência"),
            ),
            QuestionType.SELF_CRITIQUE: (
                f"Apresente a melhor argumentação a favor e a melhor argumentação contra sua própria interpretação de '{statement}'. Qual informação nova faria você mudar de opinião?",
                "Treinar revisão crítica e reduzir excesso de confiança/confirmação.",
                ("argumento contrário", "informação nova", "critério de revisão"),
            ),
        }
        result: list[ProfessionalQuestion] = []
        for index, question_type in enumerate(types, start=1):
            if question_type not in templates:
                continue
            prompt, objective, evidence = templates[question_type]
            result.append(ProfessionalQuestion(
                question_id=f"{knowledge_id}:{question_type.value.lower()}:{index}",
                question_type=question_type,
                prompt=prompt,
                objective=objective,
                expected_evidence=evidence,
                source_basis=basis,
            ))
        return tuple(result)
