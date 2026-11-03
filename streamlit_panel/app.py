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


def show_assistant() -> None:
    st.subheader("Assistente do Ecossistema")
    st.caption("Somente leitura · não envia ordens, não movimenta dinheiro e não substitui orientação fiscal profissional.")
    try:
        conversations = api("/api/assistant/conversations").get("conversations", [])
    except Exception as exc:
        conversations = []
        st.error(str(exc))
    ids = [item.get("conversation_id") for item in conversations]
    labels = {item.get("conversation_id"): item.get("title", "Conversa") for item in conversations}
    selected = st.selectbox("Histórico", options=["__new__"] + ids, format_func=lambda value: "Nova conversa" if value == "__new__" else labels.get(value, "Conversa"))
    if st.button("Iniciar nova conversa", key="new_assistant"):
        st.session_state.assistant_conversation_id = None
        st.session_state.assistant_history = []
        st.rerun()
    cid = None if selected == "__new__" else selected
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
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def show_fiscal() -> None:
    st.subheader("Reserva Fiscal")
    st.caption("Planejamento e separação estimada. Registros estrangeiros não classificados ficam fora dos totais; nenhuma alíquota genérica é aplicada.")
    try:
        summary = api("/api/fiscal-reserve?limit=50&offset=0")
        br = summary.get("categories", {}).get("BR_DAY_TRADE", {})
        foreign = summary.get("categories", {}).get("FOREIGN_FINANCIAL_ASSET", {})
        a, b, c = st.columns(3)
        a.metric("Reserva estimada · Brasil", money(br.get("reserve_amount_brl")))
        b.metric("Resultado realizado · Brasil", money(br.get("realized_result_brl")))
        c.metric("Total atualmente calculado", money(summary.get("total_reserved_brl")))
        st.caption(f"Referência: {summary.get('as_of', '—')} · Brasil day trade · percentual aplicado: {br.get('rate', '—')}%")
        st.info(f"Exterior: {foreign.get('entries', 0)} registro(s) legado(s) · classificação pendente · fora dos totais.")
        periods = summary.get("periods", {})
        cols = st.columns(4)
        for col, period, label in zip(cols, ("day", "week", "month", "year"), ("Dia", "Semana", "Mês", "Ano")):
            item = periods.get(period, {})
            col.metric(label, money(item.get("reserve_amount_brl")))
            col.caption("Resultado: " + money(item.get("realized_result_brl")))
    except Exception as exc:
        st.error(str(exc))
        summary = {}

    with st.expander("Registrar resultado realizado · Brasil day trade"):
        with st.form("fiscal_result_form"):
            occurred_on = st.date_input("Data da realização")
            result = st.number_input("Resultado realizado (R$)", min_value=0.0, step=10.0, format="%.2f")
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
        notes = st.text_area("Observações", max_chars=1000, key="foreign_notes")
        submitted = st.form_submit_button("Guardar como pendente")
    if submitted:
        try:
            api("/api/fiscal-reserve/pending", "POST", {"reference": reference, "original_amount": amount, "original_currency": currency, "instrument": instrument, "jurisdiction": jurisdiction, "occurred_on": occurred_on.isoformat(), "notes": notes})
            st.success("Registro guardado como pendente. Nenhum cálculo foi feito.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

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
st.caption("Estado do sistema: consulte /api/health para validação operacional. Esta interface não declara o runtime online sem resposta real.")
