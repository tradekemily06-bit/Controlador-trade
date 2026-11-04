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
        row.update({
            "Resultado (R$)": item.get("realized_result_brl"),
            "Percentual de planejamento (%)": item.get("reserve_rate"),
            "Reserva estimada (R$)": item.get("reserve_amount_brl"),
            "Status": "PLANEJAMENTO · BRASIL DAY TRADE",
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
    st.subheader("Reserva Fiscal")
    st.caption("Planejamento e separação estimada. Registros estrangeiros não classificados ficam fora dos totais; nenhuma alíquota genérica é aplicada.")
    try:
        summary = api("/api/fiscal-reserve?limit=50&offset=" + str(int(st.session_state.fiscal_history_offset)))
        br = summary.get("categories", {}).get("BR_DAY_TRADE", {})
        foreign = summary.get("categories", {}).get("FOREIGN_FINANCIAL_ASSET", {})
        a, b, c = st.columns(3)
        a.metric("Reserva estimada · Brasil", money(br.get("reserve_amount_brl")))
        b.metric("Resultado realizado · Brasil", money(br.get("realized_result_brl")))
        c.metric("Total atualmente calculado", money(summary.get("total_reserved_brl")))
        st.caption(f"Referência: {summary.get('as_of', '—')} · Brasil day trade · percentual aplicado: {br.get('rate', '—')}%")
        st.info(f"Exterior: {foreign.get('entries', 0)} registro(s) legado(s) · classificação pendente · fora dos totais.")
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

    with st.expander("Registrar resultado realizado · Brasil day trade"):
        with st.form("fiscal_result_form"):
            occurred_on = st.date_input("Data da realização")
            result = st.number_input("Resultado realizado (R$)", min_value=-1000000000000.0, max_value=1000000000000.0, step=10.0, format="%.2f", help="Permite registrar lucro ou prejuízo. Prejuízos são registrados, mas compensação ou transporte de perdas não é calculado automaticamente.")
            reference = st.text_input("Referência / comprovante", max_chars=160)
            notes = st.text_area("Observações", max_chars=1000)
            submitted = st.form_submit_button("Registrar resultado")
        if submitted:
            try:
                result_data = api("/api/fiscal-reserve/results", "POST", {"category": "BR_DAY_TRADE", "realized_result_brl": result, "reference": reference, "occurred_on": occurred_on.isoformat(), "notes": notes})
                st.success("Resultado registrado. Reserva estimada atualizada para este lançamento.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

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
            st.info(f"{preview.get('count', 0)} negócio(s) candidato(s) · moeda da conta: {account_currency or '—'} · consulta não registra nada automaticamente.")
            if candidates:
                st.dataframe([{"Data UTC": item.get("occurred_at_utc"), "Ativo": item.get("symbol"), "Ticket": item.get("ticket"), "Resultado": item.get("net_result_account_currency"), "Moeda": item.get("account_currency")} for item in candidates], use_container_width=True, hide_index=True)
                if account_currency == "BRL":
                    st.warning("A confirmação abaixo registra somente negócios que você classificar expressamente como Brasil · day trade. Confira o extrato completo: custos lançados em negócios anteriores da posição podem não estar incluídos.")
                    for candidate in candidates:
                        ticket = str(candidate.get("ticket", "")).strip()
                        if not ticket:
                            continue
                        with st.form("mt5_confirm_" + ticket):
                            st.write(f"**{candidate.get('symbol', 'Ativo')} · ticket {ticket}**")
                            st.caption(f"Data UTC: {candidate.get('occurred_at_utc', '—')} · Resultado do negócio de saída: {candidate.get('net_result_account_currency', '—')} {account_currency}")
                            classified = st.checkbox("Confirmo que este resultado pertence à categoria Brasil · day trade.", key="mt5_class_" + ticket)
                            confirmed = st.form_submit_button("Confirmar e registrar este negócio")
                        if confirmed:
                            if not classified:
                                st.error("Marque a confirmação de classificação antes de registrar.")
                            else:
                                try:
                                    result = api("/api/fiscal-reserve/mt5-confirm", "POST", {"ticket": ticket, "category": "BR_DAY_TRADE", "confirmed": True})
                                    st.success(f"Ticket {ticket} registrado. A referência impede duplicidade.")
                                    st.session_state.fiscal_mt5_confirmed_tickets = set(st.session_state.get("fiscal_mt5_confirmed_tickets", set())) | {ticket}
                                    st.rerun()
                                except Exception as exc:
                                    st.error(str(exc))
                else:
                    st.warning("A conta não está em BRL. O registro direto está bloqueado; mantenha os negócios fora dos totais até implementar e validar a entrada internacional com moeda original, classificação e conversão documentada.")
            else:
                st.caption("Nenhum negócio encerrado encontrado no período.")

    try:
        pending_data = api("/api/fiscal-reserve/pending?limit=50&offset=0")
        items = pending_data.get("items", [])
        st.markdown("#### Pendências registradas")
        if items:
            st.dataframe([{"Data": item.get("occurred_on"), "Instrumento": item.get("instrument"), "Jurisdição": item.get("jurisdiction"), "Valor": item.get("original_amount"), "Moeda": item.get("original_currency"), "Status": "PENDENTE DE CLASSIFICAÇÃO"} for item in items], use_container_width=True, hide_index=True)
            pending_ids = [item.get("pending_id") for item in items]
            selected_id = st.selectbox("Selecionar pendência para revisão", pending_ids, format_func=lambda value: next((f"{x.get('instrument')} · {x.get('jurisdiction')} · {x.get('original_amount')} {x.get('original_currency')}" for x in items if x.get("pending_id") == value), value))
            with st.expander("Registrar evidência de revisão profissional"):
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
                            st.caption(f"Registro declarado: {item.get('professional_registration')} · Evidência: {item.get('evidence_reference')}")
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

st.markdown('<div class="status-card"><span style="font-size:1.35rem;font-weight:800">Controlador-Trader</span> <span class="demo-pill" style="float:right">DEMO</span><div class="muted">Prévia Streamlit independente · Figma original preservado</div></div>', unsafe_allow_html=True)
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
