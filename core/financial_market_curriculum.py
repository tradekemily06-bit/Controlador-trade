"""Senior end-to-end financial-market curriculum.

The curriculum is a structured knowledge map, not a trading-rule catalogue.
Each domain is intended to be studied from fundamentals through professional
application, with practice, evidence, reassessment and jurisdiction-aware
updates. Completing a module never grants execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class CurriculumStage(str, Enum):
    FOUNDATION = "FOUNDATION"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    PROFESSIONAL = "PROFESSIONAL"
    CONTINUOUS_RESEARCH = "CONTINUOUS_RESEARCH"


class CurriculumDomain(str, Enum):
    PERSONAL_FINANCE = "PERSONAL_FINANCE"
    FINANCIAL_SYSTEM = "FINANCIAL_SYSTEM"
    FIXED_INCOME = "FIXED_INCOME"
    EQUITIES = "EQUITIES"
    FUNDS_ETFS = "FUNDS_ETFS"
    DERIVATIVES = "DERIVATIVES"
    MARKET_MICROSTRUCTURE = "MARKET_MICROSTRUCTURE"
    TECHNICAL_ANALYSIS = "TECHNICAL_ANALYSIS"
    FUNDAMENTAL_ANALYSIS = "FUNDAMENTAL_ANALYSIS"
    MACROECONOMICS = "MACROECONOMICS"
    QUANTITATIVE_METHODS = "QUANTITATIVE_METHODS"
    PORTFOLIO_CONSTRUCTION = "PORTFOLIO_CONSTRUCTION"
    RISK_MANAGEMENT = "RISK_MANAGEMENT"
    TRADING_METHODOLOGIES = "TRADING_METHODOLOGIES"
    PSYCHOLOGY = "PSYCHOLOGY"
    EXECUTION = "EXECUTION"
    SYSTEMATIC_TRADING = "SYSTEMATIC_TRADING"
    REGULATION_ETHICS = "REGULATION_ETHICS"
    CAREER_AND_PROFESSIONAL_PRACTICE = "CAREER_AND_PROFESSIONAL_PRACTICE"
    CONTINUOUS_RESEARCH = "CONTINUOUS_RESEARCH"


@dataclass(frozen=True)
class CurriculumModule:
    module_id: str
    title: str
    stage: CurriculumStage
    domain: CurriculumDomain
    prerequisites: tuple[str, ...]
    topics: tuple[str, ...]
    practical_competencies: tuple[str, ...]
    senior_capabilities: tuple[str, ...]
    requires_validation: bool = True
    execution_authorized: bool = False


class SeniorFinancialMarketCurriculum:
    """Build the complete learning map without pretending to know everything.

    The initial map is deliberately broad. Sources, regulations, market
    practices and newly discovered subjects can extend it through the existing
    validation and knowledge-memory pipeline instead of silently becoming
    operational rules.
    """

    def __init__(self) -> None:
        self._modules = self._build_modules()

    @property
    def modules(self) -> tuple[CurriculumModule, ...]:
        return self._modules

    def by_domain(self, domain: CurriculumDomain) -> tuple[CurriculumModule, ...]:
        return tuple(module for module in self._modules if module.domain is domain)

    def by_stage(self, stage: CurriculumStage) -> tuple[CurriculumModule, ...]:
        return tuple(module for module in self._modules if module.stage is stage)

    def get(self, module_id: str) -> CurriculumModule:
        for module in self._modules:
            if module.module_id == module_id:
                return module
        raise KeyError(module_id)

    @staticmethod
    def _module(
        module_id: str,
        title: str,
        stage: CurriculumStage,
        domain: CurriculumDomain,
        topics: Iterable[str],
        competencies: Iterable[str],
        senior: Iterable[str],
        prerequisites: Iterable[str] = (),
    ) -> CurriculumModule:
        return CurriculumModule(
            module_id=module_id,
            title=title,
            stage=stage,
            domain=domain,
            prerequisites=tuple(prerequisites),
            topics=tuple(topics),
            practical_competencies=tuple(competencies),
            senior_capabilities=tuple(senior),
        )

    def _build_modules(self) -> tuple[CurriculumModule, ...]:
        return (
            self._module(
                "FM-01", "Educação financeira pessoal", CurriculumStage.FOUNDATION,
                CurriculumDomain.PERSONAL_FINANCE,
                ("orçamento", "fluxo de caixa pessoal", "reserva de emergência", "dívidas", "juros", "inflação", "objetivos financeiros", "planejamento"),
                ("organizar receitas e despesas", "avaliar capacidade de poupança", "separar liquidez de risco"),
                ("avaliar decisões pelo custo de oportunidade", "reconhecer riscos financeiros antes de buscar retorno"),
            ),
            self._module(
                "FM-02", "Sistema financeiro e instituições", CurriculumStage.FOUNDATION,
                CurriculumDomain.FINANCIAL_SYSTEM,
                ("mercado monetário", "crédito", "câmbio", "mercado de capitais", "bancos", "corretoras", "bolsas", "custódia", "CVM", "Banco Central", "CMN", "B3"),
                ("identificar participantes e funções", "distinguir produto, intermediário, mercado e regulador"),
                ("entender incentivos, conflitos de interesse, jurisdição e estrutura institucional"),
            ),
            self._module(
                "FM-03", "Renda fixa", CurriculumStage.INTERMEDIATE,
                CurriculumDomain.FIXED_INCOME,
                ("Tesouro", "CDB", "LCI", "LCA", "CRI", "CRA", "pré-fixado", "pós-fixado", "híbrido", "CDI", "Selic", "IPCA", "marcação a mercado", "crédito", "duration"),
                ("comparar remuneração, liquidez, prazo, tributação e risco", "analisar cenários de juros"),
                ("decompor retorno em fatores de juros, crédito, liquidez, inflação e reinvestimento"),
            ),
            self._module(
                "FM-04", "Renda variável e fundos", CurriculumStage.INTERMEDIATE,
                CurriculumDomain.EQUITIES,
                ("ações", "direitos dos acionistas", "dividendos", "FIIs", "ETFs", "fundos", "índices", "custos", "liquidez"),
                ("analisar produto e exposição", "comparar diversificação e concentração"),
                ("entender o fator econômico realmente carregado pela posição e os riscos ocultos de concentração"),
            ),
            self._module(
                "FM-05", "Derivativos", CurriculumStage.ADVANCED,
                CurriculumDomain.DERIVATIVES,
                ("futuros", "opções", "forwards", "swaps", "hedge", "especulação", "payoff", "volatilidade implícita", "gregas", "margem"),
                ("mapear payoff e cenários", "distinguir hedge de especulação", "entender margem e risco de liquidação"),
                ("avaliar convexidade, volatilidade, liquidez, gap risk e risco de modelo"),
            ),
            self._module(
                "FM-06", "Microestrutura e formação de preço", CurriculumStage.ADVANCED,
                CurriculumDomain.MARKET_MICROSTRUCTURE,
                ("bid/ask", "spread", "livro de ofertas", "market makers", "fluxo", "liquidez", "slippage", "impacto", "execução"),
                ("interpretar condições de execução", "identificar deterioração de liquidez"),
                ("relacionar microestrutura ao regime e distinguir movimento de preço de condições de execução"),
            ),
            self._module(
                "FM-07", "Análise técnica e price action", CurriculumStage.INTERMEDIATE,
                CurriculumDomain.TECHNICAL_ANALYSIS,
                ("candles", "estrutura", "tendência", "topos/fundos", "suporte/resistência", "rompimento", "pullback", "reversão", "volume", "volatilidade", "pavio", "rejeição", "força", "GAB", "DDT", "pressão", "retirada de pavio", "taxa dívida"),
                ("ler contexto histórico e presente", "formular hipóteses sem depender de uma regra isolada"),
                ("avaliar relações entre sinais, contraevidência, regime e comportamento posterior sem contagem ingênua de sinais"),
            ),
            self._module(
                "FM-08", "Análise fundamentalista", CurriculumStage.ADVANCED,
                CurriculumDomain.FUNDAMENTAL_ANALYSIS,
                ("balanço", "DRE", "fluxo de caixa", "margens", "endividamento", "ROIC", "valuation", "múltiplos", "governança", "setores"),
                ("interpretar demonstrações", "comparar empresas e cenários"),
                ("separar qualidade econômica, preço, expectativas e catalisadores"),
            ),
            self._module(
                "FM-09", "Macroeconomia e mercados globais", CurriculumStage.ADVANCED,
                CurriculumDomain.MACROECONOMICS,
                ("PIB", "inflação", "juros", "bancos centrais", "política fiscal", "emprego", "crédito", "câmbio", "commodities", "curva de juros", "ciclos", "geopolítica"),
                ("interpretar indicadores e decisões de política econômica", "relacionar macro a classes de ativos"),
                ("construir cenários condicionais e reconhecer mudanças de regime sem confundir narrativa com evidência"),
            ),
            self._module(
                "FM-10", "Estatística, probabilidade e métodos quantitativos", CurriculumStage.ADVANCED,
                CurriculumDomain.QUANTITATIVE_METHODS,
                ("probabilidade", "distribuições", "variância", "correlação", "covariância", "expectância", "amostragem", "inferência", "significância", "robustez", "overfitting", "data snooping"),
                ("medir incerteza", "testar hipóteses", "interpretar métricas sem extrapolar além da amostra"),
                ("questionar causalidade, estabilidade, viés de seleção e validade fora da amostra"),
            ),
            self._module(
                "FM-11", "Construção e gestão de carteiras", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.PORTFOLIO_CONSTRUCTION,
                ("alocação de ativos", "diversificação", "rebalanceamento", "correlação", "fatores", "otimização", "benchmarks", "liquidez"),
                ("construir cenários de carteira", "avaliar concentração e exposição agregada"),
                ("pensar em risco conjunto e não em ativos isolados, inclusive sob estresse"),
            ),
            self._module(
                "FM-12", "Gestão de risco profissional", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.RISK_MANAGEMENT,
                ("position sizing", "drawdown", "risco de ruína", "alavancagem", "margem", "concentração", "correlação", "liquidez", "slippage", "custos", "stress testing", "gap risk", "risco de modelo", "risco operacional", "contraparte", "segurança", "recuperação"),
                ("mapear riscos materiais", "testar cenários adversos", "definir controles proporcionais ao contexto"),
                ("reavaliar risco quando premissas mudam e nunca confundir boa oportunidade com risco baixo"),
            ),
            self._module(
                "FM-13", "Metodologias de negociação", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.TRADING_METHODOLOGIES,
                ("scalping", "day trade", "swing", "position", "trend following", "momentum", "mean reversion", "breakout", "pullback", "reversão", "arbitragem", "sistemas discricionários", "sistemas sistemáticos"),
                ("comparar metodologias", "identificar premissas e limitações", "testar robustez"),
                ("selecionar metodologia conforme contexto, evidência e regime em vez de tratar uma estratégia como universal"),
            ),
            self._module(
                "FM-14", "Psicologia e comportamento de mercado", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.PSYCHOLOGY,
                ("vieses", "aversão à perda", "excesso de confiança", "FOMO", "revenge trading", "euforia", "pânico", "comportamento coletivo", "disciplina"),
                ("identificar vieses no processo", "separar resultado de qualidade da decisão"),
                ("considerar comportamento coletivo sem transformar sentimento em certeza direcional"),
            ),
            self._module(
                "FM-15", "Execução e pós-operação", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.EXECUTION,
                ("ordens", "pré-validação", "execução", "confirmação", "posição", "fechamento", "reconciliação", "auditoria", "WIN", "LOSS", "DRAW", "OPEN", "VOID", "NOT_EXECUTED"),
                ("operar com estado conhecido", "reconciliar resultado", "investigar falhas"),
                ("tratar execução como processo completo e fail-closed quando o estado é desconhecido"),
            ),
            self._module(
                "FM-16", "Sistemas quantitativos e automação", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.SYSTEMATIC_TRADING,
                ("dados históricos", "dados em tempo real", "backtest", "forward test", "simulação", "algoritmos", "APIs", "monitoramento", "reconciliação", "fail-safe"),
                ("avaliar sistemas sem vazamento de dados", "separar pesquisa de produção"),
                ("preservar proveniência, limites, observabilidade e segurança em cada transição"),
            ),
            self._module(
                "FM-17", "Regulação, ética e responsabilidade profissional", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.REGULATION_ETHICS,
                ("CVM", "Banco Central", "ANBIMA", "B3", "deveres profissionais", "conflitos de interesse", "compliance", "PLD/FT", "proteção de dados", "jurisdição"),
                ("identificar quando uma atividade exige autorização ou certificação", "consultar fonte regulatória atual"),
                ("nunca transformar uma lista histórica de certificações em regra universal; validar requisitos na jurisdição e data aplicáveis"),
            ),
            self._module(
                "FM-18", "Carreira no mercado financeiro", CurriculumStage.PROFESSIONAL,
                CurriculumDomain.CAREER_AND_PROFESSIONAL_PRACTICE,
                ("economia", "administração", "contabilidade", "engenharia", "matemática", "inglês", "Excel", "Python", "SQL", "networking", "estágio", "trainee", "research", "gestão", "investment banking", "comercial"),
                ("mapear competências por carreira", "avaliar vagas e requisitos atuais"),
                ("distinguir conhecimento acadêmico, competência prática, certificação, experiência e requisito regulatório"),
            ),
            self._module(
                "FM-19", "Pesquisa contínua e atualização do conhecimento", CurriculumStage.CONTINUOUS_RESEARCH,
                CurriculumDomain.CONTINUOUS_RESEARCH,
                ("fontes primárias", "pesquisa", "notícias", "livros", "vídeos", "artigos", "dados", "hipóteses", "contraevidência", "replicação", "atualização"),
                ("questionar fontes", "registrar proveniência", "testar novas afirmações antes de reutilizar"),
                ("manter conhecimento amplo sem tratar novidade como verdade e sem permitir que aprendizado conceda autorização operacional"),
            ),
        )
