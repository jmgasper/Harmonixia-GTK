# Application constants
APP_ID = "com.example.MusicAssistantGtk"

# Default configuration
DEFAULT_PAGE_SIZE = 200
DEFAULT_SERVER_URL = "http://localhost:8095"
SENDSPIN_PORT = 8927
SETTINGS_FILE = "settings.json"
CSS_FILE = "style.css"
FONT_DIR = "fonts"
FONT_FILES = ("NotoSans-Variable.ttf",)

# UI dimensions
ALBUM_TILE_SIZE = 256
HOME_ALBUM_ART_SIZE = 150
HOME_LIST_LIMIT = 9
SIDEBAR_WIDTH = 210
SIDEBAR_ACTION_MARGIN = 8
SIDEBAR_ART_SIZE = SIDEBAR_WIDTH - (SIDEBAR_ACTION_MARGIN * 2)
DETAIL_ART_SIZE = 200
DETAIL_BG_SIZE = 1600
DETAIL_BG_BLUR_SCALE = 0.12
DETAIL_BG_BLUR_PASSES = 3
SEARCH_RESULT_LIMIT = 50
SEARCH_DEBOUNCE_MS = 300

# Cache paths
ALBUM_ART_CACHE_DIR = ".cache"

# Media key mappings
MEDIA_KEY_NAMES = {
    "play_pause": (
        "XF86AudioPlay",
        "XF86AudioPause",
        "XF86AudioPlayPause",
        "AudioPlay",
        "AudioPause",
    ),
    "next": ("XF86AudioNext", "AudioNext"),
    "previous": (
        "XF86AudioPrev",
        "XF86AudioPrevious",
        "AudioPrev",
        "AudioPrevious",
    ),
}

# MPRIS D-Bus settings
MPRIS_BUS_NAME = "org.mpris.MediaPlayer2.musicassistantgtk"
MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_TRACK_PATH_PREFIX = "/org/mpris/MediaPlayer2/Track/"
MPRIS_NO_TRACK = "/org/mpris/MediaPlayer2/TrackList/NoTrack"
MPRIS_DESKTOP_ENTRY = "music-assistant-gtk"
MPRIS_IDENTITY = "Music Assistant GTK"
MPRIS_NOT_SUPPORTED_ERROR = "org.mpris.MediaPlayer2.Player.Error.NotSupported"
MPRIS_INTROSPECTION_XML = """
<node>
  <interface name="org.mpris.MediaPlayer2">
    <method name="Raise"/>
    <method name="Quit"/>
    <property name="CanQuit" type="b" access="read"/>
    <property name="CanRaise" type="b" access="read"/>
    <property name="HasTrackList" type="b" access="read"/>
    <property name="Identity" type="s" access="read"/>
    <property name="DesktopEntry" type="s" access="read"/>
    <property name="SupportedUriSchemes" type="as" access="read"/>
    <property name="SupportedMimeTypes" type="as" access="read"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2.Player">
    <method name="Next"/>
    <method name="Previous"/>
    <method name="Pause"/>
    <method name="PlayPause"/>
    <method name="Stop"/>
    <method name="Play"/>
    <method name="Seek">
      <arg direction="in" type="x" name="Offset"/>
    </method>
    <method name="SetPosition">
      <arg direction="in" type="o" name="TrackId"/>
      <arg direction="in" type="x" name="Position"/>
    </method>
    <method name="OpenUri">
      <arg direction="in" type="s" name="Uri"/>
    </method>
    <signal name="Seeked">
      <arg type="x" name="Position"/>
    </signal>
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="LoopStatus" type="s" access="readwrite"/>
    <property name="Rate" type="d" access="readwrite"/>
    <property name="Shuffle" type="b" access="readwrite"/>
    <property name="Metadata" type="a{sv}" access="read"/>
    <property name="Volume" type="d" access="readwrite"/>
    <property name="Position" type="x" access="read"/>
    <property name="MinimumRate" type="d" access="read"/>
    <property name="MaximumRate" type="d" access="read"/>
    <property name="CanGoNext" type="b" access="read"/>
    <property name="CanGoPrevious" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanSeek" type="b" access="read"/>
    <property name="CanControl" type="b" access="read"/>
  </interface>
</node>
"""

# Sample data
SAMPLE_ALBUMS = [
    ("Blue Morning", "The Tide Lines"),
    ("Analog Heart", "Cassette Club"),
    ("Neon Skylines", "City Pulse"),
    ("Golden Hour", "The Drift"),
    ("Station Eleven", "Late Night FM"),
    ("Hazy Memory", "Auburn Drive"),
]
SAMPLE_ARTISTS = [
    "Cassette Club",
    "The Tide Lines",
    "City Pulse",
    "The Drift",
    "Late Night FM",
    "Auburn Drive",
]
