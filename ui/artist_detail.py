from gi.repository import Gtk

from ui import track_table, ui_utils


def build_artist_albums_section(app) -> Gtk.Widget:
    container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    container.add_css_class("search-section-content")
    container.set_hexpand(True)
    container.set_vexpand(True)

    top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    back_button = Gtk.Button()
    back_button.add_css_class("artist-back")
    back_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    back_content.append(Gtk.Image.new_from_icon_name("go-previous-symbolic"))
    back_content.append(Gtk.Label(label="Back"))
    back_button.set_child(back_content)
    back_button.connect("clicked", app.on_artist_albums_back)
    top_bar.append(back_button)

    title = Gtk.Label(label="Artist", xalign=0)
    title.add_css_class("home-title")
    title.set_hexpand(True)
    title.set_halign(Gtk.Align.FILL)
    top_bar.append(title)
    container.append(top_bar)

    status = Gtk.Label()
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    container.append(status)

    albums_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    albums_section.add_css_class("search-group")

    albums_header = Gtk.Label(label="Albums")
    albums_header.add_css_class("section-title")
    albums_header.set_xalign(0)
    albums_section.append(albums_header)

    flow = Gtk.FlowBox()
    ui_utils.configure_media_flowbox(flow, Gtk.SelectionMode.SINGLE)
    flow.connect("child-activated", app.on_artist_album_activated)
    albums_section.append(flow)

    container.append(albums_section)

    tracks_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    tracks_section.add_css_class("search-group")

    tracks_header = Gtk.Label(label="Top Tracks")
    tracks_header.add_css_class("section-title")
    tracks_header.set_xalign(0)
    tracks_section.append(tracks_header)

    artist_tracks_table = track_table.build_tracks_table(
        app,
        store_attr="artist_tracks_store",
        sort_model_attr="artist_tracks_sort_model",
        selection_attr="artist_tracks_selection",
        view_attr="artist_tracks_view",
        use_track_art=True,
        include_album_column=False,
        action_labels=(
            "Play",
            "Play Next",
            "Add to Queue",
            "Start Radio",
            "Go to Album",
            "Add to existing playlist",
            "Add to new playlist",
        ),
    )
    tracks_scroller = Gtk.ScrolledWindow()
    tracks_scroller.set_policy(
        Gtk.PolicyType.AUTOMATIC,
        Gtk.PolicyType.AUTOMATIC,
    )
    tracks_scroller.set_child(artist_tracks_table)
    if hasattr(tracks_scroller, "set_propagate_natural_height"):
        tracks_scroller.set_propagate_natural_height(True)
    tracks_scroller.set_vexpand(False)
    tracks_section.append(tracks_scroller)

    container.append(tracks_section)

    scroller = Gtk.ScrolledWindow()
    scroller.add_css_class("search-section")
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(container)
    scroller.set_vexpand(True)

    app.artist_albums_view = scroller
    app.artist_albums_title = title
    app.artist_albums_header = albums_header
    app.artist_albums_status_label = status
    app.artist_albums_flow = flow
    return scroller
