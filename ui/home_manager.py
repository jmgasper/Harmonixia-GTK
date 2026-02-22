"""Home section refresh and data loading helpers."""

import threading

from gi.repository import GLib, Gtk

from constants import HOME_ALBUM_ART_SIZE, HOME_LIST_LIMIT
from music_assistant import library
from music_assistant_client import MusicAssistantClient
from music_assistant_models.enums import MediaType
from ui import album_grid, home_section, image_loader, track_utils, ui_utils
from ui.widgets.track_row import TrackRow


def refresh_home_sections(app) -> None:
    app.refresh_home_recently_played()
    app.refresh_home_recently_played_tracks()
    app.refresh_home_recently_added()
    app.refresh_home_recommendations()


def clear_home_recent_lists(app) -> None:
    app.home_recently_played_loading = False
    app.home_recently_played_tracks_loading = False
    app.home_recently_added_loading = False
    app.home_recommendations_loading = False
    if app.home_recently_played_refresh_id is not None:
        GLib.source_remove(app.home_recently_played_refresh_id)
        app.home_recently_played_refresh_id = None
    home_section.populate_home_album_list(app, app.home_recently_played_list, [])
    _populate_home_recent_tracks(app, [])
    home_section.populate_home_album_list(app, app.home_recently_added_list, [])
    home_section.populate_home_recommendations(app, [])
    home_section.update_home_status(app.home_recently_played_status, [])
    home_section.update_home_status(app.home_recent_tracks_status, [])
    home_section.update_home_status(app.home_recently_added_status, [])
    home_section.update_home_status(app.home_recommendations_status, [])


def schedule_home_recently_played_refresh(app, delay_ms: int = 1200) -> None:
    if app.home_recently_played_refresh_id is not None:
        return
    app.home_recently_played_refresh_id = GLib.timeout_add(
        delay_ms, app._handle_home_recently_played_refresh
    )


def _handle_home_recently_played_refresh(app) -> bool:
    app.home_recently_played_refresh_id = None
    app.refresh_home_recently_played()
    return False


def refresh_home_recently_played(app) -> None:
    if not app.server_url:
        home_section.populate_home_album_list(
            app, app.home_recently_played_list, []
        )
        home_section.set_home_status(
            app.home_recently_played_status,
            "Connect to your Music Assistant server to load recently played.",
        )
        return
    if app.home_recently_played_loading:
        return
    app.home_recently_played_loading = True
    home_section.set_home_status(
        app.home_recently_played_status, "Loading recently played..."
    )
    thread = threading.Thread(
        target=app._load_recently_played_worker,
        daemon=True,
    )
    thread.start()


def refresh_home_recently_played_tracks(app) -> None:
    if not getattr(app, "home_recent_tracks_store", None):
        return
    if not app.server_url:
        _populate_home_recent_tracks(app, [])
        home_section.set_home_status(
            app.home_recent_tracks_status,
            "Connect to your Music Assistant server to load recently played tracks.",
        )
        return
    if getattr(app, "home_recently_played_tracks_loading", False):
        return
    app.home_recently_played_tracks_loading = True
    home_section.set_home_status(
        app.home_recent_tracks_status,
        "Loading recently played tracks...",
    )
    thread = threading.Thread(
        target=app._load_recently_played_tracks_worker,
        daemon=True,
    )
    thread.start()


def refresh_home_recently_added(app) -> None:
    if not app.server_url:
        home_section.populate_home_album_list(
            app, app.home_recently_added_list, []
        )
        home_section.set_home_status(
            app.home_recently_added_status,
            "Connect to your Music Assistant server to load recently added albums.",
        )
        return
    if app.home_recently_added_loading:
        return
    app.home_recently_added_loading = True
    home_section.set_home_status(
        app.home_recently_added_status,
        "Loading recently added albums...",
    )
    thread = threading.Thread(
        target=app._load_recently_added_worker,
        daemon=True,
    )
    thread.start()


def refresh_home_recommendations(app) -> None:
    if not app.home_recommendations_box:
        return
    if not app.server_url:
        home_section.populate_home_recommendations(app, [])
        home_section.set_home_status(
            app.home_recommendations_status,
            "Connect to your Music Assistant server to load recommendations.",
        )
        return
    if app.home_recommendations_loading:
        return
    app.home_recommendations_loading = True
    home_section.set_home_status(
        app.home_recommendations_status,
        "Loading recommendations...",
    )
    thread = threading.Thread(
        target=app._load_recommendations_worker,
        daemon=True,
    )
    thread.start()


def _load_recently_played_worker(app) -> None:
    error = ""
    albums: list[dict] = []
    try:
        albums = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_recently_played_albums_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_recently_played_loaded, albums, error)


def _load_recently_played_tracks_worker(app) -> None:
    error = ""
    tracks: list[dict] = []
    try:
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_recently_played_tracks_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_recently_played_tracks_loaded, tracks, error)


def _load_recently_added_worker(app) -> None:
    error = ""
    albums: list[dict] = []
    try:
        albums = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_recently_added_albums_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_recently_added_loaded, albums, error)


def _load_recommendations_worker(app) -> None:
    error = ""
    sections: list[dict] = []
    try:
        sections = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_home_recommendations_async,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_recommendations_loaded, sections, error)


def on_recently_played_loaded(app, albums: list[dict], error: str) -> None:
    app.home_recently_played_loading = False
    if error:
        home_section.populate_home_album_list(
            app, app.home_recently_played_list, []
        )
        home_section.set_home_status(
            app.home_recently_played_status,
            f"Unable to load recently played: {error}",
        )
        return
    home_section.populate_home_album_list(
        app, app.home_recently_played_list, albums
    )
    home_section.update_home_status(app.home_recently_played_status, albums)


def on_recently_played_tracks_loaded(
    app,
    tracks: list[dict],
    error: str,
) -> None:
    app.home_recently_played_tracks_loading = False
    if error:
        _populate_home_recent_tracks(app, [])
        home_section.set_home_status(
            app.home_recent_tracks_status,
            f"Unable to load recently played tracks: {error}",
        )
        return
    _populate_home_recent_tracks(app, tracks)
    home_section.update_home_status(app.home_recent_tracks_status, tracks)


def on_recently_added_loaded(app, albums: list[dict], error: str) -> None:
    app.home_recently_added_loading = False
    if error:
        home_section.populate_home_album_list(
            app, app.home_recently_added_list, []
        )
        home_section.set_home_status(
            app.home_recently_added_status,
            f"Unable to load recently added albums: {error}",
        )
        return
    home_section.populate_home_album_list(
        app, app.home_recently_added_list, albums
    )
    home_section.update_home_status(app.home_recently_added_status, albums)


def on_recommendations_loaded(
    app, sections: list[dict], error: str
) -> None:
    app.home_recommendations_loading = False
    if error:
        home_section.populate_home_recommendations(app, [])
        home_section.set_home_status(
            app.home_recommendations_status,
            f"Unable to load recommendations: {error}",
        )
        return
    home_section.populate_home_recommendations(app, sections)
    home_section.update_home_status(app.home_recommendations_status, sections)


def ensure_home_artwork(app) -> None:
    flows = [
        app.home_recently_played_list,
        app.home_recently_added_list,
    ]
    flows.extend(getattr(app, "home_recommendation_flows", []) or [])
    for flow in flows:
        _ensure_flow_artwork(app, flow)


def _ensure_flow_artwork(app, flow: Gtk.FlowBox | None) -> None:
    if flow is None:
        return
    art_size = getattr(flow, "home_art_size", HOME_ALBUM_ART_SIZE)
    child = flow.get_first_child()
    while child:
        album = getattr(child, "album_data", None)
        recommendation = getattr(child, "recommendation_item", None)
        card = child.get_child()
        art = card.get_first_child() if card else None
        if isinstance(art, Gtk.Picture) and art.get_paintable() is None:
            image_url = None
            if album:
                image_url = image_loader.extract_album_image_url(
                    album,
                    app.server_url,
                )
            elif isinstance(recommendation, dict):
                image_url = recommendation.get("image_url")
                if not image_url:
                    payload = recommendation.get("payload")
                    image_url = image_loader.extract_media_image_url(
                        payload,
                        app.server_url,
                    )
            if image_url:
                image_loader.load_album_art_async(
                    art,
                    image_url,
                    art_size,
                    app.auth_token,
                    app.image_executor,
                    app.get_cache_dir(),
                )
        child = child.get_next_sibling()


async def _fetch_recently_played_albums_async(
    app, client: MusicAssistantClient
) -> list[dict]:
    items = await client.music.recently_played(
        limit=HOME_LIST_LIMIT,
        media_types=[MediaType.ALBUM],
    )
    albums: list[dict] = []
    for item in items:
        data = library._serialize_album(client, item)
        if not data.get("image_url") and not data.get("artists"):
            item_id, provider = _get_album_identity(item)
            if item_id and provider:
                try:
                    item = await client.music.get_album(item_id, provider)
                except Exception:
                    item = None
                if item is not None:
                    data = library._serialize_album(client, item)
        albums.append(data)
        if len(albums) >= HOME_LIST_LIMIT:
            break
    return albums


async def _fetch_recently_played_tracks_async(
    app,
    client: MusicAssistantClient,
) -> list[dict]:
    items = await client.music.recently_played(
        limit=HOME_LIST_LIMIT,
        media_types=[MediaType.TRACK],
    )
    describe_quality = lambda item: track_utils.describe_track_quality(
        item,
        track_utils.format_sample_rate,
    )
    tracks: list[dict] = []
    for index, item in enumerate(items or [], start=1):
        payload = track_utils.serialize_track(
            item,
            _get_recent_track_album_name(item),
            ui_utils.format_artist_names,
            track_utils.format_duration,
            describe_quality,
        )
        payload["track_number"] = index
        image_url = image_loader.resolve_media_item_image_url(
            client,
            item,
            app.server_url,
        )
        if image_url:
            payload["image_url"] = image_url
        tracks.append(payload)
        if len(tracks) >= HOME_LIST_LIMIT:
            break
    return tracks


async def _fetch_recently_added_albums_async(
    app, client: MusicAssistantClient
) -> list[dict]:
    albums = await client.music.get_library_albums(
        limit=HOME_LIST_LIMIT,
        offset=0,
        order_by="timestamp_added_desc",
    )
    serialized: list[dict] = []
    missing_ids: list[tuple[int, str, str]] = []
    for index, album in enumerate(albums):
        data = library._serialize_album(client, album)
        if not data.get("artists"):
            item_id, provider = _get_album_identity(album)
            if item_id and provider:
                missing_ids.append((index, item_id, provider))
        serialized.append(data)
    if missing_ids:
        for index, item_id, provider in missing_ids:
            try:
                result = await client.music.get_album(item_id, provider)
            except Exception:
                continue
            serialized[index] = library._serialize_album(client, result)
    return serialized


def _get_album_identity(album: object) -> tuple[str | None, str | None]:
    if isinstance(album, dict):
        return (
            album.get("item_id") or album.get("id"),
            album.get("provider")
            or album.get("provider_instance")
            or album.get("provider_domain"),
        )
    return (
        getattr(album, "item_id", None) or getattr(album, "id", None),
        getattr(album, "provider", None)
        or getattr(album, "provider_instance", None)
        or getattr(album, "provider_domain", None),
    )


async def _fetch_home_recommendations_async(
    app, client: MusicAssistantClient
) -> list[dict]:
    folders = await client.music.recommendations()
    sections: list[dict] = []
    for folder in folders or []:
        title = getattr(folder, "name", None) or "Recommendations"
        items: list[dict] = []
        for item in getattr(folder, "items", []) or []:
            normalized = await _normalize_recommendation_item(client, item)
            if normalized:
                items.append(normalized)
        sections.append(
            {
                "title": title,
                "items": items,
            }
        )
    return sections


async def _normalize_recommendation_item(
    client: MusicAssistantClient, item: object
) -> dict | None:
    media_type_value = _get_media_type_value(item)
    if media_type_value == MediaType.FOLDER.value:
        return None
    item = await _ensure_full_media_item(client, item)
    media_type_value = _get_media_type_value(item)
    if media_type_value == MediaType.ALBUM.value:
        album_data = library._serialize_album(client, item)
        title = album_data.get("name") or "Unknown Album"
        subtitle = ui_utils.format_artist_names(
            album_data.get("artists") or []
        )
        image_url = album_data.get("image_url")
        if not image_url:
            image_url = _get_item_image_url(client, item)
            if image_url:
                album_data["image_url"] = image_url
        return {
            "media_type": MediaType.ALBUM.value,
            "title": title,
            "subtitle": subtitle,
            "image_url": image_url,
            "payload": album_data,
        }
    if media_type_value == MediaType.PLAYLIST.value:
        playlist_data = library._serialize_playlist(item)
        title = playlist_data.get("name") or "Untitled Playlist"
        subtitle = playlist_data.get("owner") or ""
        image_url = _get_item_image_url(client, item)
        if image_url:
            playlist_data["image_url"] = image_url
        return {
            "media_type": MediaType.PLAYLIST.value,
            "title": title,
            "subtitle": subtitle,
            "image_url": image_url,
            "payload": playlist_data,
        }
    if media_type_value == MediaType.ARTIST.value:
        name = _get_item_name(item) or "Unknown Artist"
        image_url = _get_item_image_url(client, item)
        return {
            "media_type": MediaType.ARTIST.value,
            "title": name,
            "subtitle": "",
            "image_url": image_url,
            "payload": {"name": name},
        }
    if media_type_value == MediaType.TRACK.value:
        title = _get_item_name(item) or "Unknown Track"
        artist_label = getattr(item, "artist_str", None)
        if not artist_label:
            artist_label = ui_utils.format_artist_names(
                _extract_artist_names(item)
            )
        image_url = _get_item_image_url(client, item)
        payload = {
            "title": title,
            "artist": artist_label,
            "source": item,
            "source_uri": getattr(item, "uri", None),
        }
        return {
            "media_type": MediaType.TRACK.value,
            "title": title,
            "subtitle": artist_label,
            "image_url": image_url,
            "payload": payload,
        }
    title = _get_item_name(item) or "Recommendation"
    subtitle = (
        media_type_value.replace("_", " ").title()
        if media_type_value
        else ""
    )
    image_url = _get_item_image_url(client, item)
    return {
        "media_type": media_type_value or "item",
        "title": title,
        "subtitle": subtitle,
        "image_url": image_url,
        "payload": item,
    }


async def _ensure_full_media_item(
    client: MusicAssistantClient, item: object
) -> object:
    if isinstance(item, dict):
        return item
    if getattr(item, "provider_mappings", None):
        return item
    media_type = _coerce_media_type(getattr(item, "media_type", None))
    if not media_type or media_type == MediaType.FOLDER:
        return item
    item_id = getattr(item, "item_id", None)
    provider = getattr(item, "provider", None)
    if not item_id or not provider:
        return item
    try:
        return await client.music.get_item(media_type, item_id, provider)
    except Exception:
        return item


def _get_media_type_value(item: object) -> str:
    if isinstance(item, dict):
        value = item.get("media_type")
    else:
        value = getattr(item, "media_type", None)
    if isinstance(value, MediaType):
        return value.value
    if isinstance(value, str):
        return value
    return ""


def _coerce_media_type(value: object) -> MediaType | None:
    if isinstance(value, MediaType):
        return value
    if isinstance(value, str):
        try:
            return MediaType(value)
        except Exception:
            return None
    return None


def _get_item_image_url(
    client: MusicAssistantClient, item: object
) -> str | None:
    try:
        return client.get_media_item_image_url(item)
    except Exception:
        return None


def _get_item_name(item: object) -> str | None:
    if isinstance(item, dict):
        name = item.get("name") or item.get("sort_name")
    else:
        name = getattr(item, "name", None) or getattr(item, "sort_name", None)
    return name


def _extract_artist_names(item: object) -> list[str]:
    if isinstance(item, dict):
        artists = item.get("artists") or []
    else:
        artists = getattr(item, "artists", None) or []
    names: list[str] = []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name") or artist.get("sort_name")
        else:
            name = getattr(artist, "name", None) or getattr(
                artist, "sort_name", None
            )
        if name:
            names.append(str(name))
    return names


def _populate_home_recent_tracks(app, tracks: list[dict]) -> None:
    store = getattr(app, "home_recent_tracks_store", None)
    if store is None:
        return
    store.remove_all()
    for track in tracks:
        row = TrackRow(
            track_number=track.get("track_number", 0),
            title=track.get("title", ""),
            length_display=track.get("length_display", ""),
            length_seconds=track.get("length_seconds", 0),
            artist=track.get("artist", ""),
            album=track.get("album", ""),
            quality=track.get("quality", ""),
            is_favorite=bool(track.get("is_favorite", False)),
        )
        row.source = track.get("source")
        image_url = track.get("image_url")
        if image_url:
            row.image_url = image_url
        store.append(row)
    if getattr(app, "home_recent_tracks_view", None) and getattr(
        app,
        "home_recent_tracks_selection",
        None,
    ):
        app.home_recent_tracks_view.set_model(app.home_recent_tracks_selection)


def _get_recent_track_album_name(track: object) -> str:
    album = getattr(track, "album", None)
    if isinstance(album, dict):
        return album.get("name") or ""
    if album is not None:
        return getattr(album, "name", None) or ""
    return ""


def on_main_stack_visible_child_changed(app, stack, _param) -> None:
    try:
        visible = stack.get_visible_child_name()
    except Exception:
        return
    if visible == "home":
        ensure_home_artwork(app)
    elif visible == "albums":
        album_grid.ensure_album_grid_artwork(app)
    elif visible == "favorites":
        app.load_favorites()
    elif visible == "queue":
        app.refresh_queue_panel()


def clear_home_album_selection(app) -> None:
    flows = [
        app.home_recently_played_list,
        app.home_recently_added_list,
    ]
    flows.extend(getattr(app, "home_recommendation_flows", []) or [])
    for flow in flows:
        if flow is not None:
            flow.unselect_all()
