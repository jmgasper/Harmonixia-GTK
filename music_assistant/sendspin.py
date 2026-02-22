import asyncio, logging, platform, socket, threading, uuid
from contextlib import suppress
from urllib.parse import urlparse

from constants import SENDSPIN_PORT

Gst = None
try:
    import gi; gi.require_version("Gst", "1.0"); from gi.repository import Gst
except (ImportError, ValueError):
    Gst = None

SendspinClient = PCMFormat = DeviceInfo = ClientHelloPlayerSupport = SupportedAudioFormat = AudioCodec = PlayerCommand = PlayerStateType = Roles = None
try:
    from aiosendspin.client import PCMFormat, SendspinClient
    from aiosendspin.models.core import DeviceInfo
    from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
    from aiosendspin.models.types import AudioCodec, PlayerCommand, PlayerStateType, Roles
except (ImportError, ValueError):
    SendspinClient = None


class SendspinManager:
    def __init__(self, *, get_supported_formats=None, on_connected=None, on_disconnected=None, on_stream_start=None, on_stream_end=None, on_stream_clear=None, on_audio_chunk=None, on_volume_change=None, on_mute_change=None):
        self._get_supported_formats = get_supported_formats or (lambda: [])
        self.on_connected = on_connected; self.on_disconnected = on_disconnected
        self.on_stream_start = on_stream_start; self.on_stream_end = on_stream_end; self.on_stream_clear = on_stream_clear
        self.on_audio_chunk = on_audio_chunk; self.on_volume_change = on_volume_change; self.on_mute_change = on_mute_change
        self.client_id = None; self.client_name = self.build_sendspin_client_name(); self.stream_active = False; self.stream_format = None
        self.volume = 0.65; self.muted = False; self.connecting = False; self.connected = False; self._server_url = ""
        self._thread = None; self._stop_event = None; self._client = None; self._logger = logging.getLogger(__name__)
        self._chunk_count = 0

    @staticmethod
    def build_sendspin_client_name():
        hostname = (socket.gethostname() or platform.node() or "").strip()
        return f"Music Assistant GTK ({hostname})" if hostname else "Music Assistant GTK"

    @staticmethod
    def generate_sendspin_client_id(): return f"ma_gtk_{uuid.uuid4().hex[:10]}"

    def set_client_id(self, client_id):
        cleaned = client_id.strip() if isinstance(client_id, str) else ""
        self.client_id = cleaned or None

    def ensure_client_id(self):
        if not self.client_id: self.client_id = self.generate_sendspin_client_id()

    def has_support(self): return SendspinClient is not None and Gst is not None

    def build_sendspin_url(self):
        parsed = urlparse(self._server_url); host = parsed.hostname or "localhost"; scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{host}:{SENDSPIN_PORT}/sendspin"

    def set_volume(self, volume): self.volume = max(0.0, min(1.0, float(volume)))
    def set_volume_percent(self, volume): self.set_volume(max(0, min(100, int(volume))) / 100.0)
    def set_muted(self, muted): self.muted = bool(muted)

    def start(self, server_url):
        if not server_url or not self.has_support(): return
        if (self._thread and self._thread.is_alive()) or self.connecting: return
        self._server_url = server_url; self.ensure_client_id(); stop_event = threading.Event()
        thread = threading.Thread(target=self._sendspin_worker, args=(stop_event,), daemon=True)
        self._stop_event = stop_event; self._thread = thread; self.connecting = True; thread.start()

    def stop(self):
        if self._stop_event: self._stop_event.set()
        if self._thread and self._thread.is_alive(): self._thread.join(timeout=1)
        self._stop_event = None; self._thread = None; self._client = None; self.connecting = False; self.connected = False

    def _sendspin_worker(self, stop_event):
        try: asyncio.run(self._sendspin_async(stop_event))
        except Exception as exc: self._logger.warning("Sendspin client stopped: %s", exc)

    async def _sendspin_async(self, stop_event):
        if SendspinClient is None: return
        url = self.build_sendspin_url(); retry_delay = 3
        while not stop_event.is_set():
            client = None
            try:
                client = self.build_sendspin_client(); self._client = client; await client.connect(url)
                self.connecting = False; self.connected = True
                if self.on_connected: self.on_connected()
                await self._sendspin_run(client, stop_event)
            except Exception as exc:
                self._logger.warning("Sendspin connection failed: %s", exc)
            finally:
                if client:
                    try: await client.disconnect()
                    except Exception: pass
                was_connected = self.connected; self._client = None; self.connected = False; self.connecting = False
                if was_connected and self.on_disconnected: self.on_disconnected()
            if stop_event.is_set(): break
            await asyncio.sleep(retry_delay)

    async def _sendspin_run(self, client, stop_event):
        disconnect_event = asyncio.Event()

        def on_disconnect():
            disconnect_event.set()

        self._register_sendspin_listener(
            client,
            "disconnect",
            on_disconnect,
        )
        self._register_sendspin_listener(
            client,
            "stream_start",
            self._on_sendspin_stream_start,
        )
        self._register_sendspin_listener(
            client,
            "stream_end",
            self._on_sendspin_stream_end,
        )
        self._register_sendspin_listener(
            client,
            "stream_clear",
            self._on_sendspin_stream_clear,
        )
        self._register_sendspin_listener(
            client,
            "audio_chunk",
            self._on_sendspin_audio_chunk,
        )
        self._register_sendspin_listener(
            client,
            "server_command",
            self._on_sendspin_server_command,
        )
        state_task = asyncio.create_task(self._sendspin_state_loop(client, stop_event))
        try:
            while not stop_event.is_set():
                if disconnect_event.is_set() or not client.connected: break
                await asyncio.sleep(0.2)
        finally:
            state_task.cancel()
            with suppress(asyncio.CancelledError): await state_task

    @staticmethod
    def _register_sendspin_listener(client, event_name, callback):
        add_method = getattr(client, f"add_{event_name}_listener", None)
        if callable(add_method):
            add_method(callback)
            return
        set_method = getattr(client, f"set_{event_name}_listener", None)
        if callable(set_method):
            set_method(callback)
            return
        raise RuntimeError(
            f"Sendspin client does not support {event_name} listener registration"
        )

    def build_sendspin_client(self):
        self.ensure_client_id(); supported_formats = self.build_sendspin_supported_formats()
        player_support = ClientHelloPlayerSupport(supported_formats=supported_formats, buffer_capacity=512 * 1024, supported_commands=[PlayerCommand.VOLUME, PlayerCommand.MUTE])
        device_info = DeviceInfo(product_name=self.client_name, manufacturer="Music Assistant GTK", software_version="1.0")
        return SendspinClient(client_id=self.client_id or self.generate_sendspin_client_id(), client_name=self.client_name, roles=[Roles.PLAYER], device_info=device_info, player_support=player_support, initial_volume=int(round(self.volume * 100)), initial_muted=self.muted)

    def build_sendspin_supported_formats(self):
        formats = self._get_supported_formats() or [(48000, 16), (44100, 16)]
        supported_formats, seen = [], set()
        for sample_rate, bit_depth in formats:
            key = (sample_rate, bit_depth)
            if key in seen: continue
            seen.add(key)
            supported_formats.append(SupportedAudioFormat(codec=AudioCodec.PCM, channels=2, sample_rate=sample_rate, bit_depth=bit_depth))
        return supported_formats

    async def _sendspin_state_loop(self, client, stop_event):
        while not stop_event.is_set():
            await self.send_sendspin_state(client, state=PlayerStateType.SYNCHRONIZED)
            await asyncio.sleep(10)

    async def send_sendspin_state(self, client, state):
        try: await client.send_player_state(state=state, volume=int(round(self.volume * 100)), muted=self.muted)
        except Exception: return

    async def _on_sendspin_server_command(self, payload):
        player_payload = getattr(payload, "player", None)
        if player_payload is None: return
        command = getattr(player_payload, "command", None); command = command.value if hasattr(command, "value") else command
        if command == "volume":
            volume = getattr(player_payload, "volume", None)
            if volume is not None:
                normalized = max(0, min(100, int(volume))); self.set_volume_percent(normalized)
                if self.on_volume_change: self.on_volume_change(normalized)
        elif command == "mute":
            muted = getattr(player_payload, "mute", None)
            if muted is not None:
                value = bool(muted); self.set_muted(value)
                if self.on_mute_change: self.on_mute_change(value)
        if self._client: await self.send_sendspin_state(self._client, state=PlayerStateType.SYNCHRONIZED)

    async def _on_sendspin_stream_start(self, message):
        payload = getattr(message, "payload", None); player_info = getattr(payload, "player", None) if payload else None
        if not player_info: return
        codec = getattr(player_info, "codec", None); codec = codec.value if hasattr(codec, "value") else codec
        if codec != "pcm":
            self._logger.warning("Sendspin stream uses unsupported codec: %s", codec); return
        sample_rate = getattr(player_info, "sample_rate", 0); channels = getattr(player_info, "channels", 0); bit_depth = getattr(player_info, "bit_depth", 0)
        if not sample_rate or not channels or not bit_depth: return
        format_info = PCMFormat(sample_rate=sample_rate, channels=channels, bit_depth=bit_depth)
        self.stream_active = True; self.stream_format = format_info; self._chunk_count = 0
        self._logger.info(
            "Sendspin stream started: %s Hz/%s-bit/%s ch",
            sample_rate,
            bit_depth,
            channels,
        )
        if self.on_stream_start: self.on_stream_start(format_info)

    async def _on_sendspin_stream_end(self, _roles):
        self.stream_active = False
        if self._chunk_count:
            self._logger.info(
                "Sendspin stream ended after %s chunks.",
                self._chunk_count,
            )
        if self.on_stream_end: self.on_stream_end()

    async def _on_sendspin_stream_clear(self, _roles):
        if self.on_stream_clear: self.on_stream_clear()

    async def _on_sendspin_audio_chunk(self, timestamp_us, payload, format_info):
        if not self.stream_active: return
        self._chunk_count += 1
        if self._chunk_count == 1:
            self._logger.debug(
                "Sendspin first audio chunk: %s bytes at %s us",
                len(payload),
                timestamp_us,
            )
        if self.on_audio_chunk: self.on_audio_chunk(timestamp_us, payload, format_info)
