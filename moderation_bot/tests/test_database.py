"""Тесты хранилища настроек (SQLite + aiosqlite)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.database import SettingsRepository
from bot.models import TOGGLE_FIELDS, ChatSettings, SettingsDefaults
from tests.conftest import CHAT_ID

OTHER_CHAT_ID = -1009999999999


async def test_defaults_without_row(repository: SettingsRepository):
    settings = await repository.get(CHAT_ID)

    assert isinstance(settings, ChatSettings)
    assert settings.chat_id == CHAT_ID
    # Дефолты из SettingsDefaults: три фильтра включены, «медиа от не-админов» — нет.
    assert settings.block_target_user is True
    assert settings.block_hashtag is True
    assert settings.block_media_from_target is True
    assert settings.block_media_non_admin is False


async def test_defaults_do_not_create_row(repository: SettingsRepository):
    await repository.get(CHAT_ID)
    assert list(await repository.all_chats()) == []


async def test_set_flag_creates_row_with_defaults_for_other_flags(
    repository: SettingsRepository, config, settings_service
):
    settings = await settings_service.toggle(CHAT_ID, "block_hashtag")

    assert settings.block_hashtag is False
    # Остальные флаги пришли из значений по умолчанию.
    assert settings.block_target_user is True
    assert settings.block_media_from_target is True
    assert len(list(await repository.all_chats())) == 1


async def test_toggle_twice_returns_to_initial(repository: SettingsRepository, settings_service):
    await settings_service.toggle(CHAT_ID, "block_media_non_admin")
    settings = await settings_service.toggle(CHAT_ID, "block_media_non_admin")

    assert settings.block_media_non_admin is False


async def test_explicit_values(repository: SettingsRepository):
    await repository.set_flag(CHAT_ID, "block_target_user", False)
    settings = await repository.set_flag(CHAT_ID, "block_media_non_admin", True)

    assert settings.block_target_user is False
    assert settings.block_media_non_admin is True


async def test_reset_restores_defaults(repository: SettingsRepository, settings_service):
    await settings_service.toggle(CHAT_ID, "block_target_user")
    await settings_service.toggle(CHAT_ID, "block_media_non_admin")

    settings = await settings_service.reset(CHAT_ID)

    assert settings == ChatSettings.from_defaults(CHAT_ID, SettingsDefaults())


async def test_persistence_across_reconnect(config):
    async with SettingsRepository(config.db_path) as repo:
        await repo.set_flag(CHAT_ID, "block_hashtag", False)

    async with SettingsRepository(config.db_path) as repo:
        settings = await repo.get(CHAT_ID)

    assert settings.block_hashtag is False


async def test_settings_are_isolated_per_chat(repository: SettingsRepository):
    await repository.set_flag(CHAT_ID, "block_hashtag", False)
    await repository.set_flag(OTHER_CHAT_ID, "block_media_non_admin", True)

    first = await repository.get(CHAT_ID)
    second = await repository.get(OTHER_CHAT_ID)

    assert first.block_hashtag is False
    assert second.block_hashtag is True
    assert second.block_media_non_admin is True
    assert first.block_media_non_admin is False


async def test_all_chats_sorted(repository: SettingsRepository):
    await repository.set_flag(OTHER_CHAT_ID, "block_hashtag", False)
    await repository.set_flag(CHAT_ID, "block_hashtag", False)

    chat_ids = [settings.chat_id for settings in await repository.all_chats()]

    assert chat_ids == sorted([CHAT_ID, OTHER_CHAT_ID])


async def test_seed_writes_full_state(repository: SettingsRepository, settings):
    custom = ChatSettings.from_defaults(OTHER_CHAT_ID, SettingsDefaults()).with_flag("block_media_non_admin", True)

    await repository.seed(OTHER_CHAT_ID, custom)
    stored = await repository.get(OTHER_CHAT_ID)

    assert stored == custom
    assert settings.chat_id == CHAT_ID  # фикстура не мутирует


async def test_unknown_flag_rejected(repository: SettingsRepository):
    with pytest.raises(ValueError, match="Неизвестный фильтр"):
        await repository.set_flag(CHAT_ID, "block_everything", True)


async def test_updated_by_is_stored(repository: SettingsRepository, config):
    await repository.set_flag(CHAT_ID, "block_hashtag", False, updated_by=555)

    import aiosqlite

    async with (
        aiosqlite.connect(config.db_path) as conn,
        conn.execute("SELECT updated_by FROM chat_settings WHERE chat_id = ?", (CHAT_ID,)) as cursor,
    ):
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == 555


async def test_repository_requires_connect(tmp_path: Path):
    repo = SettingsRepository(tmp_path / "not_connected.sqlite3")

    with pytest.raises(RuntimeError, match="не инициализирована"):
        await repo.get(CHAT_ID)


async def test_all_toggle_fields_are_stored(repository: SettingsRepository):
    for flag in TOGGLE_FIELDS:
        await repository.set_flag(CHAT_ID, flag, False)

    settings = await repository.get(CHAT_ID)

    assert settings.enabled_count == 0
    assert settings.any_enabled is False
