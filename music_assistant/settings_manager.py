"""Settings loading, saving, and server connection helpers."""

import json
import logging

from gi.repository import GLib

from constants import (
    MEDIA_TILE_SIZE_COMPACT,
    MEDIA_TILE_SIZE_LARGE,
    MEDIA_TILE_SIZE_NORMAL,
    SIDEBAR_WIDTH,
)
from music_assistant import client, playback_state
from ui import playlist_manager

VALID_ALBUM_SORT_ORDERS = (
    "sort_name",
    "sort_artist",
    "year_desc",
    "timestamp_added_desc",
)


def load_settings(app) -> None:
    path = app.get_settings_path()
    server_url, auth_token = client.load_settings(path)
    if server_url:
        app.server_url = server_url
    app.auth_token = auth_token

    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return

    if not isinstance(payload, dict):
        return

    sendspin_client_id = payload.get("sendspin_client_id", "")
    if isinstance(sendspin_client_id, str):
        sendspin_client_id = sendspin_client_id.strip()
    else:
        sendspin_client_id = ""
    if sendspin_client_id:
        app.sendspin_manager.set_client_id(sendspin_client_id)

    output_player_id = payload.get("output_player_id", "")
    if isinstance(output_player_id, str):
        output_player_id = output_player_id.strip()
    else:
        output_player_id = ""
    output_local_output_id = payload.get("output_local_output_id", None)
    if isinstance(output_local_output_id, str):
        output_local_output_id = output_local_output_id.strip() or None
    elif output_local_output_id is not None:
        output_local_output_id = None
    if output_player_id:
        app.output_manager.preferred_player_id = output_player_id
        app.output_manager.preferred_local_output_id = output_local_output_id

    output_backend = payload.get("output_backend", "")
    if isinstance(output_backend, str):
        output_backend = output_backend.strip().casefold()
    else:
        output_backend = ""
    if output_backend == "pulseaudio":
        output_backend = "pulse"
    if output_backend not in ("pulse", "alsa"):
        output_backend = ""
    app.output_backend = output_backend

    output_pulse_device = payload.get("output_pulse_device", "")
    if isinstance(output_pulse_device, str):
        output_pulse_device = output_pulse_device.strip()
    else:
        output_pulse_device = ""
    app.output_pulse_device = output_pulse_device

    output_alsa_device = payload.get("output_alsa_device", "")
    if isinstance(output_alsa_device, str):
        output_alsa_device = output_alsa_device.strip()
    else:
        output_alsa_device = ""
    app.output_alsa_device = output_alsa_device

    output_bitperfect = payload.get("output_bitperfect", False)
    output_bitperfect = bool(output_bitperfect)
    app.output_bitperfect = output_bitperfect

    eq_enabled = payload.get("eq_enabled", False)
    if not isinstance(eq_enabled, bool):
        eq_enabled = False
    eq_selected_preset = payload.get("eq_selected_preset", None)
    if isinstance(eq_selected_preset, str):
        eq_selected_preset = eq_selected_preset.strip() or None
    elif eq_selected_preset is not None:
        eq_selected_preset = None
    app.eq_enabled = eq_enabled
    app.eq_selected_preset = eq_selected_preset

    album_tile_size = payload.get("album_tile_size", MEDIA_TILE_SIZE_NORMAL)
    try:
        album_tile_size = int(album_tile_size)
    except (TypeError, ValueError):
        album_tile_size = MEDIA_TILE_SIZE_NORMAL
    if album_tile_size not in (
        MEDIA_TILE_SIZE_COMPACT,
        MEDIA_TILE_SIZE_NORMAL,
        MEDIA_TILE_SIZE_LARGE,
    ):
        album_tile_size = MEDIA_TILE_SIZE_NORMAL
    app.album_tile_size = album_tile_size

    album_sort_order = payload.get("album_sort_order", "sort_name")
    if not isinstance(album_sort_order, str):
        album_sort_order = "sort_name"
    if album_sort_order not in VALID_ALBUM_SORT_ORDERS:
        album_sort_order = "sort_name"
    app.album_sort_order = album_sort_order

    search_library_only = payload.get("search_library_only", True)
    app.search_library_only = bool(search_library_only)

    sidebar_width = payload.get("sidebar_width", SIDEBAR_WIDTH)
    try:
        sidebar_width = int(sidebar_width)
    except (TypeError, ValueError):
        sidebar_width = SIDEBAR_WIDTH
    if sidebar_width < 150:
        sidebar_width = 150
    elif sidebar_width > 600:
        sidebar_width = 600
    app.sidebar_width = sidebar_width


def save_settings(app, server_url: str, auth_token: str) -> None:
    app.sendspin_manager.ensure_client_id()
    path = app.get_settings_path()
    client.save_settings(server_url, auth_token, path)
    app.persist_sendspin_settings(path)


def persist_sendspin_settings(app, path: str) -> None:
    payload: dict[str, object] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if isinstance(existing, dict):
            payload.update(existing)
    except FileNotFoundError:
        payload = {}
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).warning(
            "Failed to read settings from %s: %s",
            path,
            exc,
        )
        payload = {}
    if app.sendspin_manager.client_id:
        payload["sendspin_client_id"] = app.sendspin_manager.client_id
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            handle.write("\n")
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Failed to write settings to %s: %s",
            path,
            exc,
        )


def persist_output_selection(app, path: str | None = None) -> None:
    if not app.output_manager:
        return
    selected = app.output_manager.get_selected_output()
    if not selected:
        return
    player_id = selected.get("player_id")
    if not isinstance(player_id, str):
        return
    player_id = player_id.strip()
    if not player_id:
        return
    local_output_id = selected.get("local_output_id")
    if isinstance(local_output_id, str):
        local_output_id = local_output_id.strip() or None
    elif local_output_id is not None:
        local_output_id = None

    payload: dict[str, object] = {}
    path = path or app.get_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if isinstance(existing, dict):
            payload.update(existing)
    except FileNotFoundError:
        payload = {}
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).warning(
            "Failed to read settings from %s: %s",
            path,
            exc,
        )
        payload = {}

    payload["output_player_id"] = player_id
    payload["output_local_output_id"] = local_output_id
    payload["output_backend"] = app.output_backend or ""
    payload["output_pulse_device"] = app.output_pulse_device or ""
    payload["output_alsa_device"] = app.output_alsa_device or ""
    payload["output_bitperfect"] = bool(getattr(app, "output_bitperfect", False))
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            handle.write("\n")
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Failed to write settings to %s: %s",
            path,
            exc,
        )


def persist_eq_settings(app, path: str | None = None) -> None:
    payload: dict[str, object] = {}
    path = path or app.get_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if isinstance(existing, dict):
            payload.update(existing)
    except FileNotFoundError:
        payload = {}
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).warning(
            "Failed to read settings from %s: %s",
            path,
            exc,
        )
        payload = {}

    eq_enabled = bool(getattr(app, "eq_enabled", False))
    eq_selected_preset = getattr(app, "eq_selected_preset", None)
    if isinstance(eq_selected_preset, str):
        eq_selected_preset = eq_selected_preset.strip() or None
    elif eq_selected_preset is not None:
        eq_selected_preset = None
    payload["eq_enabled"] = eq_enabled
    payload["eq_selected_preset"] = eq_selected_preset
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            handle.write("\n")
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Failed to write settings to %s: %s",
            path,
            exc,
        )


def persist_album_density(app, path: str | None = None) -> None:
    payload: dict[str, object] = {}
    path = path or app.get_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if isinstance(existing, dict):
            payload.update(existing)
    except FileNotFoundError:
        payload = {}
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger(__name__).warning(
            "Failed to read settings from %s: %s",
            path,
            exc,
        )
        payload = {}

    tile_size = getattr(app, "album_tile_size", MEDIA_TILE_SIZE_NORMAL)
    if tile_size not in (
        MEDIA_TILE_SIZE_COMPACT,
        MEDIA_TILE_SIZE_NORMAL,
        MEDIA_TILE_SIZE_LARGE,
    ):
        tile_size = MEDIA_TILE_SIZE_NORMAL
    payload["album_tile_size"] = int(tile_size)

    album_sort_order = getattr(app, "album_sort_order", "sort_name")
    if album_sort_order not in VALID_ALBUM_SORT_ORDERS:
        album_sort_order = "sort_name"
    payload["album_sort_order"] = album_sort_order

    payload["search_library_only"] = bool(
        getattr(app, "search_library_only", True)
    )

    sidebar_width = getattr(app, "sidebar_width", SIDEBAR_WIDTH)
    try:
        sidebar_width = int(sidebar_width)
    except (TypeError, ValueError):
        sidebar_width = SIDEBAR_WIDTH
    payload["sidebar_width"] = sidebar_width

    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            )
            handle.write("\n")
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Failed to write settings to %s: %s",
            path,
            exc,
        )


def reset_ui_preferences(app) -> None:
    app.album_tile_size = MEDIA_TILE_SIZE_NORMAL
    app.album_sort_order = "sort_name"
    app.search_library_only = True
    app.sidebar_width = SIDEBAR_WIDTH
    app.persist_album_density()

    for tile_size, button in (getattr(app, "album_density_buttons", {}) or {}).items():
        button.set_active(tile_size == MEDIA_TILE_SIZE_NORMAL)

    for order_value, button in (getattr(app, "album_sort_buttons", {}) or {}).items():
        button.set_active(order_value == "sort_name")

    if getattr(app, "search_scope_toggle", None):
        app.search_scope_toggle.set_active(True)

    if getattr(app, "content_paned", None):
        app.content_paned.set_position(SIDEBAR_WIDTH)

    app.load_library()


def _on_sidebar_width_changed(app, paned, _param) -> None:
    if app._sidebar_width_persist_id:
        GLib.source_remove(app._sidebar_width_persist_id)
        app._sidebar_width_persist_id = None

    def _persist_sidebar_width() -> bool:
        app._sidebar_width_persist_id = None
        width = paned.get_position()
        try:
            width = int(width)
        except (TypeError, ValueError):
            width = SIDEBAR_WIDTH
        app.sidebar_width = width
        app.persist_album_density()
        return False

    app._sidebar_width_persist_id = GLib.timeout_add(400, _persist_sidebar_width)


def update_settings_entries(app) -> None:
    if app.settings_server_entry is not None:
        if app.server_url:
            app.settings_server_entry.set_text(app.server_url)
        else:
            app.settings_server_entry.set_text("")
    if app.settings_token_entry is not None:
        if app.auth_token:
            app.settings_token_entry.set_text(app.auth_token)
        else:
            app.settings_token_entry.set_text("")
    if app.settings_output_backend_combo is not None:
        backend = (app.output_backend or "").strip().casefold()
        if backend == "pulseaudio":
            backend = "pulse"
        if backend not in ("pulse", "alsa"):
            backend = "auto"
        app.settings_output_backend_combo.set_active_id(backend)
    if app.settings_pulse_device_entry is not None:
        app.settings_pulse_device_entry.set_text(app.output_pulse_device or "")
    if app.settings_alsa_device_entry is not None:
        app.settings_alsa_device_entry.set_text(app.output_alsa_device or "")
    if app.settings_bitperfect_switch is not None:
        app.suppress_bitperfect_sync = True
        try:
            app.settings_bitperfect_switch.set_active(
                bool(getattr(app, "output_bitperfect", False))
            )
        finally:
            app.suppress_bitperfect_sync = False


def connect_to_server(
    app,
    server_url: str,
    auth_token: str,
    persist: bool = False,
    on_success=None,
    on_error=None,
) -> None:
    app._pending_connection_callbacks = {
        "on_success": on_success,
        "on_error": on_error,
    }

    def on_server_change() -> None:
        app.sendspin_manager.stop()
        app.audio_pipeline.destroy_pipeline()
        app.clear_home_recent_lists()
        playlist_manager.populate_playlists_list(app, [])
        app.provider_manifests = {}
        app.provider_instances = {}
        app.provider_icon_cache = {}
        app.provider_manifest_loading = False

    callbacks = {
        "get_server_url": lambda: app.server_url,
        "set_server_url": lambda value: setattr(app, "server_url", value),
        "set_auth_token": lambda value: setattr(app, "auth_token", value),
        "on_server_change": on_server_change,
        "persist": persist,
        "save_settings": app.save_settings,
        "update_settings_entries": app.update_settings_entries,
        "prefetch_provider_manifests": lambda: playback_state._ensure_provider_manifests_loaded(app),
        "start_sendspin_client": lambda: app.sendspin_manager.start(app.server_url),
        "schedule_output_refresh": app.output_manager.refresh,
        "load_library": app.load_library,
    }
    client.connect_to_server(server_url, auth_token, callbacks)
    if getattr(app, "client_session", None):
        app.client_session.set_server(app.server_url, app.auth_token)
