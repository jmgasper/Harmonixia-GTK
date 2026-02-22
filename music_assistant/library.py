from __future__ import annotations

from music_assistant_client import MusicAssistantClient
from music_assistant_models.enums import AlbumType
from music_assistant_models.media_items import Playlist

from constants import DEFAULT_PAGE_SIZE


def normalize_album_type(album_type: object) -> str:
    if isinstance(album_type, AlbumType):
        return album_type.value
    if isinstance(album_type, str):
        value = album_type.strip().lower()
        if value:
            return AlbumType(value).value
    return AlbumType.UNKNOWN.value


def pick_album_value(album: object, fields: tuple[str, ...]) -> object | None:
    for field in fields:
        if isinstance(album, dict):
            value = album.get(field)
        else:
            value = getattr(album, field, None)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


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


def _extract_release_year(album: object) -> int | None:
    year = _coerce_year(
        pick_album_value(album, ("year", "release_year", "album_year"))
    )
    if year:
        return year

    metadata = pick_album_value(album, ("metadata",))
    if isinstance(metadata, dict):
        release_date = metadata.get("release_date") or metadata.get("year")
    else:
        release_date = getattr(metadata, "release_date", None) or getattr(
            metadata, "year", None
        )
    year = _coerce_year(release_date)
    if year:
        return year

    return _coerce_year(pick_album_value(album, ("release_date",)))


def _extract_album_track_count(album: object) -> int | None:
    count = _coerce_int(
        pick_album_value(
            album,
            (
                "track_count",
                "tracks_count",
                "total_tracks",
                "num_tracks",
                "track_total",
            ),
        )
    )
    if count is not None and count >= 0:
        return count
    if isinstance(album, dict):
        tracks = album.get("tracks")
        if isinstance(tracks, (list, tuple, set)):
            return len(tracks)
    return None


def _extract_album_duration_seconds(album: object) -> int | None:
    duration = _coerce_int(
        pick_album_value(
            album,
            (
                "duration_seconds",
                "total_duration_seconds",
                "duration",
                "total_duration",
                "album_duration",
            ),
        )
    )
    if duration is not None and duration >= 0:
        return duration

    duration_ms = _coerce_int(
        pick_album_value(
            album,
            (
                "duration_ms",
                "total_duration_ms",
                "album_duration_ms",
            ),
        )
    )
    if duration_ms is not None and duration_ms >= 0:
        return int(round(duration_ms / 1000))
    return None


def _extract_artist_image_url(
    client: MusicAssistantClient, artist: object
) -> str | None:
    if artist is None:
        return None
    if not isinstance(artist, dict):
        try:
            image_url = client.get_media_item_image_url(artist)
        except Exception:
            image_url = None
        if image_url:
            return image_url
    if isinstance(artist, dict):
        for key in ("image_url", "image", "thumbnail", "artwork", "cover"):
            value = artist.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                for nested_key in ("url", "path", "uri"):
                    nested = value.get(nested_key)
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
        metadata = artist.get("metadata")
        if isinstance(metadata, dict):
            images = metadata.get("images")
            if isinstance(images, (list, tuple)):
                for image in images:
                    if isinstance(image, dict):
                        for key in ("url", "path", "uri"):
                            nested = image.get(key)
                            if isinstance(nested, str) and nested.strip():
                                return nested.strip()
    return None


def _serialize_album(client: MusicAssistantClient, album: object) -> dict:
    name = pick_album_value(album, ("name", "title")) or "Unknown Album"
    item_id = pick_album_value(album, ("item_id", "id"))
    provider = pick_album_value(
        album,
        ("provider", "provider_instance", "provider_domain"),
    )
    uri = pick_album_value(album, ("uri",))
    album_type = normalize_album_type(
        pick_album_value(album, ("album_type", "type"))
    )
    provider_mappings = []
    raw_mappings = pick_album_value(album, ("provider_mappings",)) or []
    if isinstance(raw_mappings, dict):
        raw_mappings = [raw_mappings]
    elif not isinstance(raw_mappings, (list, tuple, set)):
        raw_mappings = [raw_mappings]
    for mapping in raw_mappings:
        if isinstance(mapping, dict):
            provider_mappings.append(
                {
                    "item_id": mapping.get("item_id"),
                    "provider_instance": mapping.get("provider_instance"),
                    "provider_domain": mapping.get("provider_domain"),
                    "available": mapping.get("available", True),
                }
            )
            continue
        provider_mappings.append(
            {
                "item_id": getattr(mapping, "item_id", None),
                "provider_instance": getattr(mapping, "provider_instance", None),
                "provider_domain": getattr(mapping, "provider_domain", None),
                "available": getattr(mapping, "available", True),
            }
        )

    raw_artists = pick_album_value(album, ("artists",))
    if not raw_artists:
        raw_artists = pick_album_value(
            album,
            (
                "artist",
                "artist_str",
                "album_artist",
                "album_artist_str",
            ),
        )

    artists = []
    artist_image_url = pick_album_value(
        album,
        ("artist_image_url", "primary_artist_image_url"),
    )
    if raw_artists:
        if isinstance(raw_artists, str):
            raw_artists = [raw_artists]
        elif not isinstance(raw_artists, (list, tuple, set)):
            raw_artists = [raw_artists]
        for artist in raw_artists:
            if isinstance(artist, dict):
                artist_name = artist.get("name") or artist.get("sort_name")
            else:
                artist_name = getattr(artist, "name", None) or getattr(
                    artist, "sort_name", None
                )
                if not artist_name and isinstance(artist, str):
                    artist_name = artist
            if artist_name:
                cleaned = str(artist_name).strip()
                if cleaned:
                    artists.append(cleaned)
            if not artist_image_url:
                artist_image_url = _extract_artist_image_url(client, artist)

    image_url = None
    try:
        image_url = client.get_media_item_image_url(album)
    except Exception:
        image_url = None

    year = _extract_release_year(album)
    track_count = _extract_album_track_count(album)
    duration_seconds = _extract_album_duration_seconds(album)
    added_at = pick_album_value(
        album,
        (
            "added_at",
            "date_added",
            "timestamp_added",
            "time_added",
            "created_at",
            "created",
            "sort_timestamp",
            "timestamp",
        ),
    )
    last_played = pick_album_value(
        album,
        (
            "last_played",
            "last_played_at",
            "timestamp_last_played",
            "last_played_timestamp",
            "played_at",
        ),
    )
    data = {
        "name": name,
        "artists": artists,
        "image_url": image_url,
        "item_id": item_id,
        "provider": provider,
        "uri": uri,
        "album_type": album_type,
        "provider_mappings": provider_mappings,
    }
    if artist_image_url:
        data["artist_image_url"] = artist_image_url
    if year is not None:
        data["year"] = year
    if track_count is not None:
        data["track_count"] = track_count
    if duration_seconds is not None:
        data["duration_seconds"] = duration_seconds
    if added_at is not None:
        data["added_at"] = added_at
    if last_played is not None:
        data["last_played"] = last_played
    return data


def _serialize_artist(artist: object) -> dict:
    if isinstance(artist, dict):
        name = artist.get("name")
    else:
        name = getattr(artist, "name", None)
    name = name or "Unknown Artist"
    return {"name": name}


def _serialize_playlist(playlist: object) -> dict:
    name = getattr(playlist, "name", None) or "Untitled Playlist"
    item_id = getattr(playlist, "item_id", None)
    provider = getattr(playlist, "provider", None)
    uri = getattr(playlist, "uri", None)
    owner = getattr(playlist, "owner", None)
    is_editable = bool(getattr(playlist, "is_editable", False))
    data = {
        "name": name,
        "item_id": item_id,
        "provider": provider,
        "uri": uri,
        "is_editable": is_editable,
    }
    if owner:
        data["owner"] = owner
    return data


async def fetch_albums(
    client: MusicAssistantClient,
    favorite: bool | None = None,
    order_by: str = "sort_name",
) -> list[dict]:
    albums: list[dict] = []
    offset = 0
    while True:
        params: dict[str, object] = {
            "limit": DEFAULT_PAGE_SIZE,
            "offset": offset,
            "order_by": order_by,
        }
        if favorite is not None:
            params["favorite"] = favorite
        page = await client.music.get_library_albums(**params)
        if not page:
            break
        for album in page:
            albums.append(_serialize_album(client, album))
        if len(page) < DEFAULT_PAGE_SIZE:
            break
        offset += DEFAULT_PAGE_SIZE
    return albums


async def fetch_artists(client: MusicAssistantClient) -> list[dict]:
    artists: list[dict] = []
    offset = 0
    while True:
        page = await client.music.get_library_artists(
            limit=DEFAULT_PAGE_SIZE,
            offset=offset,
            order_by="sort_name",
        )
        if not page:
            break
        for artist in page:
            artists.append(_serialize_artist(artist))
        if len(page) < DEFAULT_PAGE_SIZE:
            break
        offset += DEFAULT_PAGE_SIZE
    return artists


async def fetch_playlists(client: MusicAssistantClient) -> list[dict]:
    playlists: list[dict] = []
    offset = 0
    while True:
        page = await client.music.get_library_playlists(
            limit=DEFAULT_PAGE_SIZE,
            offset=offset,
            order_by="sort_name",
        )
        if not page:
            break
        for playlist in page:
            playlists.append(_serialize_playlist(playlist))
        if len(page) < DEFAULT_PAGE_SIZE:
            break
        offset += DEFAULT_PAGE_SIZE
    return playlists


async def load_library_data(
    client: MusicAssistantClient,
    album_favorite: bool | None = None,
    album_order_by: str = "sort_name",
) -> tuple[list[dict], list[dict], list[dict]]:
    albums = await fetch_albums(
        client,
        favorite=album_favorite,
        order_by=album_order_by,
    )
    artists = await fetch_artists(client)
    playlists = await fetch_playlists(client)
    return albums, artists, playlists


async def create_playlist(client: MusicAssistantClient, name: str) -> object:
    return await client.music.create_playlist(name)


async def delete_playlist(
    client: MusicAssistantClient, playlist_id: str | int
) -> None:
    await client.music.remove_playlist(playlist_id)


async def rename_playlist(
    client: MusicAssistantClient,
    playlist_id: str | int,
    provider: str,
    new_name: str,
) -> object:
    if hasattr(client.music, "update_playlist"):
        playlist = await client.music.get_playlist(str(playlist_id), provider)
        payload = playlist.to_dict()
        payload["name"] = new_name
        update = Playlist.from_dict(payload)
        return await client.music.update_playlist(playlist_id, update)
    return await _recreate_playlist_with_tracks(
        client, playlist_id, provider, new_name
    )


async def _recreate_playlist_with_tracks(
    client: MusicAssistantClient,
    playlist_id: str | int,
    provider: str,
    new_name: str,
) -> object:
    new_playlist = await client.music.create_playlist(new_name)
    new_playlist_id = getattr(new_playlist, "item_id", None) or getattr(
        new_playlist, "id", None
    )
    if not new_playlist_id:
        raise RuntimeError("New playlist ID missing")

    page = 0
    track_uris: list[str] = []
    while True:
        page_tracks = await client.music.get_playlist_tracks(
            str(playlist_id),
            provider,
            page=page,
        )
        if not page_tracks:
            break
        for track in page_tracks:
            uri = getattr(track, "uri", None)
            if uri:
                track_uris.append(uri)
        page += 1
    for chunk in _chunked(track_uris, 200):
        await client.music.add_playlist_tracks(new_playlist_id, chunk)
    await client.music.remove_playlist(playlist_id)
    return new_playlist


def _chunked(items: list[str], chunk_size: int):
    for index in range(0, len(items), chunk_size):
        yield items[index : index + chunk_size]


__all__ = [
    "fetch_albums",
    "fetch_artists",
    "fetch_playlists",
    "load_library_data",
    "create_playlist",
    "delete_playlist",
    "rename_playlist",
    "_serialize_album",
    "_serialize_artist",
    "_serialize_playlist",
]
