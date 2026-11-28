from __future__ import annotations

import json

import pytest

from integration.news_source_configuration import build_news_evidence_from_environment


def test_missing_news_source_policy_keeps_evidence_polling_disabled(tmp_path):
    assert build_news_evidence_from_environment(
        runtime_dir=tmp_path,
        tenant_id="tenant-a",
        subject_id="owner-a",
        raw_policies="",
    ) is None
    assert not (tmp_path / "news-evidence.sqlite3").exists()


def test_builds_owner_scoped_persistent_news_evidence_from_trusted_policy(tmp_path):
    policies = json.dumps([
        {
            "source_id": "federal-reserve",
            "source_tier": "OFFICIAL_PRIMARY",
            "allowed_hosts": ["federalreserve.gov"],
            "publisher_group": "us-central-bank",
        },
        {
            "source_id": "ecb",
            "source_tier": "OFFICIAL_PRIMARY",
            "allowed_hosts": ["ecb.europa.eu"],
        },
    ])

    correlator = build_news_evidence_from_environment(
        runtime_dir=tmp_path,
        tenant_id="tenant-a",
        subject_id="owner-a",
        raw_policies=policies,
    )

    assert correlator is not None
    assert correlator.store is not None
    assert correlator.store.tenant_id == "tenant-a"
    assert correlator.store.subject_id == "owner-a"
    assert correlator.source_id_for_url("https://www.federalreserve.gov/feeds/press_all.xml") == "federal-reserve"
    assert correlator.source_id_for_url("https://www.ecb.europa.eu/rss/press.html") == "ecb"
    assert (tmp_path / "news-evidence.sqlite3").exists()


@pytest.mark.parametrize(
    "raw",
    [
        "{invalid-json",
        "[]",
        json.dumps([{"source_id": "x", "source_tier": "UNKNOWN", "allowed_hosts": ["example.com"]}]),
        json.dumps([{"source_id": "x", "source_tier": "OFFICIAL_PRIMARY", "allowed_hosts": []}]),
        json.dumps([{"source_id": "x", "source_tier": "OFFICIAL_PRIMARY", "allowed_hosts": ["example.com"], "unexpected": True}]),
        json.dumps([
            {"source_id": "one", "source_tier": "OFFICIAL_PRIMARY", "allowed_hosts": ["example.com"]},
            {"source_id": "two", "source_tier": "TRUSTED_MEDIA", "allowed_hosts": ["example.com"]},
        ]),
    ],
)
def test_invalid_or_ambiguous_news_policy_fails_closed(tmp_path, raw):
    with pytest.raises(ValueError):
        build_news_evidence_from_environment(
            runtime_dir=tmp_path,
            tenant_id="tenant-a",
            subject_id="owner-a",
            raw_policies=raw,
        )


def test_nested_hosts_cannot_be_assigned_to_ambiguous_publishers(tmp_path):
    raw = json.dumps([
        {"source_id": "parent", "source_tier": "OFFICIAL_PRIMARY", "allowed_hosts": ["example.com"]},
        {"source_id": "child", "source_tier": "TRUSTED_MEDIA", "allowed_hosts": ["news.example.com"]},
    ])
    with pytest.raises(ValueError, match="mais de uma fonte"):
        build_news_evidence_from_environment(
            runtime_dir=tmp_path,
            tenant_id="tenant-a",
            subject_id="owner-a",
            raw_policies=raw,
        )
