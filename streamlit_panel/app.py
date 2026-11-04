from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import streamlit as st

from presentation import closed_panel_signal

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
.block-container { width: 100%; max-width: none; padding: 1rem clamp(.75rem, 2vw, 1.5rem) 6rem; }
.st-key-panel-toggle { position: fixed; left: 18px; bottom: 14px; z-index: 1000; width: 220px; display: flex; flex-direction: row; align-items: center; gap: 8px; }
.st-key-panel-toggle .stButton > button { width: 48px; min-width: 48px; height: 48px; min-height: 48px; padding: 0; border-radius: 50%; background: #080B0F; color: #46D6AD; border: 1px solid #46D6AD; box-shadow: 0 0 10px #46D6AD33; font-weight: 800; }
.st-key-panel-toggle .closed-signal { width: 150px; display: flex; flex-direction: column; align-items: center; gap: 1px; white-space: nowrap; text-align: center; font-size: 10px; line-height: 1.2; text-shadow: 0 1px 4px #080B0F; }\n.st-key-panel-toggle .closed-signal strong { font-size: 10px; font-weight: 800; }
*, *::before, *::after { box-sizing: border-box; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stMainBlockContainer"] { min-width: 0; }
[data-testid="stDataFrame"], [data-testid="stTable"], .status-card { max-width: 100%; }
[data-baseweb="tab-list"], [role="radiogroup"] { flex-wrap: wrap; }
.stMarkdown, .stCaption, [data-testid="stMetric"] { min-width: 0; overflow-wrap: anywhere; }
@media (max-width: 720px) {
  .block-container { padding: .75rem .65rem 1.25rem; }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .5rem; }
  [data-testid="column"] { min-width: min(100%, 14rem); }
  [data-testid="stDataFrame"] { overflow-x: auto; }
}
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


def save_leverage_preference() -> None:
    """Persist only the user's leverage preference; it never grants execution authority."""
    try:
        api(
            "/api/preferences",
            "POST",
            {"leverage_enabled": bool(st.session_state.get("leverage_enabled", False))},
        )
        st.session_state.leverage_preference_error = ""
    except Exception as exc:
        st.session_state.leverage_preference_error = str(exc)
        try:
            saved = api("/api/preferences").get("preferences", {})
            st.session_state.leverage_enabled = saved.get("leverage_enabled") is True
        except Exception:
            st.session_state.leverage_enabled = False


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
    """Start a fresh assistant session without exposing stored conversation history."""
    st.session_state.assistant_conversation_id = None
    st.session_state.assistant_history = []


def show_assistant() -> None:
    st.subheader("Assistente do Ecossistema")
    st.caption("Somente leitura · não envia ordens, não movimenta dinheiro e não substitui orientação fiscal profissional.")
    assistant_available = False
    try:
        readiness = api("/api/assistant/status")
        assistant_available = readiness.get("available") is True
        if not assistant_available:
            st.warning("Assistente indisponível: " + str(readiness.get("message") or "configuração do provedor ausente"))
        else:
            st.caption(str(readiness.get("message") or "Credenciais configuradas; conexão com a API ainda não testada.") + " · " + str(readiness.get("model") or "modelo configurado"))
    except Exception as exc:
        st.warning(f"Não foi possível verificar a configuração do Assistente. {exc}")

    st.caption(
        "Privacidade: a pergunta, as mensagens recentes desta conversa e um resumo operacional filtrado são enviados pelo servidor à OpenAI. "
        "As mensagens também ficam armazenadas no histórico local do Assistente no servidor do Ecossistema. "
        "A chave permanece no servidor. Não envie senhas, códigos de acesso ou dados bancários sensíveis."
    )
    if "assistant_history" not in st.session_state:
        st.session_state.assistant_history = []

    try:
        saved_conversations = api("/api/assistant/conversations").get("conversations", [])
        if saved_conversations:
            conversation_labels = {
                item["conversation_id"]: (
                    str(item.get("title") or "Conversa")
                    + " · "
                    + str(item.get("updated_at") or "")
                )
                for item in saved_conversations
                if item.get("conversation_id")
            }
            selected_saved_id = st.selectbox(
                "Conversas anteriores",
                options=list(conversation_labels),
                format_func=lambda conversation_id: conversation_labels[conversation_id],
                key="saved_assistant_conversation",
            )
            history_col, delete_col = st.columns([3, 1])
            if history_col.button("Abrir conversa", key="load_assistant_conversation"):
                saved = api(
                    "/api/assistant/history?conversation_id="
                    + urllib.parse.quote(selected_saved_id, safe="")
                ).get("messages", [])
                st.session_state.assistant_conversation_id = selected_saved_id
                st.session_state.assistant_history = [
                    {"role": item["role"], "content": item["content"]}
                    for item in saved
                    if item.get("role") in ("user", "assistant")
                ]
                st.rerun()
            if delete_col.button("Excluir conversa", key="delete_assistant_conversation"):
                api(
                    "/api/assistant/conversations?conversation_id="
                    + urllib.parse.quote(selected_saved_id, safe=""),
                    "DELETE",
                )
                if st.session_state.get("assistant_conversation_id") == selected_saved_id:
                    _reset_assistant_conversation()
                st.rerun()
    except Exception as exc:
        st.warning(f"Não foi possível carregar o histórico de conversas. {exc}")

    if st.button("Nova consulta", key="new_assistant_session"):
        _reset_assistant_conversation()
        st.rerun()

    for message in st.session_state.assistant_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    prompt = st.chat_input(
        "Pergunte sobre o Ecossistema, risco ou Reserva Fiscal",
        disabled=not assistant_available,
    )
    if prompt:
        st.session_state.assistant_history.append({"role": "user", "content": prompt})
        try:
            response = api(
                "/api/assistant/chat",
                "POST",
                {
                    "message": prompt,
                    "conversation_id": st.session_state.get("assistant_conversation_id"),
                },
            )
            st.session_state.assistant_conversation_id = response.get("conversation_id")
            answer = response.get("answer", "Sem resposta.")
            st.session_state.assistant_history.append({"role": "assistant", "content": answer})
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
        c.metric("Estimativa acumulada · Brasil", money(summary.get("total_reserved_brl")))
        st.caption(f"Referência: {summary.get('as_of', '—')} · Brasil day trade · percentual de planejamento configurado: {br.get('rate', '—')}%")
        semantics = summary.get("reserve_semantics", {})
        st.warning("ESTIMATIVA DE PLANEJAMENTO — não é imposto apurado ou devido. " + str(semantics.get("description") or "Não calcula compensação mensal de prejuízos nem créditos de IRRF."))
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
        if submitted and not confirmed:
            st.error("Confirme os critérios de day trade ou registre a operação na fila brasileira pendente.")
        elif submitted and (not instrument.strip() or not institution.strip() or not market_label.strip() or not reference.strip()):
            st.error("Preencha ativo, instituição, mercado e referência / comprovante.")
        elif submitted:
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
        if "domestic_pending_offset" not in st.session_state:
            st.session_state.domestic_pending_offset = 0
        domestic_offset = int(st.session_state.domestic_pending_offset)
        domestic_data = api(f"/api/fiscal-reserve/domestic-pending?limit=50&offset={domestic_offset}")
        domestic_items = domestic_data.get("items", [])
        domestic_summary = api("/api/fiscal-reserve/domestic-pending/summary")
        domestic_cols = st.columns(4)
        for col, period, label in zip(domestic_cols, ("day", "week", "month", "year"), ("Dia", "Semana", "Mês", "Ano")):
            period_data = domestic_summary.get("periods", {}).get(period, {})
            col.metric(f"Brasil pendente · {label}", int(period_data.get("total", 0)))
            col.caption(f"{int(period_data.get('results', 0))} resultado(s) · sem cálculo")
        if domestic_items:
            st.dataframe([{"Data": item.get("occurred_on"), "Ativo": item.get("instrument"), "Categoria candidata": item.get("category_candidate") or "Não informada", "Mercado declarado · não verificado": item.get("market_scope"), "Resultado (R$)": item.get("realized_result_brl") if item.get("realized_result_brl") is not None else "—", "Status": "PENDENTE DE CLASSIFICAÇÃO"} for item in domestic_items], use_container_width=True, hide_index=True)
            domestic_page_cols = st.columns(2)
            with domestic_page_cols[0]:
                if st.button("← Pendências brasileiras anteriores", key="domestic_pending_previous", disabled=domestic_offset <= 0):
                    st.session_state.domestic_pending_offset = max(0, domestic_offset - 50)
                    st.rerun()
            with domestic_page_cols[1]:
                if st.button("Próximas pendências brasileiras →", key="domestic_pending_next", disabled=domestic_offset + len(domestic_items) >= int(domestic_data.get("total", 0))):
                    st.session_state.domestic_pending_offset = domestic_offset + 50
                    st.rerun()
            st.caption(f"Exibindo {domestic_offset + 1}–{domestic_offset + len(domestic_items)} de {int(domestic_data.get('total', 0))} pendências brasileiras.")
            st.markdown("##### Revisão documental · Brasil")
            st.caption("A revisão registra evidências declaradas. O sistema não verifica identidade ou registro profissional, não muda a classificação e não calcula reserva.")
            review_options = {
                item["pending_id"]: f"{item.get('occurred_on')} · {item.get('instrument')} · {item.get('reference')}"
                for item in domestic_items if item.get("pending_id")
            }
            if review_options:
                selected_pending_id = st.selectbox(
                    "Pendência para revisão",
                    options=list(review_options),
                    format_func=lambda value: review_options[value],
                    key="domestic_review_pending_id",
                )
                with st.form("domestic_review_form"):
                    review_category = st.selectbox(
                        "Classificação candidata revisada",
                        ["BR_DAY_TRADE", "BR_COMMON_EXCHANGE", "BR_FII_FIAGRO", "BR_FIXED_INCOME", "BR_CRYPTO", "BR_FUTURES_OPTIONS"],
                    )
                    review_jurisdiction = st.text_input("Jurisdição confirmada pelo revisor", value="Brasil", max_chars=120)
                    reviewer_name = st.text_input("Nome do profissional", max_chars=160)
                    reviewer_role = st.selectbox("Atuação profissional", ["contador", "consultor tributário", "profissional tributário"])
                    professional_registration = st.text_input("Registro profissional informado", max_chars=100)
                    evidence_reference = st.text_input("Referência da evidência / parecer", max_chars=500)
                    reviewed_on = st.date_input("Data da revisão", key="domestic_review_date")
                    review_notes = st.text_area("Observações da revisão", max_chars=2000)
                    review_submit = st.form_submit_button("Guardar evidência da revisão")
                if review_submit:
                    try:
                        review_payload = {
                            "candidate_classification": review_category,
                            "confirmed_jurisdiction": review_jurisdiction,
                            "reviewer_name": reviewer_name,
                            "reviewer_role": reviewer_role,
                            "professional_registration": professional_registration,
                            "evidence_reference": evidence_reference,
                            "reviewed_on": reviewed_on.isoformat(),
                            "review_notes": review_notes,
                        }
                        api(
                            "/api/fiscal-reserve/domestic-pending/" + urllib.parse.quote(selected_pending_id) + "/reviews",
                            "POST", review_payload,
                        )
                        st.success("Evidência guardada. A operação continua pendente, sem cálculo ou inclusão nos totais.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                try:
                    review_data = api(
                        "/api/fiscal-reserve/domestic-pending/" + urllib.parse.quote(selected_pending_id) + "/reviews"
                    )
                    if review_data.get("reviews"):
                        st.dataframe([{
                            "Revisor declarado": item.get("reviewer_name"),
                            "Atuação": item.get("reviewer_role"),
                            "Registro informado": item.get("professional_registration"),
                            "Evidência": item.get("evidence_reference"),
                            "Data": item.get("reviewed_on"),
                            "Identidade": item.get("reviewer_identity_status"),
                        } for item in review_data["reviews"]], use_container_width=True, hide_index=True)
                    else:
                        st.caption("Nenhuma evidência de revisão registrada para esta pendência.")
                except Exception as exc:
                    st.warning(f"Histórico de revisão indisponível. {exc}")
        else:
            st.caption("Nenhuma pendência brasileira cadastrada.")
    except Exception as exc:
        st.warning(f"Fila brasileira indisponível; nenhum registro foi incluído nos totais. {exc}")

    st.markdown("#### Exterior · pendente de classificação")
    st.caption("O registro abaixo guarda evidências; não calcula imposto nem entra na reserva.")
    residency_options = {"NOT_INFORMED": "Não informado", "BRAZIL": "Brasil", "FOREIGN": "Exterior", "DUAL_OR_UNCERTAIN": "Dupla ou incerta"}
    income_options = {"NOT_INFORMED": "Não informado", "CAPITAL_GAIN": "Ganho de capital", "INVESTMENT_INCOME": "Rendimento de investimento", "TRADING_RESULT": "Resultado de negociação", "DIVIDEND": "Dividendo", "INTEREST": "Juros", "RENTAL_INCOME": "Aluguel", "OTHER": "Outro"}
    event_options = {"NOT_INFORMED": "Não informado", "ACQUISITION": "Aquisição", "DISPOSAL": "Alienação / venda", "DIVIDEND_RECEIPT": "Recebimento de dividendo", "INTEREST_RECEIPT": "Recebimento de juros", "REDEMPTION": "Resgate", "EXCHANGE": "Troca / permuta", "TRANSFER": "Transferência", "OTHER": "Outro"}
    fx_method_options = {"NOT_INFORMED": "Não informado", "NOT_CONVERTED": "Ainda não convertido", "PTAX_SELL": "PTAX venda", "PTAX_BUY": "PTAX compra", "BROKER_STATEMENT": "Extrato da corretora", "BANK_RECEIPT": "Comprovante bancário", "OTHER_DOCUMENTED": "Outro método documentado"}
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
        tax_residency = st.selectbox("Residência fiscal declarada na data", list(residency_options), format_func=lambda value: residency_options[value], key="foreign_tax_residency")
        income_nature = st.selectbox("Natureza do rendimento / valor", list(income_options), format_func=lambda value: income_options[value], key="foreign_income_nature")
        event_type = st.selectbox("Tipo de evento", list(event_options), format_func=lambda value: event_options[value], key="foreign_event_type")
        fx_rate = st.number_input("Cotação cambial (opcional)", min_value=0.0, step=0.0001, format="%.8f")
        fx_date = st.date_input("Data da cotação", key="foreign_fx_date")
        fx_source = st.text_input("Fonte da cotação (opcional)", max_chars=200)
        fx_conversion_method = st.selectbox("Método de conversão cambial", list(fx_method_options), format_func=lambda value: fx_method_options[value], key="foreign_fx_method")
        notes = st.text_area("Observações", max_chars=1000, key="foreign_notes")
        submitted = st.form_submit_button("Guardar como pendente")
    if submitted:
        try:
            pending_payload = {"reference": reference, "original_amount": amount, "original_currency": currency, "instrument": instrument, "jurisdiction": jurisdiction, "occurred_on": occurred_on.isoformat(), "tax_residency_at_event": tax_residency, "income_nature": income_nature, "event_type": event_type, "fx_conversion_method": fx_conversion_method, "notes": notes}
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
        residency_signed = st.selectbox("Residência fiscal declarada na data", list(residency_options), format_func=lambda value: residency_options[value], key="signed_tax_residency")
        income_signed = st.selectbox("Natureza do resultado", list(income_options), format_func=lambda value: income_options[value], key="signed_income_nature")
        event_signed = st.selectbox("Tipo de evento", list(event_options), format_func=lambda value: event_options[value], key="signed_event_type")
        fx_signed = st.number_input("Cotação documentada (opcional)", min_value=0.0, format="%.8f")
        fx_date_signed = st.date_input("Data da cotação", key="signed_foreign_fx_date")
        fx_source_signed = st.text_input("Fonte da cotação")
        fx_method_signed = st.selectbox("Método de conversão cambial", list(fx_method_options), format_func=lambda value: fx_method_options[value], key="signed_fx_method")
        notes_signed = st.text_area("Observações")
        submit_signed = st.form_submit_button("Guardar como pendente")
    if submit_signed:
        try:
            signed_payload = {"reference": ref_signed, "original_result": amount_signed, "original_currency": currency_signed, "instrument": instrument_signed, "jurisdiction": jurisdiction_signed, "occurred_on": date_signed.isoformat(), "tax_residency_at_event": residency_signed, "income_nature": income_signed, "event_type": event_signed, "fx_conversion_method": fx_method_signed, "notes": notes_signed}
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

    st.markdown("#### Revisão documental · Exterior")
    st.caption("A revisão registra a classificação candidata e as evidências informadas pelo profissional. O sistema não verifica identidade ou registro, não muda o status pendente e não calcula imposto.")
    try:
        if "foreign_pending_offset" not in st.session_state:
            st.session_state.foreign_pending_offset = 0
        foreign_offset = int(st.session_state.foreign_pending_offset)
        foreign_pending_data = api(f"/api/fiscal-reserve/pending?limit=50&offset={foreign_offset}")
        foreign_items = foreign_pending_data.get("items", [])
        if foreign_items:
            st.dataframe([{
                "Data": item.get("occurred_on"),
                "Referência": item.get("reference"),
                "Instrumento": item.get("instrument"),
                "Valor": item.get("original_result") if item.get("record_kind") == "REALIZED_RESULT" else item.get("original_amount"),
                "Moeda": item.get("original_currency"),
                "Residência declarada": item.get("tax_residency_at_event"),
                "Natureza": item.get("income_nature"),
                "Evento": item.get("event_type"),
                "Status": "PENDENTE DE CLASSIFICAÇÃO",
            } for item in foreign_items], use_container_width=True, hide_index=True)
            foreign_page_cols = st.columns(2)
            with foreign_page_cols[0]:
                if st.button("← Pendências do exterior anteriores", key="foreign_pending_previous", disabled=foreign_offset <= 0):
                    st.session_state.foreign_pending_offset = max(0, foreign_offset - 50)
                    st.rerun()
            with foreign_page_cols[1]:
                if st.button("Próximas pendências do exterior →", key="foreign_pending_next", disabled=foreign_offset + len(foreign_items) >= int(foreign_pending_data.get("total", 0))):
                    st.session_state.foreign_pending_offset = foreign_offset + 50
                    st.rerun()
            st.caption(f"Exibindo {foreign_offset + 1}–{foreign_offset + len(foreign_items)} de {int(foreign_pending_data.get('total', 0))} pendências do exterior.")
            foreign_review_options = {
                item["pending_id"]: f"{item.get('occurred_on')} · {item.get('instrument')} · {item.get('reference')}"
                for item in foreign_items if item.get("pending_id")
            }
            if foreign_review_options:
                selected_foreign_pending_id = st.selectbox(
                    "Pendência estrangeira para revisão",
                    options=list(foreign_review_options),
                    format_func=lambda value: foreign_review_options[value],
                    key="foreign_review_pending_id",
                )
                with st.form("foreign_review_form"):
                    foreign_review_category = st.selectbox(
                        "Classificação candidata revisada",
                        ["FOREIGN_FINANCIAL_INVESTMENT", "FOREIGN_ENTITY_CONTROLLED", "FOREIGN_CRYPTO"],
                    )
                    foreign_review_jurisdiction = st.text_input(
                        "Jurisdição confirmada pelo revisor", max_chars=120, key="foreign_review_jurisdiction"
                    )
                    foreign_reviewer_name = st.text_input("Nome do profissional", max_chars=160, key="foreign_reviewer_name")
                    foreign_reviewer_role = st.selectbox(
                        "Atuação profissional",
                        ["contador", "consultor tributário", "profissional tributário"],
                        key="foreign_reviewer_role",
                    )
                    foreign_professional_registration = st.text_input(
                        "Registro profissional informado", max_chars=100, key="foreign_professional_registration"
                    )
                    foreign_evidence_reference = st.text_input(
                        "Referência da evidência / parecer", max_chars=500, key="foreign_evidence_reference"
                    )
                    foreign_reviewed_on = st.date_input("Data da revisão", key="foreign_reviewed_on")
                    foreign_review_notes = st.text_area(
                        "Observações da revisão", max_chars=2000, key="foreign_review_notes"
                    )
                    foreign_review_submit = st.form_submit_button("Guardar evidência da revisão")
                if foreign_review_submit:
                    try:
                        foreign_review_payload = {
                            "candidate_classification": foreign_review_category,
                            "confirmed_jurisdiction": foreign_review_jurisdiction,
                            "reviewer_name": foreign_reviewer_name,
                            "reviewer_role": foreign_reviewer_role,
                            "professional_registration": foreign_professional_registration,
                            "evidence_reference": foreign_evidence_reference,
                            "reviewed_on": foreign_reviewed_on.isoformat(),
                            "review_notes": foreign_review_notes,
                        }
                        api(
                            "/api/fiscal-reserve/pending/" + urllib.parse.quote(selected_foreign_pending_id) + "/reviews",
                            "POST", foreign_review_payload,
                        )
                        st.success("Evidência guardada. A operação continua pendente, sem cálculo ou inclusão nos totais.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                try:
                    foreign_review_data = api(
                        "/api/fiscal-reserve/pending/" + urllib.parse.quote(selected_foreign_pending_id) + "/reviews"
                    )
                    if foreign_review_data.get("reviews"):
                        st.dataframe([{
                            "Classificação candidata": item.get("candidate_classification"),
                            "Jurisdição": item.get("confirmed_jurisdiction"),
                            "Revisor declarado": item.get("reviewer_name"),
                            "Atuação": item.get("reviewer_role"),
                            "Registro informado": item.get("professional_registration"),
                            "Evidência": item.get("evidence_reference"),
                            "Data": item.get("reviewed_on"),
                            "Identidade": "NÃO VERIFICADA",
                        } for item in foreign_review_data["reviews"]], use_container_width=True, hide_index=True)
                    else:
                        st.caption("Nenhuma evidência de revisão registrada para esta pendência.")
                except Exception as exc:
                    st.warning(f"Histórico de revisão estrangeira indisponível. {exc}")
        else:
            st.caption("Nenhuma pendência estrangeira cadastrada.")
    except Exception as exc:
        st.warning(f"Fila estrangeira indisponível; nenhum registro foi incluído nos totais. {exc}")

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
            st.dataframe([{"Data": item.get("occurred_on"), "Instrumento": item.get("instrument"), "Jurisdição": item.get("jurisdiction"), "Residência declarada": residency_options.get(item.get("tax_residency_at_event", "NOT_INFORMED"), "Não informado"), "Natureza": income_options.get(item.get("income_nature", "NOT_INFORMED"), "Não informado"), "Evento": event_options.get(item.get("event_type", "NOT_INFORMED"), "Não informado"), "Método cambial": fx_method_options.get(item.get("fx_conversion_method", "NOT_INFORMED"), "Não informado"), "Valor original": item.get("original_result") if item.get("record_kind") == "REALIZED_RESULT" else item.get("original_amount"), "Tipo": item.get("record_kind", "ASSET_AMOUNT"), "Moeda": item.get("original_currency"), "Status": "PENDENTE DE CLASSIFICAÇÃO"} for item in items], use_container_width=True, hide_index=True)
            pending_ids = [item.get("pending_id") for item in items]
            selected_id = st.selectbox("Selecionar pendência para revisão", pending_ids, format_func=lambda value: next((f"{x.get('instrument')} · {x.get('jurisdiction')} · {x.get('original_result') if x.get('record_kind') == 'REALIZED_RESULT' else x.get('original_amount')} {x.get('original_currency')}" for x in items if x.get("pending_id") == value), value))
            with st.expander("Registrar evidência de revisão profissional"):
                st.warning("Identidade e registro profissional são declarados pelo usuário; o sistema não verifica credenciais. A revisão é evidência documental, não validação fiscal automática.")
                with st.form("professional_review_form"):
                    classification = st.selectbox("Classificação candidata", ["FOREIGN_FINANCIAL_INVESTMENT", "FOREIGN_ENTITY_CONTROLLED", "FOREIGN_CRYPTO"])
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


def show_market_analysis() -> None:
    st.subheader("Análise de Mercado")
    st.caption("Consulta de candles do MT5 DEMO e análise. Esta tela não envia ordens nem autoriza execução.")
    try:
        assets_payload = api("/api/market/assets")
        assets = assets_payload.get("assets", [])
        symbols = []
        for asset in assets:
            if isinstance(asset, str):
                symbols.append(asset)
            elif isinstance(asset, dict) and asset.get("symbol"):
                symbols.append(str(asset["symbol"]))
        if not symbols:
            st.warning("O runtime não disponibilizou ativos do MT5 DEMO. Verifique a conexão e a fonte de candles.")
            return
        with st.form("market_analysis_form"):
            symbol = st.selectbox("Ativo", sorted(set(symbols)))
            timeframe = st.selectbox("Período gráfico", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=1)
            candle_limit = st.slider("Quantidade de candles", min_value=30, max_value=500, value=100, step=10)
            confirmed = st.checkbox("Confirmo que esta análise é somente para estudo em DEMO/SIMULAÇÃO.")
            submitted = st.form_submit_button("Analisar mercado")
        if submitted:
            if not confirmed:
                st.error("Confirme o uso somente em DEMO/SIMULAÇÃO para solicitar a análise.")
            else:
                # A solicitação nova invalida o sinal anterior até que a análise
                # atual termine. Se o runtime falhar, o C não exibe dado obsoleto.
                st.session_state.pop("market_analysis_result", None)
                try:
                    result = api("/api/runtime/analysis", "POST", {"symbol": symbol, "timeframe": timeframe, "limit": candle_limit})
                    st.session_state.market_analysis_result = result
                except Exception as exc:
                    st.error(f"Análise indisponível: {exc}")
        result = st.session_state.get("market_analysis_result")
        if result:
            analysis = result.get("analysis", {})
            signal = str(result.get("signal") or "AGUARDAR").upper()
            cols = st.columns(4)
            cols[0].metric("Sinal", signal)
            cols[1].metric("Pontuação", f"{analysis.get('score', '—')}/100")
            cols[2].metric("Ativo", analysis.get("symbol", "—"))
            cols[3].metric("Período", analysis.get("timeframe", "—"))
            st.write(result.get("reason") or "Sem justificativa fornecida pelo motor.")
            st.caption("Decisão: " + str(result.get("decision", "AGUARDAR")) + " · Execução permitida: NÃO")
            st.caption("A confirmação de uso em DEMO não substitui o fechamento do candle nem os filtros internos. As preferências de segurança do runtime são respeitadas.")
            candles = result.get("market_data", {}).get("ohlcv", [])
            if candles:
                st.markdown("#### Candles recebidos")
                st.dataframe(candles[-100:], use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"Não foi possível carregar ativos do MT5 DEMO: {exc}")


def show_replay() -> None:
    st.subheader("Replay histórico · MT5 DEMO")
    st.caption("Reproduz candles históricos já fechados, em ordem cronológica. Cada decisão usa somente os candles disponíveis até aquele instante. Não envia ordens, não altera a memória operacional e não libera execução.")
    with st.form("historical_replay_form"):
        symbol = st.text_input("Ativo no MT5", value="EURUSD", max_chars=32)
        timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=1)
        limit = st.number_input("Quantidade de candles fechados", min_value=20, max_value=500, value=100, step=10)
        submitted = st.form_submit_button("Reproduzir histórico DEMO")
    if not submitted:
        st.info("Selecione o ativo e o período para iniciar uma reprodução histórica somente de leitura.")
        return
    try:
        result = api("/api/replay/mt5", "POST", {
            "symbol": symbol.strip(),
            "timeframe": timeframe,
            "limit": int(limit),
        })
        st.caption(f"Fonte: {result.get('source', '—')} · {result.get('symbol')} · {result.get('timeframe')}")
        cols = st.columns(4)
        cols[0].metric("Candles", int(result.get("candles_replayed", 0)))
        cols[1].metric("Sinais de compra", int(result.get("buy_signals", 0)))
        cols[2].metric("Sinais de venda", int(result.get("sell_signals", 0)))
        cols[3].metric("Aguardar", int(result.get("waiting", 0)))
        records = result.get("records", [])
        if records:
            st.dataframe(records, use_container_width=True, hide_index=True)
        st.success("Replay concluído sem envio de ordens.") if result.get("orders_sent") is False else st.error("Estado de execução inesperado.")
        st.caption("Execução permitida: NÃO · Antecipação de candles futuros: NÃO")
    except Exception as exc:
        st.error(f"Replay indisponível: {exc}")


def show_simulator() -> None:
    st.subheader("Simulador histórico · MT5 DEMO")
    st.caption("Backtest determinístico com sinais no fechamento e entrada somente na abertura do candle seguinte. Configure os parâmetros reais do instrumento e da sua conta antes de executar.")
    st.info("P&L é calculado na moeda cotada do instrumento, sem conversão para a moeda da conta. Quantidade em unidades do ativo — não em lotes MT5.")
    with st.form("historical_trade_backtest_form"):
        symbol = st.text_input("Ativo no MT5", value="EURUSD", max_chars=32)
        timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=1, key="backtest_timeframe")
        limit = st.number_input("Candles históricos fechados", min_value=20, max_value=500, value=200, step=10, key="backtest_limit")
        minimum_directional_score = st.slider("Score direcional mínimo", min_value=70, max_value=95, value=80, step=1)
        st.markdown("**Parâmetros da operação hipotética**")
        stop_distance = st.number_input("Stop-loss · distância em unidades de preço", min_value=0.0, value=0.0, step=0.0001, format="%.6f")
        take_profit_distance = st.number_input("Take-profit · distância em unidades de preço", min_value=0.0, value=0.0, step=0.0001, format="%.6f")
        quantity_units = st.number_input("Quantidade em unidades/contratos", min_value=0.0, value=0.0, step=1.0, format="%.2f")
        contract_multiplier = st.number_input("Multiplicador do contrato", min_value=0.0, value=1.0, step=1.0, format="%.4f")
        st.markdown("**Custos por operação completa**")
        spread_price_units = st.number_input("Spread total em unidades de preço", min_value=0.0, value=0.0, step=0.00001, format="%.6f")
        slippage_price_units_per_side = st.number_input("Slippage por lado em unidades de preço", min_value=0.0, value=0.0, step=0.00001, format="%.6f")
        commission_quote_per_unit_round_turn = st.number_input("Comissão total por unidade · moeda cotada", min_value=0.0, value=0.0, step=0.0001, format="%.6f")
        submitted = st.form_submit_button("Executar backtest histórico DEMO")
    if not submitted:
        st.caption("Preencha stop, alvo, quantidade e custos conforme a especificação do instrumento e da corretora. Valores zero significam custo zero assumido, não custo verificado.")
        return
    if not symbol.strip() or stop_distance <= 0 or take_profit_distance <= 0 or quantity_units <= 0 or contract_multiplier <= 0 or spread_price_units <= 0:
        st.error("Informe ativo, stop-loss, take-profit, quantidade e spread maiores que zero. Não vou presumir esses parâmetros.")
        return
    try:
        result = api("/api/simulator/mt5/backtest", "POST", {
            "symbol": symbol.strip(),
            "timeframe": timeframe,
            "limit": int(limit),
            "minimum_directional_score": int(minimum_directional_score),
            "stop_distance": float(stop_distance),
            "take_profit_distance": float(take_profit_distance),
            "quantity_units": float(quantity_units),
            "contract_multiplier": float(contract_multiplier),
            "spread_price_units": float(spread_price_units),
            "slippage_price_units_per_side": float(slippage_price_units_per_side),
            "commission_quote_per_unit_round_turn": float(commission_quote_per_unit_round_turn),
        })
        st.caption(f"Fonte: {result.get('source', '—')} · {result.get('symbol')} · {result.get('timeframe')}")
        st.caption(result.get("quote_currency_note", ""))
        cols = st.columns(4)
        cols[0].metric("Operações", int(result.get("trade_count", 0)))
        cols[1].metric("Taxa vencedora", f"{float(result.get('win_rate', 0)):.2f}%")
        cols[2].metric("Fator de lucro", "—" if result.get("profit_factor") is None else f"{float(result['profit_factor']):.3f}")
        cols[3].metric("Resultado líquido", f"{float(result.get('net_pnl_quote', 0)):.6f}")
        totals = st.columns(3)
        totals[0].metric("Resultado bruto", f"{float(result.get('gross_pnl_quote', 0)):.6f}")
        totals[1].metric("Custos totais", f"{float(result.get('total_costs_quote', 0)):.6f}")
        totals[2].metric("Candles analisados", int(result.get("candles_processed", 0)))
        risk_totals = st.columns(2)
        risk_totals[0].metric("Drawdown máximo · moeda cotada", f"{float(result.get('max_drawdown_quote', 0)):.6f}")
        risk_totals[1].metric("Maior sequência de perdas", int(result.get("max_consecutive_losses", 0)))
        st.caption(result.get("drawdown_note", "Drawdown percentual não calculado sem saldo inicial."))
        trades = result.get("trades", [])
        if trades:
            st.dataframe(trades, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma operação hipotética foi aberta com estes parâmetros e sinais.")
        assumptions = result.get("assumptions", {})
        st.caption(f"Entradas: {assumptions.get('entry', '—')} · Posições simultâneas: {assumptions.get('position_limit', '—')}")
        st.warning("Limitações: stop-loss é priorizado quando stop e alvo aparecem no mesmo candle; O backtest não integra o Risk Manager, margem, alavancagem, swap ou conversão cambial. O resultado não é previsão nem promessa de rentabilidade.")
        st.caption("Execução permitida: NÃO · Ordens enviadas: NÃO · Antecipação de candles futuros: NÃO")
    except Exception as exc:
        st.error(f"Backtest histórico indisponível: {exc}")



def show_readonly_module(module_name: str) -> None:
    """Render existing runtime capabilities as clear, read-only Streamlit screens."""
    views = {
        "Operação": ("Estado operacional", "/api/health"),
        "Motor de Decisão": ("Motor de Decisão", "/api/statistics"),
        "Gestão de Risco": ("Gestão de Risco", "/api/risk"),
        "Notificações": ("Central de Notificações", "/api/notifications"),
        "MT5 DEMO / Simulação": ("Conexões e ambiente", "/api/connections"),
        "Kill Switch": ("Proteção operacional", "/api/health"),
        "Memória": ("Memória de decisões", "/api/memory?limit=50"),
        "Estatísticas": ("Estatísticas operacionais", "/api/statistics"),
        "Relatórios": ("Resumo operacional", "/api/statistics"),
        "Laboratório": ("Laboratório de aprendizado", "/api/learning"),
        "Aprendizado": ("Aprendizado validado", "/api/learning"),
        "Descobertas": ("Descobertas registradas", "/api/learning"),
        "Escola / Tutorial / Onboarding": ("Primeiros passos", "/api/onboarding"),
        "Configurações": ("Preferências do Ecossistema", "/api/preferences"),
        "Segurança": ("Segurança do Ecossistema", "/api/health"),
        "Conexões": ("Conexões disponíveis", "/api/connections"),
        "Multi-Broker": ("Disponibilidade de conexões", "/api/connections"),
        "Auditoria": ("Auditoria operacional", "/api/health"),
    }
    if module_name == "Análise de Mercado":
        show_market_analysis()
        return
    if module_name == "Replay":
        show_replay()
        return
    elif module_name == "Simulador":
        show_simulator()
        return
    else:
        view = views.get(module_name)
        if not view:
            st.subheader(module_name)
            st.info("Esta função ainda não possui integração operacional nesta versão.")
            return
        heading, endpoint = view
        st.subheader(heading)

    try:
        data = api(endpoint)
        if module_name in {"Memória", "Replay"}:
            records = data.get("records", []) if isinstance(data, dict) else []
            if records:
                st.dataframe(records, use_container_width=True, hide_index=True)
            else:
                st.caption("Ainda não há decisões registradas na memória.")
            return

        if module_name == "Notificações":
            items = data.get("items", [])
            summary_cols = st.columns(2)
            summary_cols[0].metric("Notificações", data.get("count", len(items)))
            summary_cols[1].metric("Críticas", data.get("critical_count", 0))
            if not items:
                st.success("Nenhuma notificação ativa.")
            for item in items:
                severity = str(item.get("severity", "INFO")).upper()
                message = f"{item.get('title', 'Notificação')} — {item.get('message', '')}"
                if severity == "CRITICAL":
                    st.error(message)
                elif severity == "IMPORTANT":
                    st.warning(message)
                else:
                    st.info(message)
            st.caption("Alertas críticos não são ocultados pelas preferências de notificação.")
            return

        if module_name in {"Gestão de Risco", "Simulador"}:
            limits = data.get("configured_limits", {})
            cols = st.columns(3)
            cols[0].metric("Limite de perda diária", str(limits.get("daily_loss_limit", "—")))
            cols[1].metric("Máximo de operações", str(limits.get("max_operations", "—")))
            cols[2].metric("Perdas consecutivas", str(limits.get("max_consecutive_losses", "—")))
            st.write("Gate de risco: " + ("LIBERADO" if data.get("allowed") else "BLOQUEADO"))
            st.caption(str(data.get("reason") or "O motor não forneceu uma justificativa."))
            st.caption("Os limites são informativos nesta tela; nenhum controle de execução é acionado.")
            return

        if module_name in {"Operação", "Kill Switch", "Segurança", "Auditoria"}:
            obs = data.get("operational_observability", {})
            health = str(data.get("health") or "NÃO CONFIRMADA").upper()
            st.metric("Saúde do Ecossistema", health)
            st.metric("Execução REAL", "BLOQUEADA" if data.get("real") == "DESABILITADO" else "NÃO CONFIRMADA")
            st.metric("Modo", str(data.get("mode") or "NÃO CONFIRMADO"))
            if obs:
                kill = obs.get("kill_switch", {})
                recovery = obs.get("recovery", {})
                market = obs.get("market_data", {})
                cols = st.columns(3)
                cols[0].metric("Kill Switch", "ATIVO" if kill.get("enabled") else str(kill.get("state", "NÃO CONFIRMADO")))
                cols[1].metric("Recuperação", str(recovery.get("state", "NÃO CONFIRMADA")))
                cols[2].metric("Dados de mercado", str(market.get("health", "NÃO CONFIRMADOS")))
                if recovery.get("message"):
                    st.caption(str(recovery["message"]))
            alerts = data.get("alerts", [])
            if alerts:
                st.markdown("#### Alertas que exigem atenção")
                for alert in alerts:
                    message = f"{alert.get('component', 'Sistema')} — {alert.get('message', 'Verificar')}"
                    if str(alert.get("severity", "")).upper() == "CRITICAL":
                        st.error(message)
                    else:
                        st.warning(message)
            else:
                st.caption("Nenhum alerta foi retornado pelo runtime.")
            return

        if module_name in {"MT5 DEMO / Simulação", "Conexões", "Multi-Broker"}:
            labels = {
                "decision_core": "Motor de decisão",
                "execution_gateway": "Gateway de execução",
                "ic_markets_mt5_demo": "IC Markets MT5 DEMO",
                "cTrader": "cTrader",
                "saas": "Serviços do Ecossistema",
                "real": "Execução REAL",
            }
            for key, label in labels.items():
                if key in data:
                    value = str(data[key])
                    if key == "real":
                        value = "DESABILITADO" if value in {"DESABILITADO", "DISABLED"} else "NÃO CONFIRMADO"
                    st.write(f"**{label}:** {value}")
            st.caption("Conexões futuras não são apresentadas como disponíveis. REAL permanece desabilitado.")
            return

        if module_name in {"Laboratório", "Aprendizado", "Descobertas"}:
            groups = [
                ("Materiais", "resources"),
                ("Observações", "observations"),
                ("Atividades", "activities"),
                ("Tentativas", "attempts"),
                ("Fontes", "learning_sources"),
            ]
            cols = st.columns(len(groups))
            for col, (label, key) in zip(cols, groups):
                col.metric(label, len(data.get(key, [])))
            st.caption("Fontes externas exigem validação antes de seu conhecimento ser considerado validado.")
            st.caption("Aprendizado não autoriza operações: execução permitida = NÃO.")
            for label, key in groups:
                items = data.get(key, [])
                if items:
                    with st.expander(f"{label} ({len(items)})"):
                        st.dataframe(items, use_container_width=True, hide_index=True)
            return

        if module_name == "Escola / Tutorial / Onboarding":
            guide = data.get("guide", {})
            st.markdown(f"#### {guide.get('title', 'Guia de primeiro uso')}")
            for index, step in enumerate(guide.get("steps", []), start=1):
                st.markdown(f"**{index}. {step.get('title', 'Etapa')}**")
                st.write(step.get("purpose", ""))
                st.caption(f"Local: {step.get('location', '—')} · {step.get('action_hint', '')}")
            if guide.get("completion_message"):
                st.success(str(guide["completion_message"]))
            st.caption("Concluir o guia não autoriza execução.")
            return

        if module_name == "Configurações":
            preferences = data.get("preferences", {})
            candle = preferences.get("candle", {})
            notification_prefs = preferences.get("notifications", {})
            st.caption("Preferências de apresentação e análise. Estes controles não autorizam ordens, autonomia ou execução REAL.")
            with st.form("ecosystem_preferences_form"):
                theme_options = ["DARK", "LIGHT", "SYSTEM"]
                current_theme = str(preferences.get("chart_theme", "DARK")).upper()
                theme = st.selectbox("Tema do gráfico", theme_options, index=theme_options.index(current_theme) if current_theme in theme_options else 0)
                default_symbol = st.text_input("Ativo padrão", value=str(preferences.get("default_symbol", "EURUSD")), max_chars=32)
                timeframe_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
                current_timeframe = str(preferences.get("default_timeframe", "5m"))
                timeframe = st.selectbox("Período gráfico padrão", timeframe_options, index=timeframe_options.index(current_timeframe) if current_timeframe in timeframe_options else 1)
                require_closed = st.checkbox("Exigir candle fechado", value=bool(preferences.get("require_closed_candle", True)))
                require_filters = st.checkbox("Exigir filtros internos", value=bool(preferences.get("require_filters", True)))
                show_details = st.checkbox("Exibir detalhes técnicos por padrão", value=bool(preferences.get("show_technical_details_by_default", False)))
                save_preferences = st.form_submit_button("Salvar preferências")
            if save_preferences:
                if not default_symbol.strip():
                    st.error("Informe um ativo padrão válido.")
                else:
                    try:
                        api("/api/preferences", "POST", {
                            "chart_theme": theme,
                            "default_symbol": default_symbol.strip().upper(),
                            "default_timeframe": timeframe,
                            "require_closed_candle": require_closed,
                            "require_filters": require_filters,
                            "show_technical_details_by_default": show_details,
                        })
                        st.success("Preferências de apresentação e análise salvas. Os bloqueios de execução foram preservados.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível salvar as preferências: {exc}")

            st.markdown("#### Aparência dos candles")
            with st.form("candle_preferences_form"):
                style_options = ["CANDLESTICK", "HOLLOW", "OHLC", "LINE"]
                color_options = ["DEFAULT", "CUSTOM", "MONOCHROME"]
                current_style = str(candle.get("style", "CANDLESTICK")).upper()
                current_color_mode = str(candle.get("color_mode", "DEFAULT")).upper()
                candle_style = st.selectbox("Estilo", style_options, index=style_options.index(current_style) if current_style in style_options else 0)
                color_mode = st.selectbox("Modo de cores", color_options, index=color_options.index(current_color_mode) if current_color_mode in color_options else 0)
                bullish_color = st.text_input("Cor de alta (HEX)", value=str(candle.get("bullish_color", "#58d68d")))
                bearish_color = st.text_input("Cor de baixa (HEX)", value=str(candle.get("bearish_color", "#ff7676")))
                wick_color = st.text_input("Cor do pavio (HEX)", value=str(candle.get("wick_color", "#aab5c8")))
                show_wicks = st.checkbox("Mostrar pavios", value=bool(candle.get("show_wicks", True)))
                show_bodies = st.checkbox("Mostrar corpos", value=bool(candle.get("show_bodies", True)))
                border_enabled = st.checkbox("Mostrar bordas", value=bool(candle.get("border_enabled", True)))
                save_candles = st.form_submit_button("Salvar aparência")
            if save_candles:
                try:
                    api("/api/preferences/candles", "POST", {
                        "style": candle_style, "color_mode": color_mode,
                        "bullish_color": bullish_color.strip(), "bearish_color": bearish_color.strip(),
                        "wick_color": wick_color.strip(), "show_wicks": show_wicks,
                        "show_bodies": show_bodies, "border_enabled": border_enabled,
                    })
                    st.success("Aparência dos candles salva.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível salvar a aparência: {exc}")

            st.markdown("#### Preferências de notificações")
            notification_labels = {
                "important_enabled": "Notificações importantes",
                "security_enabled": "Segurança",
                "market_enabled": "Mercado",
                "risk_enabled": "Risco",
                "connection_enabled": "Conexões",
                "execution_enabled": "Execução",
                "learning_enabled": "Aprendizado",
                "recovery_enabled": "Recuperação",
                "system_updates_enabled": "Atualizações do sistema",
                "info_enabled": "Informativas",
            }
            with st.form("notification_preferences_form"):
                updated_notifications = {}
                for key, label in notification_labels.items():
                    updated_notifications[key] = st.checkbox(label, value=bool(notification_prefs.get(key, False)), key="notification_" + key)
                st.caption("Alertas críticos permanecem sempre ativos e não podem ser desabilitados.")
                save_notifications = st.form_submit_button("Salvar notificações")
            if save_notifications:
                try:
                    api("/api/preferences/notifications", "POST", updated_notifications)
                    st.success("Preferências de notificações salvas. Alertas críticos continuam ativos.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível salvar as notificações: {exc}")
            return

        if module_name in {"Motor de Decisão", "Estatísticas", "Relatórios"}:
            scalar_values = [(key, value) for key, value in data.items() if isinstance(value, (str, int, float, bool)) or value is None]
            if scalar_values:
                cols = st.columns(min(4, len(scalar_values)))
                for index, (key, value) in enumerate(scalar_values[:12]):
                    label = key.replace("_", " ").capitalize()
                    cols[index % len(cols)].metric(label, "—" if value is None else str(value))
            periods = data.get("periods")
            if isinstance(periods, dict) and periods:
                with st.expander("Resultados por período"):
                    for period, summary in periods.items():
                        st.markdown(f"**{str(period).capitalize()}**")
                        if isinstance(summary, dict):
                            st.write(" · ".join(f"{key.replace('_', ' ')}: {value}" for key, value in summary.items() if isinstance(value, (str, int, float))))
            st.caption("Os números refletem apenas os registros disponíveis na memória do runtime.")
            return

    except Exception as exc:
        st.warning(f"Não foi possível carregar este módulo do runtime: {exc}")


# The Figma reference defines four visual areas. The Assistant is an additional
# functional module requested by the user and lives inside the Streamlit panel,
# without changing the reference JSON or creating a fifth navigation area.
AREAS = {name: list(modules) for name, modules in CONFIG["open_state"]["tabs"].items()}
AREAS["MAIS / ADMIN"].append("Assistente do Ecossistema")
if "panel_open" not in st.session_state:
    st.session_state.panel_open = True
if not st.session_state.panel_open:
    with st.container(key="panel-toggle"):
        if st.button("C", key="open_control_hub"):
            st.session_state.panel_open = True
            st.rerun()
        closed_signal, closed_score, closed_color = closed_panel_signal(
            st.session_state.get("market_analysis_result")
        )
        st.markdown(
            f'<div class="closed-signal" style="color:{closed_color}">'
            f'<strong>{closed_signal}</strong><span>{closed_score}</span></div>',
            unsafe_allow_html=True,
        )
    st.stop()

st.markdown('<div class="status-card"><span style="font-size:1.35rem;font-weight:800">Controlador-Trader</span> <span class="demo-pill" style="float:right">DEMO</span></div>', unsafe_allow_html=True)
area = st.radio("Áreas principais", list(AREAS), horizontal=True, label_visibility="collapsed")
st.divider()
module = st.radio("Módulos", AREAS[area], horizontal=False, label_visibility="collapsed")

if module == "Assistente do Ecossistema":
    show_assistant()
elif module in {"Financeiro", "Reserva Fiscal"}:
    show_fiscal()
else:
    show_readonly_module(module)

st.divider()
st.subheader("Estado do Ecossistema")
try:
    runtime_status = api("/api/health")
    components = runtime_status.get("components", {})
    health_state = str(runtime_status.get("health") or "UNKNOWN").upper()
    mt5_state = str(components.get("mt5_demo") or runtime_status.get("mt5_demo") or "UNKNOWN").upper()
    mode_state = str(runtime_status.get("mode") or "UNKNOWN").upper()
    real_state = str(runtime_status.get("real") or "DESABILITADO").upper()
    health_label = {"OK": "SISTEMA ONLINE", "WARNING": "ATENÇÃO", "CRITICAL": "INDISPONÍVEL"}.get(health_state, "ESTADO NÃO CONFIRMADO")
    status_cols = st.columns(4)
    status_cols[0].metric("Saúde do sistema", health_label)
    status_cols[1].metric("Modo", mode_state)
    status_cols[2].metric("MT5 DEMO", mt5_state)
    status_cols[3].metric("REAL", real_state)
    if runtime_status.get("execution_allowed") is not False or real_state not in {"DESABILITADO", "DISABLED"}:
        st.error("Estado de segurança inesperado. Operações bloqueadas na interface; verifique o runtime antes de continuar.")
    if runtime_status.get("alerts"):
        with st.expander("Alertas do sistema", expanded=health_state == "CRITICAL"):
            for alert in runtime_status["alerts"]:
                st.write(f"- **{alert.get('severity', 'INFO')} · {alert.get('component', 'Sistema')}** — {alert.get('message', 'Verificar componente')}")
except Exception:
    st.warning("Runtime indisponível. Estado do MT5 e do sistema não confirmado.")
left, right = st.columns([2, 1])
with left:
    st.caption("Execução REAL permanece bloqueada. Confirme o estado DEMO no runtime antes de operar.")
with right:
    if "leverage_enabled" not in st.session_state:
        try:
            saved_preferences = api("/api/preferences").get("preferences", {})
            st.session_state.leverage_enabled = saved_preferences.get("leverage_enabled") is True
        except Exception:
            st.session_state.leverage_enabled = False
    st.checkbox(
        "Alavancagem",
        key="leverage_enabled",
        on_change=save_leverage_preference,
        help="Salva somente a preferência. Não ativa ordens, não altera margem e não concede autorização de execução.",
    )
    if st.session_state.get("leverage_preference_error"):
        st.warning("Preferência de alavancagem não sincronizada com o runtime.")
with st.container(key="panel-toggle"):
    if st.button("C", key="close_control_hub"):
        st.session_state.panel_open = False
        st.rerun()
