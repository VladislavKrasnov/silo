from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import TelegramObject, User

from app.i18n import DEFAULT_LOCALE, LocaleStore, detect_locale, translate
from app.telegram.callbacks import LocaleChoice
from app.telegram.keyboards import build_language_picker_keyboard


def _extract_user(event: TelegramObject) -> User | None:
    return getattr(event, "from_user", None)


def _extract_chat_id(event: TelegramObject) -> int | None:
    message = getattr(event, "message", None) or event
    chat = getattr(message, "chat", None)
    return chat.id if chat is not None else None


class LocaleMiddleware(BaseMiddleware):
    def __init__(self, locales: LocaleStore):
        self._locales = locales

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = _extract_user(event)
        if user is None:
            data["lang"] = DEFAULT_LOCALE
            return await handler(event, data)

        locale = await self._locales.get(user.id)
        if locale is None:
            detected = detect_locale(user.language_code)
            if detected is not None:
                await self._locales.set(user.id, detected)
                locale = detected

        raw_callback_data = getattr(event, "data", None)
        is_locale_choice = isinstance(raw_callback_data, str) and raw_callback_data.startswith(
            LocaleChoice.__prefix__ + LocaleChoice.__separator__
        )

        data["lang"] = locale or DEFAULT_LOCALE

        if locale is None and not is_locale_choice:
            bot: Bot = data["bot"]
            chat_id = _extract_chat_id(event)
            if chat_id is not None:
                await bot.send_message(
                    chat_id,
                    translate("language.pick_title", "en"),
                    reply_markup=build_language_picker_keyboard(),
                )
            if hasattr(event, "answer"):
                await event.answer()
            return None

        return await handler(event, data)
