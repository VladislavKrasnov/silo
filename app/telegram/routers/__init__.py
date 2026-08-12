from __future__ import annotations

from aiogram import BaseMiddleware, Router

from app.telegram.routers.backup import router as backup_router
from app.telegram.routers.dashboard import router as dashboard_router
from app.telegram.routers.projects import router as projects_router
from app.telegram.routers.secrets import router as secrets_router
from app.telegram.routers.settings import router as settings_router


def build_root_router(locale_middleware: BaseMiddleware) -> Router:
    root = Router(name="control-panel")
    all_routers = (root, dashboard_router, projects_router, secrets_router, settings_router, backup_router)
    root.include_routers(dashboard_router, projects_router, secrets_router, settings_router, backup_router)
    for router in all_routers:
        router.message.middleware(locale_middleware)
        router.callback_query.middleware(locale_middleware)
    return root
