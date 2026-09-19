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


def _api_routes_in_application() -> set[tuple[str, str]]:
    tree = ast.parse(APP.read_text(encoding="utf-8"), filename=str(APP))
    routes: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.BoolOp) or not isinstance(test.op, ast.And):
            continue
        method = None
        path = None
        for item in test.values:
            if not isinstance(item, ast.Compare):
                continue
            if len(item.ops) != 1 or not isinstance(item.ops[0], ast.Eq) or len(item.comparators) != 1:
                continue
            if not isinstance(item.left, ast.Name):
                continue
            value = item.comparators[0]
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            if item.left.id == "path" and value.value.startswith("/api/"):
                path = value.value
            elif item.left.id == "method" and value.value in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                method = value.value
        if path is not None and method is not None:
            routes.add((method, path))
    return routes


def _declared_policy_routes() -> set[tuple[str, str]]:
    tree = ast.parse(APP.read_text(encoding="utf-8"), filename=str(APP))
    routes: set[tuple[str, str]] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id in {"PUBLIC_SAAS_OWNER_SCOPED", "PUBLIC_SAAS_GENERIC"} for target in node.targets):
            continue
        if not isinstance(node.value, ast.Set):
            continue
        for item in node.value.elts:
            if not isinstance(item, ast.Tuple) or len(item.elts) != 2:
                continue
            if all(isinstance(part, ast.Constant) and isinstance(part.value, str) for part in item.elts):
                routes.add((item.elts[0].value, item.elts[1].value))
    return routes


def test_every_api_route_is_classified_by_public_saas_policy() -> None:
    routes = _api_routes_in_application()
    policy = _declared_policy_routes()
    exempt = {route for route in routes if route[1] in EXPLICITLY_EXEMPT}
    uncovered = routes - policy - exempt
    assert not uncovered, f"API route(s) missing public SaaS security classification: {sorted(uncovered)}"


def test_policy_does_not_reference_unknown_routes() -> None:
    routes = _api_routes_in_application()
    policy = _declared_policy_routes()
    unknown = policy - routes
    assert not unknown, f"Public SaaS policy contains route(s) not handled by app: {sorted(unknown)}"
