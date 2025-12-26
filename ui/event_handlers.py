"""UI event handlers for MusicApp."""

import logging

from gi.repository import GLib, Gtk

from music_assistant_models.enums import PlaybackState


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
    if action == "Remove from this playlist":
        if track:
            from ui import playlist_operations

            playlist_operations.remove_track_from_playlist(app, track)
        return
    if action == "Add to existing playlist":
        from ui import playlist_manager

        playlist_manager.show_add_to_playlist_dialog(app, track)


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
    if not app.playback_track_info:
        return
    if app.playback_state == PlaybackState.PLAYING:
        app.set_playback_state(PlaybackState.PAUSED)
        app.send_playback_command("pause")
    else:
        app.set_playback_state(PlaybackState.PLAYING)
        app.send_playback_command("resume")


def on_previous_clicked(app, _button) -> None:
    app.handle_previous_action()


def on_next_clicked(app, _button) -> None:
    app.handle_next_action()


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


def on_now_playing_art_clicked(
    app, _gesture, _n_press: int, _x: float, _y: float
) -> None:
    _show_now_playing_album(app)


def _show_now_playing_album(app) -> None:
    album = _resolve_now_playing_album(app)
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
