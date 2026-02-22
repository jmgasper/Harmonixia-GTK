# This module adapts EQ preset concepts from pulseaudio-equalizer-ladspa
# (GPL-3.0 licensed): https://github.com/pulseaudio-equalizer-ladspa/equalizer
# OPRA (Open Parametric Room Acoustics) data is CC BY-SA 4.0 licensed.
# Attribution required; share-alike applies to adaptations of the dataset.
# https://github.com/opra-project/OPRA
"""OPRA EQ preset fetching, caching, and conversion helpers."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING
from urllib import request

from constants import ALBUM_ART_CACHE_DIR

if TYPE_CHECKING:
    from .audio_pipeline import AudioPipeline

OPRA_DATABASE_URL = "https://raw.githubusercontent.com/opra-project/OPRA/main/dist/database_v1.jsonl"
OPRA_CACHE_FILE = "opra_presets.jsonl"
OPRA_CACHE_EXPIRY_DAYS = 7
OPRA_ATTRIBUTION_TEXT = """
EQ Presets: OPRA (Open Parametric Room Acoustics)
Licensed under CC BY-SA 4.0
Data sources: AutoEQ, oratory1990, and community contributors
https://github.com/opra-project/OPRA

EQ Implementation: Concepts from pulseaudio-equalizer-ladspa
Licensed under GPL-3.0
https://github.com/pulseaudio-equalizer-ladspa/equalizer
""".strip()
MIN_FREQUENCY = 20.0
MAX_FREQUENCY = 20000.0
MIN_GAIN = -24.0
MAX_GAIN = 12.0
SHELF_FILTER_HANDLING = "approximate"
SHELF_APPROX_Q = 0.7
SHELF_APPROX_GAIN_SCALE = 1.0

_OPRA_REPO_URL = "https://github.com/opra-project/OPRA"
_OPRA_CACHE_SECONDS = OPRA_CACHE_EXPIRY_DAYS * 24 * 60 * 60
_logger = logging.getLogger(__name__)
_preset_cache: list[dict] | None = None

class BandConfigList(list):
    """List of EQ band configs with dropped filter metadata."""
    def __init__(self, iterable: list[dict] | None = None, dropped_filters: list[dict] | None = None) -> None:
        super().__init__(iterable or [])
        self.dropped_filters = dropped_filters or []

def _get_cache_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), ALBUM_ART_CACHE_DIR)

def _get_cache_path() -> str:
    return os.path.join(_get_cache_dir(), OPRA_CACHE_FILE)

def _is_cache_valid(path: str) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) < _OPRA_CACHE_SECONDS
    except OSError:
        return False

def _normalize_text(value: object) -> str:
    return "" if value is None else str(value).strip().lower()

def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _first_of(payload: dict, keys: tuple[str, ...]) -> object | None:
    for key in keys:
        value = payload.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        return value
    return None

def _build_display_name(name: object, manufacturer: object, model: object, creator: object) -> str:
    base_name = str(name).strip() if name else ""
    if not base_name:
        parts = [str(value).strip() for value in (manufacturer, model) if value]
        base_name = " ".join(dict.fromkeys(part for part in parts if part))
    if not base_name:
        base_name = "Unknown Preset"
    if creator:
        creator_value = str(creator).strip()
        if creator_value and _normalize_text(creator_value) not in _normalize_text(base_name):
            base_name = f"{base_name} - {creator_value}"
    return base_name

def _is_shelf_filter(filter_type: object) -> bool:
    normalized = _normalize_text(filter_type)
    return bool(normalized) and ("shelf" in normalized or normalized in ("lshelf", "hshelf"))

def _describe_filter(filter_entry: dict, reason: str) -> dict:
    return {
        "frequency": _coerce_float(filter_entry.get("frequency")),
        "gain": _coerce_float(filter_entry.get("gain")),
        "Q": _coerce_float(filter_entry.get("Q")),
        "type": filter_entry.get("type"),
        "reason": reason,
    }

def _collect_gstreamer_bands(filters: list[object], preset_name: str, log_warnings: bool = True) -> BandConfigList:
    band_configs: list[dict] = []
    dropped_filters: list[dict] = []
    for filter_entry in filters:
        if not isinstance(filter_entry, dict):
            if log_warnings:
                _logger.warning("Invalid filter entry for preset %s: %s", preset_name, filter_entry)
            dropped_filters.append({"raw": filter_entry, "reason": "invalid_filter"})
            continue
        freq = _coerce_float(filter_entry.get("frequency"))
        gain = _coerce_float(filter_entry.get("gain"))
        q_value = _coerce_float(filter_entry.get("Q"))
        filter_type = filter_entry.get("type")
        filter_type_normalized = _normalize_text(filter_type)
        if _is_shelf_filter(filter_type_normalized):
            if SHELF_FILTER_HANDLING == "approximate":
                if freq is None or gain is None:
                    if log_warnings:
                        _logger.warning("Skipping shelf EQ band with missing data for preset %s: %s", preset_name, filter_entry)
                    dropped_filters.append(_describe_filter(filter_entry, "incomplete_shelf"))
                    continue
                if q_value is None:
                    q_value = SHELF_APPROX_Q
                gain *= SHELF_APPROX_GAIN_SCALE
                filter_type_normalized = "peaking"
            else:
                if log_warnings:
                    _logger.warning("Skipping unsupported shelf filter for preset %s: %s", preset_name, filter_entry)
                dropped_filters.append(_describe_filter(filter_entry, "unsupported_shelf"))
                continue
        if freq is None or gain is None or q_value is None:
            if log_warnings:
                _logger.warning("Skipping incomplete EQ band for preset %s: %s", preset_name, filter_entry)
            dropped_filters.append(_describe_filter(filter_entry, "incomplete"))
            continue
        if q_value <= 0:
            if log_warnings:
                _logger.warning("Skipping non-positive Q for preset %s: %s", preset_name, q_value)
            dropped_filters.append(_describe_filter(filter_entry, "invalid_q"))
            continue
        if filter_type_normalized and filter_type_normalized not in ("peak", "peak/dip", "peaking", "dip"):
            _logger.debug("Non-peak filter for preset %s (%s); converting as peak.", preset_name, filter_entry.get("type"))
        if freq < MIN_FREQUENCY or freq > MAX_FREQUENCY:
            if log_warnings:
                _logger.warning("EQ band frequency out of range for preset %s: %s", preset_name, freq)
            freq = max(MIN_FREQUENCY, min(MAX_FREQUENCY, freq))
        if gain < MIN_GAIN or gain > MAX_GAIN:
            if log_warnings:
                _logger.warning("EQ band gain out of range for preset %s: %s", preset_name, gain)
            gain = max(MIN_GAIN, min(MAX_GAIN, gain))
        bandwidth = freq / q_value
        if bandwidth <= 0:
            if log_warnings:
                _logger.warning("Invalid EQ band bandwidth for preset %s: %s", preset_name, bandwidth)
            dropped_filters.append(_describe_filter(filter_entry, "invalid_bandwidth"))
            continue
        if bandwidth > MAX_FREQUENCY:
            _logger.debug("Clamping EQ band bandwidth for preset %s: %s", preset_name, bandwidth)
            bandwidth = MAX_FREQUENCY
        band_configs.append({"freq": freq, "bandwidth": bandwidth, "gain": gain})
    return BandConfigList(band_configs, dropped_filters)

def _normalize_filter(filter_entry: object, preset_label: str) -> dict | None:
    if not isinstance(filter_entry, dict):
        _logger.warning("Invalid filter entry for preset %s: %s", preset_label, filter_entry); return None
    return {
        "frequency": _coerce_float(filter_entry.get("frequency") or filter_entry.get("freq")),
        "gain": _coerce_float(filter_entry.get("gain") or filter_entry.get("gain_db") or filter_entry.get("db")),
        "Q": _coerce_float(filter_entry.get("Q") or filter_entry.get("q")),
        "type": filter_entry.get("type") or filter_entry.get("filter_type"),
    }

def _normalize_preset(entry: dict) -> dict | None:
    name = _first_of(entry, ("name", "title"))
    manufacturer = _first_of(entry, ("manufacturer", "brand", "vendor", "make"))
    model = _first_of(entry, ("model", "device", "product"))
    creator = _first_of(entry, ("creator", "author", "source"))
    description = _first_of(entry, ("description", "notes"))
    filters = entry.get("filters") or entry.get("bands") or entry.get("eq") or []
    if not isinstance(filters, list):
        _logger.warning("Invalid filter list for preset %s", name or entry.get("id") or "unknown"); filters = []
    display_name = _build_display_name(name or model, manufacturer, model, creator)
    normalized_filters = [normalized for filter_entry in filters if (normalized := _normalize_filter(filter_entry, display_name))]
    identifier = entry.get("id") or entry.get("identifier") or display_name
    preset = {
        "id": identifier,
        "name": name or model or display_name,
        "manufacturer": manufacturer,
        "model": model or name,
        "creator": creator,
        "description": description,
        "filters": normalized_filters,
        "display_name": display_name,
    }
    if "popularity" in entry:
        preset["popularity"] = entry.get("popularity")
    return preset

def _split_opra_product_id(product_id: object) -> tuple[str | None, str | None]:
    if not isinstance(product_id, str):
        return None, None
    if "::" in product_id:
        vendor_id, model_id = product_id.split("::", 1)
    else:
        vendor_id, model_id = "", product_id
    vendor_id = vendor_id.strip() or None
    model_id = model_id.strip() or None
    return vendor_id, model_id

def _clean_opra_details(details: object) -> str:
    if not details:
        return ""
    text = str(details).strip()
    prefix = "measured by "
    if text.lower().startswith(prefix):
        text = text[len(prefix):].strip()
    return text

def _build_opra_display_name(manufacturer: object, model: object, details: object) -> str:
    parts = [str(value).strip() for value in (manufacturer, model) if value]
    base = " ".join(part for part in parts if part)
    if not base:
        base = "Unknown Preset"
    detail_text = _clean_opra_details(details)
    if detail_text:
        return f"{base} - {detail_text}"
    return base

def _normalize_opra_eq_entry(entry: dict, products: dict, vendors: dict) -> dict | None:
    if not isinstance(entry, dict):
        return None
    if entry.get("type") != "eq":
        return None
    data = entry.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    product_id = data.get("product_id")
    vendor_id = None
    product_name = None
    if isinstance(product_id, str):
        product = products.get(product_id)
        if isinstance(product, dict):
            product_name = product.get("name")
            vendor_id = product.get("vendor_id") or vendor_id
        parsed_vendor_id, parsed_model_id = _split_opra_product_id(product_id)
        if not vendor_id:
            vendor_id = parsed_vendor_id
        if not product_name:
            product_name = parsed_model_id
    vendor_name = vendors.get(vendor_id) if vendor_id else None
    author = data.get("author")
    details = data.get("details")
    display_name = _build_opra_display_name(
        vendor_name or vendor_id,
        product_name,
        details,
    )
    parameters = data.get("parameters") or {}
    if not isinstance(parameters, dict):
        parameters = {}
    filters = parameters.get("bands") or []
    if not isinstance(filters, list):
        _logger.warning("Invalid filter list for preset %s", display_name)
        filters = []
    normalized_filters = [
        normalized for filter_entry in filters
        if (normalized := _normalize_filter(filter_entry, display_name))
    ]
    identifier = entry.get("id") or display_name
    preset = {
        "id": identifier,
        "name": display_name,
        "manufacturer": vendor_name or vendor_id,
        "model": product_name,
        "creator": author,
        "description": details,
        "filters": normalized_filters,
        "display_name": display_name,
    }
    if "gain_db" in parameters:
        preset["preamp_gain"] = _coerce_float(parameters.get("gain_db"))
    if "type" in data:
        preset["eq_type"] = data.get("type")
    return preset

def fetch_opra_database() -> str | None:
    cache_path = _get_cache_path()
    cache_dir = os.path.dirname(cache_path)
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except OSError as exc:
        _logger.warning("Unable to create cache directory %s: %s", cache_dir, exc)
    if _is_cache_valid(cache_path):
        _logger.info("Using cached OPRA presets: %s", cache_path); return cache_path
    try:
        _logger.info("Downloading OPRA presets from %s", OPRA_DATABASE_URL)
        with request.urlopen(OPRA_DATABASE_URL, timeout=30) as response:
            payload = response.read()
        with open(cache_path, "wb") as handle:
            handle.write(payload)
        _logger.info("Cached OPRA presets to %s (%s bytes)", cache_path, len(payload))
        return cache_path
    except Exception as exc:
        _logger.warning("Failed to download OPRA presets: %s", exc)
        if os.path.exists(cache_path):
            _logger.info("Falling back to cached OPRA presets: %s", cache_path); return cache_path
        _logger.error("No cached OPRA presets available.")
    return None

def parse_jsonl(path: str) -> list[dict]:
    presets: list[dict] = []
    if not path:
        return presets
    opra_eq_entries: list[dict] = []
    opra_products: dict[str, dict] = {}
    opra_vendors: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    _logger.warning("Failed to parse OPRA JSONL line %s: %s", line_number, exc); continue
                if not isinstance(payload, dict):
                    _logger.warning("Skipping non-object OPRA entry on line %s", line_number); continue
                entry_type = payload.get("type")
                data = payload.get("data")
                if entry_type in ("vendor", "product", "eq") and isinstance(data, dict):
                    # OPRA JSONL stores vendors/products/eq separately; collect maps first.
                    if entry_type == "vendor":
                        vendor_name = data.get("name")
                        vendor_id = payload.get("id")
                        if vendor_name and vendor_id:
                            opra_vendors[vendor_id] = vendor_name
                    elif entry_type == "product":
                        product_id = payload.get("id")
                        if product_id:
                            opra_products[product_id] = data
                    else:
                        opra_eq_entries.append(payload)
                    continue
                preset = _normalize_preset(payload)
                if preset is not None:
                    presets.append(preset)
    except OSError as exc:
        _logger.warning("Failed to read OPRA cache %s: %s", path, exc)
    if opra_eq_entries:
        for entry in opra_eq_entries:
            preset = _normalize_opra_eq_entry(entry, opra_products, opra_vendors)
            if preset is not None:
                presets.append(preset)
    return presets

def load_cached_presets() -> list[dict]:
    if _preset_cache is not None:
        return list(_preset_cache)
    cache_path = _get_cache_path()
    if not os.path.exists(cache_path):
        return []
    return parse_jsonl(cache_path)


def load_presets_from_cache_only() -> list[dict] | None:
    cache_path = _get_cache_path()
    if not _is_cache_valid(cache_path):
        return None
    return parse_jsonl(cache_path)

def convert_opra_to_gstreamer(preset: dict) -> BandConfigList:
    if not isinstance(preset, dict):
        return BandConfigList()
    filters = preset.get("filters") or []
    name = preset.get("display_name") or preset.get("name") or preset.get("id") or "Unknown Preset"
    if not isinstance(filters, list):
        _logger.warning("Invalid filter list for preset %s", name)
        filters = []
    return _collect_gstreamer_bands(filters, name, log_warnings=True)

def load_presets(force_reload: bool = False) -> list[dict]:
    global _preset_cache
    if _preset_cache is not None and not force_reload:
        return list(_preset_cache)
    cache_path = fetch_opra_database()
    if not cache_path:
        return []
    presets = parse_jsonl(cache_path)
    _preset_cache = presets
    return list(presets)

def get_preset_list(presets: list[dict] | None = None) -> list[dict]:
    presets = presets or load_presets()
    return [{"name": preset.get("display_name") or preset.get("name"), "manufacturer": preset.get("manufacturer"), "creator": preset.get("creator"), "id": preset.get("id")} for preset in presets]

def get_preset_by_name(name: str, presets: list[dict] | None = None) -> dict | None:
    if not name:
        return None
    presets = presets or load_presets()
    target = _normalize_text(name)
    for preset in presets:
        for candidate in (preset.get("id"), preset.get("display_name"), preset.get("name")):
            if _normalize_text(candidate) == target:
                return preset
    return None

def get_preset_details(preset: dict | str | None, presets: list[dict] | None = None) -> dict | None:
    if preset is None:
        return None
    if isinstance(preset, str):
        preset = get_preset_by_name(preset, presets)
    if not isinstance(preset, dict):
        return None
    filters = preset.get("filters") or []
    if not isinstance(filters, list):
        filters = []
    name = preset.get("display_name") or preset.get("name") or preset.get("id") or "Unknown Preset"
    band_summary = _collect_gstreamer_bands(filters, name, log_warnings=False)
    dropped_filters = band_summary.dropped_filters
    unsupported_filters = [filter_entry for filter_entry in dropped_filters if filter_entry.get("reason") == "unsupported_shelf"]
    return {
        "name": preset.get("display_name") or preset.get("name"),
        "description": preset.get("description"),
        "manufacturer": preset.get("manufacturer"),
        "model": preset.get("model"),
        "creator": preset.get("creator"),
        "num_bands": len(filters),
        "num_supported_bands": len(band_summary),
        "num_dropped_filters": len(dropped_filters),
        "dropped_filters": dropped_filters,
        "unsupported_filters": unsupported_filters,
        "filters": [{"frequency": band.get("frequency"), "gain": band.get("gain"), "Q": band.get("Q"), "type": band.get("type")} for band in filters if isinstance(band, dict)],
        "opra_repository": _OPRA_REPO_URL,
        "attribution": OPRA_ATTRIBUTION_TEXT,
    }

def apply_preset_to_pipeline(preset: dict | str | None, audio_pipeline: AudioPipeline, presets: list[dict] | None = None) -> BandConfigList:
    if preset is None:
        return BandConfigList()
    if isinstance(preset, str):
        preset = get_preset_by_name(preset, presets)
    if not isinstance(preset, dict):
        _logger.warning("Unable to apply preset: %s", preset); return BandConfigList()
    band_configs = convert_opra_to_gstreamer(preset)
    audio_pipeline.configure_eq_bands(len(band_configs), band_configs)
    audio_pipeline.set_eq_enabled(True)
    return band_configs

def filter_presets_by_manufacturer(presets: list[dict], manufacturer: str) -> list[dict]:
    if not manufacturer:
        return list(presets)
    target = _normalize_text(manufacturer)
    return [preset for preset in presets if target in _normalize_text(preset.get("manufacturer"))]

def filter_presets_by_creator(presets: list[dict], creator: str) -> list[dict]:
    if not creator:
        return list(presets)
    target = _normalize_text(creator)
    return [preset for preset in presets if target in _normalize_text(preset.get("creator"))]

def sort_presets(presets: list[dict], sort_by: str = "name", reverse: bool = False) -> list[dict]:
    sort_key = _normalize_text(sort_by)
    if sort_key == "manufacturer":
        key_func = lambda item: (_normalize_text(item.get("manufacturer")), _normalize_text(item.get("display_name") or item.get("name")))
    elif sort_key == "popularity":
        key_func = lambda item: item.get("popularity") or 0
    else:
        key_func = lambda item: _normalize_text(item.get("display_name") or item.get("name"))
    return sorted(presets, key=key_func, reverse=reverse)

def search_presets(presets: list[dict], keyword: str) -> list[dict]:
    if not keyword:
        return list(presets)
    target = _normalize_text(keyword)
    return [preset for preset in presets if target in " ".join([_normalize_text(preset.get("display_name")), _normalize_text(preset.get("name")), _normalize_text(preset.get("model"))])]
