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
.st-key-panel-toggle { position: relative; width: min(100%, 360px); max-width: 100%; margin: 2rem 0 1rem; }
.st-key-panel-toggle .stButton > button { width: 64px; min-width: 64px; height: 64px; min-height: 64px; padding: 0; border-radius: 50%; background: #080B0F; color: #46D6AD; border: 1px solid #46D6AD; box-shadow: 0 0 10px #46D6AD33; font-weight: 800; font-size: 1.25rem; }
.st-key-panel-toggle .closed-status { color: #7F8B97; font-size: 10px; font-weight: 800; letter-spacing: .06em; padding-left: 0; }
.st-key-panel-toggle .closed-signal { max-width: 190px; font-size: 13px; line-height: 1.25; font-weight: 900; letter-spacing: .025em; white-space: nowrap; }
.st-key-panel-toggle .closed-score { color: #E9EEF3; font-size: 11px; line-height: 1.2; font-weight: 700; white-space: nowrap; }
.st-key-control-hub-shell { width: 100%; max-width: none; margin: 1rem 0 2rem; padding: clamp(1rem, 2vw, 1.5rem); background: #10151B; border: 1px solid #25303B; border-radius: 24px; }
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
  .st-key-control-hub-shell { padding: .8rem; margin: .4rem auto 1rem; border-radius: 18px; }
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
        if fiscal_history:
            display_rows = [fiscal_history_display_row(item) for item in fiscal_history]
            st.dataframe(
                display_rows,
                use_container_width=True,
                hide_index=True,
            )
            csv_buffer = io.StringIO(newline="")
            csv_writer = csv.DictWriter(
                csv_buffer,
                fieldnames=list(display_rows[0].keys()),
                delimiter=";",
                extrasaction="ignore",
            )
            csv_writer.writeheader()
            csv_writer.writerows(display_rows)
            st.download_button(
                "Exportar página exibida · CSV",
                data="\ufeff" + csv_buffer.getvalue(),
                file_name="reserva-fiscal-historico.csv",
                mime="text/csv; charset=utf-8",
                key="fiscal_history_csv_download",
                help="Exporta somente os registros desta página, respeitando os campos ocultados para itens pendentes ou não classificados.",
            )
            st.caption("O arquivo é gerado nesta sessão do painel; exporta apenas a página atual do histórico.")
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
        st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")
        summary = {}

    with st.expander("Percentual de planejamento · Brasil day trade"):
        current_rate = summary.get("categories", {}).get("BR_DAY_TRADE", {}).get("rate", 0) if summary else 0
        with st.form("fiscal_rate_form"):
            rate = st.number_input("Percentual para novos lançamentos", min_value=0.0, max_value=100.0, value=float(current_rate or 0), step=0.5)
            rate_submit = st.form_submit_button("Salvar percentual", disabled=not summary_available)
        if rate_submit:
            try:
                api("/api/fiscal-reserve/rates", "POST", {"rates": {"BR_DAY_TRADE": rate}})
                st.success("Percentual atualizado para novos registros. O histórico preserva o percentual usado em cada lançamento.")
                st.rerun()
            except Exception as exc:
                st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")

    with st.expander("Registrar estimativa · Brasil day trade"):
        st.caption("Use somente se você puder confirmar os critérios abaixo. É uma estimativa de planejamento baseada na sua declaração; não valida o enquadramento nem confirma imposto devido. Se houver dúvida, registre na fila brasileira pendente.")
        with st.form("fiscal_result_form"):
            occurred_on = st.date_input("Data da realização")
            instrument = st.text_input("Ativo / instrumento negociado", max_chars=80)
            institution = st.text_input("Instituição intermediária", max_chars=120)
            market_label = st.text_input("Mercado / ambiente de negociação", max_chars=120, placeholder="Ex.: B3")
            result = st.number_input("Resultado realizado (R$)", min_value=-1000000000000.0, max_value=1000000000000.0, step=10.0, format="%.2f", help="Lucro positivo / prejuízo negativo. Compensações mensais e créditos de IRRF não são calculados.")
            reference = st.text_input("Referência / comprovante", max_chars=160)
            notes = st.text_area(
                "Observações / evidências",
                max_chars=160,
                help="Limite de 160 caracteres para manter o formulário alinhado à validação da API.",
            )
            confirmed = st.checkbox("Confirmo que foi o mesmo ativo, pela mesma instituição, no mesmo dia e em mercado brasileiro elegível.")
            submitted = st.form_submit_button("Registrar estimativa de planejamento", disabled=not summary_available)
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
                st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")

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
            st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")
    try:
        if "domestic_pending_offset" not in st.session_state:
            st.session_state.domestic_pending_offset = 0
        domestic_offset = st.session_state.domestic_pending_offset
        if isinstance(domestic_offset, bool) or not isinstance(domestic_offset, int) or domestic_offset < 0:
            domestic_offset = 0
            st.session_state.domestic_pending_offset = 0
        domestic_data = api(f"/api/fiscal-reserve/domestic-pending?limit=50&offset={domestic_offset}")
        if not _valid_pending_page(domestic_data, domestic_offset):
            raise ValueError("Resposta de paginação brasileira inválida; registros ocultados.")
        recovered_domestic_offset = _recovered_pending_offset(domestic_data["total"], domestic_offset)
        if recovered_domestic_offset != domestic_offset:
            st.session_state.domestic_pending_offset = recovered_domestic_offset
            st.rerun()
        domestic_items = domestic_data["items"]
        domestic_summary = api("/api/fiscal-reserve/domestic-pending/summary")
        if _valid_pending_queue_summary(domestic_summary, "results"):
            domestic_cols = st.columns(4)
            for col, period, label in zip(domestic_cols, ("day", "week", "month", "year"), ("Dia", "Semana", "Mês", "Ano")):
                period_data = domestic_summary.get("periods", {}).get(period, {})
                col.metric(f"Brasil pendente · {label}", _safe_fiscal_count(period_data.get("total", 0)))
                col.caption(f"{_safe_fiscal_count(period_data.get('results', 0))} resultado(s) · sem cálculo")
        else:
            st.warning("Resumo de pendências brasileiras inválido ou indisponível; contagens ocultadas. Os registros continuam fora dos totais.")
        if domestic_items:
            st.dataframe([{"Data": item.get("occurred_on"), "Ativo": item.get("instrument"), "Categoria candidata": item.get("category_candidate") or "Não informada", "Mercado declarado · não verificado": item.get("market_scope"), "Resultado (R$)": item.get("realized_result_brl") if item.get("realized_result_brl") is not None else "—", "Status": "PENDENTE DE CLASSIFICAÇÃO"} for item in domestic_items], use_container_width=True, hide_index=True)
            domestic_page_cols = st.columns(2)
            with domestic_page_cols[0]:
                if st.button("← Pendências brasileiras anteriores", key="domestic_pending_previous", disabled=domestic_offset <= 0):
                    st.session_state.domestic_pending_offset = max(0, domestic_offset - 50)
                    st.rerun()
            with domestic_page_cols[1]:
                if st.button("Próximas pendências brasileiras →", key="domestic_pending_next", disabled=domestic_offset + len(domestic_items) >= domestic_data["total"]):
                    st.session_state.domestic_pending_offset = domestic_offset + 50
                    st.rerun()
            st.caption(f"Exibindo {domestic_offset + 1}–{domestic_offset + len(domestic_items)} de {domestic_data['total']} pendências brasileiras.")
            st.markdown("##### Revisão documental · Brasil")
            st.caption("A revisão registra evidências declaradas. O sistema não verifica identidade ou registro profissional, não muda a classificação e não calcula reserva.")
            review_options = {
                item["pending_id"]: f"{item.get('occurred_on')} · {item.get('instrument')} · {item.get('reference')}"
                for item in domestic_items if item.get("pending_id")
            }
            if "domestic_review_pending_id" in st.session_state and st.session_state.domestic_review_pending_id not in review_options:
                del st.session_state.domestic_review_pending_id
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
                    review_jurisdiction = st.text_input("Jurisdição declarada pelo revisor · não verificada", value="Brasil", max_chars=120)
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
                        st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")
                try:
                    review_data = api(
                        "/api/fiscal-reserve/domestic-pending/" + urllib.parse.quote(selected_pending_id) + "/reviews"
                    )
                    if not _valid_review_history(review_data):
                        raise ValueError("Histórico de revisão brasileiro inválido; conteúdo ocultado.")
                    if review_data["reviews"]:
                        st.dataframe([{
                            "Revisor declarado": item.get("reviewer_name"),
                            "Atuação": item.get("reviewer_role"),
                            "Registro informado": item.get("professional_registration"),
                            "Evidência": item.get("evidence_reference"),
                            "Observações": item.get("review_notes", ""),
                            "Data": item.get("reviewed_on"),
                            "Identidade verificada": "NÃO VERIFICADA" if item.get("reviewer_identity_status") == "DECLARED_NOT_VERIFIED" else "Estado inválido",
                            "Registro profissional verificado": "NÃO VERIFICADO" if item.get("professional_registration_verified") is False else "Estado inválido",
                        } for item in review_data["reviews"]], use_container_width=True, hide_index=True)
                    else:
                        st.caption("Nenhuma evidência de revisão registrada para esta pendência.")
                except Exception as exc:
                    st.warning("Histórico de revisão indisponível. Nenhuma alteração foi confirmada.")
        else:
            st.caption("Nenhuma pendência brasileira cadastrada.")
    except Exception as exc:
        st.warning("Fila brasileira indisponível; nenhum registro foi incluído nos totais. Verifique os registros técnicos locais.")

    st.markdown("#### Exterior · pendente de classificação")
    st.caption("O registro abaixo guarda evidências; não calcula imposto nem entra na reserva.")
    residency_options = {"NOT_INFORMED": "Não informado", "BRAZIL": "Brasil", "FOREIGN": "Exterior", "DUAL_OR_UNCERTAIN": "Dupla ou incerta"}
    income_options = {"NOT_INFORMED": "Não informado", "CAPITAL_GAIN": "Ganho de capital", "INVESTMENT_INCOME": "Rendimento de investimento", "TRADING_RESULT": "Resultado de negociação", "DIVIDEND": "Dividendo", "INTEREST": "Juros", "RENTAL_INCOME": "Aluguel", "OTHER": "Outro"}
    event_options = {"NOT_INFORMED": "Não informado", "ACQUISITION": "Aquisição", "DISPOSAL": "Alienação / venda", "DIVIDEND_RECEIPT": "Recebimento de dividendo", "INTEREST_RECEIPT": "Recebimento de juros", "REDEMPTION": "Resgate", "EXCHANGE": "Troca / permuta", "TRANSFER": "Transferência", "OTHER": "Outro"}
    fx_method_options = {"NOT_INFORMED": "Não informado", "NOT_CONVERTED": "Ainda não convertido", "PTAX_SELL": "PTAX venda", "PTAX_BUY": "PTAX compra", "BROKER_STATEMENT": "Extrato da corretora", "BANK_RECEIPT": "Comprovante bancário", "OTHER_DOCUMENTED": "Outro método documentado"}
    with st.form("foreign_pending_form"):
        col1, col2 = st.columns(2)
        reference = col1.text_input("Referência / comprovante", max_chars=160)
        amount = col2.number_input("Valor original", min_value=0.00000001, max_value=1_000_000_000_000.0, step=1.0, format="%.8f")
        col3, col4 = st.columns(2)
        currency = col3.text_input("Código da moeda (3 letras)", value="USD", max_chars=3).strip().upper()
        instrument = col4.text_input("Instrumento", placeholder="ETF, ação, Forex, CFD, cripto", max_chars=80)
        col5, col6 = st.columns(2)
        jurisdiction = col5.text_input("Jurisdição", placeholder="EUA, Brasil, outro", max_chars=80)
        occurred_on = col6.date_input("Data da operação", key="foreign_date")
        tax_residency = st.selectbox("Residência fiscal declarada na data", list(residency_options), format_func=lambda value: residency_options[value], key="foreign_tax_residency")
        income_nature = st.selectbox("Natureza do rendimento / valor", list(income_options), format_func=lambda value: income_options[value], key="foreign_income_nature")
        event_type = st.selectbox("Tipo de evento", list(event_options), format_func=lambda value: event_options[value], key="foreign_event_type")
        fx_rate = st.number_input("Cotação cambial (opcional)", min_value=0.0, max_value=1_000_000_000_000.0, step=0.0001, format="%.8f")
        fx_date = st.date_input("Data da cotação", key="foreign_fx_date")
        fx_source = st.text_input("Fonte da cotação (opcional)", max_chars=200)
        fx_conversion_method = st.selectbox("Método de conversão cambial", list(fx_method_options), format_func=lambda value: fx_method_options[value], key="foreign_fx_method")
        institution = st.text_input("Corretora / instituição", max_chars=160, key="foreign_institution")
        custody_location = st.text_input("Local de custódia (país, instituição ou autocustódia)", max_chars=120, key="foreign_custody")
        contract_type = st.text_input("Tipo / especificação do contrato", max_chars=120, key="foreign_contract")
        col_cost1, col_cost2, col_cost3 = st.columns(3)
        has_acquisition_cost = col_cost1.checkbox("Informar custo de aquisição", key="foreign_has_acquisition_cost")
        acquisition_cost = col_cost1.number_input("Custo na moeda original", min_value=0.0, max_value=1_000_000_000_000.0, format="%.8f", key="foreign_acquisition_cost") if has_acquisition_cost else None
        has_transaction_fees = col_cost2.checkbox("Informar taxas/custos", key="foreign_has_transaction_fees")
        transaction_fees = col_cost2.number_input("Taxas na moeda original", min_value=0.0, max_value=1_000_000_000_000.0, format="%.8f", key="foreign_transaction_fees") if has_transaction_fees else None
        has_foreign_tax_paid = col_cost3.checkbox("Informar imposto pago fora", key="foreign_has_tax_paid")
        foreign_tax_paid = col_cost3.number_input("Imposto na moeda original", min_value=0.0, max_value=1_000_000_000_000.0, format="%.8f", key="foreign_tax_paid") if has_foreign_tax_paid else None
        notes = st.text_area("Observações", max_chars=1000, key="foreign_notes")
        submitted = st.form_submit_button("Guardar como pendente")
    if submitted:
        try:
            pending_payload = {"reference": reference, "original_amount": amount, "original_currency": currency, "instrument": instrument, "jurisdiction": jurisdiction, "occurred_on": occurred_on.isoformat(), "tax_residency_at_event": tax_residency, "income_nature": income_nature, "event_type": event_type, "fx_conversion_method": fx_conversion_method, "institution": institution, "custody_location": custody_location, "contract_type": contract_type, "acquisition_cost": acquisition_cost, "transaction_fees": transaction_fees, "foreign_tax_paid": foreign_tax_paid, "notes": notes}
            if fx_rate or fx_source:
                if not fx_rate or not fx_source:
                    raise ValueError("Para guardar a cotação, informe valor e fonte.")
                if fx_conversion_method == "NOT_CONVERTED":
                    raise ValueError("Altere o método cambial: há uma cotação informada, mas o método está marcado como ainda não convertido.")
                pending_payload.update({"fx_rate": fx_rate, "fx_date": fx_date.isoformat(), "fx_source": fx_source})
            api("/api/fiscal-reserve/pending", "POST", pending_payload)
            st.success("Registro guardado como pendente. Nenhum cálculo foi feito.")
            st.rerun()
        except Exception as exc:
            st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")

    st.markdown("#### Resultado realizado no exterior")
    st.caption("Informe lucro positivo ou prejuízo negativo. O valor original fica pendente e não entra na reserva.")
    with st.form("foreign_signed_result"):
        ref_signed = st.text_input("Referência do extrato", max_chars=160)
        amount_signed = st.number_input("Resultado original (+ lucro / - prejuízo)", min_value=-1000000000000.0, max_value=1000000000000.0, value=0.0, format="%.8f")
        currency_signed = st.text_input("Código da moeda original (3 letras)", value="USD", max_chars=3).strip().upper()
        instrument_signed = st.text_input("Instrumento", max_chars=80)
        jurisdiction_signed = st.text_input("Jurisdição", max_chars=80)
        date_signed = st.date_input("Data do resultado", key="signed_foreign_date")
        residency_signed = st.selectbox("Residência fiscal declarada na data", list(residency_options), format_func=lambda value: residency_options[value], key="signed_tax_residency")
        income_signed = st.selectbox("Natureza do resultado", list(income_options), format_func=lambda value: income_options[value], key="signed_income_nature")
        event_signed = st.selectbox("Tipo de evento", list(event_options), format_func=lambda value: event_options[value], key="signed_event_type")
        fx_signed = st.number_input("Cotação documentada (opcional)", min_value=0.0, max_value=1_000_000_000_000.0, format="%.8f")
        fx_date_signed = st.date_input("Data da cotação", key="signed_foreign_fx_date")
        fx_source_signed = st.text_input("Fonte da cotação", max_chars=200)
        fx_method_signed = st.selectbox("Método de conversão cambial", list(fx_method_options), format_func=lambda value: fx_method_options[value], key="signed_fx_method")
        institution_signed = st.text_input("Corretora / instituição", max_chars=160, key="signed_institution")
        custody_signed = st.text_input("Local de custódia", max_chars=120, key="signed_custody")
        contract_signed = st.text_input("Tipo / especificação do contrato", max_chars=120, key="signed_contract")
        signed_cost1, signed_cost2, signed_cost3 = st.columns(3)
        has_signed_acquisition_cost = signed_cost1.checkbox("Informar custo de aquisição", key="signed_has_acquisition_cost")
        acquisition_cost_signed = signed_cost1.number_input("Custo na moeda original", min_value=0.0, max_value=1_000_000_000_000.0, format="%.8f", key="signed_acquisition_cost") if has_signed_acquisition_cost else None
        has_signed_fees = signed_cost2.checkbox("Informar taxas/custos", key="signed_has_transaction_fees")
        fees_signed = signed_cost2.number_input("Taxas na moeda original", min_value=0.0, max_value=1_000_000_000_000.0, format="%.8f", key="signed_transaction_fees") if has_signed_fees else None
        has_signed_foreign_tax = signed_cost3.checkbox("Informar imposto pago fora", key="signed_has_tax_paid")
        tax_paid_signed = signed_cost3.number_input("Imposto na moeda original", min_value=0.0, max_value=1_000_000_000_000.0, format="%.8f", key="signed_foreign_tax_paid") if has_signed_foreign_tax else None
        notes_signed = st.text_area("Observações", max_chars=1000)
        submit_signed = st.form_submit_button("Guardar como pendente")
    if submit_signed:
        try:
            signed_payload = {"reference": ref_signed, "original_result": amount_signed, "original_currency": currency_signed, "instrument": instrument_signed, "jurisdiction": jurisdiction_signed, "occurred_on": date_signed.isoformat(), "tax_residency_at_event": residency_signed, "income_nature": income_signed, "event_type": event_signed, "fx_conversion_method": fx_method_signed, "institution": institution_signed, "custody_location": custody_signed, "contract_type": contract_signed, "acquisition_cost": acquisition_cost_signed, "transaction_fees": fees_signed, "foreign_tax_paid": tax_paid_signed, "notes": notes_signed}
            if fx_signed or fx_source_signed:
                if not fx_signed or not fx_source_signed:
                    raise ValueError("Informe cotação e fonte juntas.")
                if fx_method_signed == "NOT_CONVERTED":
                    raise ValueError("Altere o método cambial: há uma cotação informada, mas o método está marcado como ainda não convertido.")
                signed_payload.update({"fx_rate": fx_signed, "fx_date": fx_date_signed.isoformat(), "fx_source": fx_source_signed})
            api("/api/fiscal-reserve/pending-result", "POST", signed_payload)
            st.success("Resultado guardado com o sinal original; continua fora dos totais.")
            st.rerun()
        except Exception as exc:
            st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")


    st.caption("Resultados estrangeiros com sinal original serão mantidos em pendência, fora dos totais até revisão.")

    st.markdown("#### Revisão documental · Exterior")
    st.caption("A revisão registra a classificação candidata e as evidências informadas pelo profissional. O sistema não verifica identidade ou registro, não muda o status pendente e não calcula imposto.")
    try:
        if "foreign_pending_offset" not in st.session_state:
            st.session_state.foreign_pending_offset = 0
        foreign_offset = st.session_state.foreign_pending_offset
        if isinstance(foreign_offset, bool) or not isinstance(foreign_offset, int) or foreign_offset < 0:
            foreign_offset = 0
            st.session_state.foreign_pending_offset = 0
        foreign_pending_data = api(f"/api/fiscal-reserve/pending?limit=50&offset={foreign_offset}")
        if not _valid_pending_page(foreign_pending_data, foreign_offset):
            raise ValueError("Resposta de paginação estrangeira inválida; registros ocultados.")
        recovered_foreign_offset = _recovered_pending_offset(foreign_pending_data["total"], foreign_offset)
        if recovered_foreign_offset != foreign_offset:
            st.session_state.foreign_pending_offset = recovered_foreign_offset
            st.rerun()
        foreign_items = foreign_pending_data["items"]
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
                "Cotação informada (não aplicada)": item.get("fx_rate"),
                "Data da cotação": item.get("fx_date"),
                "Fonte da cotação": item.get("fx_source"),
                "Método declarado": item.get("fx_conversion_method"),
                "Instituição": item.get("institution"),
                "Custódia declarada": item.get("custody_location"),
                "Contrato": item.get("contract_type"),
                "Custo de aquisição (moeda original)": item.get("acquisition_cost"),
                "Taxas (moeda original)": item.get("transaction_fees"),
                "Imposto pago fora (moeda original)": item.get("foreign_tax_paid"),
                "Status": "PENDENTE DE CLASSIFICAÇÃO",
            } for item in foreign_items], use_container_width=True, hide_index=True)
            foreign_page_cols = st.columns(2)
            with foreign_page_cols[0]:
                if st.button("← Pendências do exterior anteriores", key="foreign_pending_previous", disabled=foreign_offset <= 0):
                    st.session_state.foreign_pending_offset = max(0, foreign_offset - 50)
                    st.rerun()
            with foreign_page_cols[1]:
                if st.button("Próximas pendências do exterior →", key="foreign_pending_next", disabled=foreign_offset + len(foreign_items) >= foreign_pending_data["total"]):
                    st.session_state.foreign_pending_offset = foreign_offset + 50
                    st.rerun()
            st.caption(f"Exibindo {foreign_offset + 1}–{foreign_offset + len(foreign_items)} de {foreign_pending_data['total']} pendências do exterior.")
            foreign_review_options = {
                item["pending_id"]: f"{item.get('occurred_on')} · {item.get('instrument')} · {item.get('reference')}"
                for item in foreign_items if item.get("pending_id")
            }
            if "foreign_review_pending_id" in st.session_state and st.session_state.foreign_review_pending_id not in foreign_review_options:
                del st.session_state.foreign_review_pending_id
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
                        "Jurisdição declarada pelo revisor · não verificada", max_chars=120, key="foreign_review_jurisdiction"
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
                        st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")
                try:
                    foreign_review_data = api(
                        "/api/fiscal-reserve/pending/" + urllib.parse.quote(selected_foreign_pending_id) + "/reviews"
                    )
                    if not _valid_review_history(foreign_review_data):
                        raise ValueError("Histórico de revisão estrangeiro inválido; conteúdo ocultado.")
                    if foreign_review_data["reviews"]:
                        st.dataframe([{
                            "Classificação candidata": item.get("candidate_classification"),
                            "Jurisdição": item.get("confirmed_jurisdiction"),
                            "Revisor declarado": item.get("reviewer_name"),
                            "Atuação": item.get("reviewer_role"),
                            "Registro informado": item.get("professional_registration"),
                            "Evidência": item.get("evidence_reference"),
                            "Observações": item.get("review_notes", ""),
                            "Data": item.get("reviewed_on"),
                            "Identidade verificada": "NÃO VERIFICADA" if item.get("reviewer_identity_status") == "DECLARED_NOT_VERIFIED" else "Estado inválido",
                            "Registro profissional verificado": "NÃO VERIFICADO" if item.get("professional_registration_verified") is False else "Estado inválido",
                        } for item in foreign_review_data["reviews"]], use_container_width=True, hide_index=True)
                    else:
                        st.caption("Nenhuma evidência de revisão registrada para esta pendência.")
                except Exception as exc:
                    st.warning("Histórico de revisão estrangeira indisponível. Nenhuma alteração foi confirmada.")
        else:
            st.caption("Nenhuma pendência estrangeira cadastrada.")
    except Exception as exc:
        st.warning("Fila estrangeira indisponível; nenhum registro foi incluído nos totais. Verifique os registros técnicos locais.")

    with st.expander("Prévia de negócios encerrados · MT5 DEMO"):
        lookback = st.number_input("Período de consulta (dias)", min_value=1, max_value=365, value=30, step=1)
        if st.button("Consultar MT5 DEMO", key="mt5_fiscal_preview"):
            try:
                preview = api("/api/fiscal-reserve/mt5-preview?lookback_days=" + str(int(lookback)))
                st.session_state.fiscal_mt5_preview = preview
                st.session_state.fiscal_mt5_confirmed_tickets = set()
            except Exception as exc:
                st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")

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
                    st.warning("A confirmação abaixo guarda a posição na fila brasileira de revisão fiscal, ainda como pendente. Ela não entra na reserva nem nos totais. A classificação de mercado é declarada por você e não verificada independentemente; confira o extrato da corretora antes de confirmar.")
                    for candidate in candidates:
                        ticket = str(candidate.get("ticket", "")).strip()
                        if not ticket:
                            continue
                        with st.form("mt5_confirm_" + ticket):
                            st.write(f"**{candidate.get('symbol', 'Ativo')} · ticket {ticket}**")
                            st.caption(f"Encerramento UTC: {candidate.get('occurred_at_utc', '—')} · Resultado líquido da posição: {candidate.get('net_result_account_currency', '—')} {account_currency} · Negócios somados: {candidate.get('deal_count', '—')}")
                            classified = st.checkbox("Confirmo que a operação ocorreu em mercado brasileiro elegível e atende ao conceito fiscal de day trade: mesmo ativo, mesma instituição e mesmo dia.", key="mt5_class_" + ticket)
                            confirmed = st.form_submit_button("Confirmar e guardar como pendência")
                        if confirmed:
                            if not classified:
                                st.error("Marque a confirmação da classificação declarada antes de guardar a pendência.")
                            else:
                                try:
                                    result = api("/api/fiscal-reserve/mt5-confirm", "POST", {"ticket": ticket, "category": "BR_DAY_TRADE", "market_scope": "BR_ELIGIBLE_MARKET", "confirmed": True})
                                    st.success(f"Ticket {ticket} guardado na fila brasileira de revisão fiscal. Continua pendente, sem cálculo e fora dos totais. A referência impede duplicidade.")
                                    st.session_state.fiscal_mt5_confirmed_tickets = set(st.session_state.get("fiscal_mt5_confirmed_tickets", set())) | {ticket}
                                    st.rerun()
                                except Exception as exc:
                                    st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")
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
                                    st.error("Não foi possível concluir esta operação. Confira os dados e a disponibilidade do serviço; os detalhes técnicos não são exibidos no painel.")
            else:
                st.caption("Nenhuma posição elegível encontrada. Se houver posições retidas, consulte o motivo antes de qualquer lançamento.")


def show_market_analysis() -> None:
    st.subheader("Análise de Mercado")
    st.caption("Disponibilidade de ativos e sessões consultada no MT5 DEMO. Capacidade de negociar no fim de semana não significa mercado aberto agora. Esta tela não envia ordens.")
    try:
        assets_payload = api("/api/market/assets")
        raw_assets = assets_payload.get("assets", [])
        assets = [item for item in raw_assets if isinstance(item, dict)] if isinstance(raw_assets, list) else []
        symbols = []
        for asset in raw_assets if isinstance(raw_assets, list) else []:
            if isinstance(asset, str):
                symbols.append(asset)
            elif isinstance(asset, dict) and asset.get("symbol"):
                symbols.append(str(asset["symbol"]))
        st.caption(f"Fonte declarada: {assets_payload.get('source', '—')} · {int(assets_payload.get('count', len(raw_assets) if isinstance(raw_assets, list) else 0))} ativo(s) retornado(s)")
        if assets:
            st.markdown("#### Universo de ativos e disponibilidade")
            asset_rows = [{
                "Ativo": item.get("symbol") or "—",
                "Classe": item.get("asset_class") or "—",
                "Moeda base": item.get("currency_base") or "—",
                "Moeda de resultado": item.get("currency_profit") or "—",
                "Moeda de margem": item.get("currency_margin") or "—",
                "Tamanho do contrato": item.get("contract_size") if item.get("contract_size") is not None else "—",
                "Dígitos": item.get("digits") if item.get("digits") is not None else "—",
                "Tick size": item.get("trade_tick_size") if item.get("trade_tick_size") is not None else "—",
                "Visível": "SIM" if item.get("visible") is True else "NÃO",
                "Negociável": "SIM" if item.get("tradeable") is True else "NÃO",
                "Cotação": "DISPONÍVEL" if item.get("quote_available") is True else "INDISPONÍVEL",
                "Estado da sessão": item.get("state") or "DESCONHECIDO",
                "Pode operar 24/7": "SIM · capacidade" if item.get("is_24_7_capable") is True or item.get("weekend_capable") is True else "NÃO CONFIRMADO",
                "Adequação": item.get("suitability") or "NÃO AVALIADA",
                "Motivo": item.get("suitability_rationale") or item.get("reason") or "—",
                "Lacunas": "; ".join(str(value) for value in (item.get("suitability_gaps") or [])) or "—",
            } for item in assets]
            st.dataframe(asset_rows, use_container_width=True, hide_index=True)
            st.caption("A indicação 24/7 representa capacidade cadastrada do instrumento, não garantia de cotação, liquidez ou execução contínua. Confirme o estado da sessão e a cotação atuais.")
        elif symbols:
            st.dataframe([{"Ativo": symbol, "Disponibilidade": "Retornado pelo runtime; detalhes não fornecidos"} for symbol in symbols], use_container_width=True, hide_index=True)
        if not symbols:
            st.warning("O runtime não disponibilizou ativos do MT5 DEMO. Verifique a conexão e a fonte de candles.")
            return
        try:
            news = api("/api/news?limit=10")
            st.markdown("#### Notícias e eventos")
            if str(news.get("provider") or "").upper() == "UNCONFIGURED" or news.get("live") is not True:
                st.info("Feed de notícias em tempo real não está configurado. Não considere filtro de notícias como ativo.")
            items = news.get("items", [])
            if items:
                st.dataframe([{
                    "Título": item.get("title") or item.get("headline") or "—",
                    "Fonte": item.get("source") or "—",
                    "Horário": item.get("timestamp") or item.get("published_at") or "—",
                    "Impacto": item.get("impact") or item.get("severity") or "—",
                    "Ativo": item.get("symbol") or "—",
                } for item in items if isinstance(item, dict)], use_container_width=True, hide_index=True)
            else:
                st.caption("Nenhum item de notícia disponível.")
        except Exception as exc:
            st.warning(f"Feed de notícias indisponível: {exc}. A ausência do feed não confirma que eventos foram filtrados.")
        with st.form("market_analysis_form"):
            symbol = st.selectbox("Ativo para análise", sorted(set(symbols)))
            timeframe = st.selectbox("Período gráfico", ["1m", "5m", "15m", "30m", "1h", "4h", "1d"], index=1)
            candle_limit = st.slider("Quantidade de candles", min_value=30, max_value=500, value=100, step=10)
            confirmed = st.checkbox("Confirmo que esta análise é somente para estudo em DEMO/SIMULAÇÃO.")
            submitted = st.form_submit_button("Analisar mercado")
        if submitted:
            if not confirmed:
                st.error("Confirme o uso somente em DEMO/SIMULAÇÃO para solicitar a análise.")
            else:
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
    if not symbol.strip() or stop_distance <= 0 or take_profit_distance <= 0 or quantity_units <= 0 or contract_multiplier <= 0 or spread_price_units < 0:
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



def show_finance_overview() -> None:
    """Keep the general Financeiro entry while fiscal workflows have their own area."""
    st.subheader("Financeiro")
    st.caption(
        "Visão geral financeira do Ecossistema. A Reserva Fiscal continua em uma área principal própria, "
        "onde ficam lançamentos, histórico completo, filas e revisões documentais."
    )
    try:
        summary = api("/api/fiscal-reserve?limit=50&offset=0")
        if not (
            _valid_fiscal_summary(summary)
            and _valid_fiscal_history_page(summary, 0)
        ):
            raise ValueError("Resumo financeiro indisponível ou inválido.")
        month = summary.get("periods", {}).get("month", {})
        columns = st.columns(3)
        columns[0].metric(
            "Reserva estimada · Brasil",
            money(summary.get("total_reserved_brl")),
        )
        columns[1].metric(
            "Reserva estimada · mês",
            money(month.get("reserve_amount_brl")),
        )
        columns[2].metric(
            "Resultado realizado · mês",
            money(month.get("realized_result_brl")),
        )
        st.caption(
            f"Período mensal: {month.get('start', '—')} a {month.get('end', '—')} · "
            "valores de planejamento, não apuração de imposto."
        )
        foreign = summary.get("foreign_pending", {})
        try:
            domestic = api("/api/fiscal-reserve/domestic-pending/summary")
        except Exception:
            domestic = {}
        pending_columns = st.columns(2)
        domestic_count = (
            str(_safe_fiscal_count(domestic.get("total", 0)))
            if _valid_pending_queue_summary(domestic, "results")
            else "Indisponível"
        )
        foreign_count = (
            str(_safe_fiscal_count(foreign.get("total", 0)))
            if isinstance(foreign, dict) and foreign.get("available") is True
            else "Indisponível"
        )
        pending_columns[0].metric("Pendências brasileiras", domestic_count)
        pending_columns[1].metric("Pendências do exterior", foreign_count)
        st.info(
            "As pendências permanecem fora dos totais e não geram reserva. "
            "Para registrar, consultar documentos e revisar itens, abra a área principal Reserva Fiscal."
        )
    except Exception:
        st.warning(
            "A visão financeira não pôde validar os dados do runtime. "
            "Nenhum valor foi estimado nesta tela."
        )


def _kill_switch_activation_payload(reason: Any, confirmed: Any) -> dict[str, Any]:
    """Require an explicit confirmation and a bounded operator reason."""
    if confirmed is not True:
        raise ValueError("Confirme explicitamente a ativação do Kill Switch.")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 240:
        raise ValueError("Informe um motivo de até 240 caracteres.")
    return dict([("confirmed", True), ("reason", reason.strip())])


def show_kill_switch() -> None:
    """Expose only the guarded activation path; deactivation is intentionally absent."""
    st.subheader("Proteção operacional · Kill Switch")
    st.caption(
        "A ativação bloqueia novas execuções. Ela não cancela solicitações já encaminhadas; "
        "essas solicitações precisam ter seus estados reconciliados."
    )
    try:
        status = api("/api/health")
        observability = status.get("operational_observability", {})
        kill = observability.get("kill_switch", {}) if isinstance(observability, dict) else {}
        enabled = kill.get("enabled") is True if isinstance(kill, dict) else None
        kill_state = kill.get("state") if isinstance(kill, dict) else None
        if enabled is True or kill_state == "ACTIVE":
            st.error("KILL SWITCH ATIVO · novas execuções bloqueadas")
            reason = kill.get("reason")
            if isinstance(reason, str) and reason.strip():
                st.caption(f"Motivo registrado: {reason}")
        elif enabled is False and kill_state == "CLEAR":
            st.success("Kill Switch confirmado como inativo pelo runtime.")
        else:
            st.warning(
                "Estado do Kill Switch não confirmado pelo runtime. "
                "Não interprete ausência de conexão como proteção inativa."
            )
        execution = observability.get("execution", {}) if isinstance(observability, dict) else {}
        st.caption(
            "Estado de execução: "
            + str(execution.get("state", "não informado"))
            + " · REAL: DESABILITADO"
        )
    except Exception:
        st.error(
            "Não foi possível consultar o estado atual. A ativação continuará protegida "
            "pela confirmação do servidor; confira a conectividade antes de prosseguir."
        )

    with st.form("guarded_kill_switch_activation_form"):
        reason = st.text_input("Motivo obrigatório da ativação", max_chars=240)
        confirmed = st.checkbox(
            "Confirmo que quero bloquear novas execuções neste runtime."
        )
        submitted = st.form_submit_button("Ativar Kill Switch")
    if not submitted:
        return
    try:
        payload = _kill_switch_activation_payload(reason, confirmed)
        result = api("/api/runtime/kill-switch/activate", "POST", payload)
        if result.get("activated") is True and result.get("execution_allowed") is False:
            st.success("Kill Switch ativado. Novas execuções estão bloqueadas.")
            st.warning(
                "Solicitações já encaminhadas não foram canceladas. "
                "Reconcilie os identificadores pendentes/desconhecidos antes de qualquer retomada."
            )
            pending = result.get("pending_request_ids", [])
            unknown = result.get("unknown_request_ids", [])
            if pending or unknown:
                st.write("Solicitações pendentes:", pending)
                st.write("Solicitações com estado desconhecido:", unknown)
        else:
            st.error("O runtime não confirmou a ativação. Verifique o estado operacional.")
    except ValueError as exc:
        st.error(str(exc))
    except Exception:
        st.error("Não foi possível confirmar a ativação. Consulte o estado do runtime antes de repetir.")


def show_readonly_module(module_name: str) -> None:
    """Render mapped runtime views and guarded controls for the selected module."""
    if module_name == "Financeiro":
        show_finance_overview()
        return
    views = {
        "Operação": ("Estado operacional", "/api/health"),
        "Motor de Decisão": ("Motor de Decisão · última análise", "/api/runtime/analysis/latest"),
        "Gestão de Risco": ("Gestão de Risco", "/api/risk"),
        "Notificações": ("Central de Notificações", "/api/notifications"),
        "Ambiente MT5 DEMO": ("Conexões e ambiente", "/api/connections"),
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
        "Auditoria": ("Auditoria operacional", "/api/security/audit"),
    }
    if module_name == "Kill Switch":
        show_kill_switch()
        return
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
        if module_name == "Configurações":
            prefs = data.get("preferences", {}) if isinstance(data, dict) else {}
            candle = prefs.get("candle", {}) if isinstance(prefs.get("candle"), dict) else {}
            notifications = prefs.get("notifications", {}) if isinstance(prefs.get("notifications"), dict) else {}
            st.caption("Preferências de apresentação e conveniência. Salvar aqui não autoriza ordens, autonomia, alteração de risco ou execução REAL.")
            cols = st.columns(4)
            cols[0].metric("Ativo padrão", str(prefs.get("default_symbol", "—")))
            cols[1].metric("Período padrão", str(prefs.get("default_timeframe", "—")))
            cols[2].metric("Tema", str(prefs.get("chart_theme", "—")))
            cols[3].metric("Modo selecionado", "DEMO · REAL bloqueado")

            with st.expander("Preferências gerais e de análise", expanded=True):
                with st.form("safe_general_preferences_form"):
                    default_symbol = st.text_input("Ativo padrão", value=str(prefs.get("default_symbol", "EURUSD")), max_chars=32)
                    timeframe_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
                    current_timeframe = str(prefs.get("default_timeframe", "5m"))
                    default_timeframe = st.selectbox("Período padrão", timeframe_options, index=timeframe_options.index(current_timeframe) if current_timeframe in timeframe_options else 1)
                    theme_options = ["DARK", "LIGHT", "SYSTEM"]
                    current_theme = str(prefs.get("chart_theme", "DARK")).upper()
                    chart_theme = st.selectbox("Tema do gráfico", theme_options, index=theme_options.index(current_theme) if current_theme in theme_options else 0)
                    st.info("Proteções obrigatórias: candle fechado e filtros de confirmação permanecem ativos e não podem ser desligados por esta tela.")
                    show_technical_details = st.checkbox("Mostrar detalhes técnicos por padrão", value=prefs.get("show_technical_details_by_default") is True)
                    general_submit = st.form_submit_button("Salvar preferências gerais")
                if general_submit:
                    if not default_symbol.strip():
                        st.error("Informe um ativo padrão.")
                    else:
                        try:
                            api("/api/preferences", "POST", {
                                "default_symbol": default_symbol.strip().upper(),
                                "default_timeframe": default_timeframe,
                                "chart_theme": chart_theme,
                                "show_technical_details_by_default": show_technical_details,
                            })
                            st.success("Preferências gerais salvas.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível salvar as preferências gerais: {exc}")

            with st.expander("Aparência dos candles"):
                with st.form("safe_candle_preferences_form"):
                    style_options = ["CANDLESTICK", "HOLLOW", "OHLC", "LINE"]
                    current_style = str(candle.get("style", "CANDLESTICK")).upper()
                    candle_style = st.selectbox("Estilo", style_options, index=style_options.index(current_style) if current_style in style_options else 0)
                    color_options = ["DEFAULT", "CUSTOM", "MONOCHROME"]
                    current_color_mode = str(candle.get("color_mode", "DEFAULT")).upper()
                    candle_color_mode = st.selectbox("Modo de cores", color_options, index=color_options.index(current_color_mode) if current_color_mode in color_options else 0)
                    bullish_color = st.text_input("Cor de alta (HEX)", value=str(candle.get("bullish_color", "#58d68d")), max_chars=7)
                    bearish_color = st.text_input("Cor de baixa (HEX)", value=str(candle.get("bearish_color", "#ff7676")), max_chars=7)
                    wick_color = st.text_input("Cor do pavio (HEX)", value=str(candle.get("wick_color", "#aab5c8")), max_chars=7)
                    border_enabled = st.checkbox("Exibir bordas", value=candle.get("border_enabled") is not False)
                    show_wicks = st.checkbox("Exibir pavios", value=candle.get("show_wicks") is not False)
                    show_bodies = st.checkbox("Exibir corpos", value=candle.get("show_bodies") is not False)
                    candle_submit = st.form_submit_button("Salvar aparência dos candles")
                if candle_submit:
                    colors = (bullish_color, bearish_color, wick_color)
                    if any(len(color) not in (4, 7) or not color.startswith("#") for color in colors):
                        st.error("Use cores HEX válidas, como #58d68d.")
                    else:
                        try:
                            api("/api/preferences/candles", "POST", {
                                "style": candle_style,
                                "color_mode": candle_color_mode,
                                "bullish_color": bullish_color,
                                "bearish_color": bearish_color,
                                "wick_color": wick_color,
                                "border_enabled": border_enabled,
                                "show_wicks": show_wicks,
                                "show_bodies": show_bodies,
                            })
                            st.success("Aparência dos candles salva.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível salvar a aparência dos candles: {exc}")

            with st.expander("Preferências de notificações"):
                notification_labels = {
                    "important_enabled": "Alertas importantes",
                    "system_updates_enabled": "Atualizações do sistema",
                    "security_enabled": "Segurança",
                    "market_enabled": "Mercado",
                    "risk_enabled": "Risco",
                    "connection_enabled": "Conexões",
                    "execution_enabled": "Execução",
                    "learning_enabled": "Aprendizado",
                    "recovery_enabled": "Recuperação",
                    "info_enabled": "Informativos",
                }
                with st.form("safe_notification_preferences_form"):
                    notification_values = {
                        key: st.checkbox(label, value=notifications.get(key) is True, key="notification_pref_" + key)
                        for key, label in notification_labels.items()
                    }
                    st.checkbox("Alertas críticos (sempre ativos)", value=True, disabled=True)
                    notification_submit = st.form_submit_button("Salvar notificações")
                if notification_submit:
                    try:
                        api("/api/preferences/notifications", "POST", notification_values)
                        st.success("Preferências de notificações salvas. Alertas críticos continuam ativos.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível salvar as notificações: {exc}")

            st.markdown("#### Limites de autorização")
            safety_cols = st.columns(3)
            safety_cols[0].metric("Operação autônoma", "DESABILITADA")
            safety_cols[1].metric("Execução REAL", "DESABILITADA")
            safety_cols[2].metric("Execução permitida", "NÃO")
            st.caption("Estas configurações não alteram limites de risco, não ativam autonomia, não enviam ordens e não liberam REAL.")
            return

        if module_name == "Escola / Tutorial / Onboarding":
            guide = data.get("guide", {}) if isinstance(data, dict) else {}
            steps = guide.get("steps", []) if isinstance(guide, dict) else []
            steps = [step for step in steps if isinstance(step, dict)] if isinstance(steps, list) else []
            st.caption("Roteiro guiado para localizar e compreender os módulos do Ecossistema. A marcação de etapas fica apenas nesta sessão do Streamlit.")
            st.subheader(str(guide.get("title") or "Primeiros passos no Ecossistema"))
            if not steps:
                st.warning("O roteiro de onboarding não está disponível no runtime.")
                st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
                return
            completed = 0
            for index, step in enumerate(steps, start=1):
                step_id = str(step.get("step_id") or f"step-{index}")
                title = str(step.get("title") or f"Etapa {index}")
                purpose = str(step.get("purpose") or "Objetivo não informado.")
                location = str(step.get("location") or "—").replace("_", " ").title()
                with st.expander(f"{index}. {title} · {location}", expanded=(index == 1)):
                    st.write(purpose)
                    st.caption("Próximo passo: " + str(step.get("action_hint") or "Consulte o módulo correspondente."))
                    if step.get("technical_details_hidden") is True:
                        st.caption("Detalhes técnicos ficam ocultos nesta orientação inicial.")
                    done = st.checkbox("Marcar etapa como revisada", key=f"onboarding_reviewed_{step_id}")
                    if done:
                        completed += 1
            st.progress(completed / len(steps))
            st.caption(f"Etapas revisadas nesta sessão: {completed}/{len(steps)}")
            st.success(str(guide.get("completion_message") or "Roteiro concluído.")) if completed == len(steps) else st.info("Você pode continuar o roteiro em qualquer ordem; a marcação não altera o runtime.")
            if guide.get("execution_authorized") is not False:
                st.error("O roteiro não confirmou explicitamente o bloqueio de execução. Não use esta tela como autorização.")
            else:
                st.caption("Este roteiro é educativo. Execução autorizada: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Memória":
            records = data.get("records", []) if isinstance(data, dict) else []
            records = [item for item in records if isinstance(item, dict)] if isinstance(records, list) else []
            st.caption("Histórico de decisões de análise mais recentes. Resultados anotados são registros de estudo manual.")
            outcomes = [str(item.get("outcome") or "SEM RESULTADO").upper() for item in records]
            cols = st.columns(4)
            cols[0].metric("Registros carregados", len(records))
            cols[1].metric("Vitórias anotadas", sum(value == "WIN" for value in outcomes))
            cols[2].metric("Derrotas anotadas", sum(value == "LOSS" for value in outcomes))
            cols[3].metric("Sem resultado", sum(value == "SEM RESULTADO" for value in outcomes))
            if not records:
                st.info("Nenhum registro de decisão disponível neste runtime.")
                st.caption("Histórico somente leitura · execução permitida: NÃO · REAL: DESABILITADO")
                return
            result_values = sorted(set(outcomes))
            signal_values = sorted({str(item.get("signal") or "—").upper() for item in records})
            filter_cols = st.columns(2)
            selected_result = filter_cols[0].selectbox("Filtrar resultado anotado", ["Todos"] + result_values, key="memory_result_filter")
            selected_signal = filter_cols[1].selectbox("Filtrar sinal", ["Todos"] + signal_values, key="memory_signal_filter")
            filtered = [
                item for item in records
                if (selected_result == "Todos" or str(item.get("outcome") or "SEM RESULTADO").upper() == selected_result)
                and (selected_signal == "Todos" or str(item.get("signal") or "—").upper() == selected_signal)
            ]
            rows = [{
                "Data/hora": item.get("created_at", "—"),
                "Ativo": item.get("symbol") or "—",
                "Timeframe": item.get("timeframe") or "—",
                "Sinal": item.get("signal") or "—",
                "Pontuação": item.get("score", "—"),
                "Confirmado para análise": "SIM" if item.get("confirmed") is True else "NÃO",
                "Resultado anotado": item.get("outcome") or "SEM RESULTADO",
                "Origem do resultado": item.get("outcome_source") or "—",
                "Motivo": item.get("reason") or "—",
            } for item in filtered]
            st.caption(f"Exibindo {len(filtered)} de {len(records)} registros carregados; a API fornece até 50 decisões recentes nesta tela.")
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum registro corresponde aos filtros selecionados.")

            pending_outcome_records = [
                item for item in records
                if isinstance(item.get("decision_id"), str)
                and bool(item.get("decision_id", "").strip())
                and item.get("confirmed") is True
                and str(item.get("signal") or "").upper() in {"COMPRA", "VENDA"}
                and not str(item.get("outcome") or "").strip()
            ]
            st.markdown("#### Registrar resultado de estudo · WIN/LOSS")
            st.caption(
                "Registre manualmente o desfecho de uma decisão confirmada de COMPRA ou VENDA. "
                "Esta anotação não consulta a corretora, não comprova lucro/prejuízo e não altera ordens."
            )
            if pending_outcome_records:
                outcome_labels = {
                    str(item["decision_id"]): (
                        f"{item.get('symbol') or 'Ativo não informado'} · "
                        f"{item.get('timeframe') or 'Período não informado'} · "
                        f"{str(item.get('signal') or '').upper()} · "
                        f"score {item.get('score', '—')} · {item.get('created_at') or 'data não informada'}"
                    )
                    for item in pending_outcome_records
                }
                with st.form("memory_manual_outcome_form"):
                    selected_decision_id = st.selectbox(
                        "Decisão confirmada sem resultado",
                        options=list(outcome_labels),
                        format_func=lambda value: outcome_labels.get(value, value),
                    )
                    selected_outcome = st.selectbox(
                        "Resultado observado · anotação manual",
                        ["WIN", "LOSS", "DRAW", "OPEN", "VOID"],
                    )
                    confirm_manual_outcome = st.checkbox(
                        "Confirmo que este resultado é uma anotação manual de estudo, não uma confirmação independente da corretora."
                    )
                    outcome_submit = st.form_submit_button(
                        "Salvar resultado manual",
                        disabled=not confirm_manual_outcome,
                    )
                if outcome_submit and confirm_manual_outcome:
                    try:
                        saved_outcome = api(
                            "/api/outcome",
                            "POST",
                            {
                                "decision_id": selected_decision_id,
                                "outcome": selected_outcome,
                            },
                        )
                        if (
                            saved_outcome.get("decision_id") == selected_decision_id
                            and saved_outcome.get("outcome") == selected_outcome
                            and saved_outcome.get("outcome_source") == "MANUAL_STUDY"
                        ):
                            st.success("Resultado manual registrado no histórico de decisões.")
                            st.rerun()
                        else:
                            st.warning("O runtime não confirmou o registro. Confira o histórico antes de tentar novamente.")
                    except Exception:
                        st.error("Não foi possível registrar o resultado manual. O estado do histórico não foi confirmado.")
            else:
                st.info("Não há decisões direcionais confirmadas sem resultado manual nos 50 registros carregados.")
            st.caption("WIN/LOSS/DRAW/OPEN/VOID são anotações manuais de estudo; não são resultados financeiros confirmados pela corretora.")
            st.caption("Somente leitura · execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Motor de Decisão":
            st.caption("Leitura da última análise calculada pelo runtime. Esta tela não solicita uma nova análise nem envia ordens.")
            if data.get("available") is not True:
                st.info("Ainda não existe uma análise recente disponível neste runtime. Abra Análise de Mercado e solicite uma análise em DEMO/SIMULAÇÃO.")
                st.caption("REAL: DESABILITADO · execução permitida: NÃO")
                return
            latest = data.get("analysis") or {}
            details = latest.get("analysis") or {}
            cycle = latest.get("analysis_cycle") or {}
            signal = str(latest.get("signal") or "AGUARDAR").upper()
            candidate = str(latest.get("candidate_signal") or details.get("candidate_signal") or "—").upper()
            score = latest.get("score", details.get("score", "—"))
            cols = st.columns(4)
            cols[0].metric("Decisão efetiva", signal)
            cols[1].metric("Pontuação", f"{score}/100" if score != "—" else "—")
            cols[2].metric("Ativo", details.get("symbol", cycle.get("symbol", "—")))
            cols[3].metric("Timeframe", details.get("timeframe", cycle.get("timeframe", "—")))
            st.write("Justificativa: " + str(latest.get("reason") or details.get("reason") or "Não informada."))
            st.caption("Sinal candidato do motor: " + candidate + " · candidato não significa autorização de operação.")
            st.caption("Horário: " + str(cycle.get("timestamp") or "não informado"))
            st.caption("Somente leitura · execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Operação":
            st.markdown("#### Estado operacional · última consulta")
            st.caption("Os indicadores abaixo são consultados ao abrir esta tela ou ao clicar em Atualizar; não representam transmissão contínua.")
            if st.button("Atualizar painel de operação", key="refresh_operation_overview"):
                for cache_key in ("operation_health", "operation_connections", "operation_risk", "latest_operation_analysis"):
                    st.session_state.pop(cache_key, None)
            read_models = (
                ("operation_health", "/api/health"),
                ("operation_connections", "/api/connections"),
                ("operation_risk", "/api/risk"),
                ("latest_operation_analysis", "/api/runtime/analysis/latest"),
            )
            for cache_key, route in read_models:
                if cache_key not in st.session_state:
                    try:
                        st.session_state[cache_key] = api(route)
                        st.session_state[cache_key + "_error"] = ""
                    except Exception as exc:
                        st.session_state[cache_key] = None
                        st.session_state[cache_key + "_error"] = str(exc)
            health = st.session_state.get("operation_health") or {}
            connections = st.session_state.get("operation_connections") or {}
            risk = st.session_state.get("operation_risk") or {}
            latest_payload = st.session_state.get("latest_operation_analysis")
            observability = health.get("operational_observability") or {}
            market_data = observability.get("market_data") or {}
            execution = observability.get("execution") or {}
            recovery = observability.get("recovery") or {}
            reconciliation = observability.get("reconciliation") or {}
            kill_switch = observability.get("kill_switch") or {}
            runtime_health = observability.get("runtime_health") or {}
            status_cols = st.columns(4)
            status_cols[0].metric("Modo", health.get("mode", "—"))
            status_cols[1].metric("Saúde geral", health.get("health", "—"))
            status_cols[2].metric("MT5 DEMO", health.get("mt5_demo", "—"))
            status_cols[3].metric("Execução REAL", health.get("real", "DESABILITADO"))
            st.caption("Execução permitida: NÃO · este painel apresenta telemetria; não envia ordens.")
            if not health:
                st.warning("Estado do runtime indisponível: " + str(st.session_state.get("operation_health_error") or "sem resposta"))
            st.markdown("#### Segurança e continuidade")
            safety_cols = st.columns(4)
            safety_cols[0].metric("Kill Switch", "ATIVO" if kill_switch.get("enabled") is True else str(kill_switch.get("state") or "DESCONHECIDO"))
            safety_cols[1].metric("Recuperação", recovery.get("state", "DESCONHECIDA"))
            safety_cols[2].metric("Reconciliação", reconciliation.get("state", "DESCONHECIDA"))
            safety_cols[3].metric("Saúde operacional", runtime_health.get("state", "DESCONHECIDA"))
            if kill_switch.get("reason"):
                st.warning("Motivo do Kill Switch: " + str(kill_switch["reason"]))
            if recovery.get("message"):
                st.caption("Recuperação: " + str(recovery["message"]))
            pending_ids = reconciliation.get("pending_request_ids") or []
            unknown_ids = reconciliation.get("unknown_request_ids") or []
            if pending_ids or unknown_ids:
                st.warning(f"Reconciliação necessária · {len(pending_ids)} solicitação(ões) pendente(s) · {len(unknown_ids)} estado(s) desconhecido(s). Não retome operações sem reconciliar.")
            st.markdown("#### Mercado e conexão")
            market_cols = st.columns(4)
            market_cols[0].metric("Dados de mercado", market_data.get("health", "DESCONHECIDOS"))
            market_cols[1].metric("Ativo observado", market_data.get("symbol") or "—")
            market_cols[2].metric("Timeframe", market_data.get("timeframe") or "—")
            market_cols[3].metric("Candles", market_data.get("candle_count") if market_data.get("candle_count") is not None else "—")
            st.caption(str(market_data.get("message") or "Estado reportado pelo runtime; não é confirmação independente da corretora."))
            if market_data.get("stale") is True or market_data.get("gap_count", 0):
                st.warning(f"Dados podem estar desatualizados ou com lacunas · lacunas: {market_data.get('gap_count', '—')}")
            connection_rows = [{"Componente": key, "Estado": value} for key, value in connections.items() if isinstance(value, (str, int, float, bool))]
            if connection_rows:
                st.dataframe(connection_rows, use_container_width=True, hide_index=True)
            st.markdown("#### Limites de risco configurados")
            configured_limits = risk.get("configured_limits") or {}
            risk_cols = st.columns(3)
            risk_cols[0].metric("Limite de perda diária", money(configured_limits.get("daily_loss_limit")))
            risk_cols[1].metric("Máximo de operações", configured_limits.get("max_operations", "—"))
            risk_cols[2].metric("Perdas consecutivas", configured_limits.get("max_consecutive_losses", "—"))
            st.caption("São parâmetros configurados, não P&L atual nem prova de que todos os limites foram aplicados a uma execução.")
            if risk.get("allowed") is not True:
                st.warning("Barreira de risco não liberou a operação: " + str(risk.get("reason") or "motivo não informado"))
            elif risk:
                st.info("A avaliação da barreira de risco está positiva, mas isso não autoriza execução neste painel.")
            st.markdown("#### Último sinal recebido")
            latest_error = st.session_state.get("latest_operation_analysis_error", "")
            if latest_error:
                st.warning("Último sinal indisponível: " + latest_error)
            elif not isinstance(latest_payload, dict) or latest_payload.get("available") is not True:
                st.info("Ainda não há análise disponível neste runtime. Abra Análise de Mercado e solicite uma análise em DEMO/SIMULAÇÃO.")
            else:
                latest = latest_payload.get("analysis") or {}
                details = latest.get("analysis") or {}
                cycle = latest.get("analysis_cycle") or {}
                signal = str(latest.get("signal") or "AGUARDAR").upper()
                score = latest.get("score", details.get("score", "—"))
                signal_cols = st.columns(4)
                signal_cols[0].metric("Sinal", signal)
                signal_cols[1].metric("Pontuação", f"{score}/100" if score != "—" else "—")
                signal_cols[2].metric("Ativo", details.get("symbol", cycle.get("symbol", "—")))
                signal_cols[3].metric("Período", details.get("timeframe", cycle.get("timeframe", "—")))
                st.caption("Horário da análise: " + str(cycle.get("timestamp") or "não informado"))
                st.write(latest.get("reason") or details.get("reason") or "Sem justificativa fornecida pelo motor.")
                st.caption("Sinal informativo · não é ordem, recomendação garantida ou autorização de execução.")
            for cache_key, _route in read_models:
                error = st.session_state.get(cache_key + "_error", "")
                if error:
                    st.caption(f"Consulta {cache_key.replace('operation_', '').replace('_', ' ')}: {error}")
        if module_name == "Notificações":
            try:
                all_payload = api("/api/notifications/all")
                all_items = all_payload.get("items", []) if isinstance(all_payload, dict) else []
            except Exception as exc:
                all_items = []
                st.warning(f"Histórico completo indisponível: {exc}")
            items = data.get("items", [])
            summary_cols = st.columns(3)
            summary_cols[0].metric("Alertas ativos", data.get("count", len(items)))
            summary_cols[1].metric("Críticos ativos", data.get("critical_count", 0))
            summary_cols[2].metric("Exigem atenção", data.get("unread", sum(1 for item in items if item.get("requires_attention"))))
            if not all_items and not items:
                st.success("Nenhuma notificação registrada ou ativa.")
                return
            st.markdown("#### Histórico de notificações")
            if all_items:
                severity_options = ["TODAS"] + sorted({str(item.get("severity", "INFO")).upper() for item in all_items})
                selected_severity = st.selectbox("Filtrar gravidade", severity_options, key="notification_history_severity")
                visible_items = [
                    item for item in all_items
                    if selected_severity == "TODAS" or str(item.get("severity", "INFO")).upper() == selected_severity
                ]
                display_rows = []
                for item in visible_items:
                    display_rows.append({
                        "Horário": item.get("created_at") or item.get("timestamp") or "—",
                        "Gravidade": str(item.get("severity", "INFO")).upper(),
                        "Categoria": str(item.get("kind", "SYSTEM")).upper(),
                        "Título": item.get("title", "Notificação"),
                        "Mensagem": item.get("message", ""),
                        "Atenção necessária": bool(item.get("requires_attention", False)),
                        "Bloqueante": bool(item.get("blocking", False)),
                    })
                st.dataframe(display_rows, use_container_width=True, hide_index=True)
                notification_csv = io.StringIO(newline="")
                notification_writer = csv.DictWriter(
                    notification_csv,
                    fieldnames=list(display_rows[0].keys()) if display_rows else [
                        "Horário", "Gravidade", "Categoria", "Título", "Mensagem",
                        "Atenção necessária", "Bloqueante",
                    ],
                    delimiter=";",
                )
                notification_writer.writeheader()
                notification_writer.writerows(display_rows)
                st.download_button(
                    "Exportar notificações filtradas · CSV",
                    data="\ufeff" + notification_csv.getvalue(),
                    file_name="controlador-trading-notificacoes.csv",
                    mime="text/csv; charset=utf-8",
                    key="notification_history_csv_download",
                )
                st.caption(f"Exibindo {len(display_rows)} de {len(all_items)} notificação(ões) retornada(s) pelo runtime.")
            else:
                st.info("Não foi possível obter o histórico completo; abaixo estão os alertas ativos disponíveis.")
                for item in items:
                    severity = str(item.get("severity", "INFO")).upper()
                    message = f"{item.get('title', 'Notificação')} — {item.get('message', '')}"
                    if severity == "CRITICAL":
                        st.error(message)
                    elif severity == "IMPORTANT":
                        st.warning(message)
                    else:
                        st.info(message)
            st.caption("Alertas críticos permanecem ativos independentemente das preferências. Histórico somente leitura; esta tela não marca, apaga ou altera notificações.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Gestão de Risco":
            limits = data.get("configured_limits", {}) if isinstance(data, dict) else {}
            allowed = data.get("allowed") is True
            st.caption("Painel de limites configurados pelo Risk Manager. Estes valores não são o P&L atual da conta nem uma autorização de ordem.")
            cols = st.columns(3)
            cols[0].metric("Limite de perda diária", str(limits.get("daily_loss_limit", "—")))
            cols[1].metric("Máximo de operações", str(limits.get("max_operations", "—")))
            cols[2].metric("Máximo de perdas consecutivas", str(limits.get("max_consecutive_losses", "—")))
            if allowed:
                st.success("Gate de risco reportado: LIBERADO")
            else:
                st.error("Gate de risco reportado: BLOQUEADO")
            st.markdown("#### Motivo informado pelo motor")
            st.write(str(data.get("reason") or "O motor não forneceu uma justificativa."))
            st.markdown("#### Dados externos")
            st.metric("Provedor de notícias", str(data.get("news_provider", "NÃO CONFIGURADO")))
            if str(data.get("news_provider", "")).upper() == "UNCONFIGURED":
                st.info("O provedor de notícias não está configurado; não trate esta tela como confirmação de filtro de notícias em tempo real.")
            st.caption("Leitura somente informativa · não altera limites, não libera execução e não envia ordens.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Auditoria":
            events = data.get("events", [])
            persistence = str(data.get("persistence") or "UNKNOWN").upper()
            cols = st.columns(4)
            cols[0].metric("Eventos retidos", data.get("count", len(events)))
            cols[1].metric("Eventos exibidos", data.get("returned", len(events)))
            cols[2].metric("Limite de retenção", data.get("retention_limit", "—"))
            cols[3].metric("Persistência", {
                "DURABLE": "PERSISTENTE",
                "NOT_CONFIGURED": "NÃO CONFIGURADA",
                "WRITE_FAILED": "FALHA DE GRAVAÇÃO",
                "READ_FAILED": "FALHA DE LEITURA",
                "SCHEMA_INVALID": "ESQUEMA INVÁLIDO",
                "UNAVAILABLE": "INDISPONÍVEL",
            }.get(persistence, "NÃO CONFIRMADA"))
            if persistence not in {"DURABLE", "NOT_CONFIGURED"}:
                st.error("A trilha de auditoria não confirmou persistência no SQLite. O histórico em memória pode não sobreviver a uma reinicialização.")
            elif persistence == "NOT_CONFIGURED":
                st.warning("Persistência SQLite não configurada. O histórico pode existir somente em memória.")
            if events:
                st.dataframe(events, use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum evento de segurança foi registrado nesta instância.")
            st.caption("Registro de segurança somente leitura. Hashes de cliente, endereços IP, credenciais e corpos de requisição não são exibidos.")
            st.caption("A trilha é limitada à retenção configurada no runtime; não substitui armazenamento centralizado nem auditoria externa.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Ambiente MT5 DEMO":
            st.markdown("#### Ambiente de operação conectado")
            st.metric("IC Markets · MT5 DEMO", str(data.get("ic_markets_mt5_demo", "NÃO CONFIRMADO")))
            cols = st.columns(2)
            cols[0].metric("Núcleo de decisão", str(data.get("decision_core", "NÃO CONFIRMADO")))
            cols[1].metric("Gateway de execução", str(data.get("execution_gateway", "NÃO CONFIRMADO")))
            st.metric("Execução REAL", str(data.get("real", "DESABILITADO")))
            st.caption("Esta tela informa o estado reportado pelo runtime. Ela não confirma que o terminal MT5 esteja aberto neste computador nem que o EA esteja instalado.")
            st.caption("Modo permitido: DEMO/SIMULAÇÃO · Execução automática: NÃO")
            st.markdown("#### Saídas temporizadas DEMO")
            try:
                timed_payload = api("/api/runtime/timed-exits")
                timed_items = timed_payload.get("timed_exits", [])
                if not isinstance(timed_items, list):
                    timed_items = []
                if not timed_items:
                    st.caption("Nenhuma saída temporizada registrada.")
                for timed_item in timed_items:
                    if not isinstance(timed_item, dict):
                        continue
                    timed_state = str(timed_item.get("state") or "UNKNOWN").upper()
                    st.write(f"**Ticket {timed_item.get('external_id', '—')} · {timed_state}**")
                    st.caption(f"Prazo alvo: {timed_item.get('due_at', '—')} · próxima tentativa: {timed_item.get('next_attempt_at', '—')} · tentativas: {timed_item.get('attempts', 0)}")
                    if timed_item.get("message"):
                        st.caption(str(timed_item["message"]))
                st.caption("Horários best-effort: indisponibilidade do MT5, rede ou runtime pode atrasar o fechamento.")
            except Exception as exc:
                st.warning(f"Status de saídas temporizadas indisponível: {exc}")
            st.markdown("#### Recuperação de posições DEMO")
            st.caption("A lista é recuperada do ledger persistente. A consulta ao MT5 é somente leitura; o fechamento exige confirmação explícita e só fica disponível depois que o MT5 confirmar que a posição continua aberta.")
            try:
                recovery_payload = api("/api/runtime/positions/recovery")
                recovery_items = recovery_payload.get("positions", [])
                if not isinstance(recovery_items, list):
                    recovery_items = []
                st.metric("Ciclos pendentes de recuperação", len(recovery_items))
                if not recovery_items:
                    st.success("Nenhum ciclo DEMO pendente de recuperação foi encontrado no ledger.")
                for index, item in enumerate(recovery_items):
                    if not isinstance(item, dict):
                        continue
                    cycle_id = item.get("cycle_id")
                    external_id = item.get("external_id")
                    state = str(item.get("recovery_state") or "UNKNOWN").upper()
                    if not isinstance(cycle_id, str) or not cycle_id.strip() or not isinstance(external_id, str) or not external_id.strip():
                        st.error("Registro de recuperação incompleto. Nenhuma ação foi habilitada.")
                        continue
                    with st.expander(f"Ticket {external_id} · {state}", expanded=(index == 0)):
                        detail_cols = st.columns(2)
                        detail_cols[0].write("**Ciclo**")
                        detail_cols[0].code(cycle_id)
                        detail_cols[1].write("**Ticket MT5**")
                        detail_cols[1].code(external_id)
                        st.caption("A listagem não consulta o broker e não afirma que a posição esteja aberta.")
                        if state == "BLOCKED_ACCOUNT_IDENTITY":
                            st.error("Fechamento bloqueado: a identidade da conta original não pode ser comprovada.")
                        elif state == "BROKER_CONFIRMED_OPEN":
                            st.success("MT5 confirmou anteriormente que esta posição continua aberta.")
                        elif state == "RECONCILIATION_REQUIRED":
                            if st.button("Consultar posição no MT5 · somente leitura", key=f"reconcile_demo_position_{cycle_id}"):
                                try:
                                    observed = api("/api/runtime/close/reconcile", "POST", {"cycle_id": cycle_id, "external_id": external_id}).get("close_reconciliation", {})
                                    observed_state = str(observed.get("state") or "UNKNOWN").upper()
                                    if observed_state == "CLOSED":
                                        st.success("MT5 confirmou: posição encerrada.")
                                    elif observed_state == "OPEN":
                                        st.success("MT5 confirmou: posição ainda aberta. O fechamento explícito ficará disponível após atualizar a lista.")
                                    else:
                                        st.warning("MT5 não conseguiu confirmar o estado. Nenhum novo fechamento foi enviado.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Reconciliação não concluída: {exc}")
                        elif state != "BROKER_CONFIRMED_OPEN":
                            st.warning(f"Estado de recuperação: {state}. Ação de fechamento indisponível.")
                        if state == "BROKER_CONFIRMED_OPEN":
                            with st.form(f"close_demo_position_form_{cycle_id}"):
                                confirmed = st.checkbox("Confirmo que desejo solicitar o fechamento desta posição DEMO específica.", key=f"confirm_close_demo_{cycle_id}")
                                submitted = st.form_submit_button("Fechar esta posição DEMO", disabled=not confirmed)
                            if submitted:
                                try:
                                    closed = api("/api/runtime/close", "POST", {"cycle_id": cycle_id, "external_id": external_id})
                                    if closed.get("closed") is True and closed.get("close_state") == "CLOSED":
                                        st.success("Fechamento confirmado pelo runtime.")
                                    else:
                                        st.warning("Fechamento inconclusivo. A posição permanece no inventário para reconciliação.")
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Fechamento não confirmado: {exc}")
            except Exception as exc:
                st.warning(f"Inventário de recuperação indisponível: {exc}")
            st.caption("Nenhuma posição é fechada automaticamente. REAL permanece DESABILITADO.")
            return

        if module_name == "Conexões":
            st.markdown("#### Estado dos serviços e integrações")
            components = [
                ("Núcleo de decisão", data.get("decision_core", "NÃO CONFIRMADO")),
                ("Gateway de execução", data.get("execution_gateway", "NÃO CONFIRMADO")),
                ("IC Markets · MT5 DEMO", data.get("ic_markets_mt5_demo", "NÃO CONFIRMADO")),
                ("cTrader", data.get("cTrader", "NÃO CONFIGURADO")),
                ("SaaS", data.get("saas", "NÃO CONFIRMADO")),
                ("REAL", data.get("real", "DESABILITADO")),
            ]
            for label, state in components:
                st.write(f"**{label}:** {state}")
            st.caption("Estado de disponibilidade reportado pelo runtime; não equivale a teste de conectividade de cada corretora.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Multi-Broker":
            st.markdown("#### Disponibilidade multi-corretora")
            st.metric("Integração MT5 DEMO", str(data.get("ic_markets_mt5_demo", "NÃO CONFIRMADO")))
            st.metric("cTrader", str(data.get("cTrader", "FUTURO_NAO_BLOQUEANTE")))
            st.warning("Não há evidência nesta resposta de uma segunda corretora conectada e validada. Não trate a arquitetura multi-broker como integração concluída.")
            st.caption("A conexão com outras corretoras exige adaptador próprio, credenciais configuradas com segurança e testes DEMO por corretora.")
            st.caption("Nenhuma ordem é enviada por esta tela. REAL permanece DESABILITADO.")
            return

        if module_name == "Kill Switch":
            obs = data.get("operational_observability", {})
            kill = obs.get("kill_switch", {})
            recovery = obs.get("recovery", {})
            reconciliation = obs.get("reconciliation", {})
            runtime_health = obs.get("runtime_health", {})
            st.markdown("#### Reconciliação de fechamentos de posição")
            st.caption(
                "Consulta somente leitura ao MT5. Esta ação não fecha posições, não cancela ordens "
                "e não envia novas ordens."
            )
            try:
                real_status = api("/api/runtime/real/status")
                close_items = real_status.get("position_close_recovery_items", [])
                if not isinstance(close_items, list):
                    close_items = []
                if real_status.get("position_close_recovery_required") is True and not close_items:
                    st.error(
                        "Há fechamento pendente, mas o histórico detalhado não está disponível. "
                        "A proteção permanece bloqueando novas entradas REAL."
                    )
                elif close_items:
                    st.warning(
                        f"{len(close_items)} fechamento(s) aguardam evidência da corretora. "
                        "Não considere o resultado resolvido até a consulta retornar."
                    )
                    labels = {
                        str(item.get("request_id")): (
                            f"{item.get('request_id')} · {item.get('state')} · tentativa {item.get('attempt')}"
                        )
                        for item in close_items
                        if isinstance(item, dict)
                        and isinstance(item.get("request_id"), str)
                        and isinstance(item.get("external_id"), str)
                    }
                    valid_items = {
                        str(item["request_id"]): item
                        for item in close_items
                        if isinstance(item, dict)
                        and isinstance(item.get("request_id"), str)
                        and item.get("request_id", "").strip()
                        and isinstance(item.get("external_id"), str)
                        and item.get("external_id", "").strip()
                    }
                    if valid_items:
                        with st.form("position_close_reconciliation_form"):
                            selected_request = st.selectbox(
                                "Fechamento pendente",
                                options=list(valid_items),
                                format_func=lambda value: labels.get(value, value),
                            )
                            selected_item = valid_items[selected_request]
                            st.caption(
                                "Ticket de abertura: "
                                + str(selected_item.get("external_id"))
                                + " · Última informação: "
                                + str(selected_item.get("message") or "sem mensagem")
                            )
                            confirm_read = st.checkbox(
                                "Confirmo consultar o histórico e as posições da conta MT5 vinculada, "
                                "sem enviar ordens."
                            )
                            reconcile_submit = st.form_submit_button(
                                "CONSULTAR E RECONCILIAR",
                                type="primary",
                            )
                        if reconcile_submit:
                            if not confirm_read:
                                st.error("Marque a confirmação para autorizar a consulta somente leitura.")
                            else:
                                try:
                                    reconciliation_result = api(
                                        "/api/runtime/real/close/reconcile",
                                        "POST",
                                        {
                                            "request_id": selected_request,
                                            "external_id": selected_item["external_id"],
                                        },
                                    ).get("close_reconciliation", {})
                                    state_label = str(reconciliation_result.get("state", "UNKNOWN"))
                                    if state_label == "CLOSED":
                                        st.success("MT5 confirmou o fechamento pelo histórico de saída.")
                                    elif state_label == "OPEN":
                                        st.warning(
                                            "MT5 confirmou que a posição continua aberta. "
                                            "Nenhuma ordem foi enviada; um novo fechamento exigiria ação separada."
                                        )
                                    else:
                                        st.error(
                                            "A situação continua inconclusiva. A proteção permanece ativa."
                                        )
                                    st.caption(str(reconciliation_result.get("message") or "Sem detalhe adicional."))
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Não foi possível reconciliar o fechamento: {exc}")
                    else:
                        st.error("Os dados do fechamento pendente não passaram pela validação da interface.")
                else:
                    st.success("Nenhum fechamento pendente ou desconhecido foi reportado pelo runtime.")
            except Exception as exc:
                st.warning(f"Reconciliação de fechamentos indisponível: {exc}")
            state = str(kill.get("state", "NOT_CONFIRMED")).upper()
            st.metric("Estado do Kill Switch", {
                "ACTIVE": "ATIVO",
                "CLEAR": "LIVRE",
                "NOT_CONNECTED": "NÃO CONECTADO",
            }.get(state, state))
            if kill.get("reason"):
                st.warning("Motivo registrado: " + str(kill["reason"]))
            else:
                st.caption("Motivo: nenhum foi informado pelo runtime.")
            cols = st.columns(3)
            cols[0].metric("Recuperação", str(recovery.get("state", "NÃO CONFIRMADA")))
            cols[1].metric("Reconciliação", str(reconciliation.get("state", "NÃO CONFIRMADA")))
            cols[2].metric("Saúde operacional", str(runtime_health.get("state", "NÃO CONFIRMADA")))
            pending = reconciliation.get("pending_request_ids", [])
            unknown = reconciliation.get("unknown_request_ids", [])
            if pending or unknown:
                st.warning("Existem solicitações pendentes ou de estado desconhecido. Não retome operações.")
                if pending:
                    st.write("Solicitações pendentes:", pending)
                if unknown:
                    st.write("Solicitações desconhecidas:", unknown)
            if recovery.get("message"):
                st.write(str(recovery["message"]))
            if state != "ACTIVE":
                st.warning("Ativar o Kill Switch bloqueia novas execuções. Não cancela ordens já encaminhadas nem substitui a reconciliação.")
                with st.form("activate_kill_switch_form"):
                    emergency_reason = st.text_input("Motivo obrigatório da parada", max_chars=240)
                    emergency_confirm = st.checkbox("Confirmo ativar a parada de emergência e bloquear novas execuções.")
                    emergency_submit = st.form_submit_button("ATIVAR KILL SWITCH", type="primary")
                if emergency_submit:
                    if not emergency_reason.strip() or not emergency_confirm:
                        st.error("Informe o motivo e marque a confirmação explícita.")
                    else:
                        try:
                            result = api(
                                "/api/runtime/kill-switch/activate",
                                "POST",
                                {"reason": emergency_reason.strip(), "confirmed": True},
                            )
                            st.success("Kill Switch ativado e estado persistido pelo runtime.")
                            if result.get("pending_request_ids") or result.get("unknown_request_ids"):
                                st.warning("Há solicitações que exigem reconciliação. A ativação não as cancela.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível confirmar a ativação: {exc}")
            else:
                st.success("Kill Switch ativo. A desativação não está disponível nesta interface.")
            st.caption("A ativação bloqueia novas execuções. Ordens já encaminhadas exigem reconciliação manual; não há cancelamento automático.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Segurança":
            storage = data.get("production_storage", {})
            gate = data.get("production_operation_gate", {})
            identity = data.get("identity", data)
            cols = st.columns(3)
            cols[0].metric("Armazenamento", str(storage.get("state", "NÃO CONFIRMADO")))
            cols[1].metric("Gate operacional", str(gate.get("storage_state", "NÃO CONFIRMADO")))
            cols[2].metric("Provedor de identidade", str(identity.get("trusted_identity_provider", "NÃO CONFIGURADO")))
            st.write("Isolamento de usuário/tenant:", str(identity.get("tenant_isolation", "NÃO CONFIRMADO")))
            st.write("Execução REAL:", str(data.get("real", "DESABILITADO")))
            alerts = data.get("alerts", [])
            if alerts:
                st.markdown("#### Alertas de segurança e integridade")
                for alert in alerts:
                    message = f"{alert.get('component', 'Sistema')} — {alert.get('message', 'Verificar')}"
                    if str(alert.get("severity", "")).upper() == "CRITICAL":
                        st.error(message)
                    else:
                        st.warning(message)
            else:
                st.info("O runtime não retornou alertas de saúde nesta consulta.")
            st.caption("A identidade remota e o isolamento dependem da configuração real do proxy/provedor confiável.")
            st.caption("Esta tela não comprova implantação remota, backup externo ou isolamento multiusuário em produção.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Laboratório":
            resources = data.get("resources", [])
            sources = data.get("learning_sources", [])
            cols = st.columns(2)
            cols[0].metric("Materiais cadastrados", len(resources))
            cols[1].metric("Fontes em avaliação", len(sources))
            st.caption("Cadastre materiais de estudo. Links externos entram em triagem; o conteúdo não é considerado validado automaticamente.")
            for label, items in (("Materiais do laboratório", resources), ("Procedência e validação das fontes", sources)):
                if items:
                    with st.expander(f"{label} ({len(items)})", expanded=True):
                        st.dataframe(items, use_container_width=True, hide_index=True)
                else:
                    st.info(f"Nenhum item disponível em: {label.lower()}.")
            if sources:
                st.subheader("Revisão manual de procedência")
                st.warning(
                    "Esta etapa registra sua declaração de revisão. O sistema não baixa, "
                    "analisa nem verifica automaticamente o conteúdo externo; isto não é "
                    "uma varredura antivírus nem uma auditoria independente."
                )
                for source_index, source in enumerate(sources):
                    if not isinstance(source, dict):
                        continue
                    source_id = str(source.get("source_id") or "").strip()
                    source_status = str(source.get("status") or "").upper()
                    if not source_id:
                        continue
                    with st.expander(
                        f"{source.get('source_type', 'FONTE')} · {source_id} · {source_status}",
                        expanded=source_status == "QUARANTINED",
                    ):
                        st.write(f"**Referência:** {source.get('uri') or 'não informada'}")
                        if source_status == "QUARANTINED":
                            with st.form(f"learning_source_review_{source_index}"):
                                content_reviewed = st.checkbox(
                                    "Li e conferi o conteúdo desta fonte.",
                                    key=f"learning_content_reviewed_{source_index}",
                                )
                                security_reviewed = st.checkbox(
                                    "Conferi a origem e os riscos antes de abrir/usar o material.",
                                    key=f"learning_security_reviewed_{source_index}",
                                )
                                review_submit = st.form_submit_button("Registrar revisão da fonte")
                            if review_submit:
                                if not content_reviewed or not security_reviewed:
                                    st.error("Marque as duas confirmações somente depois de realizar a revisão.")
                                else:
                                    try:
                                        api("/api/learning/sources/validate", "POST", {
                                            "source_id": source_id,
                                            "content_verified": True,
                                            "security_checked": True,
                                        })
                                        st.success("Revisão manual registrada. O conhecimento ainda não foi admitido.")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"Não foi possível registrar a revisão: {exc}")
                        elif source_status == "VALIDATED" and not source.get("knowledge_validated", False):
                            st.caption("A fonte passou pela revisão manual. A admissão do conhecimento é uma etapa separada.")
                            with st.form(f"learning_source_admit_{source_index}"):
                                knowledge_reviewed = st.checkbox(
                                    "Revisei a informação e considero o conhecimento adequado para estudo.",
                                    key=f"learning_knowledge_reviewed_{source_index}",
                                )
                                admit_submit = st.form_submit_button("Admitir conhecimento para estudo")
                            if admit_submit:
                                if not knowledge_reviewed:
                                    st.error("Confirme a revisão do conhecimento antes de admitir.")
                                else:
                                    try:
                                        api("/api/learning/sources/admit", "POST", {
                                            "source_id": source_id,
                                            "knowledge_validated": True,
                                        })
                                        st.success("Conhecimento admitido para uso educacional.")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"Não foi possível admitir o conhecimento: {exc}")
                        elif source.get("knowledge_validated", False):
                            st.success("Conhecimento validado para uso educacional. Isso não autoriza operações.")
            with st.expander("Adicionar material de estudo"):
                with st.form("learning_resource_create_form"):
                    resource_id = st.text_input("Identificador do material", max_chars=80)
                    resource_title = st.text_input("Título", max_chars=200)
                    content_type = st.selectbox("Tipo de material", ["VIDEO", "ARTICLE", "DOCUMENT", "IMAGE", "NOTE", "OTHER"])
                    source_url = st.text_input("Link da fonte (opcional)", max_chars=1000)
                    source_name = st.text_input("Nome da fonte (opcional)", max_chars=160)
                    tags_text = st.text_input("Etiquetas separadas por vírgula", max_chars=300)
                    resource_submit = st.form_submit_button("Adicionar material")
                if resource_submit:
                    if not resource_id.strip() or not resource_title.strip():
                        st.error("Informe o identificador e o título do material.")
                    else:
                        try:
                            api("/api/learning/resources", "POST", {
                                "resource_id": resource_id.strip(),
                                "title": resource_title.strip(),
                                "content_type": content_type,
                                "source_url": source_url.strip() or None,
                                "source_name": source_name.strip() or None,
                                "tags": [tag.strip() for tag in tags_text.split(",") if tag.strip()],
                            })
                            st.success("Material cadastrado. A fonte externa permanece em triagem até validação.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível cadastrar o material: {exc}")
            st.caption("Fontes externas exigem validação antes de seu conhecimento ser considerado validado.")
            st.caption("Execução permitida: NÃO.")
            return

        if module_name == "Aprendizado":
            activities = data.get("activities", [])
            attempts = data.get("attempts", [])
            cols = st.columns(2)
            cols[0].metric("Atividades", len(activities))
            cols[1].metric("Tentativas registradas", len(attempts))
            st.caption("Crie exercícios e registre suas respostas. O resultado é educacional e não altera sinais nem parâmetros de execução.")
            for label, items in (("Atividades de aprendizagem", activities), ("Histórico de tentativas", attempts)):
                if items:
                    with st.expander(f"{label} ({len(items)})", expanded=True):
                        st.dataframe(items, use_container_width=True, hide_index=True)
                else:
                    st.info(f"Nenhum item disponível em: {label.lower()}.")
            with st.expander("Criar atividade de estudo"):
                with st.form("learning_activity_create_form"):
                    activity_id = st.text_input("Identificador da atividade", max_chars=80)
                    activity_prompt = st.text_area("Enunciado / exercício", max_chars=3000)
                    expected_concepts = st.text_input("Conceitos esperados (separados por vírgula)", max_chars=300)
                    difficulty = st.selectbox("Dificuldade", ["INICIANTE", "BÁSICA", "INTERMEDIÁRIA", "AVANÇADA"])
                    activity_submit = st.form_submit_button("Criar atividade")
                if activity_submit:
                    if not activity_id.strip() or not activity_prompt.strip():
                        st.error("Informe o identificador e o enunciado da atividade.")
                    else:
                        try:
                            api("/api/learning/activities", "POST", {
                                "activity_id": activity_id.strip(),
                                "prompt": activity_prompt.strip(),
                                "expected_concepts": [item.strip() for item in expected_concepts.split(",") if item.strip()],
                                "difficulty": difficulty,
                            })
                            st.success("Atividade criada.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível criar a atividade: {exc}")
            activity_options = {
                str(item.get("activity_id")): str(item.get("prompt") or item.get("activity_id"))
                for item in activities if isinstance(item, dict) and item.get("activity_id")
            }
            with st.expander("Registrar tentativa"):
                with st.form("learning_attempt_create_form"):
                    selected_activity = st.selectbox(
                        "Atividade",
                        options=list(activity_options),
                        format_func=lambda value: activity_options[value],
                        disabled=not activity_options,
                    )
                    answer = st.text_area("Sua resposta", max_chars=3000, disabled=not activity_options)
                    correctness = st.selectbox("Autoavaliação", ["Não informada", "Correta", "Incorreta"], disabled=not activity_options)
                    feedback = st.text_area("Observações / feedback", max_chars=1500, disabled=not activity_options)
                    attempt_submit = st.form_submit_button("Guardar tentativa", disabled=not activity_options)
                if attempt_submit and selected_activity:
                    try:
                        api("/api/learning/attempts", "POST", {
                            "activity_id": selected_activity,
                            "answer": answer,
                            "correct": True if correctness == "Correta" else False if correctness == "Incorreta" else None,
                            "feedback": feedback,
                        })
                        st.success("Tentativa registrada.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível registrar a tentativa: {exc}")
            st.caption("Aprendizado não autoriza operações: execução permitida = NÃO.")
            return

        if module_name == "Descobertas":
            observations = data.get("observations", [])
            sources = data.get("learning_sources", [])
            resources = data.get("resources", [])
            cols = st.columns(2)
            cols[0].metric("Observações registradas", len(observations))
            cols[1].metric("Fontes relacionadas", len(sources))
            st.caption("Registre observações vinculadas a materiais de estudo. Elas permanecem não validadas e não se tornam regras de trading.")
            for label, items in (("Observações", observations), ("Fontes relacionadas", sources)):
                if items:
                    with st.expander(f"{label} ({len(items)})", expanded=True):
                        st.dataframe(items, use_container_width=True, hide_index=True)
                else:
                    st.info(f"Nenhum item disponível em: {label.lower()}.")
            resource_options = {
                str(item.get("resource_id")): str(item.get("title") or item.get("resource_id"))
                for item in resources if isinstance(item, dict) and item.get("resource_id")
            }
            with st.expander("Registrar descoberta / observação"):
                with st.form("learning_observation_create_form"):
                    selected_resource = st.selectbox(
                        "Material relacionado",
                        options=list(resource_options),
                        format_func=lambda value: resource_options[value],
                        disabled=not resource_options,
                    )
                    observation_statement = st.text_area("Observação", max_chars=3000, disabled=not resource_options)
                    observation_concepts = st.text_input("Conceitos (separados por vírgula)", max_chars=300, disabled=not resource_options)
                    observation_evidence = st.text_input("Evidência / trecho de referência (opcional)", max_chars=1000, disabled=not resource_options)
                    observation_submit = st.form_submit_button("Guardar observação", disabled=not resource_options)
                if observation_submit and selected_resource:
                    if not observation_statement.strip():
                        st.error("Escreva a observação antes de salvar.")
                    else:
                        try:
                            api("/api/learning/observations", "POST", {
                                "resource_id": selected_resource,
                                "statement": observation_statement.strip(),
                                "concepts": [item.strip() for item in observation_concepts.split(",") if item.strip()],
                                "evidence": observation_evidence.strip() or None,
                                "validated": False,
                            })
                            st.success("Observação guardada como não validada.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Não foi possível guardar a observação: {exc}")
            st.caption("Descobertas não alteram sinais, filtros ou parâmetros de execução.")
            st.caption("Execução permitida: NÃO.")
            return

        if module_name == "Estatísticas":
            periods = data.get("periods", {})
            breakdowns = data.get("breakdowns", {})
            st.caption("Indicadores calculados sobre os registros disponíveis na memória do runtime. Os períodos usam UTC.")
            totals = [
                ("Registros", data.get("total", 0)),
                ("Acionáveis", data.get("actionable", 0)),
                ("Vitórias", data.get("wins", 0)),
                ("Derrotas", data.get("losses", 0)),
                ("Empates", data.get("draws", 0)),
                ("Abertos", data.get("open", 0)),
            ]
            metric_cols = st.columns(3)
            for index, (label, value) in enumerate(totals):
                metric_cols[index % 3].metric(label, str(value))
            st.metric("Taxa de vitória · operações encerradas", f"{float(data.get('win_rate', 0.0)):.1f}%")
            st.markdown("#### Evolução por período")
            period_rows = []
            for key, label in (("daily", "Hoje · UTC"), ("weekly", "Semana · UTC"), ("monthly", "Mês · UTC")):
                item = periods.get(key, {})
                period_rows.append({
                    "Período": label,
                    "Registros": item.get("total", 0),
                    "Acionáveis": item.get("actionable", 0),
                    "Vitórias": item.get("wins", 0),
                    "Derrotas": item.get("losses", 0),
                    "Abertos": item.get("open", 0),
                    "Taxa de vitória (%)": round(float(item.get("win_rate", 0.0)), 2),
                })
            st.dataframe(period_rows, use_container_width=True, hide_index=True)
            for key, label in (
                ("by_symbol", "Por ativo"),
                ("by_timeframe", "Por timeframe"),
                ("by_signal", "Por sinal"),
                ("by_score_band", "Por faixa de pontuação"),
            ):
                groups = breakdowns.get(key, {})
                st.markdown("#### " + label)
                if groups:
                    rows = [{"Grupo": name, **summary} for name, summary in groups.items()]
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("Sem registros suficientes para este agrupamento.")
            st.caption("A taxa de vitória considera somente vitórias e derrotas; empates e operações abertas ficam fora do denominador.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

        if module_name == "Relatórios":
            periods = data.get("periods", {})
            breakdowns = data.get("breakdowns", {})
            st.caption("Relatório consolidado dos registros disponíveis no runtime. Não representa extrato financeiro, apuração fiscal ou garantia de resultado.")
            st.markdown("#### Resumo executivo")
            st.write(
                f"Base analisada: {data.get('total', 0)} registro(s), "
                f"{data.get('actionable', 0)} acionável(is), "
                f"{data.get('wins', 0)} vitória(s), {data.get('losses', 0)} derrota(s) "
                f"e {data.get('draws', 0)} empate(s)."
            )
            st.metric("Taxa de vitória · operações encerradas", f"{float(data.get('win_rate', 0.0)):.1f}%")
            report_rows = []
            for key, label in (("daily", "Hoje · UTC"), ("weekly", "Semana · UTC"), ("monthly", "Mês · UTC")):
                item = periods.get(key, {})
                report_rows.append({
                    "Seção": "Período",
                    "Grupo": label,
                    "Registros": item.get("total", 0),
                    "Acionáveis": item.get("actionable", 0),
                    "Vitórias": item.get("wins", 0),
                    "Derrotas": item.get("losses", 0),
                    "Empates": item.get("draws", 0),
                    "Abertos": item.get("open", 0),
                    "Taxa de vitória (%)": round(float(item.get("win_rate", 0.0)), 2),
                })
            for key, label in (
                ("by_symbol", "Ativo"),
                ("by_timeframe", "Timeframe"),
                ("by_signal", "Sinal"),
                ("by_score_band", "Faixa de pontuação"),
            ):
                for group, item in breakdowns.get(key, {}).items():
                    report_rows.append({
                        "Seção": label,
                        "Grupo": group,
                        "Registros": item.get("total", 0),
                        "Acionáveis": item.get("actionable", 0),
                        "Vitórias": item.get("wins", 0),
                        "Derrotas": item.get("losses", 0),
                        "Empates": item.get("draws", 0),
                        "Abertos": item.get("open", 0),
                        "Taxa de vitória (%)": round(float(item.get("win_rate", 0.0)), 2),
                    })
            if report_rows:
                st.dataframe(report_rows, use_container_width=True, hide_index=True)
                report_buffer = io.StringIO(newline="")
                report_writer = csv.DictWriter(report_buffer, fieldnames=list(report_rows[0].keys()), delimiter=";")
                report_writer.writeheader()
                report_writer.writerows(report_rows)
                st.download_button(
                    "Exportar relatório operacional · CSV",
                    data="\ufeff" + report_buffer.getvalue(),
                    file_name="controlador-trading-relatorio-operacional.csv",
                    mime="text/csv; charset=utf-8",
                    key="operational_report_csv_download",
                )
            else:
                st.info("Ainda não há dados para compor o relatório.")
            st.caption("O relatório usa somente estatísticas agregadas; não inclui credenciais, dados bancários ou ordens.")
            st.caption("Execução permitida: NÃO · REAL: DESABILITADO")
            return

    except Exception:
        # Runtime exceptions can contain filesystem paths, SQL details, or
        # connector payloads. Keep those diagnostics out of the user-facing panel.
        st.warning("Não foi possível carregar este módulo do runtime. Verifique a disponibilidade do serviço e os registros técnicos locais.")


@st.fragment(run_every="15s")
def render_latest_signal(closed: bool = False) -> None:
    """Refresh the shared signal strip periodically without rerunning the full panel."""
    try:
        latest_payload = api("/api/runtime/analysis/latest")
        latest_analysis = (
            latest_payload.get("analysis")
            if isinstance(latest_payload, dict) and latest_payload.get("available") is True
            else None
        )
    except Exception:
        latest_analysis = None
    signal_label, score_label, signal_color = closed_panel_signal(latest_analysis)
    if closed:
        try:
            health = str(api("/api/health").get("health") or "UNKNOWN").upper()
        except Exception:
            health = "UNKNOWN"
        status_label = {
            "OK": "SISTEMA ONLINE",
            "WARNING": "INDISPONÍVEL",
            "CRITICAL": "INDISPONÍVEL",
        }.get(health, "INDISPONÍVEL")
        st.markdown(
            f'<div class="closed-signal" style="color:{signal_color}">{signal_label}</div>'
            f'<div class="closed-score">{score_label}</div>'
            f'<div class="closed-status">{status_label}</div>',
            unsafe_allow_html=True,
        )
        return
    signal_col, score_col = st.columns([3, 2], vertical_alignment="center")
    with signal_col:
        st.markdown(
            f'<div class="open-signal" style="color:{signal_color}">{signal_label}</div>',
            unsafe_allow_html=True,
        )
    with score_col:
        st.markdown(f'<div class="open-score">{score_label}</div>', unsafe_allow_html=True)


# Keep the supplied Figma reference JSON untouched. The active Streamlit
# navigation separates complex product modules into their own destinations.
# "MT5 DEMO / Simulação" in the reference is operational environment/recovery,
# not the historical Simulador module already housed under ESTUDO.
_REFERENCE_TABS = CONFIG["open_state"]["tabs"]
AREAS = {
    name: [
        "Ambiente MT5 DEMO" if module == "MT5 DEMO / Simulação" else module
        for module in _REFERENCE_TABS[name]
    ]
    for name in ("COCKPIT", "ANÁLISE", "ESTUDO")
}
AREAS["RESERVA FISCAL"] = ["Reserva Fiscal"]
AREAS["ASSISTENTE DO ECOSSISTEMA"] = ["Assistente do Ecossistema"]
AREAS["MAIS / ADMIN"] = list(_REFERENCE_TABS["MAIS / ADMIN"])
if "Kill Switch" not in AREAS["MAIS / ADMIN"]:
    AREAS["MAIS / ADMIN"].append("Kill Switch")
if "panel_open" not in st.session_state:
    st.session_state.panel_open = True

if not st.session_state.panel_open:
    with st.container(key="panel-toggle"):
        toggle_col, signal_col = st.columns([1, 3], vertical_alignment="center")
        with toggle_col:
            if st.button("C", key="open_control_hub", help="Abrir painel"):
                st.session_state.panel_open = True
                st.rerun()
        with signal_col:
            render_latest_signal(closed=True)
    st.stop()

with st.container(key="control-hub-shell"):
    header_left, header_right = st.columns([4, 1])
    with header_left:
        st.markdown('<div class="hub-title">Controlador-Trader</div>', unsafe_allow_html=True)
    with header_right:
        st.markdown('<div class="demo-pill-wrap"><span class="demo-pill">DEMO</span></div>', unsafe_allow_html=True)

    # The same periodically refreshed signal and score appear in both panel states.
    with st.container(key="open-signal-strip"):
        render_latest_signal(closed=False)

    area = st.radio("Áreas principais", list(AREAS), horizontal=True, key="main_area_navigation", label_visibility="collapsed")
    st.divider()
    if area in {"RESERVA FISCAL", "ASSISTENTE DO ECOSSISTEMA"}:
        module = AREAS[area][0]
    else:
        # The previous Financeiro selector may remain in Streamlit session state
        # after navigation changes; normalize it before rendering the new options.
        if st.session_state.get("module_navigation") not in AREAS[area]:
            st.session_state["module_navigation"] = AREAS[area][0]
        module = st.radio("Módulos", AREAS[area], horizontal=False, key="module_navigation", label_visibility="collapsed")

    if module == "Reserva Fiscal":
        show_fiscal()
    elif module == "Assistente do Ecossistema":
        show_assistant()
    elif module == "Kill Switch":
        show_kill_switch()
    else:
        show_readonly_module(module)

    st.divider()
    st.markdown("**Estado do sistema**")
    try:
        runtime_status = api("/api/health")
        components = runtime_status.get("components", {})
        health_state = str(runtime_status.get("health") or "UNKNOWN").upper()
        mt5_state = str(components.get("mt5_demo") or runtime_status.get("mt5_demo") or "UNKNOWN").upper()
        mode_state = str(runtime_status.get("mode") or "UNKNOWN").upper()
        real_state = str(runtime_status.get("real") or "DESABILITADO").upper()
        health_label = {"OK": "SISTEMA ONLINE", "WARNING": "INDISPONÍVEL", "CRITICAL": "INDISPONÍVEL"}.get(health_state, "INDISPONÍVEL")
        state_left, state_right = st.columns([3, 1])
        with state_left:
            st.caption("Estado do sistema")
        with state_right:
            st.markdown(f'<div class="system-state-value">{health_label}</div>', unsafe_allow_html=True)
        if runtime_status.get("execution_allowed") is not False or real_state not in {"DESABILITADO", "DISABLED"}:
            st.error("Estado de segurança inesperado. Operações bloqueadas na interface; verifique o runtime antes de continuar.")
        if runtime_status.get("alerts"):
            with st.expander("Alertas do sistema", expanded=health_state == "CRITICAL"):
                for alert in runtime_status["alerts"]:
                    st.write(f"- **{alert.get('severity', 'INFO')} · {alert.get('component', 'Sistema')}** — {alert.get('message', 'Verificar componente')}")
    except Exception:
        st.warning("Runtime indisponível. Estado do MT5 e do sistema não confirmado.")

    leverage_left, leverage_right = st.columns([3, 1])
    with leverage_left:
        st.button("REAL — DESABILITADO", key="real_mode_disabled", disabled=True, use_container_width=True)
        st.caption("Execução REAL permanece bloqueada.")
    with leverage_right:
        if "leverage_enabled" not in st.session_state:
            try:
                saved_preferences = api("/api/preferences").get("preferences", {})
                st.session_state.leverage_enabled = saved_preferences.get("leverage_enabled") is True
            except Exception:
                st.session_state.leverage_enabled = False
        st.checkbox("Alavancagem", key="leverage_enabled", on_change=save_leverage_preference, help="Salva somente a preferência. Não ativa ordens, não altera margem e não concede autorização de execução.")
        if st.session_state.get("leverage_preference_error"):
            st.warning("Preferência de alavancagem não sincronizada com o runtime.")

    if st.button("Fechar painel", key="close_control_hub"):
        st.session_state.panel_open = False
        st.rerun()
