from gi.repository import Gtk

from constants import DEFAULT_SERVER_URL
from ui import ui_utils
from utils import normalize_server_url


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

    hint = Gtk.Label(label="Connect to Music Assistant to load your library.")
    hint.add_css_class("status-label")
    hint.set_xalign(0)
    hint.set_wrap(True)
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

    return settings_box


def on_settings_clicked(app, _button: Gtk.Button) -> None:
    if app.main_stack:
        current_view = app.main_stack.get_visible_child_name()
        if current_view != "settings":
            app.settings_previous_view = current_view
        app.main_stack.set_visible_child_name("settings")


def on_settings_back_clicked(app, _button: Gtk.Button) -> None:
    target_view = app.settings_previous_view or "home"
    if app.main_stack:
        app.main_stack.set_visible_child_name(target_view)
    app.settings_previous_view = None


def on_settings_connect_clicked(app, _button: Gtk.Button) -> None:
    if not app.settings_server_entry or not app.settings_token_entry:
        return
    server_url = normalize_server_url(app.settings_server_entry.get_text())
    if not server_url:
        app.set_status(
            "Enter a valid server address to connect.",
            is_error=True,
        )
        return
    auth_token = app.settings_token_entry.get_text().strip()
    app.connect_to_server(server_url, auth_token, persist=True)


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
