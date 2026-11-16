from __future__ import annotations

import csv
import hashlib
import ipaddress
import io
import json
import os
from datetime import date
from math import isfinite
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import streamlit as st

from trusted_identity import trusted_identity_from_headers
from presentation import closed_panel_signal

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "controlador_trader_referencia_visual.json").read_text(encoding="utf-8"))
BASE_URL = os.environ.get("CONTROLADOR_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
IDENTITY_HEADER = os.environ.get("CONTROLADOR_TRUSTED_IDENTITY_HEADER", "").strip()
REMOTE_REQUIRED = os.environ.get("CONTROLADOR_REMOTE_ACCESS_REQUIRED", "false").strip().lower() in {"1", "true", "yes"}
TIMEOUT = 20


def _validate_api_base_url(value: str, remote_required: bool) -> None:
    """Require TLS before forwarding authenticated identity to a remote API."""
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("CONTROLADOR_API_BASE_URL deve ser uma URL HTTP(S) válida.")
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        raise RuntimeError("CONTROLADOR_API_BASE_URL não pode conter credenciais, query ou fragmento.")
    try:
        parsed.port
    except ValueError as exc:
        raise RuntimeError("CONTROLADOR_API_BASE_URL contém uma porta inválida.") from exc
    hostname = parsed.hostname.rstrip(".").lower()
    try:
        loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        loopback = hostname == "localhost"
    if remote_required and not loopback and parsed.scheme != "https":
        raise RuntimeError(
            "A API remota exige HTTPS quando o encaminhamento da identidade confiável está ativado."
        )


_validate_api_base_url(BASE_URL, REMOTE_REQUIRED)

st.set_page_config(page_title="Controlador-Trader · Streamlit", page_icon="C", layout="wide")

st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: #080B0F; color: #E9EEF3; background-image: linear-gradient(rgb(255 255 255 / .025) 1px, transparent 1px), linear-gradient(90deg, rgb(255 255 255 / .025) 1px, transparent 1px); background-size: 3rem 3rem; }
[data-testid="stHeader"] { background: transparent; }
.block-container { width: 100%; max-width: none; padding: 1rem clamp(.75rem, 2vw, 1.5rem) 6rem; }
.st-key-panel-toggle { position: fixed; left: 16px; bottom: 16px; z-index: 999999; width: min(100%, 360px); max-width: calc(100vw - 32px); margin: 0; }
.st-key-panel-toggle .stButton > button { width: 64px; min-width: 64px; height: 64px; min-height: 64px; padding: 0; border-radius: 50%; background: #080B0F; color: #46D6AD; border: 1px solid #46D6AD; box-shadow: 0 0 10px #46D6AD33; font-weight: 800; font-size: 1.25rem; }
.st-key-panel-toggle .closed-status { color: #7F8B97; font-size: 10px; font-weight: 800; letter-spacing: .06em; padding-left: 0; }
.st-key-panel-toggle .closed-signal { max-width: 190px; font-size: 13px; line-height: 1.25; font-weight: 900; letter-spacing: .025em; white-space: nowrap; }
.st-key-panel-toggle .closed-score { color: #E9EEF3; font-size: 11px; line-height: 1.2; font-weight: 700; white-space: nowrap; }
.st-key-control-hub-shell { position: fixed; left: 16px; bottom: 16px; z-index: 999998; width: min(34vw, 420px); max-width: calc(100vw - 32px); max-height: min(84vh, 460px); overflow-y: auto; margin: 0; padding: clamp(.65rem, 1vw, 1rem); background: #10151B; border: 1px solid #25303B; border-radius: 24px; }
.st-key-control-hub-shell .hub-title { color: #E9EEF3; font-size: 1.35rem; font-weight: 800; padding: .35rem 0 .9rem; }
.st-key-control-hub-shell .demo-pill-wrap { display: flex; justify-content: flex-end; padding-top: .3rem; }
.st-key-control-hub-shell .system-state-value { color: #7F8B97; text-align: right; font-size: .78rem; font-weight: 800; }
.st-key-open-signal-strip { margin: .2rem 0 .8rem; padding: .55rem .8rem; border: 1px solid #25303B; border-radius: 12px; background: #0D1218; }
.st-key-open-signal-strip .open-signal { font-size: .86rem; font-weight: 900; letter-spacing: .025em; }
.st-key-open-signal-strip .open-score { color: #E9EEF3; font-size: .8rem; font-weight: 800; text-align: right; }
.st-key-control-hub-shell .st-key-main_area_navigation [role="radiogroup"] { display: flex; flex-wrap: wrap; gap: .4rem; padding: .35rem 0 .65rem; border-bottom: 1px solid #25303B; }
.st-key-control-hub-shell .st-key-main_area_navigation [role="radiogroup"] label > div:first-child, .st-key-control-hub-shell .st-key-module_navigation [role="radiogroup"] label > div:first-child { display: none; }
.st-key-control-hub-shell .st-key-main_area_navigation [role="radiogroup"] label { flex: 1 1 7rem; justify-content: center; text-align: center; border-color: transparent; background: transparent; }
.st-key-control-hub-shell .st-key-main_area_navigation [role="radiogroup"] label p { font-size: .72rem; font-weight: 800; }
.st-key-control-hub-shell .st-key-module_navigation [role="radiogroup"] { display: flex; flex-direction: column; gap: .45rem; }
.st-key-control-hub-shell .st-key-module_navigation [role="radiogroup"] label { width: 100%; display: flex; align-items: center; justify-content: space-between; border: 1px solid transparent; border-radius: 12px; background: #161C24; padding: .85rem 1rem; min-height: 58px; }
.st-key-control-hub-shell .st-key-module_navigation [role="radiogroup"] label::after { content: "›"; color: #7F8B97; font-size: 1.3rem; margin-left: auto; }
.st-key-control-hub-shell .st-key-module_navigation [role="radiogroup"] label p { color: #E9EEF3; font-size: .9rem; font-weight: 500; }
.st-key-control-hub-shell .st-key-module_navigation [role="radiogroup"] label:has(input:checked) { border-color: #25303B; background: #1A222B; }
.st-key-control-hub-shell [data-testid="stRadio"] label { background: #161C24; border: 1px solid #202A34; border-radius: 12px; padding: .65rem .8rem; min-height: 48px; }
.st-key-control-hub-shell [data-testid="stRadio"] label p { color: #E9EEF3; font-weight: 600; }
.st-key-control-hub-shell [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) { border-color: #46D6AD; background: #1A292B; }
.st-key-control-hub-shell [data-testid="stMetric"] { min-width: 0; }
.st-key-control-hub-shell [data-testid="stButton"] > button { min-height: 44px; }
@media (max-width: 720px) {
  .st-key-control-hub-shell { padding: .8rem; margin: 0; border-radius: 18px; }
  .st-key-control-hub-shell [data-testid="stRadio"] [role="radiogroup"] { gap: .35rem; }
  .st-key-control-hub-shell [data-testid="stRadio"] label { padding: .5rem .55rem; }
}
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

/* C visível nos estados recolhido e expandido */
.st-key-open_control_hub button,
.st-key-close_control_hub_top button {
    background: #101820 !important;
    color: #f2f6fa !important;
    border: 1px solid #42b8ad !important;
    border-radius: 10px !important;
    min-width: 42px !important;
    min-height: 42px !important;
    padding: 0 !important;
    font-weight: 900 !important;
    font-size: 18px !important;
}
</style>
""", unsafe_allow_html=True)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward trusted identity headers to an HTTP redirect target."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_API_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def api(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if REMOTE_REQUIRED:
        if not IDENTITY_HEADER:
            raise RuntimeError("A identidade confiável não foi configurada no servidor Streamlit.")
        incoming = st.context.headers
        identity = trusted_identity_from_headers(incoming, IDENTITY_HEADER)
        if not identity:
            raise RuntimeError("Acesso remoto bloqueado: identidade autenticada não chegou pelo proxy confiável.")
        headers[IDENTITY_HEADER] = identity
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with _API_OPENER.open(request, timeout=TIMEOUT) as response:
            try:
                body = response.read().decode("utf-8")
                result = json.loads(body) if body else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise RuntimeError("Resposta inválida do serviço do Ecossistema.") from None
            if not isinstance(result, dict):
                raise RuntimeError("Resposta inválida do serviço do Ecossistema.") from None
            return result
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(detail)
            failed_conversation_id = error_payload.get("conversation_id")
            if path == "/api/assistant/chat" and isinstance(failed_conversation_id, str) and failed_conversation_id:
                st.session_state.assistant_conversation_id = failed_conversation_id
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            pass
        # Never surface backend exception text, SQL details, paths, or connector
        # payloads in the browser. Preserve only the HTTP status category.
        safe_messages = {
            400: "Solicitação rejeitada. Confira os campos informados.",
            401: "Autenticação necessária. Entre novamente.",
            403: "Acesso não autorizado para esta operação.",
            404: "Recurso solicitado não encontrado.",
            409: "Conflito de estado. Atualize os dados antes de tentar novamente.",
            429: "Limite temporário de solicitações atingido. Aguarde e tente novamente.",
            503: "Serviço temporariamente indisponível. Nenhuma alteração foi confirmada.",
        }
        if exc.code == 503 and path == "/api/assistant/chat":
            message = (
                "A resposta não foi gerada. A pergunta pode ter sido salva no histórico; "
                "abra a conversa antes de reenviar para evitar duplicidade."
            )
        else:
            message = safe_messages.get(exc.code, "Falha de comunicação com o serviço.")
        raise RuntimeError(f"API indisponível (HTTP {exc.code}): {message}") from None
    except urllib.error.URLError:
        raise RuntimeError("Runtime indisponível. Verifique a conexão com o serviço.") from None


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


def _assistant_consent_scope() -> str:
    """Bind OpenAI consent to the authenticated principal for this Streamlit session."""
    if REMOTE_REQUIRED:
        if not IDENTITY_HEADER:
            return ""
        identity = trusted_identity_from_headers(st.context.headers, IDENTITY_HEADER)
    else:
        # Local consent must be scoped to the same explicit server identity
        # used by the API/fiscal owner. Never invent a fallback principal.
        identity = os.environ.get("CONTROLADOR_SINGLE_USER_IDENTITY", "").strip()
    if not identity:
        return ""
    return hashlib.sha256(identity.strip().casefold().encode("utf-8")).hexdigest()


def show_assistant() -> None:
    # Consent is single-use: clear it before rebuilding the widgets after every
    # submitted question, so the next question requires a fresh user action.
    if st.session_state.pop("assistant_clear_consent_before_render", False):
        st.session_state["assistant_openai_consent"] = False
    consent_scope = _assistant_consent_scope()
    previous_scope = st.session_state.get("assistant_consent_scope")
    if consent_scope != previous_scope:
        # A consent granted by one authenticated principal must not survive
        # an identity switch in the same browser session. Clear all client-side
        # conversation state too: it may contain messages loaded under the
        # previous identity even though the server store is owner-scoped.
        st.session_state["assistant_openai_consent"] = False
        st.session_state["assistant_connection_tested"] = False
        _reset_assistant_conversation()
        st.session_state.pop("saved_assistant_conversation", None)
        st.session_state.pop("assistant_submission_warning", None)
        st.session_state.pop("assistant_submission_error", None)
        st.session_state["assistant_consent_scope"] = consent_scope
    st.subheader("Assistente do Ecossistema")
    st.caption("Somente leitura · não envia ordens, não movimenta dinheiro e não substitui orientação fiscal profissional.")
    assistant_available = False
    try:
        readiness = api("/api/assistant/status")
        assistant_available = readiness.get("available") is True
        if not assistant_available:
            st.session_state["assistant_connection_tested"] = False
            st.warning("Assistente indisponível: " + str(readiness.get("message") or "configuração do provedor ausente"))
        else:
            readiness_message = (
                "Conexão com a OpenAI testada nesta sessão."
                if st.session_state.get("assistant_connection_tested") is True
                else str(readiness.get("message") or "Credenciais configuradas; conexão com a API ainda não testada.")
            )
            st.caption(readiness_message + " · " + str(readiness.get("model") or "modelo configurado"))
    except Exception as exc:
        st.warning("Não foi possível verificar a configuração do Assistente. Detalhes técnicos não são exibidos no painel.")

    if assistant_available and st.button("Testar conexão com a OpenAI", key="assistant_test_provider_connection"):
        try:
            connection_result = api("/api/assistant/test-connection", "POST", {})
            if connection_result.get("success") is True and connection_result.get("connection_tested") is True:
                st.session_state["assistant_connection_tested"] = True
                st.success("Conexão com a OpenAI testada com sucesso. Nenhuma pergunta, conversa ou dado fiscal foi enviado neste teste.")
            else:
                st.session_state["assistant_connection_tested"] = False
                st.error("O teste não confirmou a conexão. Nenhum contexto fiscal foi enviado.")
        except Exception:
            st.session_state["assistant_connection_tested"] = False
            st.error("Não foi possível testar a conexão. Nenhum contexto fiscal foi enviado; confira a configuração do provedor e tente novamente.")
    if assistant_available and st.session_state.get("assistant_connection_tested") is True:
        st.caption("O teste verifica somente o provedor. Cada envio de pergunta continua exigindo consentimento explícito para o contexto descrito abaixo.")

    st.caption(
        "Privacidade: a pergunta, as mensagens recentes desta conversa e um resumo operacional filtrado são enviados pelo servidor à OpenAI. "
        "As mensagens também ficam armazenadas no histórico local do Assistente no servidor do Ecossistema. "
        "A chave permanece no servidor. Não envie senhas, códigos de acesso ou dados bancários sensíveis."
    )
    consent_to_openai = st.checkbox(
        "Autorizo enviar minha pergunta, as mensagens recentes desta conversa e o resumo operacional filtrado à OpenAI para gerar a resposta.",
        key="assistant_openai_consent",
        disabled=not bool(consent_scope),
        help="Sem esta autorização, o campo de consulta permanece desabilitado. A chave da API continua somente no servidor.",
    )
    if not consent_to_openai:
        st.info("Para usar o Assistente, leia o aviso de privacidade e autorize explicitamente o envio do contexto descrito acima.")

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
        st.warning("Não foi possível carregar o histórico de conversas. Detalhes técnicos não são exibidos no painel.")

    if st.button("Nova consulta", key="new_assistant_session"):
        _reset_assistant_conversation()
        st.rerun()

    for message in st.session_state.assistant_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    submission_warning = st.session_state.pop("assistant_submission_warning", None)
    submission_error = st.session_state.pop("assistant_submission_error", None)
    if submission_warning:
        st.warning(submission_warning)
    if submission_error:
        st.error(submission_error)

    prompt = st.chat_input(
        "Pergunte sobre o Ecossistema, risco ou Reserva Fiscal",
        disabled=(not assistant_available) or (not consent_to_openai),
    )
    if prompt:
        # The permission authorizes this submission only, including failed
        # attempts whose delivery status may need recovery from conversation history.
        st.session_state["assistant_clear_consent_before_render"] = True
        try:
            response = api(
                "/api/assistant/chat",
                "POST",
                {
                    "message": prompt,
                    "conversation_id": st.session_state.get("assistant_conversation_id"),
                    "consent_to_openai": True,
                },
            )
            st.session_state.assistant_conversation_id = response.get("conversation_id")
            st.session_state.assistant_history.append({"role": "user", "content": prompt})
            answer = response.get("answer", "Sem resposta.")
            st.session_state.assistant_history.append({"role": "assistant", "content": answer})
            st.rerun()
        except RuntimeError as exc:
            # Do not present an unanswered prompt as if the provider had replied.
            # A 503 may still have persisted the user message locally; api() keeps
            # its conversation ID so it remains recoverable from saved history.
            if st.session_state.get("assistant_conversation_id"):
                st.session_state["assistant_submission_warning"] = (
                    "A consulta não recebeu resposta. Se o runtime informou que "
                    "a mensagem ficou no histórico, abra essa conversa em "
                    "“Conversas anteriores” depois de restabelecer o serviço."
                )
            st.session_state["assistant_submission_error"] = "Falha no Assistente: " + str(exc)
            st.rerun()
        except Exception:
            st.session_state["assistant_submission_error"] = (
                "Não foi possível enviar a consulta ao Assistente. "
                "Verifique a conexão e tente novamente. Detalhes técnicos não são exibidos no painel."
            )
            st.rerun()



def _is_finite_number(value: Any) -> bool:
    """Reject booleans and numbers that cannot be safely checked for finiteness."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _valid_monthly_planning(monthly: Any, expected_year: int) -> bool:
    """Validate optional month-by-month planning data before displaying it."""
    if not isinstance(monthly, dict):
        return False
    if monthly.get("year") != expected_year or monthly.get("kind") != "PLANNING_ESTIMATE_ONLY":
        return False
    if monthly.get("tax_assessment") is not False:
        return False
    months = monthly.get("months")
    if not isinstance(months, list) or len(months) != 12:
        return False
    for index, item in enumerate(months, start=1):
        if not isinstance(item, dict) or item.get("month") != f"{expected_year:04d}-{index:02d}":
            return False
        entries = item.get("entries")
        if isinstance(entries, bool) or not isinstance(entries, int) or not 0 <= entries <= 1_000_000_000:
            return False
        realized = item.get("realized_result_brl")
        if not _is_finite_number(realized) or not -1_000_000_000_000 <= realized <= 1_000_000_000_000:
            return False
        reserve = item.get("reserve_amount_brl")
        if not _is_finite_number(reserve) or not 0 <= reserve <= 1_000_000_000_000:
            return False
    return True


def _safe_fiscal_count(value: Any) -> int:
    """Render only bounded, genuine integer counts from fiscal API responses."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
        return 0
    return value

def _valid_pending_queue_summary(summary: Any, result_field: str) -> bool:
    if not isinstance(summary, dict) or summary.get("available") is not True:
        return False
    if summary.get("classification_status") != "PENDING_CLASSIFICATION":
        return False
    if summary.get("included_in_totals") is not False or summary.get("reserve_calculated") is not False:
        return False
    as_of_raw = summary.get("as_of")
    if not isinstance(as_of_raw, str) or len(as_of_raw) != 10:
        return False
    try:
        as_of = date.fromisoformat(as_of_raw)
        if as_of.isoformat() != as_of_raw:
            return False
    except ValueError:
        return False
    total = summary.get("total")
    if isinstance(total, bool) or not isinstance(total, int) or not 0 <= total <= 1_000_000_000:
        return False
    periods = summary.get("periods")
    if not isinstance(periods, dict):
        return False
    expected_periods = {
        "day": (as_of, as_of),
        "week": (date.fromordinal(as_of.toordinal() - as_of.weekday()), as_of),
        "month": (as_of.replace(day=1), as_of),
        "year": (as_of.replace(month=1, day=1), as_of),
    }
    for name, (expected_start, expected_end) in expected_periods.items():
        row = periods.get(name)
        if not isinstance(row, dict):
            return False
        dates = []
        for field in ("start", "end"):
            raw_date = row.get(field)
            if not isinstance(raw_date, str) or len(raw_date) != 10:
                return False
            try:
                parsed = date.fromisoformat(raw_date)
                if parsed.isoformat() != raw_date:
                    return False
                dates.append(parsed)
            except ValueError:
                return False
        if dates != [expected_start, expected_end]:
            return False
        for field in ("total", result_field):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000_000:
                return False
    return True


def _recovered_pending_offset(total: Any, requested_offset: Any, page_size: int = 50) -> int:
    """Move stale page positions to the last page that can still contain records."""
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        return 0
    if isinstance(requested_offset, bool) or not isinstance(requested_offset, int) or requested_offset < 0:
        return 0
    if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
        return 0
    if total == 0:
        return 0
    if requested_offset >= total:
        return ((total - 1) // page_size) * page_size
    return requested_offset


def _valid_pending_page(data: Any, expected_offset: int) -> bool:
    """Validate pending-page shape before rendering rows or pagination controls."""
    if not isinstance(data, dict):
        return False
    total, limit, offset, items = (
        data.get("total"), data.get("limit"), data.get("offset"), data.get("items")
    )
    if isinstance(total, bool) or not isinstance(total, int) or not 0 <= total <= 1_000_000_000:
        return False
    if (isinstance(limit, bool) or not isinstance(limit, int) or limit != 50
            or isinstance(offset, bool) or not isinstance(offset, int)
            or offset < 0 or offset != expected_offset):
        return False
    if not isinstance(items, list) or len(items) > limit:
        return False
    if offset < total and offset + len(items) > total:
        return False
    if offset >= total and items:
        return False
    seen_ids = set()
    for item in items:
        if not isinstance(item, dict) or item.get("status") != "PENDING_CLASSIFICATION":
            return False
        pending_id = item.get("pending_id")
        if not isinstance(pending_id, str) or not pending_id.strip() or len(pending_id) > 80:
            return False
        if pending_id in seen_ids:
            return False
        seen_ids.add(pending_id)
    return True


def _valid_review_history(data: Any) -> bool:
    """Only render a well-formed review history returned for the selected pending item."""
    if (not isinstance(data, dict)
            or data.get("status_unchanged") != "PENDING_CLASSIFICATION"
            or data.get("reserve_calculated") is not False
            or not isinstance(data.get("reviews"), list)):
        return False
    for item in data["reviews"]:
        if not isinstance(item, dict):
            return False
        for field in ("candidate_classification", "confirmed_jurisdiction", "reviewer_name",
                      "reviewer_role", "professional_registration", "evidence_reference",
                      "reviewed_on"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                return False
        if item.get("reviewer_identity_status") != "DECLARED_NOT_VERIFIED":
            return False
        if item.get("professional_registration_verified") is not False:
            return False
    return True



def _valid_fiscal_history_page(summary: Any, expected_offset: int, page_size: int = 50) -> bool:
    """Reject malformed fiscal ledger rows and pagination metadata before display."""
    if not isinstance(summary, dict):
        return False
    history = summary.get("history")
    page = summary.get("history_page")
    if not isinstance(history, list) or not isinstance(page, dict):
        return False
    total, limit, offset = page.get("total"), page.get("limit"), page.get("offset")
    returned, has_more = page.get("returned"), page.get("has_more")
    if (isinstance(total, bool) or not isinstance(total, int) or not 0 <= total <= 1_000_000_000
            or isinstance(limit, bool) or not isinstance(limit, int) or limit != page_size
            or isinstance(offset, bool) or not isinstance(offset, int) or offset != expected_offset
            or isinstance(returned, bool) or not isinstance(returned, int) or returned != len(history)
            or not isinstance(has_more, bool) or has_more is not (offset + returned < total)
            or len(history) > page_size or (offset >= total and history)):
        return False
    seen_ids = set()
    for item in history:
        if not isinstance(item, dict) or "owner_id" in item:
            return False
        entry_id = item.get("entry_id")
        category = item.get("category")
        reference = item.get("reference")
        occurred_on = item.get("occurred_on")
        if not isinstance(entry_id, str) or not entry_id.strip() or entry_id in seen_ids:
            return False
        if not isinstance(category, str) or not category.strip():
            return False
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 160:
            return False
        if not isinstance(occurred_on, str) or len(occurred_on) != 10:
            return False
        try:
            if date.fromisoformat(occurred_on).isoformat() != occurred_on:
                return False
        except ValueError:
            return False
        notes = item.get("notes")
        if notes is not None and not isinstance(notes, str):
            return False
        seen_ids.add(entry_id)
    return True


def _valid_fiscal_summary(summary: Any) -> bool:
    """Enable fiscal writes only when every required aggregate is structurally valid."""
    if not isinstance(summary, dict):
        return False
    categories = summary.get("categories")
    periods = summary.get("periods")
    semantics = summary.get("reserve_semantics")
    if not isinstance(categories, dict) or not isinstance(periods, dict) or not isinstance(semantics, dict):
        return False
    brazil = categories.get("BR_DAY_TRADE")
    foreign = categories.get("FOREIGN_FINANCIAL_ASSET")
    if not isinstance(brazil, dict) or not isinstance(foreign, dict):
        return False
    foreign_entries = foreign.get("entries")
    if isinstance(foreign_entries, bool) or not isinstance(foreign_entries, int) or not 0 <= foreign_entries <= 1_000_000_000:
        return False
    if foreign.get("classification_status") != "PENDING_CLASSIFICATION":
        return False
    if foreign.get("rate_available") is not False:
        return False
    for field in ("realized_result_brl", "reserve_amount_brl"):
        value = foreign.get(field)
        if not _is_finite_number(value) or value != 0:
            return False
    brazil_entries = brazil.get("entries")
    if isinstance(brazil_entries, bool) or not isinstance(brazil_entries, int) or not 0 <= brazil_entries <= 1_000_000_000:
        return False
    rate = brazil.get("rate")
    if not _is_finite_number(rate) or not 0 <= rate <= 100:
        return False
    for field in ("realized_result_brl", "reserve_amount_brl"):
        value = brazil.get(field)
        if not _is_finite_number(value) or not -1_000_000_000_000 <= value <= 1_000_000_000_000:
            return False
    if brazil.get("reserve_amount_brl") < 0:
        return False
    total = summary.get("total_reserved_brl")
    if not _is_finite_number(total) or not 0 <= total <= 1_000_000_000_000:
        return False
    if total != brazil.get("reserve_amount_brl"):
        return False
    as_of_raw = summary.get("as_of")
    if not isinstance(as_of_raw, str) or len(as_of_raw) != 10:
        return False
    try:
        as_of = date.fromisoformat(as_of_raw)
        if as_of.isoformat() != as_of_raw:
            return False
    except ValueError:
        return False
    expected_periods = {
        "day": (as_of, as_of),
        "week": (date.fromordinal(as_of.toordinal() - as_of.weekday()), as_of),
        "month": (as_of.replace(day=1), as_of),
        "year": (as_of.replace(month=1, day=1), as_of),
    }
    foreign_pending = summary.get("foreign_pending")
    if foreign_pending is not None:
        if not isinstance(foreign_pending, dict):
            return False
        if foreign_pending.get("available") is True:
            if foreign_pending.get("classification_status") != "PENDING_CLASSIFICATION":
                return False
            if foreign_pending.get("included_in_totals") is not False or foreign_pending.get("reserve_calculated") is not False:
                return False
            for field in ("total", "realized_results", "asset_amounts"):
                count = foreign_pending.get(field)
                if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000_000_000:
                    return False
            pending_as_of_raw = foreign_pending.get("as_of")
            if not isinstance(pending_as_of_raw, str) or len(pending_as_of_raw) != 10:
                return False
            try:
                pending_as_of = date.fromisoformat(pending_as_of_raw)
                if pending_as_of.isoformat() != pending_as_of_raw:
                    return False
            except ValueError:
                return False
            if foreign_pending["total"] != (
                foreign_pending["realized_results"] + foreign_pending["asset_amounts"]
            ):
                return False
            evidence_completeness = foreign_pending.get("evidence_completeness")
            if evidence_completeness is not None:
                if not isinstance(evidence_completeness, dict):
                    return False
                for field in (
                    "total",
                    "missing_institution",
                    "missing_custody_location",
                    "missing_contract_type",
                    "missing_core_evidence",
                ):
                    count = evidence_completeness.get(field)
                    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000_000_000:
                        return False
                if evidence_completeness["total"] != foreign_pending["total"]:
                    return False
                if any(
                    evidence_completeness[field] > evidence_completeness["total"]
                    for field in (
                        "missing_institution",
                        "missing_custody_location",
                        "missing_contract_type",
                        "missing_core_evidence",
                    )
                ):
                    return False
            pending_periods = foreign_pending.get("periods")
            if not isinstance(pending_periods, dict):
                return False
            pending_bounds = {
                "day": (pending_as_of, pending_as_of),
                "week": (
                    date.fromordinal(pending_as_of.toordinal() - pending_as_of.weekday()),
                    pending_as_of,
                ),
                "month": (pending_as_of.replace(day=1), pending_as_of),
                "year": (pending_as_of.replace(month=1, day=1), pending_as_of),
            }
            for period, (expected_start, expected_end) in pending_bounds.items():
                row = pending_periods.get(period)
                if not isinstance(row, dict):
                    return False
                dates = []
                for field in ("start", "end"):
                    raw_date = row.get(field)
                    if not isinstance(raw_date, str) or len(raw_date) != 10:
                        return False
                    try:
                        parsed = date.fromisoformat(raw_date)
                        if parsed.isoformat() != raw_date:
                            return False
                        dates.append(parsed)
                    except ValueError:
                        return False
                if dates != [expected_start, expected_end]:
                    return False
                for field in ("total", "realized_results", "asset_amounts"):
                    count = row.get(field)
                    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000_000_000:
                        return False
                if row["total"] != row["realized_results"] + row["asset_amounts"]:
                    return False
        elif foreign_pending.get("available") is not False:
            return False
        elif foreign_pending.get("included_in_totals") is not False or foreign_pending.get("reserve_calculated") is not False:
            return False
    if semantics.get("kind") != "PLANNING_ESTIMATE_ONLY":
        return False
    for flag in ("tax_liability_confirmed", "monthly_tax_assessment", "monthly_loss_offsets_calculated", "irrf_credits_calculated"):
        if semantics.get(flag) is not False:
            return False
    for period, (expected_start, expected_end) in expected_periods.items():
        row = periods.get(period)
        if not isinstance(row, dict):
            return False
        entries = row.get("entries")
        if isinstance(entries, bool) or not isinstance(entries, int) or not 0 <= entries <= 1_000_000_000:
            return False
        realized_result = row.get("realized_result_brl")
        if not _is_finite_number(realized_result) or not -1_000_000_000_000 <= realized_result <= 1_000_000_000_000:
            return False
        reserve_amount = row.get("reserve_amount_brl")
        if not _is_finite_number(reserve_amount) or not 0 <= reserve_amount <= 1_000_000_000_000:
            return False
        dates = []
        for field in ("start", "end"):
            value = row.get(field)
            if not isinstance(value, str) or len(value) != 10:
                return False
            try:
                parsed_date = date.fromisoformat(value)
                if parsed_date.isoformat() != value:
                    return False
                dates.append(parsed_date)
            except ValueError:
                return False
        if dates != [expected_start, expected_end]:
            return False
    return True


def show_fiscal() -> None:
    if "fiscal_history_offset" not in st.session_state:
        st.session_state.fiscal_history_offset = 0
    summary_available = False
    try:
        summary = api("/api/fiscal-reserve?limit=50&offset=" + str(int(st.session_state.fiscal_history_offset)))
        summary_available = (
            _valid_fiscal_summary(summary)
            and _valid_fiscal_history_page(summary, int(st.session_state.fiscal_history_offset))
        )
        if summary_available:
            page = summary["history_page"]
            recovered_offset = _recovered_pending_offset(page["total"], int(st.session_state.fiscal_history_offset))
            if recovered_offset != st.session_state.fiscal_history_offset:
                st.session_state.fiscal_history_offset = recovered_offset
                st.rerun()
        if not summary_available:
            st.error("Resumo fiscal incompleto ou inválido. Os lançamentos e alterações de percentual ficam bloqueados até a leitura ser validada.")
    except Exception as exc:
        summary = {}
        st.error("Resumo fiscal indisponível. Os lançamentos e alterações de percentual ficam bloqueados. Verifique a disponibilidade do serviço e os registros técnicos locais.")
        st.caption("Detalhes técnicos não são exibidos no painel.")
    st.subheader("Reserva Fiscal")
    st.caption("Planejamento e separação estimada. Operações MT5 cuja elegibilidade fiscal não foi verificada ficam em fila brasileira separada, sem cálculo e fora dos totais. Registros estrangeiros não classificados também ficam fora dos totais; nenhuma alíquota genérica é aplicada.")
    if not summary_available:
        st.info("Os dados fiscais não foram validados nesta consulta. Totais, histórico e formulários permanecem ocultos até a leitura ser recuperada.")
        return
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
                    evidence_labels = {
                        "residencia_fiscal": "residência fiscal na data",
                        "natureza_do_rendimento": "natureza do rendimento",
                        "evento": "tipo de evento",
                        "moeda": "moeda original",
                        "fx_method": "método cambial documentado",
                        "instituicao_ou_autocustodia": "instituição ou autocustódia",
                        "local_custodia": "local de custódia",
                        "tipo_de_contrato": "tipo de contrato",
                        "custodia": "custódia",
                        "local_da_operacao": "local da operação",
                        "controle": "estrutura de controle",
                        "entidade": "identificação da entidade",
                        "lucro": "lucros e documentação",
                    }
                    required_evidence = details.get("requires", [])
                    if isinstance(required_evidence, list) and required_evidence:
                        st.caption("Dados necessários para triagem: " + ", ".join(
                            evidence_labels.get(str(field), str(field).replace("_", " "))
                            for field in required_evidence
                        ))
                    recommended_evidence = details.get("recommended_evidence", [])
                    if isinstance(recommended_evidence, list) and recommended_evidence:
                        st.caption("Evidências recomendadas: " + ", ".join(
                            str(field).replace("_", " ") for field in recommended_evidence
                        ))
                    for limitation in details.get("limitations", []):
                        st.caption(limitation)
        except Exception:
            st.warning("Catálogo de categorias indisponível no momento. Nenhuma categoria adicional foi habilitada.")
    try:
        br = summary.get("categories", {}).get("BR_DAY_TRADE", {})
        foreign = summary.get("categories", {}).get("FOREIGN_FINANCIAL_ASSET", {})
        period_options = {
            "Diário": "day",
            "Semanal": "week",
            "Mensal": "month",
            "Anual": "year",
        }
        selected_period_label = st.selectbox(
            "Período da Reserva Fiscal · Brasil",
            options=list(period_options),
            index=2,
            key="fiscal_brazil_period",
        )
        selected_period_key = period_options[selected_period_label]
        selected_period = summary.get("periods", {}).get(selected_period_key, {})
        a, b, c = st.columns(3)
        a.metric(
            f"Reserva estimada · {selected_period_label.lower()}",
            money(selected_period.get("reserve_amount_brl")),
        )
        b.metric(
            f"Resultado realizado · {selected_period_label.lower()}",
            money(selected_period.get("realized_result_brl")),
        )
        c.metric("Estimativa acumulada · Brasil", money(summary.get("total_reserved_brl")))
        as_of_year = date.fromisoformat(summary["as_of"]).year
        monthly_planning = summary.get("monthly_planning")
        st.markdown(f"#### Histórico mensal de planejamento · {as_of_year}")
        st.caption(
            "Consolidação anual dos lançamentos brasileiros elegíveis já registrados. "
            "Não representa apuração mensal de imposto, não compensa prejuízos e não desconta créditos de IRRF."
        )
        if _valid_monthly_planning(monthly_planning, as_of_year):
            st.dataframe(
                [{
                    "Competência": item["month"],
                    "Lançamentos": item["entries"],
                    "Resultado registrado": money(item["realized_result_brl"]),
                    "Reserva estimada": money(item["reserve_amount_brl"]),
                } for item in monthly_planning["months"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption(
                "Histórico mensal indisponível ou inválido nesta resposta. "
                "Os valores não foram estimados nem substituídos por zeros."
            )
        rate_source_label = {
            "DEFAULT": "padrão inicial do sistema",
            "USER_CONFIGURED": "configurado pelo usuário",
            "LEGACY_UNKNOWN": "origem anterior não identificada",
        }.get(br.get("rate_source"), "origem não identificada")
        st.caption(
            f"Período: {selected_period.get('start', '—')} a {selected_period.get('end', '—')} · "
            f"Brasil day trade · percentual de planejamento {rate_source_label}: {br.get('rate', '—')}%"
        )
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
                col.metric(f"Exterior pendente · {label}", _safe_fiscal_count(pending_period.get("total", 0)))
                col.caption(
                    f"{_safe_fiscal_count(pending_period.get('realized_results', 0))} resultado(s) · "
                    f"{_safe_fiscal_count(pending_period.get('asset_amounts', 0))} ativo(s) · sem cálculo"
                )
            evidence_gaps = foreign_pending.get("evidence_completeness", {})
            if isinstance(evidence_gaps, dict) and evidence_gaps:
                st.caption(
                    "Triagem do exterior: "
                    f"{_safe_fiscal_count(evidence_gaps.get('missing_core_evidence', 0))} de "
                    f"{_safe_fiscal_count(evidence_gaps.get('total', 0))} registro(s) ainda sem instituição, "
                    "custódia ou tipo de contrato completo. Isso não altera classificação nem calcula imposto."
                )
        fiscal_history = summary.get("history", [])
        st.markdown("#### Histórico da Reserva Fiscal")