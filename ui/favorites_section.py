from gi.repository import Gtk, Pango

from ui import track_table


def build_favorites_section(app) -> Gtk.Widget:
    overlay = Gtk.Overlay()
    overlay.add_css_class("playlist-detail")
    overlay.set_hexpand(True)
    overlay.set_vexpand(True)

    background = Gtk.Picture()
    background.add_css_class("playlist-detail-bg")
    background.set_hexpand(True)
    background.set_vexpand(True)
    background.set_halign(Gtk.Align.FILL)
    background.set_valign(Gtk.Align.FILL)
    background.set_can_shrink(True)
    if hasattr(background, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        background.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(background, "set_keep_aspect_ratio"):
        background.set_keep_aspect_ratio(True)
    overlay.set_child(background)

    dimmer = Gtk.Box()
    dimmer.add_css_class("playlist-detail-dim")
    dimmer.set_hexpand(True)
    dimmer.set_vexpand(True)
    dimmer.set_halign(Gtk.Align.FILL)
    dimmer.set_valign(Gtk.Align.FILL)
    overlay.add_overlay(dimmer)

    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    container.add_css_class("playlist-detail-content")
    container.set_hexpand(True)
    container.set_vexpand(True)
    container.set_halign(Gtk.Align.FILL)
    container.set_valign(Gtk.Align.FILL)

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    title = Gtk.Label(label="Favorites", xalign=0)
    title.add_css_class("playlist-detail-title")
    title.set_wrap(True)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    subtitle = Gtk.Label(label="All favorited tracks", xalign=0)
    subtitle.add_css_class("detail-artist")
    subtitle.set_wrap(True)
    subtitle.set_ellipsize(Pango.EllipsizeMode.END)
    header.append(title)
    header.append(subtitle)
    container.append(header)

    tracks_label = Gtk.Label(label="Tracks")
    tracks_label.add_css_class("section-title")
    tracks_label.set_xalign(0)
    container.append(tracks_label)

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    container.append(status)

    tracks_table = track_table.build_tracks_table(
        app,
        store_attr="favorites_tracks_store",
        sort_model_attr="favorites_tracks_sort_model",
        selection_attr="favorites_tracks_selection",
        view_attr="favorites_tracks_view",
        use_track_art=True,
    )
    tracks_scroller = Gtk.ScrolledWindow()
    tracks_scroller.set_policy(
        Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC
    )
    tracks_scroller.set_child(tracks_table)
    if hasattr(tracks_scroller, "set_propagate_natural_height"):
        tracks_scroller.set_propagate_natural_height(True)
    tracks_scroller.set_vexpand(False)
    container.append(tracks_scroller)

    overlay.add_overlay(container)

    app.favorites_status_label = status
    return overlay
