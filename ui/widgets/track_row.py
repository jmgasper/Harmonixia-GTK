import gi

try:
    gi.require_version("GObject", "2.0")
except ValueError:
    pass
from gi.repository import GObject


class TrackRow(GObject.GObject):
    """GObject wrapper for track data in the track table."""

    track_number = GObject.Property(type=int, default=0)
    title = GObject.Property(type=str, default="")
    length_display = GObject.Property(type=str, default="")
    length_seconds = GObject.Property(type=int, default=0)
    artist = GObject.Property(type=str, default="")
    album = GObject.Property(type=str, default="")
    quality = GObject.Property(type=str, default="")
    is_playing = GObject.Property(type=bool, default=False)
    is_favorite = GObject.Property(type=bool, default=False)
