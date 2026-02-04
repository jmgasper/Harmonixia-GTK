def serialize_track(
    track: object,
    album_name: str,
    format_artist_names_fn,
    format_duration_fn,
    describe_track_quality_fn,
) -> dict:
    title = getattr(track, "name", None) or "Unknown Track"
    track_number = getattr(track, "track_number", 0) or 0
    duration = getattr(track, "duration", 0) or 0

    artist = getattr(track, "artist_str", None)
    if not artist:
        artists = []
        for artist_item in getattr(track, "artists", []) or []:
            name = getattr(artist_item, "name", None) or getattr(
                artist_item, "sort_name", None
            )
            if name:
                artists.append(name)
        artist = format_artist_names_fn(artists)

    album = album_name
    track_album = getattr(track, "album", None)
    if track_album is not None:
        album = getattr(track_album, "name", None) or album_name

    quality = describe_track_quality_fn(track)
    if isinstance(track, dict):
        is_favorite = bool(track.get("favorite", False))
    else:
        is_favorite = bool(getattr(track, "favorite", False))
    return {
        "track_number": track_number,
        "title": title,
        "length_display": format_duration_fn(duration),
        "length_seconds": duration,
        "artist": artist or "Unknown Artist",
        "album": album,
        "quality": quality,
        "is_favorite": is_favorite,
        "source": track,
    }


def describe_track_quality(track: object, format_sample_rate_fn) -> str:
    mappings = getattr(track, "provider_mappings", None)
    if not mappings:
        return "Unknown"
    mapping = max(mappings, key=lambda item: getattr(item, "quality", 0))
    audio_format = getattr(mapping, "audio_format", None)
    if not audio_format:
        return "Unknown"
    content_type = getattr(audio_format, "content_type", None)
    if content_type and hasattr(content_type, "is_lossless"):
        if content_type.is_lossless():
            sample_rate = getattr(audio_format, "sample_rate", 0)
            bit_depth = getattr(audio_format, "bit_depth", 0)
            if sample_rate and bit_depth:
                rate_text = format_sample_rate_fn(sample_rate)
                return f"Lossless {rate_text}kHz/{bit_depth}-bit"
            return "Lossless"
    bit_rate = getattr(audio_format, "bit_rate", None)
    if bit_rate:
        return f"{bit_rate} kbps"
    output = getattr(audio_format, "output_format_str", "")
    if output:
        return output
    if content_type:
        return str(content_type)
    return "Unknown"


def format_sample_rate(sample_rate: int) -> str:
    rate_khz = sample_rate / 1000.0
    if abs(rate_khz - round(rate_khz)) < 0.01:
        return str(int(round(rate_khz)))
    return f"{rate_khz:.1f}"


def format_duration(seconds: int) -> str:
    if not seconds:
        return ""
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def format_timecode(seconds: float | int) -> str:
    total_seconds = int(max(0, seconds))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def generate_sample_tracks(
    album: dict, format_artist_names_fn, format_duration_fn
) -> list[dict]:
    album_name = album.get("name") or "Unknown Album"
    artist = format_artist_names_fn(album.get("artists") or [])
    tracks = []
    for index in range(1, 9):
        duration = 160 + index * 14
        tracks.append(
            {
                "track_number": index,
                "title": f"Track {index}",
                "length_display": format_duration_fn(duration),
                "length_seconds": duration,
                "artist": artist,
                "album": album_name,
                "quality": "Lossless 44.1kHz/16-bit",
                "is_favorite": False,
                "source": None,
            }
        )
    return tracks


def get_track_identity(track: object, source_uri: str | None = None) -> tuple:
    if source_uri:
        return ("uri", source_uri)
    return ("fallback", track.track_number, track.title, track.artist)


def snapshot_track(track: object, get_track_identity_fn) -> dict:
    source = getattr(track, "source", None)
    source_uri = getattr(source, "uri", None) if source else None
    image_url = getattr(track, "cover_image_url", None) or getattr(
        track, "image_url", None
    )
    quality = getattr(track, "quality", "") or ""
    return {
        "track_number": track.track_number,
        "title": track.title,
        "artist": track.artist,
        "album": getattr(track, "album", ""),
        "length_seconds": track.length_seconds,
        "quality": quality,
        "source": source,
        "source_uri": source_uri,
        "image_url": image_url,
        "identity": get_track_identity_fn(track, source_uri),
    }
