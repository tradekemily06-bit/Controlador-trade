"""Explicit fiscal classification catalog.

The catalog contains no tax rates and does not itself authorize ledger writes.
A booking-enabled category only signals a separate, limited planning workflow;
unsupported or unconfirmed events remain pending.
"""
from __future__ import annotations

from typing import Any


CATALOG_VERSION = "2026-11-14.1"

# The categories are intake/classification lanes, not claims that every event
# in the lane has one universal tax treatment.
BRAZIL_CATEGORIES: dict[str, dict[str, Any]] = {
    "BR_DAY_TRADE": {
        "label": "Brasil · day trade",
        "scope": "BR",
        "instrument_families": ["ações", "derivativos", "mercados elegíveis"],
        "requires": ["mesmo_ativo", "mesma_instituicao", "mesmo_dia", "mercado_elegivel"],
        "calculation_status": "PARTIAL_PLANNING_ONLY",
        "booking_enabled": True,
        "limitations": [
            "Apenas confirmação explícita e posição DEMO conciliada no fluxo atual.",
            "Não calcula compensação mensal de prejuízos nem créditos de IRRF.",
        ],
    },
    "BR_COMMON_EXCHANGE": {
        "label": "Brasil · operações comuns em bolsa",
        "scope": "BR",
        "instrument_families": ["ações", "ETFs", "BDRs", "opções", "termo"],
        "requires": ["mercado_elegivel", "tipo_de_operacao", "custos", "apuracao_mensal"],
        "calculation_status": "NOT_AUTOMATED",
        "booking_enabled": False,
        "limitations": ["Exige apuração mensal, segregação por natureza e regras de compensação."],
    },
    "BR_FII_FIAGRO": {
        "label": "Brasil · FII/FIAGRO",
        "scope": "BR",
        "instrument_families": ["FII", "FIAGRO"],
        "requires": ["tipo_de_rendimento", "condicoes_de_isencao", "evento"],
        "calculation_status": "NOT_AUTOMATED",
        "booking_enabled": False,
        "limitations": ["Rendimentos e ganhos na alienação têm tratamentos distintos e condições próprias."],
    },
    "BR_FIXED_INCOME": {
        "label": "Brasil · renda fixa",
        "scope": "BR",
        "instrument_families": ["CDB", "Tesouro Direto", "LCI", "LCA", "debêntures"],
        "requires": ["produto", "prazo", "evento", "retencao_na_fonte"],
        "calculation_status": "NOT_AUTOMATED",
        "booking_enabled": False,
        "limitations": ["Regime e eventual isenção dependem do produto e do evento."],
    },
    "BR_CRYPTO": {
        "label": "Brasil · criptoativos",
        "scope": "BR",
        "instrument_families": ["criptoativos", "ativos virtuais"],
        "requires": ["custodia", "local_da_operacao", "tipo_de_evento", "valor_mensal"],
        "calculation_status": "NOT_AUTOMATED",
        "booking_enabled": False,
        "limitations": ["Regras de declaração e tributação dependem da operação e da custódia."],
    },
    "BR_FUTURES_OPTIONS": {
        "label": "Brasil · futuros e opções",
        "scope": "BR",
        "instrument_families": ["contratos futuros", "opções", "derivativos"],
        "requires": ["contrato", "mercado", "tipo_de_operacao", "apuracao_mensal"],
        "calculation_status": "NOT_AUTOMATED",
        "booking_enabled": False,
        "limitations": ["Não presumir tratamento comum ou day trade sem qualificação do contrato e mercado."],
    },
}

FOREIGN_CATEGORIES: dict[str, dict[str, Any]] = {
    "FOREIGN_FINANCIAL_INVESTMENT": {
        "label": "Exterior · aplicação financeira",
        "scope": "FOREIGN",
        "requires": ["residencia_fiscal", "natureza_do_rendimento", "evento", "moeda", "fx_method", "instituicao_ou_autocustodia", "local_custodia", "tipo_de_contrato"],
        "recommended_evidence": ["custo_de_aquisicao", "taxas_e_custos", "imposto_pago_no_exterior", "extrato_da_instituicao"],
        "calculation_status": "PARTIAL_PLANNING_ONLY",
        "booking_enabled": True,
        "limitations": [
            "Estimativa de 15% somente para resultado realizado, residência fiscal brasileira declarada e confirmação explícita desta categoria.",
            "Exige cotação documentada convertida para BRL; ajuste anual, sem compensação de perdas ou créditos de imposto estrangeiro.",
            "Não é apuração tributária; criptoativos, entidades controladas e eventos não suportados permanecem pendentes.",
        ],
    },
    "FOREIGN_ENTITY_CONTROLLED": {
        "label": "Exterior · entidade controlada",
        "scope": "FOREIGN",
        "requires": ["controle", "entidade", "lucro", "evento", "documentacao"],
        "calculation_status": "NOT_AUTOMATED",
        "booking_enabled": False,
        "limitations": ["Regime específico; não confundir com aplicação financeira direta."],
    },
    "FOREIGN_CRYPTO": {
        "label": "Exterior · criptoativos",
        "scope": "FOREIGN",
        "requires": ["custodia", "local_da_operacao", "evento", "moeda", "fx_method", "instituicao_ou_autocustodia"],
        "recommended_evidence": ["identificacao_do_criptoativo", "historico_de_transacoes", "taxas_e_custos", "imposto_pago_no_exterior"],
        "calculation_status": "NOT_AUTOMATED",
        "booking_enabled": False,
        "limitations": ["Exige determinar custódia, localização e natureza do evento."],
    },
}


def fiscal_classification_catalog() -> dict[str, Any]:
    """Return a copy-safe catalog for UI/assistant; never expose a default rate."""
    def copy_group(group: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            key: {
                **item,
                "instrument_families": list(item.get("instrument_families", [])),
                "requires": list(item["requires"]),
                "limitations": list(item["limitations"]),
                "recommended_evidence": list(item.get("recommended_evidence", [])),
            }
            for key, item in group.items()
        }

    return {
        "version": CATALOG_VERSION,
        "purpose": "CLASSIFICATION_ONLY",
        "tax_rates_included": False,
        "brazil": copy_group(BRAZIL_CATEGORIES),
        "foreign": copy_group(FOREIGN_CATEGORIES),
        "safety": {
            "unknown_category": "PENDING_CLASSIFICATION",
            "unimplemented_category": "PENDING_CLASSIFICATION",
            "pending_included_in_totals": False,
            "pending_reserve_calculated": False,
        },
    }
