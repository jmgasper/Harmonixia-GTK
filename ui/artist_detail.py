from gi.repository import Gtk, Pango

from constants import DETAIL_ART_SIZE
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
    container.append(top_bar)

    artist_header = Gtk.Box(
        orientation=Gtk.Orientation.HORIZONTAL,
        spacing=16,
    )

    artist_art = Gtk.Picture()
    artist_art.add_css_class("artist-detail-art")
    artist_art.set_size_request(DETAIL_ART_SIZE, DETAIL_ART_SIZE)
    artist_art.set_halign(Gtk.Align.START)
    artist_art.set_valign(Gtk.Align.START)
    artist_art.set_can_shrink(True)
    if hasattr(artist_art, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        artist_art.set_content_fit(Gtk.ContentFit.COVER)

    artist_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    artist_info.set_vexpand(False)

    title = Gtk.Label(label="Artist")
    title.add_css_class("detail-title")
    title.set_wrap(True)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    title.set_xalign(0)

    bio_expander = Gtk.Expander(label="Biography")
    bio_expander.add_css_class("artist-bio-expander")
    bio_expander.set_expanded(False)
    bio_expander.set_visible(False)

    bio_scroll = Gtk.ScrolledWindow()
    bio_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    bio_scroll.set_max_content_height(140)

    bio_text_view = Gtk.TextView()
    bio_text_view.set_editable(False)
    bio_text_view.set_cursor_visible(False)
    bio_text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    bio_text_view.set_left_margin(4)
    bio_text_view.set_right_margin(4)
    bio_text_view.add_css_class("artist-bio-text")
    bio_scroll.set_child(bio_text_view)
    bio_expander.set_child(bio_scroll)

    artist_info.append(title)
    artist_info.append(bio_expander)

    artist_header.append(artist_art)
    artist_header.append(artist_info)
    container.append(artist_header)

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
        disc_column_attr="artist_tracks_disc_column",
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
    app.artist_detail_art = artist_art
    app.artist_bio_expander = bio_expander
    app.artist_bio_text_view = bio_text_view
    app.artist_albums_header = albums_header
    app.artist_albums_status_label = status
    app.artist_albums_flow = flow
    return scroller
