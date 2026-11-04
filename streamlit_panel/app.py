from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "controlador_trader_referencia_visual.json").read_text(encoding="utf-8"))
BASE_URL = os.environ.get("CONTROLADOR_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
IDENTITY_HEADER = os.environ.get("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "").strip()
REMOTE_REQUIRED = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false").strip().lower() in {"1", "true", "yes"}
TIMEOUT = 20

st.set_page_config(page_title="Controlador-Trader · Streamlit", page_icon="C", layout="wide")

st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: #080B0F; color: #E9EEF3; }
[data-testid="stHeader"] { background: transparent; }
.block-container { max-width: 1180px; padding-top: 1.4rem; }
div[data-testid="stMetric"] { background:#161C24; border:1px solid #25303B; padding:14px; border-radius:12px; }
.stButton > button, .stFormSubmitButton > button { border:1px solid #25303B; border-radius:10px; }
.stButton > button[kind="primary"], .stFormSubmitButton > button { background:#46D6AD; color:#080B0F; border:0; font-weight:700; }
[data-baseweb="tab-list"] { gap:8px; }
[data-baseweb="tab"] { background:#161C24; border-radius:9px 9px 0 0; padding:10px 16px; }
section[data-testid="stSidebar"] { background:#10151B; border-right:1px solid #25303B; }
.status-card { border:1px solid #25303B; border-radius:14px; padding:12px 16px; background:#10151B; }
.demo-pill { display:inline-block; color:#46D6AD; border:1px solid #46D6AD66; background:#46D6AD12; border-radius:30px; padding:5px 12px; font-weight:800; font-size:12px; }
.muted { color:#7F8B97; }
</style>
""", unsafe_allow_html=True)


def api(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if REMOTE_REQUIRED:
        if not IDENTITY_HEADER:
            raise RuntimeError("A identidade confiável não foi configurada no servidor Streamlit.")
        incoming = st.context.headers
        identity = incoming.get(IDENTITY_HEADER) or incoming.get(IDENTITY_HEADER.lower())
        if not identity:
            raise RuntimeError("Acesso remoto bloqueado: identidade autenticada não chegou pelo proxy confiável.")
        headers[IDENTITY_HEADER] = identity
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            message = json.loads(detail).get("error", detail)
        except Exception:
            message = detail
        raise RuntimeError(f"API {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Runtime indisponível em {BASE_URL}: {exc.reason}") from exc


def money(value: Any) -> str:
    try:
        return f"R$ {float(value):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return "—"

def fiscal_history_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Fail closed: only the explicitly supported Brazilian category shows estimates."""
    category = str(item.get("category") or "").strip().upper()
    row = {
        "Data": item.get("occurred_on"),
        "Categoria": category or "NÃO CLASSIFICADA",
        "Resultado (R$)": "—",
        "Percentual de planejamento (%)": "—",
        "Reserva estimada (R$)": "—",
        "Referência": item.get("reference"),
        "Status": "PENDENTE DE CLASSIFICAÇÃO",
    }
    if category == "BR_DAY_TRADE":
        evidence = {}
        try:
            evidence = json.loads(str(item.get("notes") or "{}"))
            if not isinstance(evidence, dict):
                evidence = {}
        except (TypeError, ValueError):
            evidence = {}
        user_declared_pending = evidence.get("tax_classification_status") == "USER_DECLARED_PENDING_REVIEW"
        user_declared_planning = evidence.get("tax_classification_status") == "USER_DECLARED_PLANNING_ONLY"
        row.update({
            "Resultado (R$)": item.get("realized_result_brl"),
            "Status": (
                "DECLARAÇÃO DO USUÁRIO · REVISÃO PENDENTE"
                if user_declared_pending else
                "PLANEJAMENTO · DECLARAÇÃO DO USUÁRIO"
                if user_declared_planning else "PLANEJAMENTO · BRASIL DAY TRADE"
            ),
        })
        if not user_declared_pending:
            row.update({
                "Percentual de planejamento (%)": item.get("reserve_rate"),
                "Reserva estimada (R$)": item.get("reserve_amount_brl"),
            })
    return row


def _reset_assistant_conversation() -> None:
    st.session_state.assistant_conversation_id = None
    st.session_state.assistant_history = []
    st.session_state.assistant_loaded_id = None
    st.session_state.assistant_selector = "__new__"


def show_assistant() -> None:
    st.subheader("Assistente do Ecossistema")
    st.caption("Somente leitura · não envia ordens, não movimenta dinheiro e não substitui orientação fiscal profissional.")
    st.warning("Privacidade: sua pergunta e um resumo dos dados operacionais disponíveis são enviados pelo servidor à OpenAI para gerar a resposta. A chave permanece no servidor. Excluir uma conversa remove o histórico local, mas não solicita a exclusão de dados já transmitidos à OpenAI. Não envie senhas, códigos de acesso ou dados bancários sensíveis.")
    if "_assistant_pending_select_id" in st.session_state:
        st.session_state.assistant_selector = st.session_state.pop("_assistant_pending_select_id")
    try:
        conversations = api("/api/assistant/conversations").get("conversations", [])
    except Exception as exc:
        conversations = []
        st.error(str(exc))
    ids = [item.get("conversation_id") for item in conversations]
    labels = {item.get("conversation_id"): item.get("title", "Conversa") for item in conversations}
    if st.session_state.get("assistant_selector", "__new__") not in ["__new__"] + ids:
        st.session_state.assistant_selector = "__new__"
    selected = st.selectbox("Histórico", options=["__new__"] + ids, format_func=lambda value: "Nova conversa" if value == "__new__" else labels.get(value, "Conversa"), key="assistant_selector")
    if st.button("Iniciar nova conversa", key="new_assistant", on_click=_reset_assistant_conversation):
        st.rerun()
    if selected == "__new__" and st.session_state.get("assistant_last_selected") != "__new__":
        st.session_state.assistant_conversation_id = None
        st.session_state.assistant_history = []
        st.session_state.assistant_loaded_id = None
    st.session_state.assistant_last_selected = selected
    cid = None if selected == "__new__" else selected
    if cid and st.checkbox("Confirmo que desejo excluir a conversa selecionada", key="confirm_delete_assistant"):
        if st.button("Excluir conversa e mensagens locais", key="delete_assistant"):
            try:
                api("/api/assistant/conversations?conversation_id=" + urllib.parse.quote(cid), "DELETE")
                st.session_state.assistant_conversation_id = None
                st.session_state.assistant_loaded_id = None
                st.session_state.assistant_history = []
                st.session_state._assistant_pending_select_id = "__new__"
                st.success("Conversa removida do histórico local.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    if cid and st.session_state.get("assistant_loaded_id") != cid:
        try:
            st.session_state.assistant_history = api("/api/assistant/history?conversation_id=" + urllib.parse.quote(cid)).get("messages", [])
            st.session_state.assistant_loaded_id = cid
            st.session_state.assistant_conversation_id = cid
        except Exception as exc:
            st.error(str(exc))
    for message in st.session_state.get("assistant_history", []):
        with st.chat_message("assistant" if message.get("role") == "assistant" else "user"):
            st.write(message.get("content", ""))
    prompt = st.chat_input("Pergunte sobre o Ecossistema, risco ou Reserva Fiscal")
    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        try:
            response = api("/api/assistant/chat", "POST", {"message": prompt, "conversation_id": st.session_state.get("assistant_conversation_id")})
            st.session_state.assistant_conversation_id = response.get("conversation_id")
            with st.chat_message("assistant"):
                st.write(response.get("answer", "Sem resposta."))
            st.session_state.assistant_history = api("/api/assistant/history?conversation_id=" + urllib.parse.quote(response["conversation_id"])).get("messages", [])
            st.session_state.assistant_loaded_id = response["conversation_id"]
            st.session_state._assistant_pending_select_id = response["conversation_id"]
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def show_fiscal() -> None:
    if "fiscal_history_offset" not in st.session_state:
        st.session_state.fiscal_history_offset = 0
    try:
        summary = api("/api/fiscal-reserve?limit=50&offset=" + str(int(st.session_state.fiscal_history_offset)))
    except Exception as exc:
        summary = {}
        st.error(str(exc))
    st.subheader("Reserva Fiscal")
    st.caption("Planejamento e separação estimada. Operações MT5 cuja elegibilidade fiscal não foi verificada ficam em fila brasileira separada, sem cálculo e fora dos totais. Registros estrangeiros não classificados também ficam fora dos totais; nenhuma alíquota genérica é aplicada.")
    with st.expander("Categorias fiscais e estado da automação", expanded=False):
        try:
            catalog = summary.get("classification_catalog", {})
            st.caption("Catálogo de organização, não é cálculo tributário. Categorias sem automação permanecem pendentes e fora dos totais.")
            for scope, title in (("brazil", "Brasil"), ("foreign", "Exterior")):
                st.markdown("**" + title + "**")
                for category, details in catalog.get(scope, {}).items():
                    status = details.get("calculation_status", "NOT_AUTOMATED")
                    enabled = bool(details.get("booking_enabled", False))
                    state_label = "Lançamento parcial habilitado" if enabled else "Pendente · sem cálculo automático"
                    st.write(f"- **{details.get('label', category)}** — {state_label}")
                    for limitation in details.get("limitations", []):
                        st.caption(limitation)
        except Exception:
            st.warning("Catálogo de categorias indisponível no momento. Nenhuma categoria adicional foi habilitada.")
    try:
        br = summary.get("categories", {}).get("BR_DAY_TRADE", {})
        foreign = summary.get("categories", {}).get("FOREIGN_FINANCIAL_ASSET", {})
        a, b, c = st.columns(3)
        a.metric("Reserva estimada · Brasil", money(br.get("reserve_amount_brl")))
        b.metric("Resultado realizado · Brasil", money(br.get("realized_result_brl")))
        c.metric("Total atualmente calculado", money(summary.get("total_reserved_brl")))
        st.caption(f"Referência: {summary.get('as_of', '—')} · Brasil day trade · percentual aplicado: {br.get('rate', '—')}%")
        st.info(f"Exterior: {foreign.get('entries', 0)} registro(s) legado(s) · classificação pendente · fora dos totais.")
        foreign_pending = summary.get("foreign_pending", {})
        if foreign_pending.get("available") is False:
            st.warning("A contagem das pendências do exterior está indisponível. Nenhum registro foi incluído nos totais.")
        else:
            pending_periods = foreign_pending.get("periods", {})
            pending_cols = st.columns(4)
            for col, period, label in zip(pending_cols, ("day", "week", "month", "year"), ("Dia", "Semana", "Mês", "Ano")):
                pending_period = pending_periods.get(period, {})
                col.metric(f"Exterior pendente · {label}", int(pending_period.get("total", 0)))
                col.caption(
                    f"{int(pending_period.get('realized_results', 0))} resultado(s) · "
                    f"{int(pending_period.get('asset_amounts', 0))} ativo(s) · sem cálculo"
                )
        fiscal_history = summary.get("history", [])
        st.markdown("#### Histórico da Reserva Fiscal")
        if fiscal_history:
            st.dataframe(
                [fiscal_history_display_row(item) for item in fiscal_history],
                use_container_width=True,
                hide_index=True,
            )
            page = summary.get("history_page", {})
            st.caption(f"Exibindo {page.get('returned', len(fiscal_history))} de {page.get('total', len(fiscal_history))} registros.")
            previous_col, next_col = st.columns(2)
            with previous_col:
                if st.button("← Histórico anterior", disabled=int(page.get("offset", 0)) <= 0, key="fiscal_history_previous"):
                    st.session_state.fiscal_history_offset = max(0, int(page.get("offset", 0)) - int(page.get("limit", 50)))
                    st.rerun()
            with next_col:
                if st.button("Próximos registros →", disabled=not page.get("has_more", False), key="fiscal_history_next"):
                    st.session_state.fiscal_history_offset = int(page.get("offset", 0)) + int(page.get("limit", 50))
                    st.rerun()
        else:
            st.caption("Nenhum resultado registrado no livro fiscal.")
        periods = summary.get("periods", {})
        cols = st.columns(4)
        for col, period, label in zip(cols, ("day", "week", "month", "year"), ("Dia", "Semana", "Mês", "Ano")):
            item = periods.get(period, {})
            col.metric(label, money(item.get("reserve_amount_brl")))
            col.caption("Resultado: " + money(item.get("realized_result_brl")))
    except Exception as exc:
        st.error(str(exc))
        summary = {}

    with st.expander("Percentual de planejamento · Brasil day trade"):
        current_rate = summary.get("categories", {}).get("BR_DAY_TRADE", {}).get("rate", 0) if summary else 0
        with st.form("fiscal_rate_form"):
            rate = st.number_input("Percentual para novos lançamentos", min_value=0.0, max_value=100.0, value=float(current_rate or 0), step=0.5)
            rate_submit = st.form_submit_button("Salvar percentual")
        if rate_submit:
            try:
                api("/api/fiscal-reserve/rates", "POST", {"rates": {"BR_DAY_TRADE": rate}})
                st.success("Percentual atualizado para novos registros. O histórico preserva o percentual usado em cada lançamento.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with st.expander("Registrar estimativa · Brasil day trade"):
        st.caption("Use somente se você puder confirmar os critérios abaixo. É uma estimativa de planejamento baseada na sua declaração; não valida o enquadramento nem confirma imposto devido. Se houver dúvida, registre na fila brasileira pendente.")
        with st.form("fiscal_result_form"):
            occurred_on = st.date_input("Data da realização")
            instrument = st.text_input("Ativo / instrumento negociado", max_chars=80)
            institution = st.text_input("Instituição intermediária", max_chars=120)
            market_label = st.text_input("Mercado / ambiente de negociação", max_chars=120, placeholder="Ex.: B3")
            result = st.number_input("Resultado realizado (R$)", min_value=-1000000000000.0, max_value=1000000000000.0, step=10.0, format="%.2f", help="Lucro positivo / prejuízo negativo. Compensações mensais e créditos de IRRF não são calculados.")
            reference = st.text_input("Referência / comprovante", max_chars=160)
            notes = st.text_area("Observações / evidências", max_chars=600)
            confirmed = st.checkbox("Confirmo que foi o mesmo ativo, pela mesma instituição, no mesmo dia e em mercado brasileiro elegível.")
            submitted = st.form_submit_button("Registrar estimativa de planejamento")
        if submitted:
            try:
                result_data = api("/api/fiscal-reserve/results", "POST", {
                    "category": "BR_DAY_TRADE", "realized_result_brl": result,
                    "reference": reference, "occurred_on": occurred_on.isoformat(),
                    "instrument": instrument, "institution": institution,
                    "market_label": market_label,
                    "market_scope": "BR_ELIGIBLE_MARKET" if confirmed else "",
                    "same_asset": confirmed, "same_institution": confirmed, "same_day": confirmed,
                    "confirmed": confirmed, "notes": notes,
                })
                st.success("Estimativa de planejamento registrada. Ela não representa imposto apurado ou devido.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown("#### Brasil · pendente de classificação")
    st.caption("Esta fila é separada do exterior. Guarda evidências brasileiras sem aplicar alíquota ou incluir valores na reserva.")
    with st.form("domestic_pending_form"):
        domestic_ref = st.text_input("Referência / comprovante · Brasil", max_chars=160)
        domestic_instrument = st.text_input("Ativo ou instrumento · Brasil", max_chars=80)
        domestic_category = st.selectbox("Categoria candidata · não confirmada", ["", "BR_COMMON_EXCHANGE", "BR_FII_FIAGRO", "BR_FIXED_INCOME", "BR_CRYPTO", "BR_FUTURES_OPTIONS", "BR_DAY_TRADE"])
        domestic_market = st.text_input("Mercado / ambiente", placeholder="B3, balcão, corretora etc.", max_chars=80)
        domestic_date = st.date_input("Data da operação · Brasil", key="domestic_pending_date")
        domestic_has_result = st.checkbox("Informar resultado realizado em R$ (inclusive zero)", value=False, key="domestic_has_result")
        domestic_result = st.number_input("Resultado realizado em R$ (lucro + / prejuízo -)", min_value=-1000000000000.0, max_value=1000000000000.0, value=0.0, format="%.2f", disabled=not domestic_has_result, help="O valor fica pendente e não entra nos totais nem gera reserva.")
        domestic_notes = st.text_area("Observações / evidências", key="domestic_pending_notes", max_chars=1000)
        domestic_submit = st.form_submit_button("Guardar pendência brasileira")
    if domestic_submit:
        try:
            domestic_payload = {"reference": domestic_ref, "instrument": domestic_instrument, "category_candidate": domestic_category, "market_scope": domestic_market, "occurred_on": domestic_date.isoformat(), "notes": domestic_notes}
            if domestic_has_result:
                domestic_payload["realized_result_brl"] = domestic_result
            api("/api/fiscal-reserve/domestic-pending", "POST", domestic_payload)
            st.success("Pendência brasileira guardada separadamente. Nenhum cálculo foi realizado.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    try:
        domestic_data = api("/api/fiscal-reserve/domestic-pending?limit=50&offset=0")
        domestic_items = domestic_data.get("items", [])
        domestic_summary = api("/api/fiscal-reserve/domestic-pending/summary")
        domestic_cols = st.columns(4)
        for col, period, label in zip(domestic_cols, ("day", "week", "month", "year"), ("Dia", "Semana", "Mês", "Ano")):
            period_data = domestic_summary.get("periods", {}).get(period, {})
            col.metric(f"Brasil pendente · {label}", int(period_data.get("total", 0)))
            col.caption(f"{int(period_data.get('results', 0))} resultado(s) · sem cálculo")
        if domestic_items:
            st.dataframe([{"Data": item.get("occurred_on"), "Ativo": item.get("instrument"), "Categoria candidata": item.get("category_candidate") or "Não informada", "Mercado": item.get("market_scope"), "Resultado (R$)": item.get("realized_result_brl") if item.get("realized_result_brl") is not None else "—", "Status": "PENDENTE DE CLASSIFICAÇÃO"} for item in domestic_items], use_container_width=True, hide_index=True)
        else:
            st.caption("Nenhuma pendência brasileira cadastrada.")
    except Exception as exc:
        st.warning(f"Fila brasileira indisponível; nenhum registro foi incluído nos totais. {exc}")

    st.markdown("#### Exterior · pendente de classificação")
    st.caption("O registro abaixo guarda evidências; não calcula imposto nem entra na reserva.")
    with st.form("foreign_pending_form"):
        col1, col2 = st.columns(2)
        reference = col1.text_input("Referência / comprovante", max_chars=160)
        amount = col2.number_input("Valor original", min_value=0.00000001, step=1.0, format="%.8f")
        col3, col4 = st.columns(2)
        currency = col3.selectbox("Moeda", ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "BRL"])
        instrument = col4.text_input("Instrumento", placeholder="ETF, ação, Forex, CFD, cripto")
        col5, col6 = st.columns(2)
        jurisdiction = col5.text_input("Jurisdição", placeholder="EUA, Brasil, outro")
        occurred_on = col6.date_input("Data da operação", key="foreign_date")
        fx_rate = st.number_input("Cotação cambial (opcional)", min_value=0.0, step=0.0001, format="%.8f")
        fx_date = st.date_input("Data da cotação", key="foreign_fx_date")
        fx_source = st.text_input("Fonte da cotação (opcional)", max_chars=200)
        notes = st.text_area("Observações", max_chars=1000, key="foreign_notes")
        submitted = st.form_submit_button("Guardar como pendente")
    if submitted:
        try:
            pending_payload = {"reference": reference, "original_amount": amount, "original_currency": currency, "instrument": instrument, "jurisdiction": jurisdiction, "occurred_on": occurred_on.isoformat(), "notes": notes}
            if fx_rate or fx_source:
                if not fx_rate or not fx_source:
                    raise ValueError("Para guardar a cotação, informe valor e fonte.")
                pending_payload.update({"fx_rate": fx_rate, "fx_date": fx_date.isoformat(), "fx_source": fx_source})
            api("/api/fiscal-reserve/pending", "POST", pending_payload)
            st.success("Registro guardado como pendente. Nenhum cálculo foi feito.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.markdown("#### Resultado realizado no exterior")
    st.caption("Informe lucro positivo ou prejuízo negativo. O valor original fica pendente e não entra na reserva.")
    with st.form("foreign_signed_result"):
        ref_signed = st.text_input("Referência do extrato", max_chars=160)
        amount_signed = st.number_input("Resultado original (+ lucro / - prejuízo)", min_value=-1000000000000.0, max_value=1000000000000.0, value=0.0, format="%.8f")
        currency_signed = st.selectbox("Moeda original", ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "BRL"])
        instrument_signed = st.text_input("Instrumento")
        jurisdiction_signed = st.text_input("Jurisdição")
        date_signed = st.date_input("Data do resultado", key="signed_foreign_date")
        fx_signed = st.number_input("Cotação documentada (opcional)", min_value=0.0, format="%.8f")
        fx_date_signed = st.date_input("Data da cotação", key="signed_foreign_fx_date")
        fx_source_signed = st.text_input("Fonte da cotação")
        notes_signed = st.text_area("Observações")
        submit_signed = st.form_submit_button("Guardar como pendente")
    if submit_signed:
        try:
            signed_payload = {"reference": ref_signed, "original_result": amount_signed, "original_currency": currency_signed, "instrument": instrument_signed, "jurisdiction": jurisdiction_signed, "occurred_on": date_signed.isoformat(), "notes": notes_signed}
            if fx_signed or fx_source_signed:
                if not fx_signed or not fx_source_signed:
                    raise ValueError("Informe cotação e fonte juntas.")
                signed_payload.update({"fx_rate": fx_signed, "fx_date": fx_date_signed.isoformat(), "fx_source": fx_source_signed})
            api("/api/fiscal-reserve/pending-result", "POST", signed_payload)
            st.success("Resultado guardado com o sinal original; continua fora dos totais.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.caption("Resultados estrangeiros com sinal original serão mantidos em pendência, fora dos totais até revisão.")

    with st.expander("Prévia de negócios encerrados · MT5 DEMO"):
        lookback = st.number_input("Período de consulta (dias)", min_value=1, max_value=365, value=30, step=1)
        if st.button("Consultar MT5 DEMO", key="mt5_fiscal_preview"):
            try:
                preview = api("/api/fiscal-reserve/mt5-preview?lookback_days=" + str(int(lookback)))
                st.session_state.fiscal_mt5_preview = preview
                st.session_state.fiscal_mt5_confirmed_tickets = set()
            except Exception as exc:
                st.error(str(exc))

        preview = st.session_state.get("fiscal_mt5_preview")
        if preview:
            candidates = preview.get("candidates", [])
            account_currency = str(preview.get("account_currency", "")).upper()
            st.info(f"{preview.get('count', 0)} posição(ões) integralmente encerrada(s) e conciliada(s) · moeda da conta: {account_currency or '—'} · consulta não registra nada automaticamente.")
            if preview.get("withheld_incomplete_positions", 0):
                st.warning(f"{preview.get('withheld_incomplete_positions')} posição(ões) retida(s): aberta(s), com histórico incompleto ou volume sem conciliação. Não serão oferecidas para lançamento.")
            if candidates:
                st.dataframe([{"Abertura UTC": item.get("opened_at_utc"), "Encerramento UTC": item.get("occurred_at_utc"), "Ativo": item.get("symbol"), "Ticket final": item.get("ticket"), "Negócios somados": item.get("deal_count"), "Saídas": item.get("closing_deal_count"), "Resultado líquido da posição": item.get("net_result_account_currency"), "Moeda": item.get("account_currency")} for item in candidates], use_container_width=True, hide_index=True)
                if account_currency == "BRL":
                    st.warning("A confirmação abaixo registra somente posições que você classificar expressamente como Brasil · day trade. O resultado agrega os negócios da posição e concilia os volumes; confira o extrato da corretora antes de confirmar.")
                    for candidate in candidates:
                        ticket = str(candidate.get("ticket", "")).strip()
                        if not ticket:
                            continue
                        with st.form("mt5_confirm_" + ticket):
                            st.write(f"**{candidate.get('symbol', 'Ativo')} · ticket {ticket}**")
                            st.caption(f"Encerramento UTC: {candidate.get('occurred_at_utc', '—')} · Resultado líquido da posição: {candidate.get('net_result_account_currency', '—')} {account_currency} · Negócios somados: {candidate.get('deal_count', '—')}")
                            classified = st.checkbox("Confirmo que a operação ocorreu em mercado brasileiro elegível e atende ao conceito fiscal de day trade: mesmo ativo, mesma instituição e mesmo dia.", key="mt5_class_" + ticket)
                            confirmed = st.form_submit_button("Confirmar e registrar esta posição")
                        if confirmed:
                            if not classified:
                                st.error("Marque a confirmação de classificação antes de registrar.")
                            else:
                                try:
                                    result = api("/api/fiscal-reserve/mt5-confirm", "POST", {"ticket": ticket, "category": "BR_DAY_TRADE", "market_scope": "BR_ELIGIBLE_MARKET", "confirmed": True})
                                    st.success(f"Ticket {ticket} registrado. A referência impede duplicidade.")
                                    st.session_state.fiscal_mt5_confirmed_tickets = set(st.session_state.get("fiscal_mt5_confirmed_tickets", set())) | {ticket}
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))
                else:
                    st.warning("A conta não está em BRL. As posições conciliadas podem ser guardadas somente como pendências, com moeda e resultado original; nenhum imposto ou conversão será calculado.")
                    for candidate in candidates:
                        ticket = str(candidate.get("ticket", "")).strip()
                        if not ticket:
                            continue
                        with st.form("mt5_foreign_pending_" + ticket):
                            st.write(f"**{candidate.get('symbol', 'Ativo')} · ticket {ticket}**")
                            st.caption(f"Encerramento UTC: {candidate.get('occurred_at_utc', '—')} · Resultado líquido da posição: {candidate.get('net_result_account_currency', '—')} {account_currency} · Negócios somados: {candidate.get('deal_count', '—')}")
                            pending_confirm = st.checkbox("Confirmo que quero guardar este negócio como pendência fiscal, sem classificação ou cálculo.", key="mt5_foreign_pending_confirm_" + ticket)
                            pending_submit = st.form_submit_button("Guardar como pendência")
                        if pending_submit:
                            if not pending_confirm:
                                st.error("Confirme antes de guardar a pendência.")
                            else:
                                try:
                                    result = api("/api/fiscal-reserve/mt5-pending-result", "POST", {"ticket": ticket, "confirmed": True})
                                    st.success(f"Posição {ticket} guardada como pendência. Resultado original preservado; sem cálculo fiscal.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))
            else:
                st.caption("Nenhuma posição elegível encontrada. Se houver posições retidas, consulte o motivo antes de qualquer lançamento.")

    try:
        pending_data = api("/api/fiscal-reserve/pending?limit=50&offset=0")
        items = pending_data.get("items", [])
        st.markdown("#### Pendências registradas")
        if items:
            st.dataframe([{"Data": item.get("occurred_on"), "Instrumento": item.get("instrument"), "Jurisdição": item.get("jurisdiction"), "Valor original": item.get("original_result") if item.get("record_kind") == "REALIZED_RESULT" else item.get("original_amount"), "Tipo": item.get("record_kind", "ASSET_AMOUNT"), "Moeda": item.get("original_currency"), "Status": "PENDENTE DE CLASSIFICAÇÃO"} for item in items], use_container_width=True, hide_index=True)
            pending_ids = [item.get("pending_id") for item in items]
            selected_id = st.selectbox("Selecionar pendência para revisão", pending_ids, format_func=lambda value: next((f"{x.get('instrument')} · {x.get('jurisdiction')} · {x.get('original_result') if x.get('record_kind') == 'REALIZED_RESULT' else x.get('original_amount')} {x.get('original_currency')}" for x in items if x.get("pending_id") == value), value))
            with st.expander("Registrar evidência de revisão profissional"):
                st.warning("Identidade e registro profissional são declarados pelo usuário; o sistema não verifica credenciais. A revisão é evidência documental, não validação fiscal automática.")
                with st.form("professional_review_form"):
                    classification = st.text_input("Classificação sugerida")
                    confirmed_jurisdiction = st.text_input("Jurisdição indicada na revisão")
                    reviewer_name = st.text_input("Nome do profissional")
                    role = st.selectbox("Qualificação", ["contador", "consultor tributário", "profissional tributário"])
                    registration = st.text_input("Registro profissional declarado")
                    reviewed_on = st.date_input("Data da revisão", key="review_date")
                    evidence = st.text_input("Parecer ou referência da evidência")
                    review_notes = st.text_area("Observações da revisão")
                    review_submit = st.form_submit_button("Guardar revisão")
                if review_submit:
                    try:
                        review = {"candidate_classification": classification, "confirmed_jurisdiction": confirmed_jurisdiction, "reviewer_name": reviewer_name, "reviewer_role": role, "professional_registration": registration, "reviewed_on": reviewed_on.isoformat(), "evidence_reference": evidence, "review_notes": review_notes}
                        api(f"/api/fiscal-reserve/pending/{urllib.parse.quote(selected_id)}/reviews", "POST", review)
                        st.success("Revisão registrada. A pendência continua fora dos cálculos.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            try:
                history = api(f"/api/fiscal-reserve/pending/{urllib.parse.quote(selected_id)}/reviews").get("reviews", [])
                with st.expander("Histórico de revisões"):
                    if history:
                        for item in history:
                            st.write(f"{item.get('reviewed_on')} · {item.get('reviewer_name')} · {item.get('candidate_classification')} · {item.get('confirmed_jurisdiction')}")
                            st.caption(f"Registro declarado (não verificado): {item.get('professional_registration')} · Evidência: {item.get('evidence_reference')} · Situação: {item.get('reviewer_identity_status', 'DECLARED_NOT_VERIFIED')}")
                    else:
                        st.caption("Nenhuma revisão registrada.")
            except Exception as exc:
                st.warning(str(exc))
        else:
            st.caption("Nenhuma pendência cadastrada.")
    except Exception as exc:
        st.warning(str(exc))


AREAS = CONFIG["open_state"]["tabs"]
if "panel_open" not in st.session_state:
    st.session_state.panel_open = True
if not st.session_state.panel_open:
    if st.button("C", key="open_control_hub"):
        st.session_state.panel_open = True
        st.rerun()
    st.caption("INDISPONÍVEL")
    st.stop()

st.markdown('<div class="status-card"><span style="font-size:1.35rem;font-weight:800">Controlador-Trader</span> <span class="demo-pill" style="float:right">DEMO</span><div class="muted">Área funcional de desenvolvimento · não é a reprodução visual aprovada do Figma</div></div>', unsafe_allow_html=True)
st.warning("A referência JSON de navegação está carregada, mas as cinco imagens originais (8870.jpg, 8871.jpg, 8872.jpg, 8873.jpg e 8878.jpg) não estão presentes neste branch. Portanto, esta tela não deve ser tratada como validação visual nem como substituta do painel aprovado.")
area = st.radio("Áreas principais", list(AREAS), horizontal=True, label_visibility="collapsed")
st.divider()
module = st.radio("Módulos", AREAS[area], horizontal=False, label_visibility="collapsed")

if area == "MAIS / ADMIN" and module == "Financeiro":
    financial = st.radio("Financeiro", ["Reserva Fiscal", "Assistente do Ecossistema"], horizontal=True)
    if financial == "Reserva Fiscal":
        show_fiscal()
    else:
        show_assistant()
elif module == "Assistente do Ecossistema":
    show_assistant()
elif module == "Reserva Fiscal":
    show_fiscal()
else:
    st.info(f"Módulo {module} selecionado. A integração funcional deste módulo ainda não foi habilitada nesta prévia.")
    if module in {"MT5 DEMO / Simulação", "Operação"}:
        st.warning("Execução real permanece bloqueada. Esta prévia não envia ordens.")
    st.markdown('<div class="status-card"><b>Estado do sistema:</b> INDISPONÍVEL · <b>REAL:</b> DESABILITADO</div>', unsafe_allow_html=True)

st.divider()
left, right = st.columns([2, 1])
with left:
    st.markdown('<div class="status-card"><b>Estado do sistema:</b> INDISPONÍVEL<br><b>REAL:</b> DESABILITADO</div>', unsafe_allow_html=True)
with right:
    st.checkbox("Alavancagem", value=False, disabled=True, help="Controle visual nesta prévia; não altera a conta MT5.")
    if st.button("C · Fechar painel", key="close_control_hub"):
        st.session_state.panel_open = False
        st.rerun()
st.caption("Estado do sistema: consulte /api/health para validação operacional. Esta interface não declara o runtime online sem resposta real.")
