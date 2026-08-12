from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, Message

from app.alerts.dispatcher import Alert
from app.i18n import SUPPORTED_LOCALES, translate
from app.telegram.context import PanelContext
from app.telegram.filters import IsAdmin
from app.telegram.formatting import bold, render_alert
from app.telegram.locale_middleware import LocaleMiddleware
from app.telegram.routers import build_root_router

logger = logging.getLogger(__name__)

VISIBLE_COMMANDS: tuple[str, ...] = ("start", "stop", "restart", "help")
ALL_COMMANDS: tuple[str, ...] = (
    "status",
    "projects",
    "env",
    "logs",
    "events",
    "settings",
    "start",
    "stop",
    "restart",
    "cancel",
)


class ControlPanelBot:
    def __init__(self, bot_token: str, context: PanelContext, shutdown_event: asyncio.Event):
        self.bot = Bot(token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.context = context
        self.shutdown_event = shutdown_event
        self.dispatcher = Dispatcher(storage=MemoryStorage())
        self.dispatcher["context"] = context
        self._register_routers()

    def _register_routers(self) -> None:
        is_admin = IsAdmin(self.context.admin_ids, self.context.alerts)
        root_router = build_root_router(LocaleMiddleware(self.context.locales))
        root_router.message.filter(is_admin)
        root_router.callback_query.filter(is_admin)

        @root_router.message(Command("help"))
        async def show_help(message: Message, lang: str) -> None:
            body = "\n".join(
                [
                    bold(translate("help.title", lang)),
                    "",
                    translate("help.body", lang),
                    "",
                    *(
                        f"<code>/{command}</code> — {translate(f'command.{command}', lang)}"
                        for command in ALL_COMMANDS
                    ),
                ]
            )
            await message.answer(body)

        self.dispatcher.include_router(root_router)

    async def deliver_alert(self, alert: Alert) -> None:
        rendered = render_alert(alert)
        for admin_id in self.context.admin_ids:
            try:
                await self.bot.send_message(admin_id, rendered, disable_notification=alert.severity == "info")
            except TelegramAPIError as error:
                logger.warning("failed to deliver alert to %s: %s", admin_id, error)

    async def _publish_commands(self) -> None:
        for locale in SUPPORTED_LOCALES:
            commands = [
                BotCommand(command=command, description=translate(f"command.{command}", locale))
                for command in VISIBLE_COMMANDS
            ]
            with contextlib.suppress(TelegramAPIError):
                await self.bot.set_my_commands(commands, language_code=locale)

        for admin_id in self.context.admin_ids:
            locale = await self.context.locales.get(admin_id)
            if locale is None:
                continue
            commands = [
                BotCommand(command=command, description=translate(f"command.{command}", locale))
                for command in VISIBLE_COMMANDS
            ]
            with contextlib.suppress(TelegramAPIError):
                await self.bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=admin_id))

    async def run(self) -> None:
        await self._publish_commands()

        polling_task = asyncio.create_task(
            self.dispatcher.start_polling(self.bot, handle_signals=False), name="telegram-polling"
        )
        shutdown_task = asyncio.create_task(self.shutdown_event.wait(), name="telegram-shutdown-wait")

        _done, pending = await asyncio.wait(
            (polling_task, shutdown_task), return_when=asyncio.FIRST_COMPLETED
        )
        for pending_task in pending:
            pending_task.cancel()
        await asyncio.gather(polling_task, shutdown_task, return_exceptions=True)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self.bot.session.close()
