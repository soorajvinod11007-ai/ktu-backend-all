"""Every registered route must require auth — except the allowlist.

This test is the security net: it will fail the moment someone adds a new
route without a role dependency.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.main import app

# Routes that are intentionally reachable without a token.
PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    # FastAPI internals:
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    # 404 handler / static:
    "/favicon.ico",
}


def _all_api_routes() -> list[APIRoute]:
    routes: list[APIRoute] = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            routes.append(route)
    return routes


def _route_requires_auth(route: APIRoute) -> bool:
    """A route requires auth if any dependency on it (or its router) uses
    one of our auth dependencies. We detect by name to avoid importing
    internals that change between FastAPI versions."""
    AUTH_DEP_NAMES = {
        "get_current_user",
        "require_admin",
        "require_admin_or_principal",
        "require_roles",
    }
    for dep in route.dependant.dependencies or []:
        stack = [dep]
        while stack:
            d = stack.pop()
            call = getattr(d, "call", None)
            if call is not None and getattr(call, "__name__", "") in AUTH_DEP_NAMES:
                return True
            stack.extend(getattr(d, "dependencies", []) or [])
    return False


@pytest.mark.parametrize(
    "route",
    _all_api_routes(),
    ids=lambda r: f"{sorted(r.methods)[0]} {r.path}",
)
def test_route_is_not_publicly_accessible(route: APIRoute, client):
    # Skip explicitly-public paths.
    if route.path in PUBLIC_PATHS:
        pytest.skip(f"{route.path} is intentionally public")

    # If the route carries one of our auth dependencies, it's gated.
    if _route_requires_auth(route):
        return

    # Otherwise, actually call it without a token and expect 401/403.
    method = sorted(route.methods)[0].lower()
    response = getattr(client, method)(route.path)
    assert response.status_code in (401, 403), (
        f"{route.methods} {route.path} returned {response.status_code} "
        f"without a token — a route was added without auth!"
    )