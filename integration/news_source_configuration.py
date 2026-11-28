"""Trusted environment configuration for persistent news evidence ingestion.

The RSS feed list and publisher trust policy are separate controls:
a feed URL alone never grants a publisher a trusted identity or tier.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from analysis.news_evidence_corroboration import (
    NewsEvidenceCorroborator,
    NewsSourcePolicy,
    SQLiteNewsEvidenceStore,
)


def build_news_evidence_from_environment(
    *,
    runtime_dir: str | Path,
    tenant_id: str,
    subject_id: str,
    raw_policies: str | None = None,
) -> NewsEvidenceCorroborator | None:
    """Build the owner-scoped evidence stack from explicit trusted host policy.

    CONTROLADOR_NEWS_SOURCE_POLICIES is a JSON array of objects containing
    source_id, source_tier, allowed_hosts, and optional publisher_group.
    Missing configuration disables evidence polling; malformed configuration
    aborts startup rather than silently downgrading source trust.
    """
    raw = (
        os.getenv("CONTROLADOR_NEWS_SOURCE_POLICIES", "").strip()
        if raw_policies is None
        else raw_policies.strip()
    )
    if not raw:
        return None

    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("CONTROLADOR_NEWS_SOURCE_POLICIES deve ser JSON válido") from exc
    if not isinstance(payload, list) or not payload or len(payload) > 100:
        raise ValueError("news source policies deve ser uma lista de 1 a 100 fontes")

    policies: dict[str, NewsSourcePolicy] = {}
    host_owners: dict[str, str] = {}
    allowed_keys = {"source_id", "source_tier", "allowed_hosts", "publisher_group"}
    for entry in payload:
        if not isinstance(entry, dict) or set(entry) - allowed_keys:
            raise ValueError("news source policy contém formato ou campos não permitidos")
        source_id = entry.get("source_id")
        source_tier = entry.get("source_tier")
        hosts = entry.get("allowed_hosts")
        publisher_group = entry.get("publisher_group")
        if not isinstance(hosts, list) or not hosts:
            raise ValueError("allowed_hosts deve ser uma lista não vazia")
        policy = NewsSourcePolicy(
            source_id=source_id,
            source_tier=source_tier,
            allowed_hosts=tuple(hosts),
            publisher_group=publisher_group,
        )
        if policy.source_id in policies:
            raise ValueError("source_id duplicado na política de notícias")
        for host in policy.allowed_hosts:
            normalized = host.strip().lower().rstrip(".")
            previous = host_owners.get(normalized)
            if previous is not None and previous != policy.source_id:
                raise ValueError("host de notícias atribuído a mais de uma fonte confiável")
            host_owners[normalized] = policy.source_id
        policies[policy.source_id] = policy

    store = SQLiteNewsEvidenceStore(
        Path(runtime_dir) / "news-evidence.sqlite3",
        tenant_id=tenant_id,
        subject_id=subject_id,
    )
    store.initialize_schema()
    return NewsEvidenceCorroborator(policies, store=store)
