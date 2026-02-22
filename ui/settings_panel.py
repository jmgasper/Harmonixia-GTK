import logging
import os
import threading

from gi.repository import GLib, Gtk

from constants import DEFAULT_SERVER_URL
from music_assistant import eq_presets, playback
from ui import eq_settings, ui_utils
from utils import normalize_server_url

DEFAULT_SETTINGS_HINT = "Connect to Music Assistant to load your library."
ONBOARDING_SETTINGS_HINT = (
    "Enter your Music Assistant server address and click Connect to get started."
)


def update_settings_hint(app) -> None:
    label = getattr(app, "settings_hint_label", None)
    if not label:
        return
    if getattr(app, "server_url", ""):
        label.set_label(DEFAULT_SETTINGS_HINT)
    else:
        label.set_label(ONBOARDING_SETTINGS_HINT)


def _set_settings_status(app, message: str, is_error: bool = False) -> None:
    label = getattr(app, "settings_status_label", None)
    if not label:
        return
    if is_error:
        label.add_css_class("error")
    else:
        label.remove_css_class("error")
    label.set_label(message)
    label.set_visible(bool(message))


def _reset_settings_status(app) -> None:
    label = getattr(app, "settings_status_label", None)
    if not label:
        return
    label.remove_css_class("error")
    label.set_label("")
    label.set_visible(False)


def _get_connection_inputs(app) -> tuple[str, str] | None:
    if not app.settings_server_entry or not app.settings_token_entry:
        return None
    server_url = normalize_server_url(app.settings_server_entry.get_text())
    if not server_url:
        _set_settings_status(
            app,
            "Enter a valid server address to connect.",
            is_error=True,
        )
        return None
    auth_token = app.settings_token_entry.get_text().strip()
    return server_url, auth_token


def build_settings_section(app) -> Gtk.Widget:
    settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    settings_box.add_css_class("settings-section")
    settings_box.set_margin_top(16)
    settings_box.set_margin_bottom(16)
    settings_box.set_margin_start(16)
    settings_box.set_margin_end(16)

    top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    top_bar.set_halign(Gtk.Align.START)
    back_button = Gtk.Button()
    back_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    back_content.append(Gtk.Image.new_from_icon_name("go-previous-symbolic"))
    back_content.append(Gtk.Label(label="Back"))
    back_button.set_child(back_content)
    back_button.connect(
        "clicked",
        lambda button: on_settings_back_clicked(app, button),
    )
    top_bar.append(back_button)
    settings_box.append(top_bar)

    header = Gtk.Label(label="Settings")
    header.add_css_class("section-title")
    header.set_xalign(0)
    settings_box.append(header)

    hint = Gtk.Label()
    hint.add_css_class("status-label")
    hint.set_xalign(0)
    hint.set_wrap(True)
    app.settings_hint_label = hint
    update_settings_hint(app)
    settings_box.append(hint)

    form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    form.add_css_class("settings-card")

    grid = Gtk.Grid(column_spacing=10, row_spacing=10)

    server_label = Gtk.Label(label="Server address", xalign=0)
    server_entry = Gtk.Entry()
    server_entry.set_placeholder_text(DEFAULT_SERVER_URL)
    server_entry.set_hexpand(True)
    server_entry.set_input_purpose(Gtk.InputPurpose.URL)
    if app.server_url:
        server_entry.set_text(app.server_url)

    token_label = Gtk.Label(label="Access token", xalign=0)
    token_entry = Gtk.Entry()
    token_entry.set_placeholder_text("Optional")
    token_entry.set_hexpand(True)
    if app.auth_token:
        token_entry.set_text(app.auth_token)

    grid.attach(server_label, 0, 0, 1, 1)
    grid.attach(server_entry, 1, 0, 1, 1)
    grid.attach(token_label, 0, 1, 1, 1)
    grid.attach(token_entry, 1, 1, 1, 1)

    form.append(grid)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    test_button = Gtk.Button(label="Test Connection")
    test_button.connect(
        "clicked",
        lambda button: on_settings_test_clicked(app, button),
    )
    actions.append(test_button)
    connect_button = Gtk.Button(label="Connect")
    connect_button.add_css_class("suggested-action")
    connect_button.connect(
        "clicked",
        lambda button: on_settings_connect_clicked(app, button),
    )
    actions.append(connect_button)

    form.append(actions)
    settings_box.append(form)

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    app.settings_status_label = status
    settings_box.append(status)

    output_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    output_card.add_css_class("settings-card")
    output_header = Gtk.Label(label="Audio Output")
    output_header.set_xalign(0)
    output_header.set_margin_top(2)
    output_header.set_margin_bottom(4)
    output_card.append(output_header)

    output_hint = Gtk.Label(
        label=(
            "Override the output backend if PipeWire is silent. "
            "Leave blank for auto."
        )
    )
    output_hint.add_css_class("status-label")
    output_hint.set_xalign(0)
    output_hint.set_wrap(True)
    output_card.append(output_hint)

    output_grid = Gtk.Grid(column_spacing=10, row_spacing=10)

    backend_label = Gtk.Label(label="Output backend", xalign=0)
    backend_combo = Gtk.ComboBoxText()
    backend_combo.append("auto", "Auto (PipeWire)")
    backend_combo.append("pulse", "PulseAudio (pipewire-pulse)")
    backend_combo.append("alsa", "ALSA (direct)")
    backend_combo.set_hexpand(True)
    backend_value = (app.output_backend or "").strip().casefold()
    if backend_value == "pulseaudio":
        backend_value = "pulse"
    if backend_value not in ("pulse", "alsa"):
        backend_value = "auto"
    backend_combo.set_active_id(backend_value)

    pulse_label = Gtk.Label(label="PulseAudio device", xalign=0)
    pulse_entry = Gtk.Entry()
    pulse_entry.set_placeholder_text(
        "e.g. alsa_output.usb-SMSL_SMSL_USB_AUDIO-00.iec958-stereo"
    )
    pulse_entry.set_hexpand(True)
    if app.output_pulse_device:
        pulse_entry.set_text(app.output_pulse_device)

    alsa_label = Gtk.Label(label="ALSA device", xalign=0)
    alsa_entry = Gtk.Entry()
    alsa_entry.set_placeholder_text("e.g. iec958:3 or hw:3,0")
    alsa_entry.set_hexpand(True)
    if app.output_alsa_device:
        alsa_entry.set_text(app.output_alsa_device)

    output_grid.attach(backend_label, 0, 0, 1, 1)
    output_grid.attach(backend_combo, 1, 0, 1, 1)
    output_grid.attach(pulse_label, 0, 1, 1, 1)
    output_grid.attach(pulse_entry, 1, 1, 1, 1)
    output_grid.attach(alsa_label, 0, 2, 1, 1)
    output_grid.attach(alsa_entry, 1, 2, 1, 1)
    output_card.append(output_grid)

    output_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    output_apply_button = Gtk.Button(label="Apply Output Settings")
    output_apply_button.connect(
        "clicked",
        lambda button: on_output_settings_apply_clicked(app, button),
    )
    output_actions.append(output_apply_button)
    output_card.append(output_actions)

    settings_box.append(output_card)

    playback_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    playback_card.add_css_class("settings-card")
    playback_header = Gtk.Label(label="Playback")
    playback_header.set_xalign(0)
    playback_header.set_margin_top(2)
    playback_header.set_margin_bottom(4)
    playback_card.append(playback_header)

    playback_hint = Gtk.Label(
        label=(
            "Per-player playback tuning for crossfade and flow mode."
        )
    )
    playback_hint.add_css_class("status-label")
    playback_hint.set_xalign(0)
    playback_hint.set_wrap(True)
    playback_card.append(playback_hint)

    playback_grid = Gtk.Grid(column_spacing=10, row_spacing=10)
    crossfade_label = Gtk.Label(label="Crossfade (seconds)", xalign=0)
    crossfade_spin = Gtk.SpinButton.new_with_range(0, 10, 1)
    crossfade_spin.set_numeric(True)
    crossfade_spin.set_hexpand(True)
    crossfade_spin.set_value(0)

    flow_mode_label = Gtk.Label(label="Flow Mode", xalign=0)
    flow_mode_switch = Gtk.Switch()
    flow_mode_switch.set_halign(Gtk.Align.START)

    playback_grid.attach(crossfade_label, 0, 0, 1, 1)
    playback_grid.attach(crossfade_spin, 1, 0, 1, 1)
    playback_grid.attach(flow_mode_label, 0, 1, 1, 1)
    playback_grid.attach(flow_mode_switch, 1, 1, 1, 1)
    playback_card.append(playback_grid)

    playback_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    playback_apply_button = Gtk.Button(label="Apply Playback Settings")
    playback_apply_button.connect(
        "clicked",
        lambda button: on_playback_settings_apply_clicked(app, button),
    )
    playback_actions.append(playback_apply_button)
    playback_card.append(playback_actions)

    playback_status = Gtk.Label()
    playback_status.add_css_class("status-label")
    playback_status.set_xalign(0)
    playback_status.set_wrap(True)
    playback_status.set_visible(False)
    playback_card.append(playback_status)

    settings_box.append(playback_card)

    eq_card = eq_settings.build_eq_section(app)
    app.eq_settings_card = eq_card
    settings_box.append(eq_card)

    gtk_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    gtk_card.add_css_class("settings-card")
    gtk_header = Gtk.Label(label="GTK")
    gtk_header.set_xalign(0)
    gtk_header.set_margin_top(2)
    gtk_header.set_margin_bottom(4)
    gtk_card.append(gtk_header)

    gtk_version, gtk_theme = ui_utils.get_gtk_environment_info()
    gtk_grid = Gtk.Grid(column_spacing=10, row_spacing=6)
    gtk_version_label = Gtk.Label(label="Version", xalign=0)
    gtk_version_value = Gtk.Label(label=gtk_version, xalign=0)
    gtk_theme_label = Gtk.Label(label="Theme", xalign=0)
    gtk_theme_value = Gtk.Label(label=gtk_theme, xalign=0)
    gtk_grid.attach(gtk_version_label, 0, 0, 1, 1)
    gtk_grid.attach(gtk_version_value, 1, 0, 1, 1)
    gtk_grid.attach(gtk_theme_label, 0, 1, 1, 1)
    gtk_grid.attach(gtk_theme_value, 1, 1, 1, 1)
    gtk_card.append(gtk_grid)
    settings_box.append(gtk_card)

    if os.getenv("MA_GTK_DEBUG"):
        gtk_debug_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        gtk_debug_card.add_css_class("settings-card")
        gtk_debug_header = Gtk.Label(label="GTK Debug")
        gtk_debug_header.set_xalign(0)
        gtk_debug_header.set_margin_top(2)
        gtk_debug_header.set_margin_bottom(4)
        gtk_debug_card.append(gtk_debug_header)

        gtk_debug_hint = Gtk.Label(
            label=(
                "Enable the GTK Inspector to identify which widget draws the row "
                "separators. Press Ctrl+Shift+D after enabling."
            )
        )
        gtk_debug_hint.add_css_class("status-label")
        gtk_debug_hint.set_xalign(0)
        gtk_debug_hint.set_wrap(True)
        gtk_debug_card.append(gtk_debug_hint)

        debug_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        debug_button = Gtk.Button(label="Enable Inspector")
        debug_button.connect(
            "clicked",
            lambda button: on_gtk_debug_enable_clicked(app, button),
        )
        debug_actions.append(debug_button)
        gtk_debug_card.append(debug_actions)

        debug_status = Gtk.Label()
        debug_status.add_css_class("status-label")
        debug_status.set_xalign(0)
        debug_status.set_wrap(True)
        debug_status.set_visible(False)
        app.gtk_debug_status_label = debug_status
        gtk_debug_card.append(debug_status)
        settings_box.append(gtk_debug_card)

    app.settings_server_entry = server_entry
    app.settings_token_entry = token_entry
    app.settings_connect_button = connect_button
    app.settings_output_backend_combo = backend_combo
    app.settings_pulse_device_entry = pulse_entry
    app.settings_alsa_device_entry = alsa_entry
    app.settings_crossfade_spin = crossfade_spin
    app.settings_flow_mode_switch = flow_mode_switch
    app.settings_playback_apply_button = playback_apply_button
    app.settings_playback_status_label = playback_status
    server_entry.connect(
        "activate",
        lambda *_: on_settings_connect_clicked(app, connect_button),
    )
    token_entry.connect(
        "activate",
        lambda *_: on_settings_connect_clicked(app, connect_button),
    )
    pulse_entry.connect(
        "activate",
        lambda *_: on_output_settings_apply_clicked(app, output_apply_button),
    )
    alsa_entry.connect(
        "activate",
        lambda *_: on_output_settings_apply_clicked(app, output_apply_button),
    )

    scrolled_window = Gtk.ScrolledWindow()
    scrolled_window.set_policy(
        Gtk.PolicyType.NEVER,
        Gtk.PolicyType.AUTOMATIC,
    )
    scrolled_window.set_vexpand(True)
    scrolled_window.set_child(settings_box)
    app.settings_scrolled_window = scrolled_window
    GLib.idle_add(app.refresh_playback_settings)

    return scrolled_window


def on_settings_clicked(app, _button: Gtk.Button) -> None:
    if app.main_stack:
        current_view = app.main_stack.get_visible_child_name()
        if current_view != "settings":
            app.settings_previous_view = current_view
        app.main_stack.set_visible_child_name("settings")
    update_settings_hint(app)


def navigate_to_eq_settings(app) -> None:
    on_settings_clicked(app, None)
    threading.Thread(
        target=_refresh_eq_presets_on_open,
        daemon=True,
    ).start()

    def _scroll_to_eq() -> bool:
        if not app.settings_scrolled_window or not app.eq_settings_card:
            return False
        vadjustment = app.settings_scrolled_window.get_vadjustment()
        if not vadjustment:
            return False
        target_value = app.eq_settings_card.get_allocation().y - 50
        max_value = max(
            0.0,
            vadjustment.get_upper() - vadjustment.get_page_size(),
        )
        if target_value < 0:
            target_value = 0.0
        elif target_value > max_value:
            target_value = max_value
        vadjustment.set_value(target_value)
        return False

    GLib.idle_add(_scroll_to_eq)


def _refresh_eq_presets_on_open() -> None:
    try:
        eq_presets.load_presets()
    except Exception as exc:
        logging.getLogger(__name__).debug(
            "Failed to refresh EQ presets on settings open: %s",
            exc,
        )


def on_settings_back_clicked(app, _button: Gtk.Button) -> None:
    target_view = app.settings_previous_view or "home"
    if app.main_stack:
        app.main_stack.set_visible_child_name(target_view)
    app.settings_previous_view = None


def on_settings_test_clicked(app, _button: Gtk.Button) -> None:
    _reset_settings_status(app)
    inputs = _get_connection_inputs(app)
    if not inputs:
        return
    server_url, auth_token = inputs
    _set_settings_status(app, "Testing connection...", is_error=False)

    def on_success() -> None:
        _set_settings_status(
            app,
            f"Connection to {server_url} succeeded. Settings not saved.",
            is_error=False,
        )

    def on_error(error: str) -> None:
        message = error or f"Unable to connect to {server_url}."
        _set_settings_status(app, message, is_error=True)

    app.connect_to_server(
        server_url,
        auth_token,
        persist=False,
        on_success=on_success,
        on_error=on_error,
    )


def on_settings_connect_clicked(app, _button: Gtk.Button) -> None:
    _reset_settings_status(app)
    inputs = _get_connection_inputs(app)
    if not inputs:
        return
    server_url, auth_token = inputs
    _set_settings_status(app, "Connecting…", is_error=False)

    def on_success() -> None:
        _set_settings_status(
            app,
            f"Connected to {server_url}.",
            is_error=False,
        )

    def on_error(error: str) -> None:
        message = error or f"Unable to connect to {server_url}."
        _set_settings_status(app, message, is_error=True)

    app.connect_to_server(
        server_url,
        auth_token,
        persist=True,
        on_success=on_success,
        on_error=on_error,
    )
    update_settings_hint(app)


def on_gtk_debug_enable_clicked(app, _button: Gtk.Button) -> None:
    Gtk.Window.set_interactive_debugging(True)
    try:
        flags = Gtk.get_debug_flags()
        Gtk.set_debug_flags(flags | Gtk.DebugFlags.INTERACTIVE)
    except (AttributeError, TypeError):
        pass
    if app.gtk_debug_status_label is not None:
        app.gtk_debug_status_label.set_text(
            "GTK Inspector enabled. Press Ctrl+Shift+D to open it."
        )
        app.gtk_debug_status_label.set_visible(True)


def on_output_settings_apply_clicked(app, _button: Gtk.Button) -> None:
    if (
        app.settings_output_backend_combo is None
        or app.settings_pulse_device_entry is None
        or app.settings_alsa_device_entry is None
    ):
        return
    backend = app.settings_output_backend_combo.get_active_id() or "auto"
    if backend == "auto":
        backend = ""
    pulse_device = app.settings_pulse_device_entry.get_text().strip()
    alsa_device = app.settings_alsa_device_entry.get_text().strip()
    changed = (
        backend != (app.output_backend or "")
        or pulse_device != (app.output_pulse_device or "")
        or alsa_device != (app.output_alsa_device or "")
    )
    if not changed:
        return
    app.output_backend = backend
    app.output_pulse_device = pulse_device
    app.output_alsa_device = alsa_device
    app.persist_output_selection()
    app.on_local_output_selection_changed()


def refresh_playback_settings(app) -> None:
    if (
        getattr(app, "settings_crossfade_spin", None) is None
        or getattr(app, "settings_flow_mode_switch", None) is None
    ):
        return
    player_id = app.output_manager.preferred_player_id if app.output_manager else None
    app.settings_playback_player_id = player_id
    if not app.server_url or not player_id:
        _set_playback_settings_status(
            app,
            "Select an output to load playback settings.",
            is_error=False,
        )
        return
    _set_playback_settings_status(app, "Loading playback settings...")
    thread = threading.Thread(
        target=app._load_playback_settings_worker,
        args=(player_id,),
        daemon=True,
    )
    thread.start()


def _load_playback_settings_worker(app, player_id: str) -> None:
    error = ""
    crossfade_duration = 0
    flow_mode = False
    try:
        payload = app.client_session.run(
            app.server_url,
            app.auth_token,
            app._fetch_player_playback_settings_async,
            player_id,
        )
        crossfade_duration = _coerce_crossfade_duration(
            payload.get("crossfade_duration")
        )
        flow_mode = _coerce_flow_mode(payload.get("flow_mode"))
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(
        app.on_player_playback_settings_loaded,
        player_id,
        crossfade_duration,
        flow_mode,
        error,
    )


async def _fetch_player_playback_settings_async(app, client, player_id: str) -> dict:
    if hasattr(client.players, "fetch_state"):
        await client.players.fetch_state()
    player = None
    if hasattr(client.players, "get"):
        player = client.players.get(player_id)
    if not player:
        return {
            "crossfade_duration": 0,
            "flow_mode": False,
        }
    return {
        "crossfade_duration": getattr(player, "crossfade_duration", 0),
        "flow_mode": getattr(player, "flow_mode", False),
    }


def on_player_playback_settings_loaded(
    app,
    player_id: str,
    crossfade_duration: int,
    flow_mode: bool,
    error: str,
) -> None:
    current_player_id = (
        app.output_manager.preferred_player_id if app.output_manager else None
    )
    if current_player_id != player_id:
        return
    if error:
        _set_playback_settings_status(
            app,
            f"Unable to load playback settings: {error}",
            is_error=True,
        )
        return
    app.settings_crossfade_spin.set_value(float(crossfade_duration))
    app.settings_flow_mode_switch.set_active(bool(flow_mode))
    _set_playback_settings_status(app, "")


def on_playback_settings_apply_clicked(app, _button: Gtk.Button) -> None:
    player_id = app.output_manager.preferred_player_id if app.output_manager else None
    if not app.server_url or not player_id:
        _set_playback_settings_status(
            app,
            "Select an output to apply playback settings.",
            is_error=True,
        )
        return
    if (
        getattr(app, "settings_crossfade_spin", None) is None
        or getattr(app, "settings_flow_mode_switch", None) is None
    ):
        return
    crossfade_duration = int(round(app.settings_crossfade_spin.get_value()))
    flow_mode = bool(app.settings_flow_mode_switch.get_active())
    _set_playback_settings_status(app, "Applying playback settings...")
    thread = threading.Thread(
        target=_apply_playback_settings_worker,
        args=(app, player_id, crossfade_duration, flow_mode),
        daemon=True,
    )
    thread.start()


def _apply_playback_settings_worker(
    app,
    player_id: str,
    crossfade_duration: int,
    flow_mode: bool,
) -> None:
    error = ""
    try:
        playback.update_player_settings(
            app.client_session,
            app.server_url,
            app.auth_token,
            player_id,
            crossfade_duration,
            flow_mode,
        )
    except Exception as exc:
        error = str(exc)
    GLib.idle_add(
        _on_playback_settings_applied,
        app,
        player_id,
        error,
    )


def _on_playback_settings_applied(app, player_id: str, error: str) -> bool:
    current_player_id = (
        app.output_manager.preferred_player_id if app.output_manager else None
    )
    if current_player_id != player_id:
        return False
    if error:
        _set_playback_settings_status(
            app,
            f"Unable to apply playback settings: {error}",
            is_error=True,
        )
        return False
    _set_playback_settings_status(app, "Playback settings applied.")
    return False


def _set_playback_settings_status(
    app,
    message: str,
    is_error: bool = False,
) -> None:
    label = getattr(app, "settings_playback_status_label", None)
    if not label:
        return
    if is_error:
        label.add_css_class("error")
    else:
        label.remove_css_class("error")
    label.set_label(message)
    label.set_visible(bool(message))


def _coerce_crossfade_duration(value: object) -> int:
    try:
        number = int(value)
    except Exception:
        return 0
    return max(0, min(10, number))


def _coerce_flow_mode(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in ("1", "true", "yes", "on")
    return bool(value)
