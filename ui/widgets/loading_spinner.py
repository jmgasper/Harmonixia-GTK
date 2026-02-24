from gi.repository import Gtk


def create_loading_overlay() -> tuple[
    Gtk.Widget, Gtk.Spinner, Gtk.Label, Gtk.ProgressBar, Gtk.Label
]:
    loading_overlay = Gtk.CenterBox()
    loading_overlay.add_css_class("library-loading-overlay")
    loading_overlay.set_hexpand(True)
    loading_overlay.set_vexpand(True)
    loading_overlay.set_halign(Gtk.Align.FILL)
    loading_overlay.set_valign(Gtk.Align.FILL)
    loading_overlay.set_visible(False)

    indicator = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    indicator.add_css_class("library-loading-indicator")
    indicator.set_halign(Gtk.Align.CENTER)
    indicator.set_valign(Gtk.Align.CENTER)

    spinner_shell = Gtk.CenterBox()
    spinner_shell.add_css_class("library-loading-shell")
    spinner_shell.set_halign(Gtk.Align.CENTER)
    spinner_shell.set_valign(Gtk.Align.CENTER)

    spinner = Gtk.Spinner()
    spinner.add_css_class("library-loading-spinner")
    spinner.set_size_request(110, 110)
    spinner_shell.set_center_widget(spinner)

    loading_label = Gtk.Label(label="Loading library...")
    loading_label.add_css_class("library-loading-label")
    loading_label.set_xalign(0.5)

    indicator.append(spinner_shell)
    indicator.append(loading_label)

    progress_bar = Gtk.ProgressBar()
    progress_bar.add_css_class("library-loading-progress")
    progress_bar.set_pulse_step(0.12)
    progress_bar.set_visible(False)
    indicator.append(progress_bar)

    sub_label = Gtk.Label()
    sub_label.add_css_class("library-loading-sub-label")
    sub_label.set_xalign(0.5)
    sub_label.set_visible(False)
    indicator.append(sub_label)

    loading_overlay.set_center_widget(indicator)

    return loading_overlay, spinner, loading_label, progress_bar, sub_label
