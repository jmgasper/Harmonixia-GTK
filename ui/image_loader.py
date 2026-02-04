import concurrent.futures
import hashlib
import logging
import os
import threading
from collections import OrderedDict
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import gi
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Gtk', '4.0')

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

from constants import (
    ALBUM_ART_CACHE_DIR,
    ALBUM_TILE_SIZE,
    DETAIL_ART_SIZE,
    DETAIL_BG_BLUR_PASSES,
    DETAIL_BG_BLUR_SCALE,
    DETAIL_BG_SIZE,
)

_default_executor: concurrent.futures.ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()
_TEXTURE_CACHE_MAX_DIM = 256
_TEXTURE_CACHE_LIMIT = 256
_texture_cache: OrderedDict[str, tuple[int, Gdk.Texture]] = OrderedDict()
_texture_cache_lock = threading.Lock()


def _get_cached_texture(image_url: str, size: int) -> Gdk.Texture | None:
    if not image_url or size <= 0 or size > _TEXTURE_CACHE_MAX_DIM:
        return None
    with _texture_cache_lock:
        cached = _texture_cache.get(image_url)
        if not cached:
            return None
        cached_size, texture = cached
        if cached_size < size:
            return None
        _texture_cache.move_to_end(image_url)
        return texture


def _store_cached_texture(
    image_url: str, size: int, texture: Gdk.Texture
) -> None:
    if not image_url or size <= 0 or size > _TEXTURE_CACHE_MAX_DIM:
        return
    with _texture_cache_lock:
        cached = _texture_cache.get(image_url)
        if cached and cached[0] >= size:
            _texture_cache.move_to_end(image_url)
            return
        _texture_cache[image_url] = (size, texture)
        _texture_cache.move_to_end(image_url)
        while len(_texture_cache) > _TEXTURE_CACHE_LIMIT:
            _texture_cache.popitem(last=False)


def _get_default_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _default_executor
    if _default_executor is None:
        with _executor_lock:
            if _default_executor is None:
                _default_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=6,
                    thread_name_prefix="album-art",
                )
    return _default_executor


def extract_album_image_url(album: dict, server_url: str) -> str | None:
    for candidate in iter_album_image_candidates(album):
        resolved = resolve_image_url(candidate, server_url)
        if resolved:
            return resolved
    return None


def extract_media_image_url(item: object, server_url: str) -> str | None:
    for candidate in iter_media_image_candidates(item):
        resolved = resolve_image_url(candidate, server_url)
        if resolved:
            return resolved
    return None


def resolve_media_item_image_url(
    client: object, item: object, server_url: str
) -> str | None:
    if client is not None and item is not None:
        try:
            image_url = client.get_media_item_image_url(item)
        except Exception:
            image_url = None
        if image_url:
            resolved = resolve_image_url(image_url, server_url)
            if resolved:
                return resolved
    return extract_media_image_url(item, server_url)


def iter_media_image_candidates(item: object):
    if item is None:
        return
    if isinstance(item, dict):
        yield from iter_album_image_candidates(item)
        album = item.get("album")
        if album is not None and album is not item:
            yield from iter_media_image_candidates(album)
        return
    for key in ("image", "image_url", "artwork", "cover", "thumbnail"):
        yield from iter_image_candidates(getattr(item, key, None))
    metadata = getattr(item, "metadata", None)
    if metadata is not None:
        if isinstance(metadata, dict):
            yield from iter_image_candidates(metadata.get("image"))
            yield from iter_image_candidates(metadata.get("images"))
        else:
            yield from iter_image_candidates(getattr(metadata, "image", None))
            yield from iter_image_candidates(getattr(metadata, "images", None))
    album = getattr(item, "album", None)
    if album is not None and album is not item:
        yield from iter_media_image_candidates(album)


def iter_album_image_candidates(album: dict):
    if not isinstance(album, dict):
        return
    for key in ("image", "image_url", "artwork", "cover", "thumbnail"):
        yield from iter_image_candidates(album.get(key))
    metadata = album.get("metadata")
    if isinstance(metadata, dict):
        yield from iter_image_candidates(metadata.get("image"))
        yield from iter_image_candidates(metadata.get("images"))


def iter_image_candidates(value: object):
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            yield candidate
        return
    if isinstance(value, dict):
        for key in ("url", "path", "uri"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                yield candidate.strip()
        return
    if hasattr(value, "url") or hasattr(value, "path") or hasattr(value, "uri"):
        for key in ("url", "path", "uri"):
            candidate = getattr(value, key, None)
            if isinstance(candidate, str) and candidate.strip():
                yield candidate.strip()
        return
    if isinstance(value, list):
        for item in value:
            yield from iter_image_candidates(item)




def resolve_image_url(value: str, server_url: str) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https"):
        return value
    if parsed.scheme:
        return None
    if not server_url:
        return None
    return urljoin(f"{server_url}/", value.lstrip("/"))


def load_album_art_async(
    picture: Gtk.Picture,
    image_url: str,
    size: int,
    auth_token: str,
    image_executor,
    cache_dir: str,
) -> None:
    if not image_url:
        return
    if image_executor is None:
        image_executor = _get_default_executor()
    try:
        picture.expected_image_url = image_url
    except Exception:
        pass
    cached_texture = _get_cached_texture(image_url, size)
    if cached_texture is not None:
        try:
            picture.set_paintable(cached_texture)
        except Exception:
            pass
        else:
            return
    image_executor.submit(
        _fetch_album_art,
        image_url,
        picture,
        size,
        auth_token,
        cache_dir,
    )


def load_album_background_async(
    picture: Gtk.Picture,
    image_url: str,
    auth_token: str,
    image_executor,
    cache_dir: str,
) -> None:
    if not image_url:
        return
    if image_executor is None:
        image_executor = _get_default_executor()
    try:
        picture.expected_image_url = image_url
    except Exception:
        pass
    image_executor.submit(
        _fetch_album_background,
        image_url,
        picture,
        auth_token,
        cache_dir,
    )


def load_playlist_cover_async(
    picture: Gtk.Picture,
    image_urls: list[str],
    size: int,
    auth_token: str,
    image_executor,
    cache_dir: str,
) -> None:
    normalized = normalize_playlist_image_urls(image_urls)
    if not normalized:
        return
    if image_executor is None:
        image_executor = _get_default_executor()
    image_key = tuple(normalized)
    try:
        picture.expected_image_urls = image_key
    except Exception:
        pass
    image_executor.submit(
        _fetch_playlist_cover,
        normalized,
        image_key,
        picture,
        size,
        auth_token,
        cache_dir,
    )


def load_playlist_background_async(
    picture: Gtk.Picture,
    image_urls: list[str],
    auth_token: str,
    image_executor,
    cache_dir: str,
) -> None:
    normalized = normalize_playlist_image_urls(image_urls)
    if not normalized:
        return
    if image_executor is None:
        image_executor = _get_default_executor()
    image_key = tuple(normalized)
    try:
        picture.expected_image_urls = image_key
    except Exception:
        pass
    image_executor.submit(
        _fetch_playlist_background,
        normalized,
        image_key,
        picture,
        auth_token,
        cache_dir,
    )


def normalize_playlist_image_urls(
    image_urls: list[str] | None, limit: int = 4
) -> list[str]:
    if not image_urls:
        return []
    normalized = [url for url in image_urls if url]
    if not normalized:
        return []
    if len(normalized) >= limit:
        return normalized[:limit]
    index = 0
    while len(normalized) < limit:
        normalized.append(normalized[index % len(normalized)])
        index += 1
    return normalized


def apply_playlist_art(
    picture: Gtk.Picture,
    pixbuf: GdkPixbuf.Pixbuf,
    image_key: tuple[str, ...],
) -> bool:
    if hasattr(picture, "expected_image_urls"):
        expected = picture.expected_image_urls
        if not expected or expected != image_key:
            return False
    try:
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    except Exception:
        return False
    try:
        picture.set_paintable(texture)
    except Exception:
        return False
    return False


def build_playlist_cover_pixbuf(
    image_urls: list[str],
    size: int,
    auth_token: str,
    cache_dir: str,
) -> GdkPixbuf.Pixbuf | None:
    if not image_urls:
        return None
    normalized = normalize_playlist_image_urls(image_urls)
    if not normalized:
        return None
    tile_width = max(1, size // 2)
    tile_height = max(1, size // 2)
    right_width = max(1, size - tile_width)
    bottom_height = max(1, size - tile_height)
    targets = (
        (0, 0, tile_width, tile_height),
        (tile_width, 0, right_width, tile_height),
        (0, tile_height, tile_width, bottom_height),
        (tile_width, tile_height, right_width, bottom_height),
    )
    composite = GdkPixbuf.Pixbuf.new(
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        size,
        size,
    )
    composite.fill(0x000000ff)
    pixbufs = [
        fetch_album_art_pixbuf(url, auth_token, cache_dir)
        for url in normalized
    ]
    fallback = next((pixbuf for pixbuf in pixbufs if pixbuf is not None), None)
    if fallback is None:
        return None
    for index, (x, y, width, height) in enumerate(targets):
        pixbuf = pixbufs[index] or fallback
        scaled = pixbuf.scale_simple(
            width,
            height,
            GdkPixbuf.InterpType.BILINEAR,
        )
        if scaled is None:
            continue
        scaled.copy_area(0, 0, width, height, composite, x, y)
    return composite


def _fetch_playlist_cover(
    image_urls: list[str],
    image_key: tuple[str, ...],
    picture: Gtk.Picture,
    size: int,
    auth_token: str,
    cache_dir: str,
) -> None:
    pixbuf = build_playlist_cover_pixbuf(
        image_urls,
        size,
        auth_token,
        cache_dir,
    )
    if pixbuf is None:
        return
    GLib.idle_add(apply_playlist_art, picture, pixbuf, image_key)


def _fetch_playlist_background(
    image_urls: list[str],
    image_key: tuple[str, ...],
    picture: Gtk.Picture,
    auth_token: str,
    cache_dir: str,
) -> None:
    pixbuf = build_playlist_cover_pixbuf(
        image_urls,
        DETAIL_BG_SIZE,
        auth_token,
        cache_dir,
    )
    if pixbuf is None:
        return
    pixbuf = blur_pixbuf(
        pixbuf,
        scale=DETAIL_BG_BLUR_SCALE,
        passes=DETAIL_BG_BLUR_PASSES,
    )
    GLib.idle_add(apply_playlist_art, picture, pixbuf, image_key)


def get_album_art_cache_path(image_url: str, cache_dir: str) -> str | None:
    if not image_url:
        return None
    if not cache_dir:
        cache_dir = os.path.join(os.path.dirname(__file__), ALBUM_ART_CACHE_DIR)
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Failed to create cache directory %s: %s",
            cache_dir,
            exc,
        )
        return None
    digest = hashlib.sha256(image_url.encode("utf-8")).hexdigest()
    return os.path.join(cache_dir, f"{digest}.img")


def read_album_art_cache(cache_path: str) -> bytes | None:
    try:
        with open(cache_path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def write_album_art_cache(cache_path: str, data: bytes) -> None:
    cache_dir = os.path.dirname(cache_path)
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError:
        return
    tmp_path = f"{cache_path}.tmp-{threading.get_ident()}"
    try:
        with open(tmp_path, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, cache_path)
    except OSError:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def remove_album_art_cache(cache_path: str) -> None:
    try:
        os.remove(cache_path)
    except OSError:
        return


def download_album_art(image_url: str, auth_token: str) -> bytes | None:
    request = Request(image_url)
    if auth_token:
        request.add_header(
            "Authorization",
            f"Bearer {auth_token}",
        )
    try:
        with urlopen(request, timeout=10) as response:
            return response.read()
    except Exception:
        return None


def fetch_album_art_pixbuf(
    image_url: str,
    auth_token: str,
    cache_dir: str,
) -> GdkPixbuf.Pixbuf | None:
    cache_path = get_album_art_cache_path(image_url, cache_dir)
    data = None
    loaded_from_cache = False
    if cache_path:
        data = read_album_art_cache(cache_path)
        loaded_from_cache = data is not None
    if data is None:
        data = download_album_art(image_url, auth_token)
        if data is None:
            return None
        if cache_path:
            write_album_art_cache(cache_path, data)
    pixbuf = decode_album_art(data)
    if pixbuf is None and loaded_from_cache:
        if cache_path:
            remove_album_art_cache(cache_path)
        data = download_album_art(image_url, auth_token)
        if data is None:
            return None
        if cache_path:
            write_album_art_cache(cache_path, data)
        pixbuf = decode_album_art(data)
    return pixbuf


def decode_album_art(data: bytes) -> GdkPixbuf.Pixbuf | None:
    try:
        loader = GdkPixbuf.PixbufLoader.new()
        loader.write(data)
        loader.close()
        return loader.get_pixbuf()
    except Exception:
        return None


def load_svg_texture(svg_text: str) -> Gdk.Texture | None:
    if not svg_text:
        return None
    try:
        loader = GdkPixbuf.PixbufLoader.new()
        loader.write(svg_text.encode("utf-8"))
        loader.close()
        pixbuf = loader.get_pixbuf()
    except Exception:
        return None
    if not pixbuf:
        return None
    try:
        return Gdk.Texture.new_for_pixbuf(pixbuf)
    except Exception:
        return None


def scale_album_art(
    pixbuf: GdkPixbuf.Pixbuf, max_size: int = ALBUM_TILE_SIZE
) -> GdkPixbuf.Pixbuf:
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    if width <= max_size and height <= max_size:
        return pixbuf
    scale = min(max_size / width, max_size / height)
    new_width = max(1, int(width * scale))
    new_height = max(1, int(height * scale))
    return pixbuf.scale_simple(
        new_width,
        new_height,
        GdkPixbuf.InterpType.BILINEAR,
    )


def blur_pixbuf(
    pixbuf: GdkPixbuf.Pixbuf,
    scale: float = 0.08,
    passes: int = 2,
) -> GdkPixbuf.Pixbuf:
    width = pixbuf.get_width()
    height = pixbuf.get_height()
    if width < 2 or height < 2:
        return pixbuf
    scale = max(0.02, min(scale, 1.0))
    target_width = max(1, int(width * scale))
    target_height = max(1, int(height * scale))
    blurred = pixbuf
    for _ in range(max(1, passes)):
        small = blurred.scale_simple(
            target_width,
            target_height,
            GdkPixbuf.InterpType.BILINEAR,
        )
        if small is None:
            return blurred
        blurred = small.scale_simple(
            width,
            height,
            GdkPixbuf.InterpType.BILINEAR,
        )
        if blurred is None:
            return small
    return blurred


def apply_album_art(
    picture: Gtk.Picture,
    pixbuf: GdkPixbuf.Pixbuf,
    image_url: str,
    sidebar_art: Gtk.Picture,
    sidebar_url: str,
) -> bool:
    try:
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    except Exception:
        return False
    _store_cached_texture(
        image_url,
        max(pixbuf.get_width(), pixbuf.get_height()),
        texture,
    )
    if sidebar_art is not None and picture is sidebar_art:
        if not sidebar_url or sidebar_url != image_url:
            return False
    else:
        if hasattr(picture, "expected_image_url"):
            expected = picture.expected_image_url
            if not expected or expected != image_url:
                return False
    try:
        picture.set_paintable(texture)
    except Exception:
        return False
    return False


def _fetch_album_art(
    image_url: str,
    picture: Gtk.Picture,
    size: int,
    auth_token: str,
    cache_dir: str,
) -> None:
    pixbuf = fetch_album_art_pixbuf(image_url, auth_token, cache_dir)
    if pixbuf is None:
        return
    pixbuf = scale_album_art(pixbuf, size)
    GLib.idle_add(apply_album_art, picture, pixbuf, image_url, None, None)


def _fetch_album_background(
    image_url: str,
    picture: Gtk.Picture,
    auth_token: str,
    cache_dir: str,
) -> None:
    pixbuf = fetch_album_art_pixbuf(image_url, auth_token, cache_dir)
    if pixbuf is None:
        return
    pixbuf = scale_album_art(pixbuf, DETAIL_BG_SIZE)
    pixbuf = blur_pixbuf(
        pixbuf,
        scale=DETAIL_BG_BLUR_SCALE,
        passes=DETAIL_BG_BLUR_PASSES,
    )
    GLib.idle_add(apply_album_art, picture, pixbuf, image_url, None, None)
