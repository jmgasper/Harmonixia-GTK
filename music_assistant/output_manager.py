import asyncio, ctypes, ctypes.util, logging, os, re, threading
from contextlib import contextmanager

from music_assistant_client import MusicAssistantClient

Gst = None
try:
    import gi; gi.require_version("Gst", "1.0"); from gi.repository import Gst
except (ImportError, ValueError):
    Gst = None

_ALSA_LIB = None
_ALSA_ERROR_HANDLER = None
_ALSA_HANDLER_LOCK = threading.Lock()
_ALSA_HANDLER_REFCOUNT = 0


def _load_alsa_lib():
    global _ALSA_LIB
    if _ALSA_LIB is not None:
        return _ALSA_LIB or None
    path = ctypes.util.find_library("asound") or "libasound.so.2"
    try:
        lib = ctypes.CDLL(path)
    except OSError:
        _ALSA_LIB = False
        return None
    lib.snd_lib_error_set_handler.argtypes = [ctypes.c_void_p]
    lib.snd_lib_error_set_handler.restype = None
    _ALSA_LIB = lib
    return lib


def _get_alsa_error_handler():
    global _ALSA_ERROR_HANDLER
    if _ALSA_ERROR_HANDLER is not None:
        return _ALSA_ERROR_HANDLER
    handler_type = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)

    def _handler(_file, _line, _function, _err, _fmt):
        return None

    _ALSA_ERROR_HANDLER = handler_type(_handler)
    return _ALSA_ERROR_HANDLER


@contextmanager
def _suppress_alsa_errors():
    if os.getenv("MA_SHOW_ALSA_ERRORS"):
        yield
        return
    lib = _load_alsa_lib()
    if not lib:
        yield
        return
    handler = _get_alsa_error_handler()
    handler_ptr = ctypes.cast(handler, ctypes.c_void_p)
    global _ALSA_HANDLER_REFCOUNT
    with _ALSA_HANDLER_LOCK:
        _ALSA_HANDLER_REFCOUNT += 1
        if _ALSA_HANDLER_REFCOUNT == 1:
            lib.snd_lib_error_set_handler(handler_ptr)
    try:
        yield
    finally:
        with _ALSA_HANDLER_LOCK:
            _ALSA_HANDLER_REFCOUNT -= 1
            if _ALSA_HANDLER_REFCOUNT <= 0:
                _ALSA_HANDLER_REFCOUNT = 0
                lib.snd_lib_error_set_handler(ctypes.c_void_p(0))


class OutputManager:
    def __init__(self, *, get_server_url, get_auth_token, get_sendspin_client_id, get_sendspin_client_name, has_sendspin_support, get_output_backend=None, get_pulse_device=None, get_alsa_device=None, local_device_names=None, on_outputs_changed=None, on_output_selected=None, on_loading_state_changed=None, client_session=None):
        self._get_server_url = get_server_url; self._get_auth_token = get_auth_token; self._client_session = client_session; self._get_sendspin_client_id = get_sendspin_client_id; self._get_sendspin_client_name = get_sendspin_client_name; self._has_sendspin_support = has_sendspin_support
        self._get_output_backend = get_output_backend or (lambda: "")
        self._get_pulse_device = get_pulse_device or (lambda: "")
        self._get_alsa_device = get_alsa_device or (lambda: "")
        self.local_device_names = local_device_names or set(); self.on_outputs_changed = on_outputs_changed; self.on_output_selected = on_output_selected; self.on_loading_state_changed = on_loading_state_changed
        self.local_audio_outputs = []; self.local_audio_outputs_by_id = {}; self.local_audio_lock = threading.Lock(); self.output_targets = []; self.output_target_rows = {}; self.sendspin_player_id = None
        self.preferred_player_id = None; self.preferred_local_output_id = None; self.preferred_local_output_name = None; self.output_loading = False; self.status_message = ""
        self._selected_key = None; self._refresh_pending = False; self._refresh_after_load = False
        self._logger = logging.getLogger(__name__)

    def get_local_outputs(self): return list(self.local_audio_outputs)
    def get_output_targets(self): return list(self.output_targets)
    def get_selected_output(self): return self.output_target_rows.get(self._selected_key) if self._selected_key else None

    def schedule_refresh(self):
        if self._refresh_pending: return
        self._refresh_pending = True; timer = threading.Timer(0.3, self._handle_scheduled_refresh); timer.daemon = True; timer.start()

    def _handle_scheduled_refresh(self): self._refresh_pending = False; self.refresh()

    def refresh(self):
        if self.output_loading: self._refresh_after_load = True; return
        if not self._get_server_url(): self._set_loading_state(False, "Connect to your Music Assistant server to see outputs."); self.populate_output_targets([]); return
        self._set_loading_state(True, "Loading outputs..."); threading.Thread(target=self._load_output_targets_worker, daemon=True).start()

    def _load_output_targets_worker(self):
        try:
            if self._client_session:
                players = self._client_session.run(
                    self._get_server_url(),
                    self._get_auth_token(),
                    self._fetch_output_targets_async,
                )
            else:
                players = asyncio.run(self._fetch_output_targets_legacy())
            error = ""
        except Exception as exc:
            players, error = [], str(exc)
        self.on_output_targets_loaded(players, error)

    async def _fetch_output_targets_async(self, client):
        await client.players.fetch_state()
        players = [
            player
            for player in client.players.players
            if player.available and player.enabled
        ]
        players.sort(key=lambda player: player.name.casefold())
        return players

    async def _fetch_output_targets_legacy(self):
        token = self._get_auth_token() or None
        async with MusicAssistantClient(self._get_server_url(), None, token=token) as client:
            return await self._fetch_output_targets_async(client)

    def on_output_targets_loaded(self, players, error):
        if error: self.populate_output_targets([]); self._set_loading_state(False, f"Unable to load outputs: {error}"); return
        if players:
            for player in players: self._logger.info("Output option: %s (id=%s)", getattr(player, "name", "Unknown"), getattr(player, "player_id", "unknown"))
        else: self._logger.info("Output option list is empty.")
        self.populate_output_targets(players); self._set_loading_state(False, "" if players else "No outputs available.")
        if self._refresh_after_load: self._refresh_after_load = False; self.refresh()

    def populate_output_targets(self, players):
        self.output_targets = []; self.output_target_rows = {}; self.sendspin_player_id = None
        local_outputs = self.refresh_local_audio_outputs() if self._has_sendspin_support() else []
        for player in players:
            display_name = player.name
            if self.is_sendspin_player(player): self.sendspin_player_id = player.player_id; self.add_sendspin_output_rows(player, local_outputs); continue
            if self.is_local_player(player): display_name = f"{display_name} (This Computer)"
            self.add_output_row(player.player_id, display_name)
        selected_key = self.pick_default_output_key()
        selection_changed = self._set_selection(selected_key[0], selected_key[1]) if selected_key else (self._set_selection(None, None) if not players else False)
        self._notify_outputs_changed();
        if selection_changed: self._notify_output_selected()

    def add_sendspin_output_rows(self, player, local_outputs):
        self.add_output_row(player.player_id, "This Computer (Music Assistant GTK)", local_output_id=None, local_output_name="System Default")
        backend, _pulse_device, _alsa_device = self.get_effective_output_settings()
        for output in local_outputs:
            name = output["name"]; suffix_parts = []
            alsa_path = output.get("alsa_path") or ""
            if backend == "alsa" and alsa_path:
                suffix_parts.append(f"ALSA {alsa_path}")
            if output.get("is_usb") and "usb" not in name.casefold(): suffix_parts.append("USB DAC")
            suffix_parts.append("This Computer"); suffix = ", ".join(suffix_parts); display_name = f"{name} ({suffix})" if suffix else name
            self.add_output_row(player.player_id, display_name, local_output_id=output["id"], local_output_name=output["name"])

    def add_output_row(self, player_id, display_name, local_output_id=None, local_output_name=None):
        key = (player_id, local_output_id)
        if key in self.output_target_rows:
            return
        output = {"player_id": player_id, "display_name": display_name, "local_output_id": local_output_id, "local_output_name": local_output_name}
        self.output_targets.append(output); self.output_target_rows[key] = output

    def pick_default_output_key(self):
        if not self.output_target_rows: return None
        if self.preferred_player_id:
            preferred_key = (self.preferred_player_id, self.preferred_local_output_id)
            if preferred_key in self.output_target_rows: return preferred_key
            fallback_key = (self.preferred_player_id, None)
            if fallback_key in self.output_target_rows: return fallback_key
        if self.sendspin_player_id:
            preferred_key = (self.sendspin_player_id, self.preferred_local_output_id)
            if preferred_key in self.output_target_rows: return preferred_key
            fallback_key = (self.sendspin_player_id, None)
            if fallback_key in self.output_target_rows: return fallback_key
        return next(iter(self.output_target_rows.keys()))

    def is_sendspin_player(self, player):
        player_id = getattr(player, "player_id", None)
        if not player_id: return False
        sendspin_id = self._get_sendspin_client_id()
        if sendspin_id: return player_id == sendspin_id
        player_name = getattr(player, "name", ""); sendspin_name = self._get_sendspin_client_name()
        return bool(sendspin_name and player_name and player_name.strip().casefold() == sendspin_name.casefold())

    def is_sendspin_player_id(self, player_id):
        if not player_id: return False
        if self.sendspin_player_id and player_id == self.sendspin_player_id: return True
        sendspin_id = self._get_sendspin_client_id(); return bool(sendspin_id and player_id == sendspin_id)

    def is_local_player(self, player):
        if self.is_sendspin_player(player): return True
        if not self.local_device_names: return False
        name = getattr(player, "name", "") or ""; normalized = name.casefold()
        if normalized in self.local_device_names: return True
        return any(local in normalized for local in self.local_device_names)

    def select_output(self, player_id, local_output_id=None):
        if self._set_selection(player_id, local_output_id): self._notify_output_selected()

    def _set_selection(self, player_id, local_output_id):
        previous_key = self._selected_key; self.preferred_player_id = player_id
        if self.is_sendspin_player_id(player_id):
            self.preferred_local_output_id = local_output_id; output = self.output_target_rows.get((player_id, local_output_id))
            self.preferred_local_output_name = output.get("local_output_name") if output else None
        self._selected_key = (player_id, local_output_id) if player_id else None
        return previous_key != self._selected_key

    def get_preferred_local_output(self):
        if not self.preferred_local_output_id: return None
        if not self.local_audio_outputs_by_id: self.refresh_local_audio_outputs()
        return self.local_audio_outputs_by_id.get(self.preferred_local_output_id)

    def get_preferred_local_output_formats(self):
        local_output = self.get_preferred_local_output(); return list(local_output.get("supported_formats") or []) if local_output else []

    def get_preferred_local_output_formats_for_sendspin(self):
        formats = self.get_preferred_local_output_formats()
        if not formats:
            return []
        rates_with_16 = {rate for rate, depth in formats if depth == 16}
        result = list(formats)
        for rate in sorted({rate for rate, _depth in formats}):
            if rate in rates_with_16:
                continue
            result.append((rate, 16))
        return result

    def _is_pipewire_device_obj(self, item):
        try: return self.is_pipewire_device(item.get_properties(), item.get_device_class() or "")
        except Exception: return False

    def _list_audio_sink_devices(self):
        if Gst is None: return []
        Gst.init(None); monitor = Gst.DeviceMonitor(); monitor.add_filter("Audio/Sink", None)
        try:
            with _suppress_alsa_errors():
                monitor.start(); devices = list(monitor.get_devices() or [])
        finally: monitor.stop()
        if not devices: return []
        if any(self._is_pipewire_device_obj(device) for device in devices): devices = [device for device in devices if self._is_pipewire_device_obj(device)]
        return devices

    def refresh_local_audio_outputs(self):
        backend, _pulse_device, _alsa_device = self.get_effective_output_settings()
        if backend == "alsa":
            outputs = self.list_alsa_outputs()
            if outputs:
                with self.local_audio_lock:
                    output_map = {output["id"]: output for output in outputs}
                    self.local_audio_outputs = outputs; self.local_audio_outputs_by_id = output_map; return outputs
        if Gst is None: self.local_audio_outputs = []; self.local_audio_outputs_by_id = {}; return []
        with self.local_audio_lock:
            outputs, output_map = [], {}
            for device in self._list_audio_sink_devices():
                output = self.describe_local_audio_output(device)
                if not output or output["id"] in output_map: continue
                outputs.append(output); output_map[output["id"]] = output
            outputs.sort(key=lambda item: (not item["is_usb"], item["name"].casefold()))
            self.local_audio_outputs = outputs; self.local_audio_outputs_by_id = output_map; return outputs

    def describe_local_audio_output(self, device):
        if Gst is None: return None
        try:
            display_name = device.get_display_name() or ""
            props = device.get_properties()
            device_class = device.get_device_class() or ""
        except Exception:
            return None
        alsa_path = self.get_alsa_device_path(props)
        try:
            caps = device.get_caps()
        except Exception:
            caps = None
        output_id = self.extract_gst_device_id(props, display_name)
        supported_formats = self.get_supported_pcm_formats(caps)
        return {
            "id": output_id,
            "name": display_name or output_id,
            "supported_formats": supported_formats,
            "is_usb": self.is_usb_audio_device(props, display_name),
            "is_pipewire": self.is_pipewire_device(props, device_class),
            "alsa_path": alsa_path,
        }

    def list_alsa_outputs(self):
        cards = self.read_alsa_cards()
        playback_devices = self.read_alsa_playback_devices()
        outputs = []
        for card_index in sorted(playback_devices.keys()):
            device_index = playback_devices[card_index]
            card_name = cards.get(card_index) or f"Card {card_index}"
            alsa_path = f"plughw:{card_index},{device_index}"
            output_id = f"alsa:{alsa_path}"
            is_usb = "usb" in card_name.casefold()
            outputs.append(
                {
                    "id": output_id,
                    "name": card_name,
                    "supported_formats": [],
                    "is_usb": is_usb,
                    "is_pipewire": False,
                    "alsa_path": alsa_path,
                    "alsa_hw_path": f"hw:{card_index},{device_index}",
                }
            )
        return outputs

    @staticmethod
    def read_alsa_cards():
        cards = {}
        try:
            with open("/proc/asound/cards", "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return cards
        for line in lines:
            match = re.match(r"\s*(\d+)\s+\[(.*?)\]:\s*(.*)", line)
            if not match:
                continue
            try:
                card_index = int(match.group(1))
            except ValueError:
                continue
            short_name = match.group(2).strip()
            description = match.group(3).strip()
            label = description
            if " - " in label:
                label = label.split(" - ", 1)[1].strip()
            if not label:
                label = short_name or f"Card {card_index}"
            cards[card_index] = label
        return cards

    @staticmethod
    def read_alsa_playback_devices():
        playback_devices = {}
        try:
            with open("/proc/asound/pcm", "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            return playback_devices
        for line in lines:
            match = re.match(r"\s*(\d+)-(\d+):\s*(.*?)\s*:\s*(.*?)\s*:\s*(.*)", line)
            if not match:
                continue
            try:
                card_index = int(match.group(1))
                device_index = int(match.group(2))
            except ValueError:
                continue
            caps = match.group(5)
            if "playback" not in (caps or "").casefold():
                continue
            current = playback_devices.get(card_index)
            if current is None or device_index < current:
                playback_devices[card_index] = device_index
        return playback_devices

    def get_effective_output_settings(self):
        backend = (self._get_output_backend() or "").strip().casefold()
        pulse_device = (self._get_pulse_device() or "").strip()
        alsa_device = self.normalize_alsa_device_path((self._get_alsa_device() or "").strip())
        env_backend = os.getenv("SENDSPIN_OUTPUT_BACKEND", "").strip().casefold()
        env_pulse_device = os.getenv("SENDSPIN_PULSE_DEVICE", "").strip()
        env_alsa_device = self.normalize_alsa_device_path(os.getenv("SENDSPIN_ALSA_DEVICE", "").strip())
        if env_backend:
            backend = env_backend
        if env_pulse_device:
            pulse_device = env_pulse_device
        if env_alsa_device:
            alsa_device = env_alsa_device
        if backend == "pulseaudio":
            backend = "pulse"
        if not backend:
            if pulse_device:
                backend = "pulse"
            elif alsa_device:
                backend = "alsa"
        return backend, pulse_device, alsa_device

    @staticmethod
    def extract_gst_device_id(props, fallback):
        if props:
            for key in ("device.id", "node.name", "object.path", "device.name", "device.serial", "device.nick"):
                try:
                    if props.has_field(key): value = props.get_value(key)
                    else: continue
                except Exception: continue
                if isinstance(value, str):
                    cleaned = value.strip()
                    if cleaned: return cleaned
        return fallback or "audio-output"

    @staticmethod
    def is_pipewire_device(props, device_class):
        if "pipewire" in (device_class or "").casefold(): return True
        if props:
            try:
                if props.has_field("node.name") or props.has_field("object.serial"):
                    return True
            except Exception:
                pass
            try: props_str = props.to_string()
            except Exception: props_str = ""
            if "pipewire" in props_str.casefold(): return True
        return False

    @staticmethod
    def is_usb_audio_device(props, display_name):
        if "usb" in (display_name or "").casefold(): return True
        if props:
            for key in ("device.bus", "device.bus-path", "device.bus_path", "device.description", "device.name", "node.description", "node.name"):
                try:
                    if props.has_field(key): value = props.get_value(key)
                    else: continue
                except Exception: continue
                if isinstance(value, str) and "usb" in value.casefold(): return True
        return False

    def get_supported_pcm_formats(self, caps):
        if Gst is None or caps is None: return []
        try:
            if caps.is_empty(): return []
        except Exception: pass
        candidate_rates = (44100, 48000, 88200, 96000, 176400, 192000, 352800, 384000); candidate_depths = (16, 24, 32); supported = set()
        for bit_depth in candidate_depths:
            gst_formats = [self.get_gst_pcm_format(bit_depth)]
            if bit_depth == 24:
                gst_formats.append("S24_32LE")
            for sample_rate in candidate_rates:
                for gst_format in gst_formats:
                    candidate = Gst.Caps.from_string("audio/x-raw," f"format={gst_format}," "channels=2," f"rate={sample_rate}," "layout=interleaved")
                    try:
                        if caps.can_intersect(candidate):
                            supported.add((sample_rate, bit_depth))
                            break
                    except Exception:
                        continue
        return sorted(supported, key=lambda item: (item[0], item[1]))

    @staticmethod
    def get_pipewire_node_name(props):
        if not props:
            return ""
        try:
            if props.has_field("node.name"):
                value = props.get_value("node.name")
            else:
                value = None
        except Exception:
            value = None
        if isinstance(value, str):
            return value.strip()
        return ""

    @staticmethod
    def get_alsa_device_path(props):
        if not props:
            return ""
        raw_path = None
        try:
            if props.has_field("api.alsa.path"):
                raw_path = props.get_value("api.alsa.path")
            else:
                raw_path = None
        except Exception:
            raw_path = None
        if isinstance(raw_path, str):
            cleaned = OutputManager.normalize_alsa_device_path(raw_path)
            if cleaned:
                return cleaned
        card = None
        device = None
        try:
            if props.has_field("api.alsa.pcm.card"):
                card = props.get_value("api.alsa.pcm.card")
        except Exception:
            card = None
        try:
            if props.has_field("api.alsa.pcm.device"):
                device = props.get_value("api.alsa.pcm.device")
        except Exception:
            device = None
        if isinstance(card, (int, float)) and isinstance(device, (int, float)):
            return f"hw:{int(card)},{int(device)}"
        return ""

    @staticmethod
    def normalize_alsa_device_path(value: str) -> str:
        if not isinstance(value, str):
            return ""
        cleaned = value.strip()
        if not cleaned:
            return ""
        if "{" in cleaned:
            cleaned = cleaned.split("{", 1)[0].rstrip()
        if cleaned.endswith(":"):
            cleaned = cleaned[:-1].rstrip()
        return cleaned

    @staticmethod
    def _looks_like_alsa_device(value: str) -> bool:
        if not isinstance(value, str):
            return False
        cleaned = value.strip()
        if not cleaned:
            return False
        lowered = cleaned.casefold()
        if "{" in cleaned:
            return True
        if lowered.startswith(("hw:", "plughw:", "iec958:", "front:", "surround", "sysdefault", "dmix:", "dsnoop:", "alsa:", "plug:")):
            return True
        return False

    @staticmethod
    def _extract_alsa_target(value: str) -> str:
        if not isinstance(value, str):
            return ""
        cleaned = value.strip()
        if cleaned.startswith("alsa:"):
            cleaned = cleaned.split(":", 1)[1]
        return OutputManager.normalize_alsa_device_path(cleaned)

    def get_pulse_device_name(self, props, output_id: str | None = None) -> str:
        candidates = []
        if props:
            for key in ("node.name", "device.name", "device.nick", "object.path", "device.id"):
                try:
                    if not props.has_field(key):
                        continue
                    value = props.get_value(key)
                except Exception:
                    continue
                if isinstance(value, (int, float)):
                    value = str(int(value))
                if isinstance(value, str) and value.strip():
                    candidates.append(value)
        if isinstance(output_id, str) and output_id.strip():
            candidates.append(output_id)
        for candidate in candidates:
            cleaned = candidate.strip()
            if not cleaned:
                continue
            if self._looks_like_alsa_device(cleaned):
                continue
            if cleaned.isdigit():
                continue
            return cleaned
        return ""

    def create_sink_for_output(self, output_id):
        if Gst is None or not output_id: return None
        Gst.init(None)
        backend, pulse_device, alsa_device = self.get_effective_output_settings()
        if isinstance(output_id, str) and output_id.startswith("alsa:"):
            output_target = self.normalize_alsa_device_path(
                output_id.split(":", 1)[1]
            )
            if alsa_device and alsa_device == output_target:
                target = alsa_device
            else:
                target = output_target or alsa_device
            return self.create_alsa_sink(target)
        for device in self._list_audio_sink_devices():
            try:
                props = device.get_properties()
                display_name = device.get_display_name() or ""
                device_class = device.get_device_class() or ""
            except Exception:
                continue
            device_id = self.extract_gst_device_id(props, display_name)
            if device_id != output_id: continue
            is_pipewire = self.is_pipewire_device(props, device_class)
            if backend in ("pulse", "pulseaudio"):
                prefer_pipewire = bool(os.getenv("SENDSPIN_PREFER_PIPEWIRE"))
                if is_pipewire and prefer_pipewire:
                    target = self.get_pipewire_target_object(props)
                    sink = self._create_pipewire_sink(target)
                    if sink:
                        if os.getenv("SENDSPIN_DEBUG"):
                            if target:
                                self._logger.info(
                                    "Using PipeWire sink target-object=%s for output %s",
                                    target,
                                    output_id,
                                )
                            else:
                                self._logger.info(
                                    "Using PipeWire default sink for output %s",
                                    output_id,
                                )
                        return sink
                sink = Gst.ElementFactory.make("pulsesink", None)
                if sink:
                    target = pulse_device or self.get_pulse_device_name(props, output_id)
                    if target:
                        try:
                            sink.set_property("device", target)
                            if os.getenv("SENDSPIN_DEBUG"):
                                self._logger.info(
                                    "Using PulseAudio sink=%s for output %s",
                                    target,
                                    output_id,
                                )
                        except Exception:
                            pass
                        return sink
                    if not is_pipewire:
                        alsa_target = self.get_alsa_device_path(props)
                        if not alsa_target and isinstance(output_id, str) and self._looks_like_alsa_device(output_id):
                            alsa_target = self._extract_alsa_target(output_id)
                        if alsa_target:
                            fallback = self.create_alsa_sink(alsa_target)
                            if fallback:
                                if os.getenv("SENDSPIN_DEBUG"):
                                    self._logger.info(
                                        "PulseAudio backend requested but output %s looks like ALSA; using ALSA sink=%s",
                                        output_id,
                                        alsa_target,
                                    )
                                return fallback
                    return sink
                if os.getenv("SENDSPIN_DEBUG"):
                    self._logger.info(
                        "PulseAudio backend requested but unavailable; falling back."
                    )
            if backend == "alsa":
                target = alsa_device or self.get_alsa_device_path(props)
                sink = self.create_alsa_sink(target)
                if sink:
                    if os.getenv("SENDSPIN_DEBUG") and target:
                        self._logger.info(
                            "Using ALSA device=%s for output %s",
                            target,
                            output_id,
                        )
                    return sink
                if os.getenv("SENDSPIN_DEBUG"):
                    self._logger.info(
                        "ALSA backend requested but unavailable; falling back."
                    )
            try: sink = device.create_element(None)
            except Exception: return None
            if sink and is_pipewire:
                target = self.get_pipewire_target_object(props)
                if target:
                    try:
                        sink.set_property("target-object", target)
                        if os.getenv("SENDSPIN_DEBUG"):
                            self._logger.info(
                                "Using PipeWire target-object=%s for output %s",
                                target,
                                output_id,
                            )
                    except Exception:
                        pass
            return sink
        self._logger.warning("No GStreamer sink matched output id: %s", output_id)
        return None

    def create_default_sink(self):
        if Gst is None:
            return None
        Gst.init(None)
        backend, pulse_device, alsa_device = self.get_effective_output_settings()
        if backend in ("pulse", "pulseaudio"):
            prefer_pipewire = bool(os.getenv("SENDSPIN_PREFER_PIPEWIRE"))
            if prefer_pipewire:
                pw_sink = self._create_pipewire_sink(os.getenv("SENDSPIN_PIPEWIRE_TARGET", "").strip() or None)
                if pw_sink:
                    if os.getenv("SENDSPIN_DEBUG"):
                        self._logger.info("Using PipeWire default sink")
                    return pw_sink
            sink = Gst.ElementFactory.make("pulsesink", None)
            if sink and pulse_device:
                try:
                    sink.set_property("device", pulse_device)
                except Exception:
                    pass
            if sink:
                if os.getenv("SENDSPIN_DEBUG"):
                    if pulse_device:
                        self._logger.info(
                            "Using PulseAudio default sink device=%s",
                            pulse_device,
                        )
                    else:
                        self._logger.info("Using PulseAudio default sink")
                return sink
            if os.getenv("SENDSPIN_DEBUG"):
                self._logger.info(
                    "PulseAudio backend requested but unavailable; using auto sink."
                )
            return None
        if backend == "alsa":
            sink = self.create_alsa_sink(alsa_device)
            if sink:
                if os.getenv("SENDSPIN_DEBUG") and alsa_device:
                    self._logger.info(
                        "Using ALSA default device=%s",
                        alsa_device,
                    )
                return sink
            if os.getenv("SENDSPIN_DEBUG"):
                self._logger.info(
                    "ALSA backend requested but unavailable; using auto sink."
                )
            return None
        return None

    def create_alsa_sink(self, target: str):
        if Gst is None:
            return None
        sink = Gst.ElementFactory.make("alsasink", None)
        if not sink:
            return None
        target = self.normalize_alsa_device_path(target) if target else ""
        if target:
            try:
                sink.set_property("device", target)
            except Exception:
                pass
        return sink

    @staticmethod
    def get_gst_pcm_format(bit_depth):
        if bit_depth == 16: return "S16LE"
        if bit_depth == 24: return "S24LE"
        if bit_depth == 32: return "S32LE"
        return "S16LE"

    @staticmethod
    def get_pipewire_target_object(props):
        if not props:
            return ""
        override = os.getenv("SENDSPIN_PIPEWIRE_TARGET", "").strip()
        if override:
            return override
        for key in ("object.serial", "object.id", "node.name", "object.path"):
            try:
                if not props.has_field(key):
                    continue
                value = props.get_value(key)
            except Exception:
                continue
            if value is None:
                continue
            if isinstance(value, (int, float)):
                return str(int(value))
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
        return ""

    @staticmethod
    def _create_pipewire_sink(target: str | None):
        if Gst is None:
            return None
        sink = Gst.ElementFactory.make("pipewiresink", None)
        if not sink:
            return None
        if target:
            try:
                sink.set_property("target-object", target)
            except Exception:
                pass
        return sink

    def _set_loading_state(self, loading, message):
        changed = False
        if self.output_loading != loading: self.output_loading = loading; changed = True
        if self.status_message != message: self.status_message = message; changed = True
        if changed: self._notify_loading_state_changed()

    def _notify_outputs_changed(self):
        if self.on_outputs_changed: self.on_outputs_changed()

    def _notify_output_selected(self):
        if self.on_output_selected: self.on_output_selected()

    def _notify_loading_state_changed(self):
        if self.on_loading_state_changed: self.on_loading_state_changed()
