from __future__ import annotations

from app.alerts.kinds import USER_CONFIGURABLE_ALERT_KINDS, AlertKind
from app.database.engine import Database
from app.database.repositories import UserPreferenceRepository
from app.i18n import LocaleStore, detect_locale, translate
from app.i18n.catalog import STRINGS


class TestLocaleDetection:
    def test_detects_russian_from_any_regional_variant(self) -> None:
        assert detect_locale("ru") == "ru"
        assert detect_locale("ru-RU") == "ru"

    def test_falls_back_to_english_for_other_known_languages(self) -> None:
        assert detect_locale("en-US") == "en"
        assert detect_locale("fr") == "en"
        assert detect_locale("de-DE") == "en"

    def test_returns_none_when_telegram_gives_nothing(self) -> None:
        assert detect_locale(None) is None
        assert detect_locale("") is None


class TestTranslate:
    def test_every_key_has_both_locales(self) -> None:
        for key, entry in STRINGS.items():
            assert "en" in entry and entry["en"], key
            assert "ru" in entry and entry["ru"], key

    def test_interpolates_named_parameters(self) -> None:
        assert translate("menu.projects_running", "en", running=2, total=5) == "Running: 2 / 5"
        assert translate("menu.projects_running", "ru", running=2, total=5) == "Запущено: 2 / 5"

    def test_unknown_key_returns_the_key_itself(self) -> None:
        assert translate("does.not.exist", "en") == "does.not.exist"


class TestLocaleStore:
    async def test_unset_user_resolves_to_none(self, database: Database) -> None:
        store = LocaleStore(UserPreferenceRepository(database))
        assert await store.get(42) is None

    async def test_persists_and_caches_a_choice(self, database: Database) -> None:
        repository = UserPreferenceRepository(database)
        store = LocaleStore(repository)

        await store.set(42, "ru")
        assert await store.get(42) == "ru"

        reloaded = LocaleStore(repository)
        assert await reloaded.get(42) == "ru"


class TestAlertCatalogCuration:
    def test_exactly_six_kinds_are_user_configurable(self) -> None:
        assert set(USER_CONFIGURABLE_ALERT_KINDS) == {
            AlertKind.PROJECT_CRASHED,
            AlertKind.PROJECT_RESTART_LOOP,
            AlertKind.PROJECT_BUILD_FAILED,
            AlertKind.HOST_RESOURCE_PRESSURE,
            AlertKind.PROJECT_SECRETS_MISSING,
            AlertKind.ORCHESTRATOR_DEGRADED_ISOLATION,
        }
