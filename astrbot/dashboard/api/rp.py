"""Dashboard endpoints for the roleplay engine.

Served under the legacy ``/api/rp`` prefix: the dashboard auth middleware
already protects every ``/api/*`` path with the dashboard JWT, so these routes
need no OpenAPI entry and cannot be reached anonymously.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from astrbot.dashboard.api.auth import require_dashboard_user
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.services.rp_service import RPService, RPServiceError

legacy_router = APIRouter(
    prefix="/api/rp",
    tags=["Dashboard Roleplay"],
    include_in_schema=False,
)


def get_service(request: Request) -> RPService:
    return request.app.state.services.rp


async def _json_or_empty(request: Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


async def _run(operation) -> dict[str, Any]:
    try:
        return ok(await operation())
    except RPServiceError as exc:
        raise ApiError(str(exc)) from exc


@legacy_router.get("/overview")
async def overview(
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    return await _run(service.overview)


@legacy_router.get("/platforms")
async def platforms(
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    return await _run(service.platforms)


@legacy_router.post("/cards/list")
async def list_cards(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.list_cards(body))


@legacy_router.post("/cards/detail")
async def card_detail(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.card_detail(body))


@legacy_router.post("/cards/save")
async def save_card(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.save_card(body))


@legacy_router.post("/cards/create")
async def create_card(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.create_card(body))


@legacy_router.post("/cards/delete")
async def delete_card(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_card(body))


@legacy_router.post("/cards/bind")
async def bind_card(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.bind_card(body))


@legacy_router.post("/books/list")
async def list_books(
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    return await _run(service.list_books)


@legacy_router.post("/books/detail")
async def book_detail(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.book_detail(body))


@legacy_router.post("/books/save")
async def save_book(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.save_book(body))


@legacy_router.post("/books/delete")
async def delete_book(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_book(body))


@legacy_router.post("/books/entry/save")
async def save_entry(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.save_entry(body))


@legacy_router.post("/books/entry/delete")
async def delete_entry(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.delete_entry(body))


@legacy_router.post("/books/entry/test")
async def test_entry(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.test_entry(body))


@legacy_router.post("/import/scan")
async def import_scan(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.import_scan(body))


@legacy_router.post("/import/commit")
async def import_commit(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.import_commit(body))


@legacy_router.post("/preview")
async def preview(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.build_preview(body))


@legacy_router.post("/send")
async def send(
    request: Request,
    _username: str = Depends(require_dashboard_user),
    service: RPService = Depends(get_service),
):
    body = await _json_or_empty(request)
    return await _run(lambda: service.send(body))
