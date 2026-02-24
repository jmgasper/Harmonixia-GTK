from gi.repository import Gtk


def make_eq_bars_widget(size: int = 14) -> Gtk.Box:
    container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    container.add_css_class("eq-bars")
    container.set_size_request(size, size)

    for index in range(1, 4):
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        bar.add_css_class("eq-bar")
        bar.add_css_class(f"eq-bar-{index}")
        bar.set_size_request(0, 0)
        bar.set_valign(Gtk.Align.END)
        container.append(bar)

    return container
