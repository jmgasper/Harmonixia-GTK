"""UI event handlers for MusicApp."""

import logging
import threading
import time
from types import SimpleNamespace

from gi.repository import Gdk, GLib, Gtk

from music_assistant import playback
from music_assistant_models.enums import PlaybackState
from ui import image_loader


def on_track_action_clicked(app, button: Gtk.Button, menu_button, action: str) -> None:
    track = getattr(button, "track_item", None)
    track_name = getattr(track, "title", "Track")
    logging.getLogger(__name__).info(
        "Track action '%s' for %s", action, track_name
    )
    if menu_button:
        menu_button.popdown()
    if action == "Play":
        if track:
            app.start_playback_from_track(track)
        return
    if action == "Play Next":
        _run_track_queue_action(
            app,
            track,
            playback.play_next,
            "Play Next",
        )
        return
    if action == "Add to Queue":
        _run_track_queue_action(
            app,
            track,
            playback.add_to_queue,
            "Add to Queue",
        )
        return
    if action == "Start Radio":
        _run_track_queue_action(
            app,
            track,
            playback.play_radio,
            "Start Radio",
        )
        return
    if action == "Go to Album":
        if track:
            _show_track_album_detail(app, track)
        return
    if action == "Remove from this playlist":
        if track:
            from ui import playlist_operations

            playlist_operations.remove_track_from_playlist(app, track)
        return
    if action == "Add to existing playlist":
        from ui import playlist_manager

        playlist_manager.show_add_to_playlist_dialog(app, track)
        return
    if action == "Add to favorites":
        if track:
            from ui import favorites_manager

            favorites_manager.add_track_to_favorites(app, track)
        return
    if action == "Remove from favorites":
        if track:
            from ui import favorites_manager

            favorites_manager.remove_track_from_favorites(app, track)
        return
    if action == "Add to new playlist":
        from ui import playlist_manager

        playlist_manager.show_create_playlist_dialog(app, track)
        return


def _run_track_queue_action(
    app,
    track,
    action_fn,
    action_label: str,
) -> None:
    if not track or not app.server_url:
        return
    source_uri = _resolve_track_source_uri(track)
    if not source_uri:
        logging.getLogger(__name__).warning(
            "Track action '%s' failed: missing source URI.",
            action_label,
        )
        return
    thread = threading.Thread(
        target=_track_queue_action_worker,
        args=(app, action_fn, source_uri, action_label),
        daemon=True,
    )
    thread.start()


def _track_queue_action_worker(
    app,
    action_fn,
    source_uri: str,
    action_label: str,
) -> None:
    error = ""
    try:
        action_fn(
            app.client_session,
            app.server_url,
            app.auth_token,
            source_uri,
            app.output_manager.preferred_player_id
            if app.output_manager
            else None,
        )
        if action_fn is playback.play_radio:
            _refresh_remote_playback_state(app)
    except Exception as exc:
        error = str(exc)
    if error:
        logging.getLogger(__name__).warning(
            "Track action '%s' failed: %s",
            action_label,
            error,
        )


def _resolve_track_source_uri(track) -> str | None:
    source = getattr(track, "source", None)
    if isinstance(source, dict):
        uri = source.get("uri") or source.get("source_uri")
    else:
        uri = getattr(source, "uri", None) or getattr(
            source, "source_uri", None
        )
    if not uri:
        uri = getattr(track, "source_uri", None)
    if isinstance(uri, str):
        uri = uri.strip()
    return uri or None


def on_track_selection_changed(app, selection, _position: int, _n_items: int) -> None:
    if app.suppress_track_selection:
        return
    item = selection.get_selected_item()
    if item is None:
        return
    app.start_playback_from_track(item)


def clear_track_selection(app, selection=None) -> None:
    selection = selection or app.album_tracks_selection
    if not selection:
        return
    previous = app.suppress_track_selection
    app.suppress_track_selection = True
    try:
        invalid_pos = getattr(Gtk, "INVALID_LIST_POSITION", GLib.MAXUINT)
        selection.set_selected(invalid_pos)
    finally:
        app.suppress_track_selection = previous


def on_play_pause_clicked(app, _button) -> None:
    if app.playback_state == PlaybackState.PLAYING:
        app.send_playback_command("pause")
    else:
        app.send_playback_command("play")


def on_previous_clicked(app, _button) -> None:
    app.send_playback_command("previous")


def on_next_clicked(app, _button) -> None:
    app.send_playback_command("next")


def on_repeat_clicked(app, _button) -> None:
    app.cycle_repeat_mode()


def on_shuffle_clicked(app, _button) -> None:
    app.toggle_shuffle()


def on_volume_changed(app, scale: Gtk.Scale) -> None:
    if app.suppress_volume_changes:
        return
    volume = int(round(scale.get_value()))
    app.pending_volume_value = volume
    if app.volume_update_id is None:
        app.volume_update_id = GLib.timeout_add(150, app._apply_volume_change)


def _apply_volume_change(app) -> bool:
    app.volume_update_id = None
    volume = app.pending_volume_value
    app.pending_volume_value = None
    if volume is None:
        return False
    app.set_output_volume(volume)
    return False


def on_volume_drag_begin(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    app.volume_dragging = True


def on_volume_drag_end(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    app.volume_dragging = False
    if app.pending_volume_value is None and app.last_volume_value is not None:
        app.update_volume_slider(app.last_volume_value)


def on_seek_scale_changed(app, scale: Gtk.Scale) -> None:
    if not getattr(app, "seek_dragging", False):
        return
    if app.playback_track_info is None:
        return
    duration = app.playback_duration or 0
    if duration <= 0:
        return
    value = max(0.0, min(1.0, float(scale.get_value())))
    position = max(0.0, min(float(duration), value * float(duration)))
    app.playback_elapsed = position
    app.playback_last_tick = time.monotonic()
    app.update_playback_progress_ui()


def on_seek_drag_begin(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    app.seek_dragging = True


def on_seek_drag_end(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    if app.playback_track_info is None:
        app.seek_dragging = False
        return
    duration = app.playback_duration or 0
    scale = getattr(app, "playback_seek_scale", None)
    if duration <= 0 or scale is None:
        app.seek_dragging = False
        return
    value = max(0.0, min(1.0, float(scale.get_value())))
    position = int(round(value * float(duration)))
    position = max(0, min(position, int(duration)))
    app.playback_elapsed = float(position)
    app.playback_last_tick = time.monotonic()
    app.update_playback_progress_ui()
    app.send_playback_command("seek", position=position)
    if app.mpris_manager:
        app.mpris_manager.emit_mpris_seeked(int(position * 1_000_000))
    app.seek_dragging = False


def on_mute_button_clicked(app, _button: Gtk.Button) -> None:
    current_muted = bool(getattr(app.sendspin_manager, "muted", False))
    target_muted = not current_muted
    app.set_sendspin_muted(target_muted)
    app.update_mute_button_icon()
    output_manager = getattr(app, "output_manager", None)
    if not output_manager or not app.server_url:
        return
    player_id = output_manager.preferred_player_id
    if not player_id:
        return
    if output_manager.is_sendspin_player_id(player_id):
        return
    thread = threading.Thread(
        target=_remote_mute_worker,
        args=(app, player_id, target_muted),
        daemon=True,
    )
    thread.start()


def _remote_mute_worker(app, player_id: str, muted: bool) -> None:
    try:
        app.client_session.run(
            app.server_url,
            app.auth_token,
            _remote_mute_async,
            player_id,
            muted,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Mute toggle failed for %s: %s",
            player_id,
            exc,
        )


async def _remote_mute_async(client, player_id: str, muted: bool) -> None:
    players = getattr(client, "players", None)
    if players is None:
        return
    if hasattr(players, "volume_mute"):
        await players.volume_mute(player_id, muted)
        return
    if hasattr(players, "player_command_volume_mute"):
        await players.player_command_volume_mute(player_id, muted)
        return
    if hasattr(players, "player_command"):
        from music_assistant_models.enums import PlayerCommand

        await players.player_command(
            player_id,
            PlayerCommand.VOLUME_MUTE,
            muted,
        )


def on_playback_progress_clicked(
    app, _gesture, _n_press: int, x: float, _y: float
) -> None:
    progress = getattr(app, "playback_seek_scale", None) or getattr(
        app, "playback_progress_bar", None
    )
    if not progress or app.playback_track_info is None:
        return
    duration = app.playback_duration or 0
    if duration <= 0:
        return
    width = progress.get_allocated_width()
    if width <= 0:
        return
    fraction = max(0.0, min(1.0, x / width))
    position = int(round(fraction * duration))
    position = max(0, min(position, int(duration)))
    app.playback_elapsed = float(position)
    app.playback_last_tick = time.monotonic()
    app.update_playback_progress_ui()
    app.send_playback_command("seek", position=position)
    if app.mpris_manager:
        app.mpris_manager.emit_mpris_seeked(int(position * 1_000_000))


def on_now_playing_title_clicked(app, _button) -> None:
    _show_now_playing_album(app)


def on_now_playing_artist_clicked(app, _button) -> None:
    artist_name = _resolve_now_playing_artist_name(app)
    if not artist_name:
        return
    previous_view = _get_current_view(app)
    if previous_view == "artist-albums":
        previous_view = None
    app.show_artist_albums(artist_name, previous_view)


def on_album_detail_artist_clicked(app, _button) -> None:
    album = getattr(app, "current_album", None)
    if not album:
        return
    if isinstance(album, dict):
        artists = album.get("artists")
    else:
        artists = getattr(album, "artists", None)
    artist_name = _pick_artist_name(artists)
    if not artist_name:
        return
    previous_view = _get_current_view(app)
    if previous_view == "artist-albums":
        previous_view = None
    app.show_artist_albums(artist_name, previous_view)


def on_now_playing_art_clicked(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    _show_now_playing_album(app)


def on_now_playing_art_context_menu(
    app, _gesture, _n_press: int, x: float, y: float
) -> None:
    popover = getattr(app, "sidebar_now_playing_popover", None)
    if not popover:
        return
    track = _build_now_playing_track_action_item(app)
    if not track:
        return
    for button in getattr(app, "sidebar_now_playing_action_buttons", []):
        button.track_item = track
    if hasattr(popover, "set_pointing_to"):
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
    popover.popup()


def on_album_card_play_clicked(app, album_data: object) -> None:
    if not album_data:
        return
    _run_album_card_action(
        app,
        album_data,
        "Play",
        playback.play_album,
    )


def on_album_card_context_action(
    app,
    _button: Gtk.Button,
    popover: Gtk.Popover,
    action: str,
    album_data: object,
) -> None:
    if popover:
        popover.popdown()
    if not album_data:
        return
    if action == "Play":
        app.on_album_card_play_clicked(album_data)
        return
    if action == "Play Next":
        _run_album_card_action(
            app,
            album_data,
            action,
            playback.play_next,
        )
        return
    if action == "Add to Queue":
        _run_album_card_action(
            app,
            album_data,
            action,
            playback.add_to_queue,
        )
        return
    if action == "Start Radio":
        _run_album_card_action(
            app,
            album_data,
            action,
            playback.play_radio,
        )
        return
    if action == "Add to Playlist":
        from ui import album_operations

        thread = threading.Thread(
            target=album_operations._album_add_to_playlist_worker,
            args=(app, album_data),
            daemon=True,
        )
        thread.start()


def on_artist_row_context_action(
    app,
    _button: Gtk.Button,
    popover: Gtk.Popover,
    action: str,
    artist_data: object,
) -> None:
    if popover:
        popover.popdown()
    if not artist_data:
        return
    if action == "View Albums":
        previous_view = _get_current_view(app)
        if previous_view == "artist-albums":
            previous_view = None
        app.show_artist_albums(artist_data, previous_view)
        return
    if action == "Start Radio":
        _start_artist_radio(app, artist_data)


def on_playlist_row_context_action(
    app,
    _button: Gtk.Button,
    popover: Gtk.Popover,
    action: str,
    playlist_data: object,
) -> None:
    if popover:
        popover.popdown()
    if not playlist_data:
        return
    if action == "Delete Playlist":
        from ui import playlist_manager

        playlist_manager.show_delete_playlist_dialog(app, playlist_data)
        return
    if action in ("Play", "Add to Queue"):
        _run_playlist_context_action(app, playlist_data, action)


def _run_album_card_action(
    app,
    album_data: object,
    action_label: str,
    action_fn,
) -> None:
    if not app.server_url:
        from ui import toast

        toast.show_toast(
            app,
            "Connect to a server to use this action.",
            is_error=True,
        )
        return
    thread = threading.Thread(
        target=_album_card_action_worker,
        args=(app, album_data, action_label, action_fn),
        daemon=True,
    )
    thread.start()


def _album_card_action_worker(
    app,
    album_data: object,
    action_label: str,
    action_fn,
) -> None:
    from ui import album_operations, toast

    error = ""
    try:
        media = album_operations._resolve_album_queue_media(app, album_data)
        preferred_player_id = (
            app.output_manager.preferred_player_id
            if app.output_manager
            else None
        )
        if action_fn is playback.play_album:
            player_id = action_fn(
                app.client_session,
                app.server_url,
                app.auth_token,
                media,
                None,
                preferred_player_id,
            )
            if player_id and app.output_manager:
                app.output_manager.preferred_player_id = player_id
            _refresh_remote_playback_state(app)
        else:
            action_fn(
                app.client_session,
                app.server_url,
                app.auth_token,
                media,
                preferred_player_id,
            )
            if action_fn is playback.play_radio:
                _refresh_remote_playback_state(app)
    except Exception as exc:
        error = str(exc)
    if error:
        GLib.idle_add(
            toast.show_toast,
            app,
            f"{action_label} failed: {error}",
            True,
        )


def _refresh_remote_playback_state(app) -> None:
    GLib.idle_add(app.refresh_remote_playback_state)


def _run_playlist_context_action(
    app,
    playlist_data: object,
    action: str,
) -> None:
    from ui import toast

    if not app.server_url:
        toast.show_toast(
            app,
            "Connect to a server to use this action.",
            is_error=True,
        )
        return
    media = _resolve_playlist_media(playlist_data)
    if not media:
        toast.show_toast(
            app,
            "Playlist source is unavailable for this action.",
            is_error=True,
        )
        return
    thread = threading.Thread(
        target=_playlist_context_action_worker,
        args=(app, action, media),
        daemon=True,
    )
    thread.start()


def _playlist_context_action_worker(
    app,
    action: str,
    media: object,
) -> None:
    from ui import toast

    error = ""
    preferred_player_id = (
        app.output_manager.preferred_player_id if app.output_manager else None
    )
    try:
        if action == "Play":
            playback.play_album(
                app.client_session,
                app.server_url,
                app.auth_token,
                media,
                None,
                preferred_player_id,
            )
            _refresh_remote_playback_state(app)
        else:
            playback.add_to_queue(
                app.client_session,
                app.server_url,
                app.auth_token,
                media,
                preferred_player_id,
            )
    except Exception as exc:
        error = str(exc)
    if error:
        GLib.idle_add(
            toast.show_toast,
            app,
            f"{action} failed: {error}",
            True,
        )


def _start_artist_radio(app, artist_data: object) -> None:
    from ui import toast

    if not app.server_url:
        toast.show_toast(
            app,
            "Connect to a server to use this action.",
            is_error=True,
        )
        return
    media = _resolve_artist_media(artist_data)
    if not media:
        toast.show_toast(
            app,
            "Artist source is unavailable for this action.",
            is_error=True,
        )
        return
    thread = threading.Thread(
        target=_artist_radio_worker,
        args=(app, media),
        daemon=True,
    )
    thread.start()


def _artist_radio_worker(app, media: object) -> None:
    from ui import toast

    error = ""
    preferred_player_id = (
        app.output_manager.preferred_player_id if app.output_manager else None
    )
    try:
        playback.play_radio(
            app.client_session,
            app.server_url,
            app.auth_token,
            media,
            preferred_player_id,
        )
        _refresh_remote_playback_state(app)
    except Exception as exc:
        error = str(exc)
    if error:
        GLib.idle_add(
            toast.show_toast,
            app,
            f"Start Radio failed: {error}",
            True,
        )


def _resolve_playlist_media(playlist_data: object) -> object | None:
    if isinstance(playlist_data, dict):
        uri = playlist_data.get("uri")
        if isinstance(uri, str):
            uri = uri.strip()
        if uri:
            return uri
        item_id = playlist_data.get("item_id") or playlist_data.get("id")
        provider = (
            playlist_data.get("provider")
            or playlist_data.get("provider_instance")
            or playlist_data.get("provider_domain")
        )
    else:
        uri = getattr(playlist_data, "uri", None)
        if isinstance(uri, str):
            uri = uri.strip()
        if uri:
            return uri
        item_id = getattr(playlist_data, "item_id", None) or getattr(
            playlist_data, "id", None
        )
        provider = (
            getattr(playlist_data, "provider", None)
            or getattr(playlist_data, "provider_instance", None)
            or getattr(playlist_data, "provider_domain", None)
        )
    if item_id and provider:
        return {
            "item_id": item_id,
            "provider": provider,
        }
    return None


def _resolve_artist_media(artist_data: object) -> object | None:
    if isinstance(artist_data, dict):
        uri = artist_data.get("uri")
        if isinstance(uri, str):
            uri = uri.strip()
        if uri:
            return uri
        item_id = artist_data.get("item_id") or artist_data.get("id")
        provider = (
            artist_data.get("provider")
            or artist_data.get("provider_instance")
            or artist_data.get("provider_domain")
        )
    else:
        uri = getattr(artist_data, "uri", None)
        if isinstance(uri, str):
            uri = uri.strip()
        if uri:
            return uri
        item_id = getattr(artist_data, "item_id", None) or getattr(
            artist_data, "id", None
        )
        provider = (
            getattr(artist_data, "provider", None)
            or getattr(artist_data, "provider_instance", None)
            or getattr(artist_data, "provider_domain", None)
        )
    if item_id and provider:
        return {
            "item_id": item_id,
            "provider": provider,
        }
    return None


def _show_now_playing_album(app) -> None:
    album = _resolve_now_playing_album(app)
    if not album:
        return
    album = _hydrate_now_playing_album(app, album)
    previous_view = _get_current_view(app)
    if previous_view and previous_view != "album-detail":
        app.album_detail_previous_view = previous_view
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def _show_track_album_detail(app, track: object) -> None:
    source = getattr(track, "source", None)
    album = _extract_album_from_source(source)
    if album:
        matched = _match_album_in_library(app, album)
        if matched:
            album = matched
        elif isinstance(album, dict) and not _album_has_identity(album):
            album_name = album.get("name")
            if not album_name:
                album_name = getattr(track, "album", None)
            artist_name = _resolve_artist_name_from_track(
                source,
                getattr(track, "artist", None),
            )
            matched = _match_album_by_name(app, album_name, artist_name)
            if matched:
                album = matched
    else:
        album = _match_album_by_name(
            app,
            getattr(track, "album", None),
            getattr(track, "artist", None),
        )
    if not album:
        return
    previous_view = _get_current_view(app)
    if previous_view and previous_view != "album-detail":
        app.album_detail_previous_view = previous_view
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def _resolve_now_playing_album(app):
    track_info = app.playback_track_info or {}
    source = track_info.get("source")
    album = _extract_album_from_source(source)
    if album:
        matched = _match_album_in_library(app, album)
        if matched:
            return matched
        if isinstance(album, dict) and not _album_has_identity(album):
            name = album.get("name")
            artist = _resolve_artist_name_from_track(source, track_info.get("artist"))
            matched = _match_album_by_name(app, name, artist)
            if matched:
                return matched
        return album
    playback_album = getattr(app, "playback_album", None)
    if _is_album_like(playback_album):
        return playback_album
    return None


def _build_now_playing_track_action_item(app) -> object | None:
    track_info = app.playback_track_info or {}
    if not track_info:
        return None
    source = track_info.get("source")
    source_uri = track_info.get("source_uri")
    uri = None
    if source is not None:
        if isinstance(source, dict):
            uri = source.get("uri") or source_uri
        else:
            uri = getattr(source, "uri", None) or source_uri
    else:
        uri = source_uri
    if source is not None and not isinstance(source, dict) and getattr(
        source, "uri", None
    ):
        source_obj = source
    else:
        source_obj = SimpleNamespace(uri=uri)
    return SimpleNamespace(
        title=track_info.get("title") or "Unknown Track",
        artist=track_info.get("artist") or "Unknown Artist",
        album=track_info.get("album") or "",
        length_seconds=track_info.get("length_seconds") or 0,
        source=source_obj,
    )


def _hydrate_now_playing_album(app, album: object) -> object:
    track_info = app.playback_track_info or {}
    source = track_info.get("source")
    payload = _coerce_album_payload(album)
    if payload is None:
        return album
    if not payload.get("name"):
        album_name = track_info.get("album")
        if isinstance(album_name, str):
            album_name = album_name.strip()
        if album_name:
            payload["name"] = album_name
    if not payload.get("artists"):
        artist_name = _resolve_artist_name_from_track(
            source, track_info.get("artist")
        )
        if artist_name:
            payload["artists"] = [artist_name]
    if not image_loader.extract_album_image_url(payload, app.server_url):
        image_url = track_info.get("image_url")
        if isinstance(image_url, str):
            image_url = image_url.strip() or None
        else:
            image_url = None
        if not image_url and source:
            image_url = image_loader.extract_media_image_url(
                source, app.server_url
            )
        if not image_url:
            playback_album = getattr(app, "playback_album", None)
            if playback_album:
                image_url = image_loader.extract_media_image_url(
                    playback_album, app.server_url
                )
        if image_url:
            payload["image_url"] = image_url
    return payload


def _coerce_album_payload(album: object) -> dict | None:
    if album is None:
        return None
    if isinstance(album, dict):
        return dict(album)
    payload: dict = {}
    name = getattr(album, "name", None)
    if isinstance(name, str):
        name = name.strip() or None
    if name:
        payload["name"] = name
    item_id = getattr(album, "item_id", None) or getattr(album, "id", None)
    if item_id is not None:
        payload["item_id"] = item_id
    provider = (
        getattr(album, "provider", None)
        or getattr(album, "provider_instance", None)
        or getattr(album, "provider_domain", None)
    )
    if isinstance(provider, str):
        provider = provider.strip() or None
    if provider:
        payload["provider"] = provider
    uri = getattr(album, "uri", None)
    if isinstance(uri, str):
        uri = uri.strip() or None
    if uri:
        payload["uri"] = uri
    album_type = getattr(album, "album_type", None)
    if album_type is not None:
        payload["album_type"] = getattr(album_type, "value", album_type)
    mappings = getattr(album, "provider_mappings", None) or []
    if mappings:
        payload["provider_mappings"] = _serialize_provider_mappings(mappings)
    artist_names = _collect_artist_names(getattr(album, "artists", None))
    if artist_names:
        payload["artists"] = artist_names
    return payload


def _serialize_provider_mappings(mappings: object) -> list[dict]:
    if isinstance(mappings, dict):
        mappings = [mappings]
    elif not isinstance(mappings, (list, tuple, set)):
        mappings = [mappings]
    serialized = []
    for mapping in mappings:
        if isinstance(mapping, dict):
            serialized.append(dict(mapping))
            continue
        serialized.append(
            {
                "item_id": getattr(mapping, "item_id", None),
                "provider_instance": getattr(mapping, "provider_instance", None),
                "provider_domain": getattr(mapping, "provider_domain", None),
                "available": getattr(mapping, "available", True),
            }
        )
    return serialized


def _collect_artist_names(artists: object) -> list[str]:
    if not artists:
        return []
    if isinstance(artists, str):
        cleaned = artists.strip()
        return [cleaned] if cleaned else []
    if not isinstance(artists, (list, tuple, set)):
        artists = [artists]
    names: list[str] = []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or artist.get("sort_name")
        else:
            name = getattr(artist, "name", None) or getattr(
                artist, "sort_name", None
            )
            if name is None:
                name = str(artist)
        if name:
            names.append(str(name).strip())
    return names


def _resolve_now_playing_artist_name(app) -> str | None:
    track_info = app.playback_track_info or {}
    source = track_info.get("source")
    name = _resolve_artist_name_from_track(source, track_info.get("artist"))
    return name or None


def _resolve_artist_name_from_track(
    source: object | None, fallback_label: str | None
) -> str:
    name = _extract_artist_name_from_source(source)
    if name:
        return name
    return _normalize_artist_label(fallback_label)


def _extract_album_from_source(source: object | None):
    if not source:
        return None
    if isinstance(source, dict):
        album = source.get("album")
        if album is not None and not isinstance(album, str):
            return album
        album_name = album.strip() if isinstance(album, str) else ""
        item_id = source.get("album_item_id") or source.get("album_id")
        provider = source.get("album_provider") or source.get("provider")
        if item_id and provider:
            return _build_album_stub(item_id, provider, album_name or None)
        if album_name:
            return {"name": album_name}
        return None
    album = getattr(source, "album", None)
    if album is not None and not isinstance(album, str):
        return album
    album_name = album.strip() if isinstance(album, str) else ""
    item_id = getattr(source, "album_item_id", None) or getattr(
        source, "album_id", None
    )
    provider = getattr(source, "album_provider", None) or getattr(
        source, "provider", None
    )
    if item_id and provider:
        return _build_album_stub(item_id, provider, album_name or None)
    if album_name:
        return {"name": album_name}
    return None


def _build_album_stub(
    item_id: str | int, provider: str, name: str | None
) -> dict:
    payload = {"item_id": item_id, "provider": provider}
    if name:
        payload["name"] = name
    return payload


def _extract_artist_name_from_source(source: object | None) -> str:
    if not source:
        return ""
    if isinstance(source, dict):
        name = _pick_artist_name(source.get("artists"))
        if name:
            return name
        for key in ("artist", "artist_str"):
            value = source.get(key)
            if value:
                return str(value).strip()
        return ""
    name = _pick_artist_name(getattr(source, "artists", None))
    if name:
        return name
    for attr in ("artist", "artist_str"):
        value = getattr(source, attr, None)
        if value:
            return str(value).strip()
    return ""


def _pick_artist_name(artists: object) -> str:
    if not artists:
        return ""
    if isinstance(artists, str):
        return artists.strip()
    if not isinstance(artists, (list, tuple, set)):
        artists = [artists]
    for artist in artists:
        name = None
        if isinstance(artist, dict):
            name = artist.get("name") or artist.get("sort_name")
        else:
            name = getattr(artist, "name", None) or getattr(
                artist, "sort_name", None
            )
            if not name:
                name = str(artist)
        if name:
            return str(name).strip()
    return ""


def _match_album_in_library(app, album) -> object | None:
    for candidate in app.library_albums or []:
        if app.is_same_album(album, candidate):
            return candidate
    return None


def _match_album_by_name(
    app, album_name: str | None, artist_name: str | None
) -> object | None:
    if not album_name:
        return None
    normalized_album = album_name.strip().casefold()
    if not normalized_album:
        return None
    normalized_artist = _normalize_name(artist_name)
    for album in app.library_albums or []:
        if not isinstance(album, dict):
            continue
        candidate = (album.get("name") or "").strip()
        if not candidate or candidate.casefold() != normalized_album:
            continue
        if not normalized_artist:
            return album
        if _album_has_artist(album, normalized_artist):
            return album
    return None


def _album_has_artist(album: dict, normalized_artist: str) -> bool:
    artists = album.get("artists") or []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or artist.get("sort_name")
        else:
            name = str(artist)
        if _normalize_name(name) == normalized_artist:
            return True
    return False


def _album_has_identity(album: object) -> bool:
    if isinstance(album, dict):
        return bool(album.get("item_id") or album.get("id") or album.get("uri"))
    return bool(
        getattr(album, "item_id", None)
        or getattr(album, "id", None)
        or getattr(album, "uri", None)
    )


def _normalize_artist_label(label: str | None) -> str:
    if not label:
        return ""
    text = str(label).strip()
    if not text:
        return ""
    if " +" in text:
        text = text.split(" +", 1)[0]
    if "," in text:
        text = text.split(",", 1)[0]
    return text.strip()


def _normalize_name(value: str | None) -> str:
    return (value or "").strip().casefold()


def _is_album_like(item: object) -> bool:
    if not item:
        return False
    if isinstance(item, dict):
        if item.get("is_search") or item.get("is_editable") or item.get("owner"):
            return False
        return bool(
            item.get("album_type")
            or item.get("artists")
            or item.get("provider_mappings")
            or item.get("is_sample")
        )
    return bool(
        getattr(item, "album_type", None)
        or getattr(item, "artists", None)
        or getattr(item, "provider_mappings", None)
    )


def _get_current_view(app) -> str | None:
    if not app.main_stack:
        return None
    try:
        return app.main_stack.get_visible_child_name()
    except Exception:
        return None
