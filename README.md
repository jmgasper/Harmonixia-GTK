# Music Assistant GTK Client

A GTK 4 desktop client for Music Assistant that focuses on fast library browsing, reliable playback, and seamless desktop media integration.

Mainly built with help from ChatGPT Codex.

## Features

- Album browsing with grid and detail views
- Playback controls with queue support
- MPRIS integration for media keys
- Sendspin streaming for Music Assistant audio

## Dependencies

### System Dependencies

GStreamer 1.0 with plugins:

- gst-plugins-base
- gst-plugins-good
- gst-plugins-bad

Install GStreamer packages:

```bash
# Debian/Ubuntu
sudo apt install gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad

# Fedora
sudo dnf install gstreamer1-plugins-base gstreamer1-plugins-good gstreamer1-plugins-bad

# Arch Linux
sudo pacman -S gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad

# macOS (Homebrew)
brew install gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad
```

PyGObject/GTK 4 system packages (PyGObject from pip requires these system libraries):

```bash
# Debian/Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0

# Fedora
sudo dnf install pygobject3 gtk4

# Arch Linux
sudo pacman -S python-gobject gtk4

# macOS (Homebrew)
brew install pygobject gtk4
```

### Python Dependencies

- PyGObject >= 3.42
- aiosendspin
- music-assistant-client

Install Python dependencies:

```bash
pip install -r requirements.txt
```

## Code Structure

### Root Level Files

| Path | Purpose |
| --- | --- |
| `main.py` | Application entry point and MusicApp class orchestration |
| `constants.py` | Application constants (APP_ID, UI dimensions, MPRIS settings, MPRIS introspection XML) |
| `utils.py` | Utility functions (URL normalization, TrackRow class) |
| `app_helpers.py` | Helper methods for settings, logging, and album operations |
| `requirements.txt` | Python package dependencies |
| `settings.json` | User settings (server URL, auth token) |

### `music_assistant/` Directory

- `client.py` - Server connection logic, settings persistence, connection validation
- `library.py` - Library loading, album/artist/playlist fetching
- `library_manager.py` - Library state management and UI updates
- `playback.py` - Playback command functions (play, pause, next, previous)
- `playback_state.py` - Playback state management, progress tracking, queue handling
- `sendspin.py` - Sendspin WebSocket client for audio streaming
- `audio_pipeline.py` - GStreamer pipeline management for local audio output
- `output_manager.py` - Audio output device detection and selection
- `output_handlers.py` - Output-related event handlers
- `mpris.py` - MPRIS D-Bus interface for media key integration
- `settings_manager.py` - Settings loading and persistence

### `ui/` Directory

- `playback_controls.py` - Top control bar with play/pause/next/previous buttons, volume slider, progress bar
- `sidebar.py` - Left sidebar with navigation, library sections, playlists, now-playing art
- `settings_panel.py` - Settings view for server connection configuration
- `album_grid.py` - Album grid/list view with filtering
- `album_detail.py` - Album detail view with background art and metadata
- `track_table.py` - Track table with ColumnView, sorting, and selection
- `home_section.py` - Home view with recently played/added sections
- `output_selector.py` - Output device selection popover
- `image_loader.py` - Async image loading, caching, and blur effects
- `ui_utils.py` - UI utilities (CSS loading, font loading, GTK environment detection)
- `event_handlers.py` - UI event handlers
- `album_operations.py` - Album-related operations
- `home_manager.py` - Home section management
- `playlist_manager.py` - Playlist operations
- `track_utils.py` - Track-related utilities

### `ui/widgets/` Directory

- `album_card.py` - Individual album card widget for grid views
- `track_row.py` - Track row widget for track tables
- `loading_spinner.py` - Loading spinner overlay widget

### `ui/css/` Directory

- `style.css` - Application stylesheet

### `fonts/` Directory

- Custom fonts for the application (NotoSans-Variable.ttf)

## Configuration

### Connecting to Music Assistant Server

- This app requires a running Music Assistant server (version 2.x).
- Default server URL is `http://localhost:8095`.
- Open the settings panel by clicking the Settings button in the sidebar.
- Configure the Server URL and Authentication Token fields.

### Generating an API Token

1. Open the Music Assistant web interface (typically `http://localhost:8095`).
2. Navigate to Settings > Security > Long-Lived Access Tokens.
3. Click "Create Token".
4. Give the token a descriptive name (for example, "GTK Client").
5. Copy the generated token.
6. Paste the token into the GTK app's settings panel.
7. Click "Connect" to establish the connection.

### Settings Persistence

- Settings are saved to `settings.json` in the application directory.
- The file stores the server URL and authentication token.
- Settings are automatically loaded on application startup.

## Running the Application

### Starting the App

```bash
python main.py
```

### Debug Mode

```bash
MA_DEBUG=1 python main.py
```

- Enables verbose logging for troubleshooting.
- Shows detailed information about library loading, playback events, and Sendspin connection.
- Add `MA_DEBUG_RESPONSES=1` alongside `MA_DEBUG=1` to include raw Music Assistant request/response payloads.
- Add `SENDSPIN_DEBUG=1` to enable Sendspin + GStreamer pipeline debug logs without turning on full `MA_DEBUG`.

### First Run

- On first launch, configure the server connection in Settings.
- After connecting, the app automatically loads your library.
- Albums, artists, and playlists appear in the sidebar.

### Testing Playback

- Browse to Albums or the Home section.
- Click an album to view details.
- Click the play button or double-click a track to start playback.
- Use playback controls in the top bar.
- Select an audio output device using the output selector button.

### MPRIS Integration

- Media keys (play/pause, next, previous) work automatically.
- Desktop notifications and media player integrations work via D-Bus.
- Control playback from system media controls.

## Troubleshooting

### Common Issues

| Issue | Solution |
| --- | --- |
| "Cannot connect to server" | Verify the Music Assistant server is running and accessible at the configured URL. Check firewall settings. |
| "Authentication failed" | Regenerate the API token in the Music Assistant web interface and update it in the app settings. |
| No audio output | Check GStreamer installation: `gst-inspect-1.0 autoaudiosink`. Verify audio device selection in the output selector. |
| Sendspin connection fails | Ensure port 8927 is accessible. Check Music Assistant server logs for Sendspin errors. |
| Album art not loading | Check network connectivity. Clear the cache directory (`.cache/`) and restart the app. |
| GTK warnings/errors | Ensure GTK 4 and PyGObject are properly installed. Check `MA_DEBUG=1` output for details. |

### Development Notes

- The application uses GTK 4 with libadwaita-style components.
- All UI components are designed to be under 300 lines for maintainability.
- Image loading is asynchronous using ThreadPoolExecutor to prevent UI blocking.
- Playback state is synchronized between local UI and the Music Assistant server.
- The Sendspin protocol handles audio streaming over WebSocket with PCM format support.
- MPRIS implementation follows the MPRIS D-Bus Interface Specification 2.2.

### Code Organization Principles

- Each module has a single, well-defined responsibility.
- UI components are separated from business logic.
- Music Assistant integration is isolated in the `music_assistant/` directory.
- Shared utilities and constants are in root-level files.
- The method binding pattern in `main.py` allows clean separation while maintaining app context.

### Testing Checklist

- [ ] Server connection and authentication
- [ ] Library loading (albums, artists, playlists)
- [ ] Album browsing and filtering
- [ ] Track playback and queue management
- [ ] Playback controls (play, pause, next, previous)
- [ ] Volume control and mute
- [ ] Output device selection
- [ ] MPRIS media key integration
- [ ] Now-playing display and progress tracking
- [ ] Album art loading and caching

## Requirements Summary

- Python 3.8 or higher
- GTK 4.0 or higher
- GStreamer 1.0 with plugins
- Music Assistant server 2.x

## Project Status

- This is a GTK 4 client for Music Assistant.
- Supports local audio playback via GStreamer.
- Supports remote streaming via the Sendspin protocol.
- MPRIS integration for desktop media controls.

## Contributing

- The codebase is organized for easy maintenance and extension.
- Each file is limited to about 300 lines for readability.
- Follow existing patterns when adding new features.
- Test with `MA_DEBUG=1` to verify changes.
