import threading

from gi.repository import GLib, Gtk

from constants import DEFAULT_PAGE_SIZE, DETAIL_ART_SIZE, MEDIA_TILE_SIZE
from music_assistant import library, playback
from music_assistant_client import MusicAssistantClient
from music_assistant_models.enums import MediaType
from ui import image_loader, toast, ui_utils
from ui import track_utils
from ui.widgets import album_card
from ui.widgets.track_row import TrackRow


def on_artist_row_activated(
    app,
    listbox: Gtk.ListBox,
    row: Gtk.ListBoxRow | None,
) -> None:
    if not row:
        return
    artist = getattr(row, "artist_data", None)
    if not artist:
        return
    previous_view = None
    if listbox is app.search_artists_list:
        previous_view = "search"
    elif listbox is app.artists_list:
        previous_view = "artists"
    elif app.main_stack:
        try:
            previous_view = app.main_stack.get_visible_child_name()
        except Exception:
            previous_view = None
    app.show_artist_albums(artist, previous_view)


def show_artist_albums(
    app,
    artist: object,
    previous_view: str | None = None,
) -> None:
    artist = _resolve_artist_reference(app, artist)
    app.current_artist = artist
    if previous_view:
        app.artist_albums_previous_view = previous_view
    elif not getattr(app, "artist_albums_previous_view", None):
        app.artist_albums_previous_view = "artists"
    refresh_artist_albums(app)
    if app.main_stack:
        app.main_stack.set_visible_child_name("artist-albums")


def _resolve_artist_reference(app, artist: object) -> object:
    if isinstance(artist, dict) or not isinstance(artist, str):
        return artist
    name = _normalize_text(artist)
    if not name:
        return artist
    normalized_name = normalize_artist_name(name)
    candidates = getattr(app, "library_artists", None) or []
    best_match = None
    best_score = -1
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_name = normalize_artist_name(get_artist_name(candidate))
        if candidate_name != normalized_name:
            continue
        score = 0
        if _get_artist_item_id(candidate):
            score += 2
        if _get_artist_provider(candidate):
            score += 2
        if candidate.get("provider_mappings"):
            score += 1
        if candidate.get("image_url"):
            score += 1
        if score > best_score:
            best_match = candidate
            best_score = score
    return best_match if best_match is not None else name


def refresh_artist_albums(app) -> None:
    artist = getattr(app, "current_artist", None)
    if not artist:
        return
    _update_artist_playback_controls(app, artist)
    artist_name = get_artist_name(artist)
    library_albums = filter_artist_albums(app, artist_name)
    update_artist_albums_header(app, artist_name, len(library_albums))
    populate_artist_album_flow(app, library_albums)
    update_artist_albums_status(app, artist_name, library_albums)
    _start_artist_all_albums_refresh(app, artist, library_albums)
    _start_artist_top_tracks_refresh(app, artist)
    _start_artist_bio_refresh(app, artist)


def update_artist_albums_header(
    app,
    artist_name: str,
    library_album_count: int,
    all_album_count: int | None = None,
) -> None:
    if app.artist_albums_title:
        app.artist_albums_title.set_label(artist_name)
    if app.artist_albums_header:
        app.artist_albums_header.set_label(f"My Albums ({library_album_count})")
    all_header = getattr(app, "artist_all_albums_header", None)
    if all_header:
        if all_album_count is None:
            all_header.set_label("All Albums")
        else:
            all_header.set_label(f"All Albums ({all_album_count})")


def update_artist_albums_status(
    app,
    artist_name: str,
    albums: list[dict],
) -> None:
    if not app.artist_albums_status_label:
        return
    message = ""
    if not artist_name:
        message = "Select an artist to view albums."
    elif app.library_loading and not app.library_albums:
        message = "Loading library..."
    elif not albums:
        message = (
            f"No albums in your library for {artist_name}."
            " All available albums are shown below."
        )
    app.artist_albums_status_label.set_label(message)
    app.artist_albums_status_label.set_visible(bool(message))


def _set_artist_all_albums_status(app, message: str) -> None:
    status_label = getattr(app, "artist_all_albums_status_label", None)
    if not status_label:
        return
    status_label.set_label(message)
    status_label.set_visible(bool(message))


def populate_artist_album_flow(
    app,
    albums: list[dict],
    target_flow: Gtk.FlowBox | None = None,
) -> None:
    flow = target_flow if target_flow is not None else app.artist_albums_flow
    if not flow:
        return
    ui_utils.clear_container(flow)
    for album in albums:
        if not isinstance(album, dict):
            continue
        title = app.get_album_name(album)
        artist_label = ui_utils.format_artist_names(album.get("artists") or [])
        image_url = image_loader.extract_album_image_url(album, app.server_url)
        card = album_card.make_album_card(
            app,
            title,
            artist_label,
            image_url,
            art_size=MEDIA_TILE_SIZE,
            album_data=album,
        )
        _append_artist_album_metadata(card, album)
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(MEDIA_TILE_SIZE, -1)
        child.album_data = album
        flow.append(child)


def _start_artist_all_albums_refresh(
    app,
    artist: object,
    library_albums: list[dict],
) -> None:
    all_flow = getattr(app, "artist_all_albums_flow", None)
    if not all_flow:
        return
    if not app.server_url:
        all_albums = _dedupe_artist_albums(library_albums)
        populate_artist_album_flow(app, all_albums, all_flow)
        update_artist_albums_header(
            app,
            get_artist_name(artist),
            len(library_albums),
            len(all_albums),
        )
        _set_artist_all_albums_status(
            app,
            "Connect to a server to load albums across all providers.",
        )
        return
    ui_utils.clear_container(all_flow)
    _set_artist_all_albums_status(app, "Loading all albums across providers...")
    thread = threading.Thread(
        target=_load_artist_all_albums_worker,
        args=(app, artist),
        daemon=True,
    )
    thread.start()


def _load_artist_all_albums_worker(
    app,
    artist: object,
) -> None:
    error = ""
    albums: list[dict] = []
    try:
        albums = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_artist_all_albums_async,
            artist,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_artist_all_albums_loaded, artist, albums, error)


def _artist_identity(artist: object | None) -> tuple[str, str] | str:
    if artist is None:
        return ""
    item_id = _get_artist_item_id(artist)
    provider = _get_artist_provider(artist)
    if item_id and provider:
        return (item_id.casefold(), provider.casefold())
    return normalize_artist_name(get_artist_name(artist))


def on_artist_all_albums_loaded(
    app,
    artist: object,
    albums: list[dict],
    error: str,
) -> None:
    current_artist = getattr(app, "current_artist", None)
    if _artist_identity(artist) != _artist_identity(current_artist):
        return
    artist_name = get_artist_name(current_artist)
    library_albums = filter_artist_albums(app, artist_name)
    all_albums = _dedupe_artist_albums(albums)
    if not all_albums:
        all_albums = _dedupe_artist_albums(library_albums)
    populate_artist_album_flow(
        app,
        all_albums,
        getattr(app, "artist_all_albums_flow", None),
    )
    update_artist_albums_header(
        app,
        artist_name,
        len(library_albums),
        len(all_albums),
    )
    message = ""
    if error and not all_albums:
        message = f"Could not load all provider albums: {error}"
    elif error:
        message = "Showing available albums; full provider catalog could not be loaded."
    elif not all_albums:
        message = f"No albums available for {artist_name}."
    _set_artist_all_albums_status(app, message)


def on_artist_album_activated(
    app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild
) -> None:
    album = getattr(child, "album_data", None)
    if not album:
        return
    app.album_detail_previous_view = "artist-albums"
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def on_artist_albums_back(app, _button: Gtk.Button) -> None:
    target_view = app.artist_albums_previous_view or "artists"
    if app.main_stack:
        app.main_stack.set_visible_child_name(target_view)


def on_artist_play_clicked(app, _button: Gtk.Button) -> None:
    _start_artist_playback(app, shuffle=False)


def on_artist_shuffle_clicked(app, _button: Gtk.Button) -> None:
    _start_artist_playback(app, shuffle=True)


def _start_artist_playback(app, shuffle: bool) -> None:
    artist = getattr(app, "current_artist", None)
    if not artist:
        toast.show_toast(app, "No artist selected.", is_error=True)
        return
    if not app.server_url:
        toast.show_toast(
            app,
            "Connect to a server to use this action.",
            is_error=True,
        )
        return
    action_label = "Shuffle" if shuffle else "Play"
    thread = threading.Thread(
        target=_artist_playback_worker,
        args=(app, artist, action_label, shuffle),
        daemon=True,
    )
    thread.start()


def _artist_playback_worker(
    app,
    artist: object,
    action_label: str,
    shuffle: bool,
) -> None:
    error = ""
    preferred_player_id = (
        app.output_manager.preferred_player_id if app.output_manager else None
    )
    try:
        media = _resolve_artist_media(artist)
        if not media:
            media = _resolve_artist_track_media(app, artist)
        if not media:
            raise RuntimeError("Artist source is unavailable for this action.")
        player_id = playback.play_album(
            app.client_session,
            app.server_url,
            app.auth_token,
            media,
            None,
            preferred_player_id,
        )
        if player_id and app.output_manager:
            app.output_manager.preferred_player_id = player_id
        if shuffle:
            playback.set_queue_shuffle(
                app.client_session,
                app.server_url,
                app.auth_token,
                True,
                player_id or preferred_player_id,
            )
        _schedule_artist_remote_playback_refresh(app)
    except Exception as exc:
        error = str(exc)
    if error:
        GLib.idle_add(
            toast.show_toast,
            app,
            f"{action_label} failed: {error}",
            True,
        )


def _schedule_artist_remote_playback_refresh(app) -> None:
    GLib.idle_add(app.refresh_remote_playback_state)
    GLib.timeout_add(200, _deferred_artist_remote_playback_refresh, app)
    GLib.timeout_add(800, _deferred_artist_remote_playback_refresh, app)
    GLib.timeout_add(2000, _deferred_artist_remote_playback_refresh, app)


def _deferred_artist_remote_playback_refresh(app) -> bool:
    app.refresh_remote_playback_state()
    return False


def _update_artist_playback_controls(app, artist: object) -> None:
    normalized_artist = normalize_artist_name(get_artist_name(artist))
    can_play = bool(app.server_url) and bool(
        normalized_artist and normalized_artist != "unknown artist"
    )
    for attr in ("artist_play_button", "artist_shuffle_button"):
        button = getattr(app, attr, None)
        if button:
            button.set_sensitive(can_play)


def get_artist_name(artist: object) -> str:
    if isinstance(artist, dict):
        name = artist.get("name") or artist.get("sort_name")
    elif isinstance(artist, str):
        name = artist
    else:
        name = getattr(artist, "name", None) or getattr(artist, "sort_name", None)
        if not name and artist is not None:
            name = str(artist)
    return name or "Unknown Artist"


def _get_artist_item_id(artist: object) -> str | None:
    if isinstance(artist, dict):
        item_id = artist.get("item_id") or artist.get("id")
    else:
        item_id = getattr(artist, "item_id", None) or getattr(
            artist,
            "id",
            None,
        )
    if item_id is None:
        return None
    item_id_value = str(item_id).strip()
    return item_id_value or None


def _extract_artist_bio(artist: object) -> str:
    metadata = None
    if isinstance(artist, dict):
        metadata = artist.get("metadata")
    else:
        metadata = getattr(artist, "metadata", None)

    if isinstance(metadata, dict):
        for key in ("description", "biography", "bio"):
            value = metadata.get(key)
            if isinstance(value, str):
                text = value.strip()
                if text:
                    return text
        return ""

    for key in ("description", "biography", "bio"):
        value = getattr(metadata, key, None) if metadata is not None else None
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return ""


def _extract_artist_image_url(
    artist: object,
    server_url: str,
) -> str | None:
    return image_loader.extract_media_image_url(artist, server_url)


def filter_artist_albums(app, artist_name: str) -> list[dict]:
    normalized = normalize_artist_name(artist_name)
    if not normalized:
        return []
    albums: list[dict] = []
    for album in app.library_albums or []:
        if not isinstance(album, dict):
            continue
        artists = album.get("artists") or []
        if isinstance(artists, str):
            artists = [artists]
        for artist in artists:
            candidate = None
            if isinstance(artist, dict):
                candidate = artist.get("name") or artist.get("sort_name")
            else:
                candidate = str(artist)
            if candidate and normalize_artist_name(candidate) == normalized:
                albums.append(album)
                break
    return _dedupe_artist_albums(albums)


def _collect_album_artist_names(album: object) -> list[str]:
    raw_artists = _pick_album_field(
        album,
        (
            "artists",
            "artist",
            "artist_str",
            "album_artist",
            "album_artist_str",
        ),
    )
    if not raw_artists:
        return []
    if isinstance(raw_artists, str):
        values = [raw_artists]
    elif isinstance(raw_artists, (list, tuple, set)):
        values = list(raw_artists)
    else:
        values = [raw_artists]
    names: list[str] = []
    for artist in values:
        if isinstance(artist, dict):
            candidate = artist.get("name") or artist.get("sort_name")
        else:
            candidate = getattr(artist, "name", None) or getattr(
                artist, "sort_name", None
            )
            if not candidate and isinstance(artist, str):
                candidate = artist
        normalized = _normalize_text(candidate)
        if normalized:
            names.append(normalized)
    return names


def _album_matches_artist(album: object, artist_name: str) -> bool:
    normalized_artist = normalize_artist_name(artist_name)
    if not normalized_artist:
        return False
    for name in _collect_album_artist_names(album):
        if normalize_artist_name(name) == normalized_artist:
            return True
    return False


def _album_dedupe_key(album: object) -> tuple[str, str, int | None, str]:
    title = (
        _normalize_text(_pick_album_field(album, ("name", "title")))
        or "Unknown Album"
    ).casefold()
    artist_key = "|".join(
        sorted(normalize_artist_name(name) for name in _collect_album_artist_names(album))
    )
    year = _extract_artist_album_year(album)
    album_type = _normalize_album_type(_pick_album_field(album, ("album_type", "type")))
    return title, artist_key, year, album_type


def _dedupe_artist_albums(albums: list[object]) -> list[dict]:
    seen: set[tuple[str, str, int | None, str]] = set()
    deduped: list[dict] = []
    for album in albums:
        if not isinstance(album, dict):
            continue
        key = _album_dedupe_key(album)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(album)
    return deduped


def normalize_artist_name(name: str) -> str:
    return (name or "").strip().casefold()


def _normalize_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iter_artist_provider_mappings(artist: object):
    if isinstance(artist, dict):
        mappings = artist.get("provider_mappings") or []
    else:
        mappings = getattr(artist, "provider_mappings", None) or []
    if isinstance(mappings, dict):
        mappings = [mappings]
    elif not isinstance(mappings, (list, tuple, set)):
        mappings = [mappings]
    for mapping in mappings:
        if isinstance(mapping, dict):
            item_id = mapping.get("item_id")
            provider_instance = mapping.get("provider_instance")
            provider_domain = mapping.get("provider_domain")
        else:
            item_id = getattr(mapping, "item_id", None)
            provider_instance = getattr(mapping, "provider_instance", None)
            provider_domain = getattr(mapping, "provider_domain", None)
        yield item_id, provider_instance, provider_domain


def _collect_artist_lookup_candidates(
    artist: object,
    preferred_provider: str | None = None,
) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add_candidate(
        item_id: object | None,
        provider_value: object | None,
    ) -> None:
        item_id_text = _normalize_text(item_id)
        provider_text = _normalize_text(provider_value)
        if not item_id_text or not provider_text:
            return
        key = (item_id_text.casefold(), provider_text.casefold())
        if key in seen:
            return
        seen.add(key)
        candidates.append((item_id_text, provider_text))

    item_id = _get_artist_item_id(artist)
    if preferred_provider:
        _add_candidate(item_id, preferred_provider)
    _add_candidate(item_id, _get_artist_provider(artist))
    for (
        mapping_item_id,
        mapping_provider_instance,
        mapping_provider_domain,
    ) in _iter_artist_provider_mappings(artist):
        _add_candidate(mapping_item_id, mapping_provider_instance)
        _add_candidate(mapping_item_id, mapping_provider_domain)
    return candidates


def _resolve_artist_media(artist_data: object) -> object | None:
    if isinstance(artist_data, dict):
        uri = _normalize_text(artist_data.get("uri"))
        if uri:
            return uri
        item_id = artist_data.get("item_id") or artist_data.get("id")
        provider = (
            artist_data.get("provider")
            or artist_data.get("provider_instance")
            or artist_data.get("provider_domain")
        )
    else:
        uri = _normalize_text(getattr(artist_data, "uri", None))
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
    item_id_text = _normalize_text(item_id)
    provider_text = _normalize_text(provider)
    if item_id_text and provider_text:
        return {
            "item_id": item_id_text,
            "provider": provider_text,
        }
    return None


def _resolve_artist_track_media(app, artist: object) -> object | None:
    artist_name = get_artist_name(artist)
    normalized_artist = normalize_artist_name(artist_name)
    if not normalized_artist or normalized_artist == "unknown artist":
        return None
    provider = _get_artist_provider(artist)
    try:
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_artist_top_tracks_async,
            artist,
            provider,
        )
    except Exception:
        return None
    uris: list[str] = []
    for track in tracks or []:
        if isinstance(track, dict):
            source_uri = track.get("source_uri") or track.get("uri")
        else:
            source_uri = getattr(track, "source_uri", None) or getattr(
                track, "uri", None
            )
        normalized_uri = _normalize_text(source_uri)
        if normalized_uri:
            uris.append(normalized_uri)
    if uris:
        return uris
    return playback.build_media_uri_list(tracks)


def _coerce_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def _coerce_year(value: object) -> int | None:
    if value is None:
        return None
    if hasattr(value, "year"):
        year = _coerce_int(getattr(value, "year", None))
    elif isinstance(value, str):
        text = value.strip()
        if len(text) >= 4 and text[:4].isdigit():
            year = _coerce_int(text[:4])
        else:
            year = _coerce_int(text)
    else:
        year = _coerce_int(value)
    if year is None or year < 1000 or year > 3000:
        return None
    return year


def _pick_album_field(album: object, names: tuple[str, ...]) -> object | None:
    for name in names:
        if isinstance(album, dict):
            value = album.get(name)
        else:
            value = getattr(album, name, None)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _extract_artist_album_year(album: object) -> int | None:
    year = _coerce_year(
        _pick_album_field(album, ("year", "release_year", "album_year"))
    )
    if year:
        return year
    metadata = _pick_album_field(album, ("metadata",))
    if isinstance(metadata, dict):
        release_date = metadata.get("release_date") or metadata.get("year")
    else:
        release_date = getattr(metadata, "release_date", None) or getattr(
            metadata, "year", None
        )
    metadata_year = _coerce_year(release_date)
    if metadata_year:
        return metadata_year
    return _coerce_year(_pick_album_field(album, ("release_date",)))


def _normalize_album_type(value: object) -> str:
    raw = getattr(value, "value", value)
    text = str(raw).strip().casefold() if raw is not None else ""
    if text.startswith("albumtype."):
        return text.split(".", 1)[1]
    return text


def _is_live_album(album: object) -> bool:
    if _normalize_album_type(_pick_album_field(album, ("album_type", "type"))) == "live":
        return True
    metadata = _pick_album_field(album, ("metadata",))
    if metadata is None:
        return False
    if isinstance(metadata, dict):
        nested_type = metadata.get("album_type") or metadata.get("type")
    else:
        nested_type = getattr(metadata, "album_type", None) or getattr(
            metadata, "type", None
        )
    return _normalize_album_type(nested_type) == "live"


def _append_artist_album_metadata(card: Gtk.Widget, album: object) -> None:
    year = _extract_artist_album_year(album)
    is_live = _is_live_album(album)
    if year is None and not is_live:
        return
    meta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    meta_row.add_css_class("artist-album-meta-row")
    meta_row.set_halign(Gtk.Align.CENTER)
    if year is not None:
        year_label = Gtk.Label(label=str(year), xalign=0.5)
        year_label.add_css_class("artist-album-year")
        meta_row.append(year_label)
    if is_live:
        live_label = Gtk.Label(label="Live")
        live_label.add_css_class("artist-album-live-pill")
        meta_row.append(live_label)
    card.append(meta_row)


def _start_artist_top_tracks_refresh(
    app,
    artist: object,
) -> None:
    if not getattr(app, "artist_tracks_store", None):
        return
    app.artist_tracks_store.remove_all()
    if not app.server_url:
        return
    provider = _get_artist_provider(artist)
    thread = threading.Thread(
        target=_load_artist_top_tracks_worker,
        args=(app, artist, provider),
        daemon=True,
    )
    thread.start()


def _start_artist_bio_refresh(app, artist: object) -> None:
    if getattr(app, "artist_detail_art", None):
        app.artist_detail_art.set_paintable(None)
    bio_label = getattr(app, "artist_bio_label", None)
    if bio_label:
        bio_label.set_label("")
        bio_label.set_visible(False)
    if not app.server_url:
        bio = _extract_artist_bio(artist)
        image_url = _extract_artist_image_url(artist, app.server_url or "")
        GLib.idle_add(app.on_artist_bio_loaded, artist, bio, image_url, "")
        return
    provider = _get_artist_provider(artist)
    thread = threading.Thread(
        target=_load_artist_bio_worker,
        args=(app, artist, provider),
        daemon=True,
    )
    thread.start()


def _load_artist_top_tracks_worker(
    app,
    artist: object,
    provider: str | None,
) -> None:
    error = ""
    tracks: list[dict] = []
    try:
        tracks = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_artist_top_tracks_async,
            artist,
            provider,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_artist_top_tracks_loaded, artist, tracks, error)


def _load_artist_bio_worker(
    app,
    artist: object,
    provider: str | None,
) -> None:
    error = ""
    bio = ""
    image_url: str | None = None
    try:
        bio, image_url = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_artist_bio_async,
            artist,
            provider,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(app.on_artist_bio_loaded, artist, bio, image_url, error)


async def _fetch_artist_all_albums_async(
    app,
    client: MusicAssistantClient,
    artist: object,
) -> list[dict]:
    candidates = await _fetch_artist_album_candidates(client, artist)
    serialized: list[dict] = []
    for album in candidates:
        full_album = await _ensure_full_artist_album(client, album)
        serialized.append(library._serialize_album(client, full_album))
    return _dedupe_artist_albums(serialized)


async def _fetch_artist_album_candidates(
    client: MusicAssistantClient,
    artist: object,
) -> list[object]:
    item_id = _get_artist_item_id(artist)
    provider = _get_artist_provider(artist)
    artist_name = get_artist_name(artist)
    if item_id and provider:
        albums = await _fetch_artist_albums_by_reference(
            client,
            item_id,
            provider,
        )
        if albums:
            return albums
    if artist_name and provider:
        albums = await _fetch_artist_albums_by_reference(
            client,
            artist_name,
            provider,
        )
        if albums:
            return albums
    return await _search_artist_album_candidates(client, artist_name)


async def _fetch_artist_albums_by_reference(
    client: MusicAssistantClient,
    artist_reference: str,
    provider: str,
) -> list[object]:
    getter = getattr(client.music, "get_artist_albums", None)
    if getter is None:
        return []
    try:
        return list(
            await getter(
                artist_reference,
                provider,
                in_library_only=False,
            )
            or []
        )
    except TypeError:
        try:
            return list(await getter(artist_reference, provider) or [])
        except Exception:
            return []
    except Exception:
        return []


async def _search_artist_album_candidates(
    client: MusicAssistantClient,
    artist_name: str,
) -> list[object]:
    if not normalize_artist_name(artist_name):
        return []
    try:
        search_results = await client.music.search(
            search_query=artist_name,
            media_types=[MediaType.ALBUM],
            limit=DEFAULT_PAGE_SIZE,
            library_only=False,
        )
    except Exception:
        return []
    albums = list(getattr(search_results, "albums", None) or [])
    matches = [album for album in albums if _album_matches_artist(album, artist_name)]
    return matches or albums


async def _ensure_full_artist_album(
    client: MusicAssistantClient,
    album: object,
) -> object:
    if getattr(album, "provider_mappings", None):
        return album
    item_id = _pick_album_field(album, ("item_id", "id"))
    provider = _pick_album_field(
        album,
        ("provider", "provider_instance", "provider_domain"),
    )
    if not item_id or not provider:
        return album
    try:
        return await client.music.get_album(str(item_id), str(provider))
    except Exception:
        return album


async def _fetch_artist_top_tracks_async(
    app,
    client: MusicAssistantClient,
    artist: object,
    provider: str | None,
) -> list[dict]:
    tracks: list[object] = []
    artist_name = get_artist_name(artist)
    for item_id, provider_id in _collect_artist_lookup_candidates(
        artist,
        provider,
    ):
        try:
            tracks = await client.music.get_artist_tracks(item_id, provider_id)
        except Exception:
            continue
        if tracks:
            break
    if not tracks and artist_name:
        if provider:
            try:
                tracks = await client.music.get_artist_tracks(artist_name, provider)
            except Exception:
                tracks = []
        if not tracks:
            try:
                tracks = await client.music.get_artist_tracks(artist_name)
            except Exception:
                tracks = []
    describe_quality = lambda item: track_utils.describe_track_quality(
        item,
        track_utils.format_sample_rate,
    )
    serialized: list[dict] = []
    for index, track in enumerate(tracks or [], start=1):
        payload = track_utils.serialize_track(
            track,
            "",
            ui_utils.format_artist_names,
            track_utils.format_duration,
            describe_quality,
        )
        payload["track_number"] = index
        image_url = image_loader.resolve_media_item_image_url(
            client,
            track,
            app.server_url,
        )
        if image_url:
            payload["image_url"] = image_url
        serialized.append(payload)
    return serialized


async def _fetch_artist_bio_async(
    app,
    client: MusicAssistantClient,
    artist: object,
    provider: str | None,
) -> tuple[str, str | None]:
    bio = ""
    image_url: str | None = None
    for item_id, provider_id in _collect_artist_lookup_candidates(
        artist,
        provider,
    ):
        try:
            full_artist = await client.music.get_artist(item_id, provider_id)
        except Exception:
            continue
        if not bio:
            bio = _extract_artist_bio(full_artist)
        if not image_url:
            image_url = image_loader.resolve_media_item_image_url(
                client,
                full_artist,
                app.server_url,
            )
        if bio and image_url:
            break
    if (not bio or not image_url) and get_artist_name(artist):
        for search_artist in await _search_artist_candidates(
            client,
            get_artist_name(artist),
        ):
            if not bio:
                bio = _extract_artist_bio(search_artist)
            if not image_url:
                image_url = image_loader.resolve_media_item_image_url(
                    client,
                    search_artist,
                    app.server_url,
                )
            if bio and image_url:
                break
            for item_id, provider_id in _collect_artist_lookup_candidates(
                search_artist,
                None,
            ):
                try:
                    full_artist = await client.music.get_artist(
                        item_id,
                        provider_id,
                    )
                except Exception:
                    continue
                if not bio:
                    bio = _extract_artist_bio(full_artist)
                if not image_url:
                    image_url = image_loader.resolve_media_item_image_url(
                        client,
                        full_artist,
                        app.server_url,
                    )
                if bio and image_url:
                    break
            if bio and image_url:
                break
    if not bio:
        fallback_bio = _extract_artist_bio(artist)
        if fallback_bio:
            bio = fallback_bio
    if not image_url:
        fallback_image_url = _extract_artist_image_url(
            artist,
            app.server_url,
        )
        if fallback_image_url:
            image_url = fallback_image_url
    return bio, image_url


async def _search_artist_candidates(
    client: MusicAssistantClient,
    artist_name: str,
) -> list[object]:
    normalized_name = normalize_artist_name(artist_name)
    if not normalized_name:
        return []
    try:
        search_results = await client.music.search(
            search_query=artist_name,
            media_types=[MediaType.ARTIST],
            limit=10,
            library_only=False,
        )
    except Exception:
        return []
    artists = list(getattr(search_results, "artists", None) or [])
    exact_matches = [
        item
        for item in artists
        if normalize_artist_name(get_artist_name(item)) == normalized_name
    ]
    return exact_matches or artists


def on_artist_top_tracks_loaded(
    app,
    artist: object,
    tracks: list[dict],
    error: str,
) -> None:
    if _artist_identity(artist) != _artist_identity(
        getattr(app, "current_artist", None)
    ):
        return
    if error:
        return
    _populate_artist_tracks_store(app, tracks)


def on_artist_bio_loaded(
    app,
    artist: object,
    bio: str,
    image_url: str | None,
    error: str,
) -> None:
    if _artist_identity(artist) != _artist_identity(
        getattr(app, "current_artist", None)
    ):
        return
    bio_label = getattr(app, "artist_bio_label", None)
    if bio_label:
        if bio:
            bio_label.set_label(bio)
            bio_label.set_visible(True)
        else:
            bio_label.set_label("")
            bio_label.set_visible(False)
    if image_url and getattr(app, "artist_detail_art", None):
        image_loader.load_album_art_async(
            app.artist_detail_art,
            image_url,
            DETAIL_ART_SIZE,
            app.auth_token,
            app.image_executor,
            app.get_cache_dir(),
        )


def _populate_artist_tracks_store(app, tracks: list[dict]) -> None:
    store = getattr(app, "artist_tracks_store", None)
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
    if getattr(app, "artist_tracks_view", None) and getattr(
        app,
        "artist_tracks_selection",
        None,
    ):
        app.artist_tracks_view.set_model(app.artist_tracks_selection)


def _get_artist_provider(artist: object) -> str | None:
    if isinstance(artist, dict):
        provider = (
            artist.get("provider")
            or artist.get("provider_instance")
            or artist.get("provider_domain")
        )
    else:
        provider = (
            getattr(artist, "provider", None)
            or getattr(artist, "provider_instance", None)
            or getattr(artist, "provider_domain", None)
        )
    if isinstance(provider, str):
        provider = provider.strip()
    return provider or None
