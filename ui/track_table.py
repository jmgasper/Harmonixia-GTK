import logging

from gi.repository import Gio, GObject, Gtk, Pango

from constants import TRACK_ART_SIZE
from ui import image_loader
from ui.widgets.track_row import TrackRow

DEFAULT_ACTION_LABELS = (
    "Play",
    "Play Next",
    "Add to Queue",
    "Start Radio",
    "Go to Album",
    "Add to existing playlist",
    "Add to new playlist",
)
FAVORITE_ADD_LABEL = "Add to favorites"
FAVORITE_REMOVE_LABEL = "Remove from favorites"
FAVORITES_ACTION_LABELS = (
    FAVORITE_ADD_LABEL,
    FAVORITE_REMOVE_LABEL,
)


def build_action_labels(
    action_labels: tuple[str, ...] | None,
) -> tuple[str, ...]:
    labels = list(action_labels or DEFAULT_ACTION_LABELS)
    labels = [label for label in labels if label not in FAVORITES_ACTION_LABELS]
    insert_at = 0
    if "Play" in labels:
        insert_at = labels.index("Play") + 1
    for label in reversed(FAVORITES_ACTION_LABELS):
        labels.insert(insert_at, label)
    return tuple(labels)


def build_tracks_table(
    app,
    *,
    store_attr: str = "album_tracks_store",
    sort_model_attr: str = "album_tracks_sort_model",
    selection_attr: str = "album_tracks_selection",
    view_attr: str = "album_tracks_view",
    action_labels: tuple[str, ...] | None = None,
    use_track_art: bool = False,
    include_album_column: bool = True,
) -> Gtk.Widget:
    store = Gio.ListStore.new(TrackRow)
    sort_model = Gtk.SortListModel.new(store, None)
    selection = Gtk.SingleSelection.new(sort_model)
    selection.set_autoselect(False)
    selection.set_can_unselect(True)
    selection.connect("selection-changed", app.on_track_selection_changed)
    setattr(app, store_attr, store)
    setattr(app, sort_model_attr, sort_model)
    setattr(app, selection_attr, selection)
    view = Gtk.ColumnView.new(selection)
    view.add_css_class("track-table")
    view.set_hexpand(True)
    view.set_vexpand(False)
    if hasattr(view, "set_vscroll_policy") and hasattr(Gtk, "ScrollablePolicy"):
        view.set_vscroll_policy(Gtk.ScrollablePolicy.NATURAL)
    view.set_show_row_separators(False)
    view.set_show_column_separators(True)
    setattr(app, view_attr, view)

    sort_model.set_sorter(view.get_sorter())

    playing_column = make_playing_indicator_column(app)
    if use_track_art:
        leading_column = make_track_art_column(app)
    else:
        leading_column = make_track_column(
            app,
            "#",
            "track_number",
            xalign=1.0,
            numeric=True,
            fixed_width=60,
        )
    title_column = make_track_column(
        app,
        "Track",
        "title",
        xalign=0.0,
        expand=True,
    )
    length_column = make_track_column(
        app,
        "Length",
        "length_display",
        xalign=1.0,
        numeric=True,
        sort_prop="length_seconds",
        fixed_width=90,
    )
    artist_column = make_track_column(app, "Artist", "artist", xalign=0.0)
    album_column = make_track_column(app, "Album", "album", xalign=0.0)
    quality_column = make_track_column(app, "Quality", "quality", xalign=0.0)
    actions_column = make_actions_column(app, action_labels=action_labels)

    view.append_column(playing_column)
    view.append_column(leading_column)
    view.append_column(title_column)
    view.append_column(length_column)
    view.append_column(artist_column)
    if include_album_column:
        view.append_column(album_column)
    view.append_column(quality_column)
    view.append_column(actions_column)

    return view


def make_playing_indicator_column(app) -> Gtk.ColumnViewColumn:
    factory = Gtk.SignalListItemFactory()
    factory.connect(
        "setup",
        lambda factory, list_item: on_track_playing_setup(
            app, factory, list_item
        ),
    )
    factory.connect(
        "bind",
        lambda factory, list_item: on_track_playing_bind(
            app, factory, list_item
        ),
    )
    factory.connect(
        "unbind",
        lambda factory, list_item: on_track_playing_unbind(
            app, factory, list_item
        ),
    )
    column = Gtk.ColumnViewColumn.new("", factory)
    column.set_fixed_width(28)
    return column


def make_track_art_column(app) -> Gtk.ColumnViewColumn:
    factory = Gtk.SignalListItemFactory()
    factory.connect(
        "setup",
        lambda factory, list_item: on_track_art_setup(
            app, factory, list_item
        ),
    )
    factory.connect(
        "bind",
        lambda factory, list_item: on_track_art_bind(
            app, factory, list_item
        ),
    )
    factory.connect(
        "unbind",
        lambda factory, list_item: on_track_art_unbind(
            app, factory, list_item
        ),
    )
    column = Gtk.ColumnViewColumn.new("", factory)
    column.set_fixed_width(TRACK_ART_SIZE + 16)
    return column


def on_track_playing_setup(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    icon = Gtk.Image.new_from_icon_name("audio-volume-high-symbolic")
    icon.set_pixel_size(14)
    icon.set_visible(False)
    icon.add_css_class("playing-indicator")
    container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    container.set_halign(Gtk.Align.CENTER)
    container.append(icon)
    list_item.set_child(container)
    list_item.playing_icon = icon


def on_track_playing_bind(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    item = list_item.get_item()
    icon = getattr(list_item, "playing_icon", None)
    if icon is None:
        return
    is_playing = bool(getattr(item, "is_playing", False))
    icon.set_visible(is_playing)
    if item is not None:
        handler_id = item.connect(
            "notify::is-playing",
            lambda item, param, icon=icon: on_track_playing_notify(
                app, item, param, icon
            ),
        )
        list_item.playing_handler_id = handler_id
        list_item.playing_item = item


def on_track_playing_unbind(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    item = getattr(list_item, "playing_item", None)
    handler_id = getattr(list_item, "playing_handler_id", None)
    if item is not None and handler_id is not None:
        item.disconnect(handler_id)
    list_item.playing_handler_id = None
    list_item.playing_item = None


def on_track_art_setup(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    art = Gtk.Picture()
    art.add_css_class("track-art")
    art.set_size_request(TRACK_ART_SIZE, TRACK_ART_SIZE)
    art.set_halign(Gtk.Align.CENTER)
    art.set_valign(Gtk.Align.CENTER)
    art.set_can_shrink(True)
    art.set_margin_start(6)
    art.set_margin_end(6)
    art.set_margin_top(2)
    art.set_margin_bottom(2)
    if hasattr(art, "set_content_fit") and hasattr(Gtk, "ContentFit"):
        art.set_content_fit(Gtk.ContentFit.COVER)
    elif hasattr(art, "set_keep_aspect_ratio"):
        art.set_keep_aspect_ratio(False)
    container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    container.set_halign(Gtk.Align.CENTER)
    container.set_valign(Gtk.Align.CENTER)
    container.append(art)
    list_item.set_child(container)
    list_item.art_picture = art


def on_track_art_bind(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    item = list_item.get_item()
    art = getattr(list_item, "art_picture", None)
    if art is None:
        return
    image_url = _resolve_track_art_url(app, item)
    if not image_url:
        art.set_paintable(None)
        try:
            art.expected_image_url = None
        except Exception:
            pass
        return
    if getattr(art, "expected_image_url", None) == image_url:
        try:
            current_paintable = art.get_paintable()
        except Exception:
            current_paintable = None
        if current_paintable is not None:
            return
    art.set_paintable(None)
    image_loader.load_album_art_async(
        art,
        image_url,
        TRACK_ART_SIZE,
        app.auth_token,
        app.image_executor,
        app.get_cache_dir(),
    )


def on_track_art_unbind(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    art = getattr(list_item, "art_picture", None)
    if art is None:
        return
    art.set_paintable(None)
    try:
        art.expected_image_url = None
    except Exception:
        pass


def _resolve_track_art_url(app, item: TrackRow | None) -> str | None:
    if item is None:
        return None
    image_url = getattr(item, "image_url", None) or getattr(
        item, "cover_image_url", None
    )
    if not image_url:
        source = getattr(item, "source", None)
        if source is not None:
            image_url = image_loader.extract_media_image_url(
                source,
                app.server_url,
            )
    if not image_url:
        return None
    resolved = image_loader.resolve_image_url(image_url, app.server_url)
    return resolved or image_url


def on_track_playing_notify(
    app, item: TrackRow, _param: GObject.ParamSpec, icon: Gtk.Image
) -> None:
    icon.set_visible(bool(getattr(item, "is_playing", False)))


def make_track_column(
    app,
    title: str,
    prop: str,
    xalign: float = 0.0,
    expand: bool = False,
    numeric: bool = False,
    sort_prop: str | None = None,
    fixed_width: int | None = None,
) -> Gtk.ColumnViewColumn:
    factory = Gtk.SignalListItemFactory()
    factory.connect(
        "setup",
        lambda factory, list_item: on_track_cell_setup(
            app, factory, list_item, xalign
        ),
    )
    factory.connect(
        "bind",
        lambda factory, list_item: on_track_cell_bind(
            app, factory, list_item, prop
        ),
    )
    column = Gtk.ColumnViewColumn.new(title, factory)
    column.set_expand(expand)
    column.set_property("resizable", True)
    if fixed_width:
        column.set_fixed_width(fixed_width)
    sorter_prop = sort_prop or prop
    column.set_sorter(make_track_sorter(sorter_prop, numeric))
    return column


def make_track_sorter(prop: str, numeric: bool) -> Gtk.Sorter:
    expression = Gtk.PropertyExpression.new(TrackRow, None, prop)
    if numeric:
        return Gtk.NumericSorter.new(expression)
    sorter = Gtk.StringSorter.new(expression)
    sorter.set_ignore_case(True)
    return sorter


def on_track_cell_setup(
    app,
    _factory: Gtk.SignalListItemFactory,
    list_item: Gtk.ListItem,
    xalign: float,
) -> None:
    label = Gtk.Label(xalign=xalign)
    label.set_xalign(xalign)
    label.set_hexpand(True)
    label.set_halign(Gtk.Align.FILL)
    label.set_ellipsize(Pango.EllipsizeMode.END)
    label.set_single_line_mode(True)
    label.set_margin_start(8)
    label.set_margin_end(8)
    label.set_margin_top(1)
    label.set_margin_bottom(1)
    list_item.set_child(label)


def on_track_cell_bind(
    app,
    _factory: Gtk.SignalListItemFactory,
    list_item: Gtk.ListItem,
    prop: str,
) -> None:
    item = list_item.get_item()
    label = list_item.get_child()
    if label is None:
        label = Gtk.Label()
        label.set_margin_start(8)
        label.set_margin_end(8)
        label.set_margin_top(1)
        label.set_margin_bottom(1)
        list_item.set_child(label)
    value = getattr(item, prop, "")
    if prop == "track_number" and value == 0:
        text = ""
    else:
        text = "" if value is None else str(value)
    label.set_label(text)
    if not app.track_bind_logged:
        logging.getLogger(__name__).debug(
            "Track bind item=%s prop=%s value=%s",
            type(item).__name__,
            prop,
            text,
        )
        app.track_bind_logged = True


def make_actions_column(
    app, action_labels: tuple[str, ...] | None = None
) -> Gtk.ColumnViewColumn:
    factory = Gtk.SignalListItemFactory()
    labels = build_action_labels(action_labels)
    factory.connect(
        "setup",
        lambda factory, list_item: on_track_actions_setup(
            app, factory, list_item, labels
        ),
    )
    factory.connect(
        "bind",
        lambda factory, list_item: on_track_actions_bind(
            app, factory, list_item
        ),
    )
    factory.connect(
        "unbind",
        lambda factory, list_item: on_track_actions_unbind(
            app, factory, list_item
        ),
    )
    column = Gtk.ColumnViewColumn.new("Actions", factory)
    column.set_fixed_width(70)
    return column


def on_track_actions_setup(
    app,
    _factory: Gtk.SignalListItemFactory,
    list_item: Gtk.ListItem,
    action_labels: tuple[str, ...],
) -> None:
    menu_button = Gtk.MenuButton()
    menu_button.add_css_class("track-action-button")
    menu_button.set_has_frame(False)
    menu_button.set_child(Gtk.Image.new_from_icon_name("open-menu-symbolic"))

    popover = Gtk.Popover()
    popover.set_has_arrow(False)
    popover.add_css_class("track-action-popover")

    actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    actions_box.set_margin_start(6)
    actions_box.set_margin_end(6)
    actions_box.set_margin_top(6)
    actions_box.set_margin_bottom(6)

    action_buttons = []
    for label in action_labels:
        action_button = Gtk.Button(label=label)
        action_button.set_halign(Gtk.Align.FILL)
        action_button.set_hexpand(True)
        action_button.add_css_class("track-action-item")
        action_button.connect(
            "clicked", app.on_track_action_clicked, menu_button, label
        )
        actions_box.append(action_button)
        action_buttons.append(action_button)

    popover.set_child(actions_box)
    menu_button.set_popover(popover)

    container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    container.set_halign(Gtk.Align.CENTER)
    container.append(menu_button)
    list_item.set_child(container)
    list_item.action_buttons = action_buttons


def on_track_actions_bind(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    item = list_item.get_item()
    remove_enabled = getattr(app, "playlist_detail_is_editable", True)
    for button in getattr(list_item, "action_buttons", []):
        button.track_item = item
        if button.get_label() == "Remove from this playlist":
            button.set_sensitive(remove_enabled)
    is_favorite = bool(getattr(item, "is_favorite", False))
    update_favorite_action_buttons(list_item, is_favorite)
    if item is not None:
        handler_id = item.connect(
            "notify::is-favorite",
            lambda item, param, list_item=list_item: on_track_favorite_notify(
                app, item, param, list_item
            ),
        )
        list_item.favorite_handler_id = handler_id
        list_item.favorite_item = item


def on_track_actions_unbind(
    app, _factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem
) -> None:
    item = getattr(list_item, "favorite_item", None)
    handler_id = getattr(list_item, "favorite_handler_id", None)
    if item is not None and handler_id is not None:
        item.disconnect(handler_id)
    list_item.favorite_handler_id = None
    list_item.favorite_item = None
    for button in getattr(list_item, "action_buttons", []):
        button.track_item = None


def on_track_favorite_notify(
    app,
    item: TrackRow,
    _param: GObject.ParamSpec,
    list_item: Gtk.ListItem,
) -> None:
    update_favorite_action_buttons(list_item, bool(item.is_favorite))


def update_favorite_action_buttons(
    list_item: Gtk.ListItem,
    is_favorite: bool,
) -> None:
    for button in getattr(list_item, "action_buttons", []):
        label = button.get_label()
        if label == FAVORITE_ADD_LABEL:
            button.set_visible(not is_favorite)
        elif label == FAVORITE_REMOVE_LABEL:
            button.set_visible(is_favorite)
