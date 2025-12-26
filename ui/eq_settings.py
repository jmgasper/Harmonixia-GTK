import logging
import math
import threading

from gi.repository import GLib, Gtk, Pango

try:
    from gi.repository import PangoCairo
except (ImportError, ValueError):
    PangoCairo = None

from music_assistant import eq_presets

_LOGGER = logging.getLogger(__name__)
_PRESET_CACHE = None
_PRESET_DETAILS_CACHE = None
_PRESET_LOAD_INFLIGHT = False
_PRESET_LOAD_ERROR = ""
EQ_PRESET_RESULT_LIMIT = 200
EQ_GRAPH_GAIN_RANGE = max(
    24.0,
    abs(eq_presets.MIN_GAIN),
    abs(eq_presets.MAX_GAIN),
)
EQ_GRAPH_MIN_FREQ = eq_presets.MIN_FREQUENCY
EQ_GRAPH_MAX_FREQ = eq_presets.MAX_FREQUENCY
EQ_GRAPH_MIN_GAIN = -EQ_GRAPH_GAIN_RANGE
EQ_GRAPH_MAX_GAIN = EQ_GRAPH_GAIN_RANGE
EQ_GRAPH_SAMPLE_POINTS = 240
EQ_GRAPH_SAMPLE_RATE = 48000.0
EQ_GRAPH_DEFAULT_Q = eq_presets.SHELF_APPROX_Q
EQ_GRAPH_FREQ_TICKS = (
    20,
    50,
    100,
    200,
    500,
    1000,
    2000,
    5000,
    10000,
    20000,
)
EQ_GRAPH_GAIN_TICKS = tuple(
    range(
        int(EQ_GRAPH_MIN_GAIN),
        int(EQ_GRAPH_MAX_GAIN) + 1,
        6,
    )
)
EQ_GRAPH_LOG_MIN = math.log10(EQ_GRAPH_MIN_FREQ)
EQ_GRAPH_LOG_RANGE = math.log10(EQ_GRAPH_MAX_FREQ) - EQ_GRAPH_LOG_MIN


def build_eq_section(app) -> Gtk.Widget:
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    card.add_css_class("settings-card")

    header = Gtk.Label(label="Equalizer")
    header.set_xalign(0)
    header.set_margin_top(2)
    header.set_margin_bottom(4)
    card.append(header)

    hint = Gtk.Label(
        label="Adjust the audio EQ for local playback. Changes apply in real time."
    )
    hint.add_css_class("status-label")
    hint.set_xalign(0)
    hint.set_wrap(True)
    card.append(hint)

    grid = Gtk.Grid(column_spacing=10, row_spacing=10)

    toggle_label = Gtk.Label(label="Enable equalizer", xalign=0)
    toggle_switch = Gtk.Switch()
    toggle_switch.set_halign(Gtk.Align.START)
    grid.attach(toggle_label, 0, 0, 1, 1)
    grid.attach(toggle_switch, 1, 0, 1, 1)

    search_label = Gtk.Label(label="Search presets", xalign=0)
    search_entry = Gtk.SearchEntry()
    search_entry.set_placeholder_text("Type a name, brand, or creator")
    search_entry.set_hexpand(True)
    grid.attach(search_label, 0, 1, 1, 1)
    grid.attach(search_entry, 1, 1, 1, 1)

    preset_label = Gtk.Label(label="Preset", xalign=0)
    preset_combo = Gtk.ComboBoxText()
    preset_combo.set_hexpand(True)
    grid.attach(preset_label, 0, 2, 1, 1)
    grid.attach(preset_combo, 1, 2, 1, 1)

    apply_button = Gtk.Button(label="Apply Preset")
    apply_button.set_halign(Gtk.Align.START)
    grid.attach(Gtk.Label(label=""), 0, 3, 1, 1)
    grid.attach(apply_button, 1, 3, 1, 1)

    card.append(grid)

    graph_overlay = Gtk.Overlay()
    graph_overlay.set_hexpand(True)

    graph_area = Gtk.DrawingArea()
    graph_area.add_css_class("eq-graph")
    graph_area.set_hexpand(True)
    graph_area.set_vexpand(False)
    graph_area.set_size_request(-1, 220)
    graph_area.eq_curve = []
    graph_area.set_draw_func(_draw_eq_graph, None)
    graph_overlay.set_child(graph_area)

    graph_placeholder = Gtk.Label(label="Loading presets...")
    graph_placeholder.add_css_class("eq-graph-placeholder")
    graph_placeholder.set_wrap(True)
    graph_placeholder.set_justify(Gtk.Justification.CENTER)
    graph_placeholder.set_halign(Gtk.Align.CENTER)
    graph_placeholder.set_valign(Gtk.Align.CENTER)
    graph_overlay.add_overlay(graph_placeholder)
    if hasattr(graph_overlay, "set_overlay_pass_through"):
        graph_overlay.set_overlay_pass_through(graph_placeholder, True)
    elif hasattr(graph_placeholder, "set_can_target"):
        graph_placeholder.set_can_target(False)

    card.append(graph_overlay)

    details_scroller = Gtk.ScrolledWindow()
    details_scroller.set_policy(
        Gtk.PolicyType.NEVER,
        Gtk.PolicyType.AUTOMATIC,
    )
    details_scroller.set_min_content_height(200)

    details_view = Gtk.TextView()
    details_view.set_editable(False)
    details_view.set_cursor_visible(False)
    details_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    details_view.set_left_margin(8)
    details_view.set_right_margin(8)
    details_view.set_top_margin(6)
    details_view.set_bottom_margin(6)
    details_scroller.set_child(details_view)
    card.append(details_scroller)

    attribution = Gtk.Label(label=eq_presets.OPRA_ATTRIBUTION_TEXT)
    attribution.add_css_class("status-label")
    attribution.set_xalign(0)
    attribution.set_wrap(True)
    card.append(attribution)

    app.eq_preset_combo = preset_combo
    app.eq_preset_search_entry = search_entry
    app.eq_toggle_switch = toggle_switch
    app.eq_details_view = details_view
    app.eq_graph_area = graph_area
    app.eq_graph_placeholder = graph_placeholder

    eq_state = app.audio_pipeline.get_eq_state()
    app.eq_enabled = bool(eq_state.get("enabled", False))
    toggle_switch.set_active(app.eq_enabled)

    toggle_handler_id = toggle_switch.connect(
        "state-set",
        lambda switch, state: on_eq_toggle_changed(app, switch, state),
    )
    toggle_switch._eq_toggle_handler_id = toggle_handler_id
    handler_id = preset_combo.connect(
        "changed",
        lambda combo: on_eq_preset_changed(app, combo),
    )
    preset_combo._eq_changed_handler_id = handler_id
    search_entry.connect(
        "search-changed",
        lambda entry: on_eq_preset_search_changed(app, entry),
    )
    apply_button.connect(
        "clicked",
        lambda _button: on_eq_preset_changed(app, preset_combo),
    )

    _set_details_text(details_view, "Loading presets...")
    preset_combo.set_sensitive(False)
    card.connect("map", lambda *_: _ensure_presets_loaded(app))

    return card


def on_eq_toggle_changed(app, _switch: Gtk.Switch, state: bool) -> bool:
    app.audio_pipeline.set_eq_enabled(state)
    app.eq_enabled = bool(state)
    app.persist_eq_settings()
    return False


def _set_eq_toggle_state(app, active: bool) -> None:
    toggle_switch = app.eq_toggle_switch
    if not toggle_switch:
        return
    handler_id = getattr(toggle_switch, "_eq_toggle_handler_id", None)
    if handler_id:
        toggle_switch.handler_block(handler_id)
    toggle_switch.set_active(active)
    if handler_id:
        toggle_switch.handler_unblock(handler_id)


def on_eq_preset_search_changed(app, entry: Gtk.SearchEntry) -> None:
    query = (entry.get_text() or "").strip()
    _refresh_preset_results(app, query=query)


def on_eq_preset_changed(app, combo: Gtk.ComboBoxText) -> None:
    preset_id = combo.get_active_id()
    if not preset_id or preset_id == "none":
        app.eq_selected_preset = None
        app.audio_pipeline.set_eq_enabled(False)
        app.eq_enabled = False
        _set_eq_toggle_state(app, False)
        update_preset_details(app, None)
        app.persist_eq_settings()
        _refresh_preset_results(app)
        return
    app.eq_selected_preset = preset_id
    presets = _PRESET_DETAILS_CACHE
    if not presets:
        if _PRESET_LOAD_ERROR:
            _set_details_text(app.eq_details_view, "Failed to load presets.")
            _update_eq_graph(app, None, "Failed to load presets.")
        else:
            _set_details_text(
                app.eq_details_view,
                "Presets are still loading. Please try again.",
            )
            _update_eq_graph(app, None, "Loading presets...")
            _ensure_presets_loaded(app)
        return
    preset = eq_presets.get_preset_by_name(preset_id, presets)
    if not preset:
        _set_details_text(
            app.eq_details_view,
            "Selected preset not found.",
        )
        _update_eq_graph(app, None, "Selected preset not found.")
        return
    update_preset_details(app, preset_id)
    try:
        eq_presets.apply_preset_to_pipeline(
            preset,
            app.audio_pipeline,
        )
    except Exception as exc:
        _LOGGER.warning("Failed to apply EQ preset %s: %s", preset_id, exc)
        _set_details_text(
            app.eq_details_view,
            f"Failed to apply preset: {exc}",
        )
        return
    app.eq_enabled = True
    _set_eq_toggle_state(app, True)
    app.persist_eq_settings()


def update_preset_details(app, preset_id: str | None) -> None:
    if not app.eq_details_view:
        return
    if not preset_id or preset_id == "none":
        _set_details_text(app.eq_details_view, "No preset selected.")
        _update_eq_graph(
            app,
            None,
            "Select a preset to view its EQ curve.",
        )
        return
    presets = _PRESET_DETAILS_CACHE
    if not presets:
        if _PRESET_LOAD_ERROR:
            _set_details_text(app.eq_details_view, "Failed to load presets.")
            _update_eq_graph(app, None, "Failed to load presets.")
        else:
            _set_details_text(
                app.eq_details_view,
                "Presets are still loading. Please try again.",
            )
            _update_eq_graph(app, None, "Loading presets...")
        return
    try:
        details = eq_presets.get_preset_details(preset_id, presets)
    except Exception as exc:
        _LOGGER.warning(
            "Failed to load EQ preset details for %s: %s",
            preset_id,
            exc,
        )
        _set_details_text(
            app.eq_details_view,
            f"Failed to load preset details: {exc}",
        )
        _update_eq_graph(app, None, "Failed to load preset details.")
        return
    if not details:
        _set_details_text(app.eq_details_view, "No preset details available.")
        _update_eq_graph(app, None, "No EQ curve data available.")
        return
    formatted = _format_preset_details(details)
    _set_details_text(app.eq_details_view, formatted)
    filters = _extract_filters(details)
    if filters:
        _update_eq_graph(app, details, None)
    else:
        _update_eq_graph(app, details, "No EQ curve data available.")


def populate_preset_dropdown(
    combo: Gtk.ComboBoxText,
    presets: list,
) -> None:
    combo.remove_all()
    combo.append("none", "None")
    for preset in presets or []:
        preset_id = _get_value(
            preset,
            ("id", "preset_id", "name"),
        )
        display_name = _get_value(
            preset,
            ("display_name", "name", "label"),
        )
        preset_id = str(preset_id or display_name or preset)
        display_name = str(display_name or preset_id)
        combo.append(preset_id, display_name)


def _refresh_preset_results(
    app,
    presets: list | None = None,
    query: str | None = None,
) -> None:
    combo = app.eq_preset_combo
    if not combo:
        return
    if presets is None:
        if _PRESET_CACHE is None:
            return
        presets = _PRESET_CACHE
    if query is None:
        query = _get_preset_search_query(app)
    results = _filter_presets(presets, query)
    options = _build_preset_options(presets, results, app.eq_selected_preset)
    handler_id = getattr(combo, "_eq_changed_handler_id", None)
    if handler_id:
        combo.handler_block(handler_id)
    populate_preset_dropdown(combo, options)
    combo.set_sensitive(True)

    selected_id = app.eq_selected_preset or "none"
    combo.set_active_id(selected_id)
    if combo.get_active_id() is None:
        combo.set_active_id("none")
    if handler_id:
        combo.handler_unblock(handler_id)
    update_preset_details(app, combo.get_active_id())


def _get_preset_search_query(app) -> str:
    entry = getattr(app, "eq_preset_search_entry", None)
    if not entry:
        return ""
    return (entry.get_text() or "").strip()


def _build_preset_options(
    presets: list,
    results: list,
    selected_id: str | None,
) -> list:
    options = list(results)
    if selected_id and selected_id != "none":
        if not _preset_in_list(options, selected_id):
            selected_preset = _find_preset_by_id(presets, selected_id)
            if selected_preset:
                options.insert(0, selected_preset)
            else:
                options.insert(0, {"id": selected_id, "name": selected_id})
    return options


def _preset_in_list(presets: list, preset_id: str) -> bool:
    if not preset_id:
        return False
    return any(_matches_preset_id(preset, preset_id) for preset in presets or [])


def _find_preset_by_id(presets: list, preset_id: str) -> dict | None:
    for preset in presets or []:
        if _matches_preset_id(preset, preset_id):
            return preset
    return None


def _matches_preset_id(preset, preset_id: str) -> bool:
    target = _normalize_text(preset_id)
    for candidate in (
        _get_value(preset, ("id", "preset_id")),
        _get_value(preset, ("display_name", "name", "label")),
    ):
        if _normalize_text(candidate) == target:
            return True
    return False


def _filter_presets(presets: list, query: str) -> list:
    tokens = [token for token in _normalize_text(query).split() if token]
    if not tokens:
        return []
    matches = []
    for preset in presets or []:
        search_blob = _build_preset_search_blob(preset)
        if all(token in search_blob for token in tokens):
            matches.append(preset)
    matches.sort(
        key=lambda preset: _normalize_text(
            _get_value(preset, ("display_name", "name", "label"))
        )
    )
    return matches[:EQ_PRESET_RESULT_LIMIT]


def _build_preset_search_blob(preset) -> str:
    parts = (
        _get_value(preset, ("display_name", "name", "label")),
        _get_value(preset, ("manufacturer", "maker", "brand")),
        _get_value(preset, ("model", "device", "product")),
        _get_value(preset, ("creator", "author")),
        _get_value(preset, ("id", "preset_id")),
    )
    return " ".join(
        _normalize_text(part) for part in parts if part not in (None, "")
    )


def _normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip().casefold()


def _ensure_presets_loaded(app) -> None:
    global _PRESET_LOAD_INFLIGHT
    if _PRESET_CACHE is not None:
        _populate_preset_data(app, _PRESET_CACHE, _PRESET_LOAD_ERROR)
        return
    if _PRESET_LOAD_INFLIGHT:
        return
    _PRESET_LOAD_INFLIGHT = True
    thread = threading.Thread(
        target=_load_presets_worker,
        args=(app,),
        daemon=True,
    )
    thread.start()


def _load_presets_worker(app) -> None:
    presets = []
    full_presets = []
    error = ""
    try:
        full_presets = eq_presets.load_presets()
        presets = eq_presets.get_preset_list(full_presets)
    except Exception as exc:
        error = str(exc) or "Unknown error"
        try:
            full_presets = eq_presets.load_cached_presets()
            presets = eq_presets.get_preset_list(full_presets)
        except Exception:
            presets = []
            full_presets = []
    GLib.idle_add(_on_presets_loaded, app, presets, full_presets, error)


def _on_presets_loaded(
    app,
    presets: list,
    full_presets: list,
    error: str,
) -> None:
    global _PRESET_CACHE, _PRESET_DETAILS_CACHE, _PRESET_LOAD_INFLIGHT, _PRESET_LOAD_ERROR
    _PRESET_LOAD_INFLIGHT = False
    if presets:
        _PRESET_CACHE = presets
    if full_presets:
        _PRESET_DETAILS_CACHE = full_presets
    if error:
        _PRESET_LOAD_ERROR = error
    else:
        _PRESET_LOAD_ERROR = ""
    _populate_preset_data(app, presets, error)


def _populate_preset_data(app, presets: list, error: str) -> None:
    if not presets and _PRESET_CACHE:
        presets = _PRESET_CACHE
    _refresh_preset_results(app, presets=presets)

    if error and not presets:
        _set_details_text(app.eq_details_view, "Failed to load presets.")
        _update_eq_graph(app, None, "Failed to load presets.")
    elif error and not app.eq_selected_preset:
        _set_details_text(
            app.eq_details_view,
            "Loaded cached presets. Unable to refresh.",
        )
        _update_eq_graph(app, None, "Loaded cached presets.")


def _set_details_text(details_view: Gtk.TextView | None, text: str) -> None:
    if not details_view:
        return
    buffer = details_view.get_buffer()
    buffer.set_text(text or "")


def _update_eq_graph(
    app,
    details: dict | None,
    placeholder_text: str | None,
) -> None:
    graph_area = getattr(app, "eq_graph_area", None)
    if not graph_area:
        return
    graph_area.eq_curve = _build_eq_curve(details)
    graph_area.queue_draw()

    placeholder = getattr(app, "eq_graph_placeholder", None)
    if not placeholder:
        return
    if placeholder_text:
        placeholder.set_text(placeholder_text)
        placeholder.set_visible(True)
    else:
        placeholder.set_visible(False)


def _build_eq_curve(details: dict | None) -> list[tuple[float, float]]:
    if not details:
        return []
    filters = _extract_filters(details)
    if not filters:
        return []
    return _calculate_eq_curve(filters)


def _calculate_eq_curve(filters: list) -> list[tuple[float, float]]:
    parsed_filters = []
    for filter_data in filters:
        params = _extract_filter_params(filter_data)
        if params:
            parsed_filters.append(params)
    if not parsed_filters:
        return []

    curve = []
    for freq in _log_space(
        EQ_GRAPH_MIN_FREQ,
        EQ_GRAPH_MAX_FREQ,
        EQ_GRAPH_SAMPLE_POINTS,
    ):
        total_db = 0.0
        for f0, gain_db, q_value in parsed_filters:
            total_db += _peaking_eq_db(freq, f0, q_value, gain_db)
        total_db = max(EQ_GRAPH_MIN_GAIN, min(EQ_GRAPH_MAX_GAIN, total_db))
        curve.append((freq, total_db))
    return curve


def _log_space(start: float, stop: float, count: int) -> list[float]:
    if count <= 1:
        return [start]
    log_start = math.log10(start)
    step = (math.log10(stop) - log_start) / (count - 1)
    return [10 ** (log_start + step * index) for index in range(count)]


def _extract_filter_params(filter_data) -> tuple[float, float, float] | None:
    freq = _coerce_float(_get_value(filter_data, ("freq", "frequency", "f")))
    gain = _coerce_float(_get_value(filter_data, ("gain", "gain_db", "db")))
    if freq is None or gain is None:
        return None
    if abs(gain) < 1e-3:
        return None
    freq = max(EQ_GRAPH_MIN_FREQ, min(EQ_GRAPH_MAX_FREQ, freq))

    q_value = _coerce_float(
        _get_value(filter_data, ("q", "Q", "quality", "q_factor"))
    )
    if q_value is None or q_value <= 0:
        bandwidth = _coerce_float(_get_value(filter_data, ("bandwidth",)))
        if bandwidth and bandwidth > 0:
            q_value = freq / bandwidth
    if q_value is None or q_value <= 0:
        q_value = EQ_GRAPH_DEFAULT_Q
    return freq, gain, q_value


def _peaking_eq_db(
    freq: float,
    center_freq: float,
    q_value: float,
    gain_db: float,
) -> float:
    if freq <= 0 or center_freq <= 0 or q_value <= 0:
        return 0.0
    a = 10 ** (gain_db / 40.0)
    omega0 = 2.0 * math.pi * center_freq / EQ_GRAPH_SAMPLE_RATE
    alpha = math.sin(omega0) / (2.0 * q_value)
    cos_omega0 = math.cos(omega0)

    b0 = 1.0 + alpha * a
    b1 = -2.0 * cos_omega0
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * cos_omega0
    a2 = 1.0 - alpha / a

    omega = 2.0 * math.pi * freq / EQ_GRAPH_SAMPLE_RATE
    cos_w = math.cos(omega)
    sin_w = math.sin(omega)
    cos_2w = math.cos(2.0 * omega)
    sin_2w = math.sin(2.0 * omega)

    num_real = b0 + b1 * cos_w + b2 * cos_2w
    num_imag = -(b1 * sin_w + b2 * sin_2w)
    den_real = a0 + a1 * cos_w + a2 * cos_2w
    den_imag = -(a1 * sin_w + a2 * sin_2w)
    denom = den_real * den_real + den_imag * den_imag
    if denom <= 0:
        return 0.0
    magnitude = math.sqrt(
        (num_real * num_real + num_imag * num_imag) / denom
    )
    if magnitude <= 0:
        return 0.0
    return 20.0 * math.log10(magnitude)


def _log_position(freq: float) -> float:
    freq = max(EQ_GRAPH_MIN_FREQ, min(EQ_GRAPH_MAX_FREQ, freq))
    return (math.log10(freq) - EQ_GRAPH_LOG_MIN) / EQ_GRAPH_LOG_RANGE


def _gain_to_y(gain: float, top: float, height: float) -> float:
    return top + (
        (EQ_GRAPH_MAX_GAIN - gain)
        / (EQ_GRAPH_MAX_GAIN - EQ_GRAPH_MIN_GAIN)
        * height
    )


def _format_frequency_label(freq: float) -> str:
    if freq >= 1000:
        value = freq / 1000.0
        if value.is_integer():
            return f"{int(value)}k"
        return f"{value:.1f}k"
    return str(int(freq))


def _format_gain_label(gain: float) -> str:
    if abs(gain) < 1e-6:
        return "0"
    sign = "+" if gain > 0 else ""
    return f"{sign}{int(gain)}"


def _draw_eq_graph(
    area: Gtk.DrawingArea,
    cr,
    width: int,
    height: int,
    _data,
) -> None:
    curve = getattr(area, "eq_curve", []) or []
    left = 42.0
    right = 12.0
    top = 12.0
    bottom = 24.0
    plot_width = width - left - right
    plot_height = height - top - bottom
    if plot_width <= 0 or plot_height <= 0:
        return

    grid_color = (0.17, 0.2, 0.26, 0.6)
    axis_color = (0.3, 0.35, 0.43, 0.9)
    curve_color = (0.94, 0.96, 0.98, 1.0)
    label_color = (0.65, 0.7, 0.76, 0.95)

    cr.set_line_width(1.0)
    for freq in EQ_GRAPH_FREQ_TICKS:
        x = left + _log_position(freq) * plot_width
        cr.set_source_rgba(*grid_color)
        cr.move_to(x, top)
        cr.line_to(x, top + plot_height)
        cr.stroke()

    for gain in EQ_GRAPH_GAIN_TICKS:
        y = _gain_to_y(gain, top, plot_height)
        if gain == 0:
            cr.set_source_rgba(*axis_color)
        else:
            cr.set_source_rgba(*grid_color)
        cr.move_to(left, y)
        cr.line_to(left + plot_width, y)
        cr.stroke()

    if curve:
        cr.set_source_rgba(*curve_color)
        cr.set_line_width(2.0)
        for index, (freq, gain) in enumerate(curve):
            x = left + _log_position(freq) * plot_width
            y = _gain_to_y(gain, top, plot_height)
            if index == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
    else:
        cr.set_source_rgba(curve_color[0], curve_color[1], curve_color[2], 0.6)
        cr.set_line_width(1.5)
        y = _gain_to_y(0.0, top, plot_height)
        cr.move_to(left, y)
        cr.line_to(left + plot_width, y)
        cr.stroke()

    if PangoCairo is None:
        return

    cr.set_source_rgba(*label_color)
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription("Noto Sans 8"))

    for gain in EQ_GRAPH_GAIN_TICKS:
        label = _format_gain_label(gain)
        layout.set_text(label, -1)
        _, logical = layout.get_pixel_extents()
        x = left - logical.width - 6
        y = _gain_to_y(gain, top, plot_height) - (logical.height / 2)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    for freq in EQ_GRAPH_FREQ_TICKS:
        label = _format_frequency_label(freq)
        layout.set_text(label, -1)
        _, logical = layout.get_pixel_extents()
        x = left + _log_position(freq) * plot_width - (logical.width / 2)
        y = top + plot_height + 4
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)


def _format_preset_details(details) -> str:
    lines = []
    name = _get_value(details, ("display_name", "name", "preset_name"))
    manufacturer = _get_value(details, ("manufacturer", "maker", "brand"))
    model = _get_value(details, ("model", "device", "product"))
    creator = _get_value(details, ("creator", "author"))
    description = _get_value(details, ("description", "desc"))

    if name:
        lines.append(f"Name: {name}")
    if manufacturer:
        lines.append(f"Manufacturer: {manufacturer}")
    if model:
        lines.append(f"Model: {model}")
    if creator:
        lines.append(f"Creator: {creator}")

    if description:
        lines.append("")
        lines.append("Description:")
        lines.append(str(description))

    filters = _extract_filters(details)
    band_count = _get_value(details, ("band_count", "num_bands"))
    if band_count is None and filters:
        band_count = len(filters)
    supported_bands = _get_value(
        details,
        ("supported_bands", "supported_band_count", "max_bands"),
    )
    dropped_filters = _get_value(
        details,
        ("dropped_filters", "dropped", "unsupported_filters"),
    )
    dropped_count = _count_items(dropped_filters)

    band_lines = []
    if band_count is not None:
        band_lines.append(f"Band count: {band_count}")
    if supported_bands is not None:
        band_lines.append(f"Supported bands: {supported_bands}")
    if dropped_filters is not None:
        band_lines.append(f"Dropped filters: {dropped_count}")
    if band_lines:
        lines.append("")
        lines.extend(band_lines)
        if dropped_count:
            lines.append(
                "Warning: Some filters were dropped because they are unsupported."
            )

    if filters:
        lines.append("")
        lines.append("Filters:")
        for index, filter_data in enumerate(filters, start=1):
            lines.append(_format_filter_line(index, filter_data))

    if not lines:
        return "No preset details available."
    return "\n".join(lines)


def _format_filter_line(index: int, filter_data) -> str:
    freq = _get_value(filter_data, ("freq", "frequency", "f"))
    gain = _get_value(filter_data, ("gain", "gain_db", "db"))
    q_value = _get_value(filter_data, ("q", "Q", "quality", "q_factor"))
    if q_value is None:
        q_value = _get_value(filter_data, ("bandwidth",))
    filter_type = _get_value(filter_data, ("type", "filter_type"))

    parts = []
    if freq is not None:
        parts.append(f"{_format_number(freq)} Hz")
    if gain is not None:
        parts.append(_format_gain(gain))
    if q_value is not None:
        parts.append(f"Q {_format_number(q_value)}")
    if filter_type:
        parts.append(str(filter_type))

    if parts:
        return f"{index}. " + ", ".join(parts)
    return f"{index}. (no data)"


def _extract_filters(details) -> list:
    for key in ("filters", "filter_list", "band_configs", "bands"):
        value = _get_value(details, (key,))
        if isinstance(value, list):
            return value
    return []


def _count_items(value) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int):
        return value
    return 0


def _get_value(source, keys: tuple) -> object | None:
    for key in keys:
        if isinstance(source, dict):
            value = source.get(key)
        else:
            value = getattr(source, key, None)
        if value not in (None, ""):
            return value
    return None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value) -> str:
    if isinstance(value, (int, float)):
        formatted = f"{value:.2f}"
        formatted = formatted.rstrip("0").rstrip(".")
        return formatted
    return str(value)


def _format_gain(value) -> str:
    if isinstance(value, (int, float)):
        formatted = f"{value:+.2f}"
        formatted = formatted.rstrip("0").rstrip(".")
        return f"{formatted} dB"
    return f"{value} dB"
