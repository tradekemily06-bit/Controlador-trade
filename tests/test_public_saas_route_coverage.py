from __future__ import annotations

import ast
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app.py"

# These endpoints are intentionally outside the tenant-scoped public SaaS data
# plane because they have a narrower, explicit security contract.
EXPLICITLY_EXEMPT = {
    "/api/health",       # intentionally sanitized public health surface
    "/api/onboarding",   # first-use guide; execution_authorized is always false
    "/api/updates",      # internal bearer-protected publisher endpoint
}


def _api_paths_in_application() -> set[str]:
    tree = ast.parse(APP.read_text(encoding="utf-8"), filename=str(APP))
    paths: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.BoolOp) or not isinstance(test.op, ast.And):
            continue
        for item in test.values:
            if not isinstance(item, ast.Compare):
                continue
            if len(item.ops) != 1 or not isinstance(item.ops[0], ast.Eq):
                continue
            if not isinstance(item.left, ast.Name) or item.left.id != "path":
                continue
            if len(item.comparators) != 1:
                continue
            value = item.comparators[0]
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.startswith("/api/"):
                paths.add(value.value)
    return paths


def _declared_policy_paths() -> set[str]:
    tree = ast.parse(APP.read_text(encoding="utf-8"), filename=str(APP))
    paths: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id in {"PUBLIC_SAAS_MUTATIONS", "PUBLIC_SAAS_READS"} for target in node.targets):
            continue
        if not isinstance(node.value, ast.Set):
            continue
        for item in node.value.elts:
            if isinstance(item, ast.Constant) and isinstance(item.value, str):
                paths.add(item.value)
    return paths


def test_every_api_route_is_classified_by_public_saas_policy() -> None:
    routes = _api_paths_in_application()
    policy = _declared_policy_paths()
    uncovered = routes - policy - EXPLICITLY_EXEMPT
    assert not uncovered, f"API route(s) missing public SaaS security classification: {sorted(uncovered)}"


def test_policy_does_not_reference_unknown_routes() -> None:
    routes = _api_paths_in_application()
    policy = _declared_policy_paths()
    unknown = policy - routes
    assert not unknown, f"Public SaaS policy contains route(s) not handled by app: {sorted(unknown)}"
