from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

from music_assistant_client import MusicAssistantClient
from music_assistant_client.exceptions import CannotConnect, InvalidServerVersion
from music_assistant_models.errors import AuthenticationFailed, AuthenticationRequired

from utils import normalize_server_url


Callback = Callable[..., object]


def _get_callback(callbacks: dict[str, object], key: str) -> Callback | None:
    callback = callbacks.get(key)
    return callback if callable(callback) else None


def connect_to_server(
    server_url: str, auth_token: str, callbacks: dict[str, object]
) -> None:
    normalized_url = normalize_server_url(server_url)
    token_value = auth_token.strip() if isinstance(auth_token, str) else ""
    get_server_url = _get_callback(callbacks, "get_server_url")
    previous_server_url = get_server_url() if get_server_url else ""

    set_server_url = _get_callback(callbacks, "set_server_url")
    if set_server_url:
        set_server_url(normalized_url)
    set_auth_token = _get_callback(callbacks, "set_auth_token")
    if set_auth_token:
        set_auth_token(token_value)

    if previous_server_url != normalized_url:
        on_server_change = _get_callback(callbacks, "on_server_change")
        if on_server_change:
            on_server_change()

    if callbacks.get("persist"):
        save_settings = _get_callback(callbacks, "save_settings")
        if save_settings:
            save_settings(normalized_url, token_value)

    update_settings_entries = _get_callback(callbacks, "update_settings_entries")
    if update_settings_entries:
        update_settings_entries()

    start_sendspin_client = _get_callback(callbacks, "start_sendspin_client")
    if start_sendspin_client:
        start_sendspin_client()

    schedule_output_refresh = _get_callback(callbacks, "schedule_output_refresh")
    if schedule_output_refresh:
        schedule_output_refresh()

    prefetch_provider_manifests = _get_callback(
        callbacks, "prefetch_provider_manifests"
    )
    if prefetch_provider_manifests:
        prefetch_provider_manifests()

    load_library = _get_callback(callbacks, "load_library")
    if load_library:
        load_library()


def save_settings(
    server_url: str, auth_token: str, settings_file: str
) -> None:
    logger = logging.getLogger(__name__)
    payload: dict[str, object] = {}
    try:
        with open(settings_file, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if isinstance(existing, dict):
            payload.update(existing)
    except FileNotFoundError:
        payload = {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read settings from %s: %s", settings_file, exc)
        payload = {}

    payload["server_url"] = normalize_server_url(server_url)
    payload["auth_token"] = auth_token

    try:
        with open(settings_file, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            handle.write("\n")
    except OSError as exc:
        logger.warning("Failed to write settings to %s: %s", settings_file, exc)


def load_settings(settings_file: str) -> tuple[str, str]:
    logger = logging.getLogger(__name__)
    try:
        with open(settings_file, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError:
        return "", ""
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read settings from %s: %s", settings_file, exc)
        return "", ""

    if not isinstance(payload, dict):
        return "", ""

    server_url = normalize_server_url(payload.get("server_url", ""))
    auth_token = payload.get("auth_token", "")
    if isinstance(auth_token, str):
        auth_token = auth_token.strip()
    else:
        auth_token = ""
    return server_url, auth_token


def validate_connection(server_url: str, auth_token: str) -> bool:
    async def _validate() -> None:
        token = auth_token or None
        async with MusicAssistantClient(server_url, None, token=token) as client:
            await client.players.fetch_state()

    try:
        asyncio.run(_validate())
    except Exception:
        return False
    return True


__all__ = [
    "AuthenticationRequired",
    "AuthenticationFailed",
    "CannotConnect",
    "InvalidServerVersion",
    "connect_to_server",
    "save_settings",
    "load_settings",
    "validate_connection",
]
