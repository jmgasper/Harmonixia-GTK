from gi.repository import Gtk

from ui import ui_utils
from ui.widgets import album_card


def build_home_section(app) -> Gtk.Widget:
    home_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    home_box.add_css_class("home-section-content")

    header = Gtk.Label(label="Home")
    header.add_css_class("home-title")
    header.set_xalign(0)
    home_box.append(header)

    played_section, played_list, played_status = build_home_album_list(
        "Recently Played",
        "Play an album to see it here.",
    )
    played_list.album_app = app
    app.home_recently_played_list = played_list
    app.home_recently_played_status = played_status
    home_box.append(played_section)

    added_section, added_list, added_status = build_home_album_list(
        "Recently Added Albums",
        "Recently added albums will appear here.",
    )
    added_list.album_app = app
    app.home_recently_added_list = added_list
    app.home_recently_added_status = added_status
    home_box.append(added_section)

    scroller = Gtk.ScrolledWindow()
    scroller.add_css_class("home-section")
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    scroller.set_child(home_box)
    scroller.set_vexpand(True)

    app.refresh_home_sections()
    return scroller


def build_home_album_list(
    title: str, empty_message: str
) -> tuple[Gtk.Widget, Gtk.FlowBox, Gtk.Label]:
    section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    section.add_css_class("home-card")

    header = Gtk.Label(label=title)
    header.add_css_class("section-title")
    header.set_xalign(0)
    section.append(header)

    flow = Gtk.FlowBox()
    flow.add_css_class("home-grid")
    flow.set_homogeneous(True)
    flow.set_min_children_per_line(3)
    flow.set_max_children_per_line(3)
    flow.set_selection_mode(Gtk.SelectionMode.NONE)
    flow.set_halign(Gtk.Align.FILL)
    flow.set_valign(Gtk.Align.START)
    flow.set_hexpand(True)
    flow.set_vexpand(False)
    flow.set_column_spacing(12)
    flow.set_row_spacing(12)
    flow.set_activate_on_single_click(True)
    flow.connect(
        "child-activated",
        lambda flowbox, child: on_home_album_activated(
            getattr(flowbox, "album_app", None),
            flowbox,
            child,
        ),
    )
    section.append(flow)

    status = Gtk.Label(label=empty_message)
    status.add_css_class("status-label")
    status.set_xalign(0)
    status.set_wrap(True)
    status.set_visible(False)
    status.empty_message = empty_message
    section.append(status)

    return section, flow, status


def on_home_album_activated(app, _flowbox: Gtk.FlowBox, child: Gtk.FlowBoxChild) -> None:
    if not app:
        return
    album = getattr(child, "album_data", None)
    if not album:
        return
    app.album_detail_previous_view = "home"
    app.show_album_detail(album)
    if app.main_stack:
        app.main_stack.set_visible_child_name("album-detail")


def populate_home_album_list(app, listbox: Gtk.FlowBox | None, albums: list) -> None:
    if not listbox:
        return
    ui_utils.clear_container(listbox)
    for album in albums:
        if not isinstance(album, dict):
            continue
        card = album_card.make_home_album_card(app, album)
        child = Gtk.FlowBoxChild()
        child.set_child(card)
        child.set_halign(Gtk.Align.CENTER)
        child.set_valign(Gtk.Align.START)
        child.set_hexpand(False)
        child.set_vexpand(False)
        child.set_size_request(album_card.HOME_ALBUM_ART_SIZE, -1)
        child.album_data = album
        listbox.append(child)


def set_home_status(label: Gtk.Label | None, message: str) -> None:
    if not label:
        return
    label.set_label(message)
    label.set_visible(bool(message))


def update_home_status(label: Gtk.Label | None, albums: list) -> None:
    if not label:
        return
    empty_message = getattr(label, "empty_message", "")
    label.set_label(empty_message if not albums else "")
    label.set_visible(not albums and bool(empty_message))
