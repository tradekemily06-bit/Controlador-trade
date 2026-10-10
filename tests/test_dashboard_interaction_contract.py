from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PANEL = (ROOT / "mql5" / "Experts" / "ControladorTrading" / "Controlador-Trading.mq5").read_text(encoding="utf-8")


def test_dashboard_primary_controls_are_wired_to_click_or_change_handlers():
    # The circular C opens the ecosystem drawer; confirmation controls are
    # generated after successful API responses and bind inside their flows.
    required_bindings = (
        "const cToggle=$('ecosystemC'),ecosystemDrawer=$('ecosystemDrawer');" ,
        "$('refreshChart').onclick=refreshMarketChart",
        "$('saveOperationMode').onclick=async()",
        "$('realPrepare').onclick=async()",
        "$('realConfirm').onclick=async()",
        "$('runtimeCycle').onclick=runRuntimeCycle",
        "$('analyze').onclick=async()",
        "$('replayBtn').onclick=async()",
        "$('savePrefs').onclick=async()",
        "$('symbolInput').addEventListener('change'",
        "$('tfInput').addEventListener('change'",
        "window.addEventListener('hashchange',()=>applyDefaultView",
    )
    for binding in required_bindings:
        assert binding in WEB, f"Dashboard control lost its interaction binding: {binding}"


def test_dashboard_navigation_targets_are_supported_and_react_to_hash_changes():
    nav_targets = ("painel", "analise", "memoria", "laboratorio", "noticias", "config")
    for target in nav_targets:
        assert f'href="#{target}"' in WEB, f"Missing navigation target: {target}"

    allowed_views = "const allowed=new Set(['painel','analise','laboratorio','memoria','noticias','config'])"
    assert allowed_views in WEB
    assert "function applyDefaultView(view)" in WEB
    assert "window.addEventListener('hashchange',()=>applyDefaultView" in WEB


def test_dashboard_actions_have_matching_runtime_api_routes():
    required_routes = (
        "/api/preferences",
        "/api/runtime/real/status",
        "/api/runtime/real/prepare",
        "/api/runtime/real/confirm",
        "/api/runtime/cycle",
        "/api/runtime/close",
        "/api/runtime/analysis",
        "/api/market/assets",
        "/api/replay",
        "/api/risk",
        "/api/statistics",
        "/api/memory",
        "/api/news",
        "/api/outcome",
        "/api/learning",
        "/api/learning/activities",
        "/api/learning/attempts",
        "/api/learning/resources",
        "/api/learning/observations",
        "/api/status",
    )
    for route in required_routes:
        assert f'"{route}"' in APP, f"Dashboard route is missing from app.py: {route}"


def test_mql5_visible_buttons_dispatch_chart_click_events():
    click_start = PANEL.index("void OnChartEvent(")
    handler = PANEL[click_start:]
    handler = handler.split("\n}\n", 1)[0]

    required_buttons = (
        "PANEL_TOGGLE",
        "V1",
        "V2",
        "V3",
        "V4",
        "V5",
        "V6",
        "V7",
        "ANALYZE",
        "CYCLE",
        "SAVE",
        "CLOSE",
    )
    assert "if(id!=CHARTEVENT_OBJECT_CLICK) return;" in handler
    for button in required_buttons:
        assert f'Obj("{button}")' in handler, f"MQL5 button has no click dispatch: {button}"


def test_compact_signal_shows_validated_quality_independently_of_final_action_gate():
    render = next(line for line in WEB.splitlines() if line.startswith("function render(d){"))
    assert "const actionable=q.actionable===true&&(isBuy||isSell);" in render
    assert "const signal=actionable?" in render
    assert "esc(qs+'/100 · '+qs+'% '+ql)" in render
    assert "const hasQuality=Boolean(qs&&ql&&ql!=='NENHUMA'&&Number.isFinite(Number(q.score))&&Number(q.score)>=0&&Number(q.score)<=100)" in render


def test_compact_signal_does_not_promote_weak_or_unconfirmed_analysis():
    render = next(line for line in WEB.splitlines() if line.startswith("function render(d){"))
    assert "const signal=actionable?(isBuy?'COMPRAR':'VENDER'):'AGUARDAR';" in render
    assert "const hasQuality=Boolean(qs&&ql&&ql!=='NENHUMA'&&Number.isFinite(Number(q.score))&&Number(q.score)>=0&&Number(q.score)<=100)" in render


def test_statistics_visually_separate_manual_study_from_confirmed_demo_financial_results():
    assert "ESTUDO — registros manuais (não representam lucro financeiro)" in WEB
    assert "DEMO — resultados financeiros confirmados pelo histórico MT5" in WEB
    for field in ("demoTotal", "demoWins", "demoLosses", "demoDraws", "demoWinrate", "demoNet"):
        assert f'id="{field}"' in WEB
    assert "st.demo||{}" in WEB
    assert "demo.periods?.daily" in WEB
    assert "demo.periods?.weekly" in WEB
    assert "demo.periods?.monthly" in WEB
    assert "MT5_DEMO_HISTORY" in WEB


def test_statistics_use_distinct_win_loss_colors_and_signed_net_result():
    assert ".stat-win{color:#58d68d}" in WEB
    assert ".stat-loss{color:#ff7676}" in WEB
    assert ".stat-neutral{color:#ffd166}" in WEB
    assert "Number(value)>0?'stat-win':Number(value)<0?'stat-loss':'stat-neutral'" in WEB


def test_statistics_do_not_report_zero_win_rate_when_no_closed_outcomes_exist():
    assert "!(Number(st.wins)+Number(st.losses))" in WEB
    assert "!(Number(data?.wins)+Number(data?.losses))" in WEB
    assert "!(Number(demo.wins)+Number(demo.losses))" in WEB


def test_manual_outcome_controls_are_visually_study_only_and_color_coded():
    assert "Estudo por ativo" in WEB
    assert "Estudo por timeframe" in WEB
    assert "Últimas decisões de estudo" in WEB
    assert "Resultado do estudo (registro manual)" in WEB
    assert "nem altera os resultados financeiros DEMO" in WEB
    assert 'button[data-outcome="WIN"]' in WEB
    assert 'button[data-outcome="LOSS"]' in WEB


def test_demo_net_result_is_unavailable_when_there_are_no_confirmed_records():
    assert "Number(demo.total)>0?demo.net_result:null" in WEB
    assert "Number(d.total)>0?d.net_result:null" in WEB


def test_quality_level_remains_visible_when_final_gate_changes_signal_to_wait():
    render = next(line for line in WEB.splitlines() if line.startswith("function render(d){"))
    assert "const signal=actionable?(isBuy?'COMPRAR':'VENDER'):'AGUARDAR';" in render
    assert "const hasQuality=Boolean(qs&&ql&&ql!=='NENHUMA'&&Number.isFinite(Number(q.score))&&Number(q.score)>=0&&Number(q.score)<=100)" in render
    assert "esc(qs+'/100 · '+qs+'% '+ql)" in render


def test_training_and_material_modules_have_real_runtime_actions():
    assert 'id="createStudyActivity"' in WEB
    assert "$('createStudyActivity').onclick=async()" in WEB
    assert "'/api/learning/activities'" in WEB
    assert "'/api/learning/attempts'" in WEB
    assert 'id="registerStudyResource"' in WEB
    assert "$('registerStudyResource').onclick=async()" in WEB
    assert "'/api/learning/resources'" in WEB
    assert "correção automática não configurada" in WEB
    assert "não baixa nem analisa automaticamente URLs ou vídeos" in WEB


def test_dashboard_does_not_invent_startup_quality_score():
    assert '<div class="value" id="score">—</div>' in WEB
    assert 'id="score">50/100</div>' not in WEB


def test_analysis_panel_keeps_market_signal_separate_from_runtime_decision():
    assert "const analysisHtml='<b>'+esc(d.signal||'AGUARDAR')" in WEB
    assert "esc(d.decision||d.signal" not in WEB
    assert "d.score===null||d.score===undefined?'—':String(d.score)+'/100'" in WEB


def test_learning_textareas_use_responsive_control_styles():
    assert ".controls textarea{resize:vertical;line-height:1.45}" in WEB
    assert ".controls input,.controls select,.controls textarea{min-width:0;max-width:100%}" in WEB


def test_technical_readout_uses_calculated_evidence_not_static_concept_badges():
    assert 'id="indicatorReadout"' in WEB
    assert "GAB, DDT, pressão e taxa dívida permanecem conceitos contextuais" in WEB
    assert '<span class="chip">Tendência</span>' not in WEB


def test_protection_panel_reads_real_runtime_observability():
    for element in ("killSwitchState", "reconciliationState", "recoveryState", "runtimeIntegrityState"):
        assert f'id="{element}"' in WEB
    assert "function renderProtectionStatus(status)" in WEB
    assert "status?.operational_observability" in WEB
    assert "renderProtectionStatus(s)" in WEB


def test_mt5_demo_validation_and_market_source_are_not_static_claims():
    assert 'id="demoValidationBadge">MT5 DEMO: VERIFICANDO' in WEB
    assert "status?.mt5_demo||status?.components?.mt5_demo" in WEB
    assert 'id="marketSourceBadge">Fonte: aguardando runtime' in WEB
    assert "$('marketSourceBadge').textContent='Fonte: '+String(d.market_data?.source||'NÃO CONFIRMADA')" in WEB
    assert "DEMO VALIDADO</span>" not in WEB
    assert "DEMO • leitura real do MT5" not in WEB


def test_protection_status_fails_closed_when_runtime_status_is_unavailable():
    assert "catch(e){renderRuntime(null,null);renderProtectionStatus(null);" in WEB
    assert "String(status?.mt5_demo||status?.components?.mt5_demo||'NÃO CONFIRMADO')" in WEB


def test_signal_quality_level_has_its_own_color_without_recoloring_wait_signal():
    assert ".quality-strong{color:#58d68d}" in WEB
    assert ".quality-moderate{color:#ffd166}" in WEB
    assert ".quality-weak{color:#ff7676}" in WEB
    assert "$('compactSignal').innerHTML=esc(signal)+(hasQuality?" in WEB


def test_material_module_registers_reviewed_observations_without_claiming_auto_analysis():
    assert 'id="recordStudyObservation"' in WEB
    assert "$('recordStudyObservation').onclick=async()" in WEB
    assert "'/api/learning/observations'" in WEB
    assert "validated:false" in WEB
    assert "REGISTRAR OBSERVAÇÃO" in WEB
    assert "não finge que extraiu conteúdo de URL ou vídeo" in WEB


def test_analysis_failure_discards_stale_quality_and_indicator_evidence():
    assert "$('score').textContent='—';$('scorebar').style.width='0%';" in WEB
    assert "score e qualidade descartados até nova leitura válida" in WEB
    assert "Evidência técnica indisponível." in WEB


def test_web_runtime_cycle_displays_market_signal_decision_and_quality_separately():
    assert "esc(x.signal||'AGUARDAR')" in WEB
    assert " · decisão '+esc(x.decision||'AGUARDAR')" in WEB
    assert "const q=x.quality||{}" in WEB
    assert "esc(qScore+'/100 · '+qScore+'% '+qLevel)" in WEB
    assert "esc(x.decision||x.signal||'AGUARDAR')" not in WEB


def test_visible_ecosystem_actions_are_bound_to_real_handlers():
    for control in (
        "refreshChart",
        "saveOperationMode",
        "realPrepare",
        "runtimeCycle",
        "analyze",
        "replayBtn",
        "createStudyActivity",
        "registerStudyResource",
        "recordStudyObservation",
        "savePrefs",
    ):
        assert "$('" + control + "').onclick" in WEB
    assert "cToggle.onclick=" in WEB
    assert "$('realConfirm').onclick=async()" in WEB
    assert "$('closeRuntimeCycle').onclick=" in WEB
    assert "document.querySelectorAll('[data-outcome]').forEach(b=>b.onclick" in WEB
    assert "document.querySelectorAll('[data-learning-attempt]').forEach(b=>b.onclick" in WEB


def test_dashboard_statistics_wait_for_runtime_data_instead_of_showing_fake_zeros():
    assert 'id="total">—</div>' in WEB
    assert 'id="actionable">—</div>' in WEB
    assert 'id="demoTotal">—</div>' in WEB
    assert 'id="demoWins">—</div>' in WEB
    assert 'id="demoLosses">—</div>' in WEB
    assert 'id="demoDraws">—</div>' in WEB
    assert 'id="demoSourceNote">Fonte: aguardando resposta do runtime.' in WEB


def test_real_and_environment_badges_follow_runtime_instead_of_static_claims():
    assert 'id="realSafetyBadge">REAL: CONSULTANDO' in WEB
    assert 'id="realConnectionState">CONSULTANDO' in WEB
    assert "realSafetyBadge').textContent=ready?'REAL: AGUARDA CONFIRMAÇÃO':'REAL: BLOQUEADO'" in WEB
    assert "realConnectionState').textContent=ready?'AGUARDA CONFIRMAÇÃO HUMANA':'DESABILITADO'" in WEB
    assert 'id="environmentMode">CONSULTANDO MODO' in WEB
    assert "$('environmentMode').textContent=mode==='REAL'?" in WEB


def test_saved_mode_updates_the_visible_environment_badge_immediately():
    assert "$('environmentMode').textContent=mode==='REAL'?'REAL selecionado • execução continua controlada':'DEMO / SIMULAÇÃO';await refreshReal();" in WEB


def test_secondary_api_failure_does_not_leave_modules_claiming_empty_data():
    assert "Memória indisponível: '+esc(e.message)" in WEB
    assert "Resultados indisponíveis até a API responder." in WEB
    assert "Fonte de notícias indisponível; nenhum dado foi inventado." in WEB


def test_async_runtime_loaders_are_declared_async():
    assert "async function refreshMode(){try{const d=await getJson('/api/preferences');" in WEB
    assert "function refreshMode(){try{const d=await getJson('/api/preferences');" not in WEB


def test_dashboard_script_has_no_literal_escape_sequences_between_functions():
    assert "}\\nasync function" not in WEB
    assert "}}\\n$('saveOperationMode')" not in WEB
    assert "}}\\nasync function refreshReal" not in WEB


def test_ci_validates_dashboard_javascript_syntax():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "Validate dashboard JavaScript syntax" in workflow
    assert "node --check /tmp/controlador-dashboard.js" in workflow
