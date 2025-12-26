from __future__ import annotations

import logging
import os
from typing import Callable

from .sendspin import PCMFormat

Gst = None
try:
    import gi

    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
except (ImportError, ValueError):
    Gst = None


class AudioPipeline:
    def __init__(
        self,
        *,
        get_supported_formats: Callable[[], list[tuple[int, int]]] | None = None,
    ) -> None:
        self._get_supported_formats = get_supported_formats or (lambda: [])
        self.pipeline: Gst.Pipeline | None = None
        self.appsrc: Gst.Element | None = None
        self.volume_element: Gst.Element | None = None
        self.eq_element: Gst.Element | None = None
        self.stream_format: PCMFormat | None = None
        self.stream_start_ts: int | None = None
        self.last_pts_ns: int | None = None
        self._bytes_per_sample_override: int | None = None
        self._bus: Gst.Bus | None = None
        self._bus_watch_id: int | None = None
        self.volume = 0.65
        self.muted = False
        self.eq_enabled = False
        self.eq_num_bands = 10
        self.eq_band_configs: list[dict] = []
        self._logger = logging.getLogger(__name__)

    @staticmethod
    def _configure_queue(queue: Gst.Element) -> None:
        queue.set_property("max-size-time", 200_000_000)
        queue.set_property("max-size-bytes", 0)
        queue.set_property("max-size-buffers", 0)

    @staticmethod
    def _pick_output_format(
        format_info: PCMFormat,
        supported_formats: list[tuple[int, int]],
    ) -> tuple[int, int] | None:
        if not supported_formats:
            return None
        stream_rate = format_info.sample_rate
        best = None
        best_key = None
        for sample_rate, bit_depth in supported_formats:
            key = (abs(sample_rate - stream_rate), -bit_depth)
            if best_key is None or key < best_key:
                best_key = key
                best = (sample_rate, bit_depth)
        return best

    def is_active(self) -> bool:
        return bool(self.pipeline and self.appsrc)

    def create_pipeline(
        self,
        format_info: PCMFormat,
        sink_element: Gst.Element | None,
        volume: float,
        muted: bool,
    ) -> None:
        if Gst is None:
            return
        if (
            self.stream_format
            and self.pipeline
            and self.appsrc
            and self.stream_format == format_info
        ):
            self.pipeline.set_state(Gst.State.PLAYING)
            self.set_volume(volume)
            self.set_muted(muted)
            return
        self.destroy_pipeline()
        Gst.init(None)
        pipeline = Gst.Pipeline.new("sendspin-pipeline")
        appsrc = Gst.ElementFactory.make("appsrc", "sendspin-src")
        queue = Gst.ElementFactory.make("queue", None)
        if queue:
            self._configure_queue(queue)
        audioconvert = Gst.ElementFactory.make("audioconvert", None)
        volume_element = Gst.ElementFactory.make("volume", None)
        eq_element = Gst.ElementFactory.make("equalizer-nbands", None)
        post_convert = None
        sink = sink_element
        supported_formats = list(self._get_supported_formats() or [])
        output_format = None
        if sink is not None and supported_formats:
            output_format = self._pick_output_format(
                format_info, supported_formats
            )
        if sink is None:
            sink = Gst.ElementFactory.make("autoaudiosink", None)
        target_rate = format_info.sample_rate
        target_bit_depth = format_info.bit_depth
        if output_format:
            target_rate, target_bit_depth = output_format
        use_resample = target_rate != format_info.sample_rate
        audioresample = None
        if use_resample:
            audioresample = Gst.ElementFactory.make("audioresample", None)
        capsfilter = None
        if output_format:
            capsfilter = Gst.ElementFactory.make("capsfilter", None)
            if eq_element:
                post_convert = Gst.ElementFactory.make("audioconvert", None)
        if not pipeline or not appsrc or not audioconvert or not sink:
            self._logger.warning(
                "Failed to initialize GStreamer pipeline for Sendspin audio."
            )
            return
        if use_resample and not audioresample:
            self._logger.warning(
                "Failed to initialize GStreamer pipeline for Sendspin audio."
            )
            return
        if output_format and not capsfilter:
            self._logger.warning(
                "Failed to initialize caps filter for Sendspin audio."
            )
            return
        if volume_element is None:
            self._logger.warning(
                "Failed to initialize volume control for Sendspin audio."
            )
        if eq_element is None:
            self._logger.warning(
                "Failed to initialize equalizer for Sendspin audio."
            )
        if output_format and eq_element and post_convert is None:
            self._logger.warning(
                "Failed to initialize post-EQ converter for Sendspin audio."
            )
        caps = Gst.Caps.from_string(self.build_pcm_caps(format_info))
        appsrc.set_property("caps", caps)
        appsrc.set_property("format", Gst.Format.TIME)
        appsrc.set_property("is-live", True)
        appsrc.set_property("do-timestamp", False)
        appsrc.set_property("block", True)
        pipeline.add(appsrc)
        if queue:
            pipeline.add(queue)
        pipeline.add(audioconvert)
        if volume_element:
            pipeline.add(volume_element)
        if eq_element:
            pipeline.add(eq_element)
        if post_convert:
            pipeline.add(post_convert)
        if capsfilter:
            output_caps = Gst.Caps.from_string(
                "audio/x-raw,"
                f"format={self.get_gst_pcm_format(target_bit_depth)},"
                f"channels={format_info.channels},"
                f"rate={target_rate},"
                "layout=interleaved"
            )
            capsfilter.set_property("caps", output_caps)
            pipeline.add(capsfilter)
        pipeline.add(sink)
        if queue:
            appsrc.link(queue)
            queue.link(audioconvert)
        else:
            appsrc.link(audioconvert)
        link_element = audioconvert
        if volume_element:
            audioconvert.link(volume_element)
            link_element = volume_element
            if eq_element:
                volume_element.link(eq_element)
                link_element = eq_element
        elif eq_element:
            audioconvert.link(eq_element)
            link_element = eq_element
        if post_convert:
            link_element.link(post_convert)
            link_element = post_convert
        tail_element = link_element
        if audioresample:
            pipeline.add(audioresample)
            tail_element.link(audioresample)
            tail_element = audioresample
        if capsfilter:
            tail_element.link(capsfilter)
            tail_element = capsfilter
        tail_element.link(sink)
        self._attach_bus_watch(pipeline)
        pipeline.set_state(Gst.State.PLAYING)
        self.pipeline = pipeline
        self.appsrc = appsrc
        self.volume_element = volume_element
        self.eq_element = eq_element
        self.stream_format = format_info
        self.stream_start_ts = None
        self.last_pts_ns = None
        pipeline_message = (
            "Sendspin pipeline ready: %s Hz/%s-bit/%s ch, sink=%s, resample=%s, eq=%s"
        )
        pipeline_args = (
            format_info.sample_rate,
            format_info.bit_depth,
            format_info.channels,
            sink.get_factory().get_name() if sink and sink.get_factory() else "unknown",
            use_resample,
            bool(eq_element),
        )
        if os.getenv("SENDSPIN_DEBUG"):
            if output_format:
                self._logger.info(
                    "Sendspin output caps: %s Hz/%s-bit/%s ch",
                    target_rate,
                    target_bit_depth,
                    format_info.channels,
                )
            self._logger.info(pipeline_message, *pipeline_args)
        else:
            self._logger.debug(pipeline_message, *pipeline_args)
        self.set_volume(volume)
        self.set_muted(muted)
        self._apply_eq_config()

    def destroy_pipeline(self) -> None:
        if not self.pipeline:
            return
        self.pipeline.set_state(Gst.State.NULL)
        self.pipeline = None
        self.appsrc = None
        self.volume_element = None
        self.eq_element = None
        self.stream_format = None
        self.stream_start_ts = None
        self.last_pts_ns = None
        self._bytes_per_sample_override = None
        self._detach_bus_watch()

    def flush(self) -> None:
        if self.appsrc is None or Gst is None:
            return
        self.stream_start_ts = None
        self.last_pts_ns = None
        pipeline = self.pipeline
        try:
            if pipeline:
                pipeline.send_event(Gst.Event.new_flush_start())
                pipeline.send_event(Gst.Event.new_flush_stop(True))
                return
            self.appsrc.send_event(Gst.Event.new_flush_start())
            self.appsrc.send_event(Gst.Event.new_flush_stop(True))
        except Exception:
            self._logger.debug("Flush events failed.", exc_info=True)

    def push_audio(
        self,
        timestamp_us: int,
        data: bytes,
        format_info: PCMFormat,
    ) -> None:
        if not self.appsrc or Gst is None:
            return
        frame_size = self._get_frame_size(format_info)
        if frame_size <= 0:
            return
        if len(data) % frame_size != 0:
            if format_info.bit_depth == 24:
                packed_frame = format_info.channels * 3
                aligned_frame = format_info.channels * 4
                if len(data) % aligned_frame == 0:
                    if self._bytes_per_sample_override != 4:
                        self._bytes_per_sample_override = 4
                        self._logger.info(
                            "Detected 24-bit PCM in 32-bit frames; "
                            "switching to S24_32LE caps."
                        )
                        self._update_caps(format_info)
                    frame_size = aligned_frame
                elif (
                    self._bytes_per_sample_override
                    and len(data) % packed_frame == 0
                ):
                    self._bytes_per_sample_override = None
                    self._logger.info(
                        "Detected packed 24-bit PCM; switching to S24LE caps."
                    )
                    self._update_caps(format_info)
                    frame_size = packed_frame
                else:
                    self._logger.warning(
                        "Dropping Sendspin audio chunk with invalid size: %s",
                        len(data),
                    )
                    return
            else:
                self._logger.warning(
                    "Dropping Sendspin audio chunk with invalid size: %s",
                    len(data),
                )
                return
        sample_count = len(data) // frame_size
        duration_ns = int(sample_count / format_info.sample_rate * 1_000_000_000)
        if self.stream_start_ts is None:
            self.stream_start_ts = timestamp_us
        pts_ns = max(0, (timestamp_us - self.stream_start_ts) * 1000)
        if self.last_pts_ns is not None and pts_ns <= self.last_pts_ns:
            pts_ns = self.last_pts_ns + duration_ns
        self.last_pts_ns = pts_ns
        buffer = Gst.Buffer.new_allocate(None, len(data), None)
        buffer.fill(0, data)
        buffer.pts = pts_ns
        buffer.dts = pts_ns
        buffer.duration = duration_ns
        result = self.appsrc.emit("push-buffer", buffer)
        if result != Gst.FlowReturn.OK:
            self._logger.warning("Sendspin audio push failed: %s", result)

    def build_pcm_caps(self, format_info: PCMFormat) -> str:
        bytes_per_sample = self._get_bytes_per_sample(format_info)
        gst_format = self.get_gst_pcm_format(
            format_info.bit_depth,
            bytes_per_sample,
        )
        return (
            "audio/x-raw,"
            f"format={gst_format},"
            f"channels={format_info.channels},"
            f"rate={format_info.sample_rate},"
            "layout=interleaved"
        )

    @staticmethod
    def get_gst_pcm_format(
        bit_depth: int,
        bytes_per_sample: int | None = None,
    ) -> str:
        if bit_depth == 16:
            return "S16LE"
        if bit_depth == 24:
            if bytes_per_sample == 4:
                return "S24_32LE"
            return "S24LE"
        if bit_depth == 32:
            return "S32LE"
        return "S16LE"

    def _get_bytes_per_sample(self, format_info: PCMFormat) -> int:
        if format_info.bit_depth == 24 and self._bytes_per_sample_override:
            return self._bytes_per_sample_override
        return max(1, format_info.bit_depth // 8)

    def _get_frame_size(self, format_info: PCMFormat) -> int:
        return format_info.channels * self._get_bytes_per_sample(format_info)

    def _update_caps(self, format_info: PCMFormat) -> None:
        if not self.appsrc or Gst is None:
            return
        caps = Gst.Caps.from_string(self.build_pcm_caps(format_info))
        self.appsrc.set_property("caps", caps)

    def _attach_bus_watch(self, pipeline: Gst.Pipeline) -> None:
        if Gst is None:
            return
        bus = pipeline.get_bus()
        if not bus:
            return
        bus.add_signal_watch()
        self._bus = bus
        self._bus_watch_id = bus.connect("message", self._on_bus_message)

    def _detach_bus_watch(self) -> None:
        if not self._bus:
            return
        try:
            self._bus.remove_signal_watch()
        except Exception:
            pass
        if self._bus_watch_id is not None:
            try:
                self._bus.disconnect(self._bus_watch_id)
            except Exception:
                pass
        self._bus = None
        self._bus_watch_id = None

    def _on_bus_message(self, _bus: Gst.Bus, message: Gst.Message) -> None:
        msg_type = message.type
        if msg_type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            self._logger.warning("GStreamer error: %s", error)
            if debug:
                if os.getenv("SENDSPIN_DEBUG"):
                    self._logger.info("GStreamer debug: %s", debug)
                else:
                    self._logger.debug("GStreamer debug: %s", debug)
        elif msg_type == Gst.MessageType.WARNING:
            warning, debug = message.parse_warning()
            self._logger.warning("GStreamer warning: %s", warning)
            if debug:
                if os.getenv("SENDSPIN_DEBUG"):
                    self._logger.info("GStreamer debug: %s", debug)
                else:
                    self._logger.debug("GStreamer debug: %s", debug)

    def set_volume(self, volume: float) -> None:
        volume = max(0.0, min(1.0, float(volume)))
        self.volume = volume
        self._apply_volume()

    def set_muted(self, muted: bool) -> None:
        self.muted = bool(muted)
        self._apply_volume()

    def _apply_volume(self) -> None:
        if not self.volume_element:
            return
        self.volume_element.set_property("volume", self.volume)
        self.volume_element.set_property("mute", self.muted)

    def configure_eq_bands(
        self,
        num_bands: int,
        band_configs: list[dict],
    ) -> None:
        try:
            num_bands = int(num_bands)
        except (TypeError, ValueError):
            self._logger.warning("Invalid EQ band count: %s", num_bands)
            return
        if num_bands < 1 or num_bands > 64:
            self._logger.warning("EQ band count out of range: %s", num_bands)
            num_bands = max(1, min(64, num_bands))
        validated_configs: list[dict] = []
        for config in band_configs or []:
            if len(validated_configs) >= num_bands:
                break
            if not isinstance(config, dict):
                self._logger.warning(
                    "Invalid EQ band configuration: %s", config
                )
                continue
            try:
                freq = float(config.get("freq", 0.0))
                bandwidth = float(config.get("bandwidth", 0.0))
                gain = float(config.get("gain", 0.0))
            except (TypeError, ValueError):
                self._logger.warning(
                    "Invalid EQ band configuration: %s", config
                )
                continue
            if freq <= 0 or bandwidth <= 0:
                self._logger.warning(
                    "Invalid EQ band configuration: %s", config
                )
                continue
            if gain < -24.0 or gain > 12.0:
                self._logger.warning(
                    "EQ band gain out of range: %s", gain
                )
                gain = max(-24.0, min(12.0, gain))
            validated_configs.append(
                {"freq": freq, "bandwidth": bandwidth, "gain": gain}
            )
        self.eq_num_bands = num_bands
        self.eq_band_configs = validated_configs
        if self.pipeline:
            self._apply_eq_config()

    def set_eq_enabled(self, enabled: bool) -> None:
        self.eq_enabled = bool(enabled)
        self._apply_eq_config()

    def _apply_eq_config(self) -> None:
        if not self.eq_element:
            return
        self.eq_element.set_property("num-bands", self.eq_num_bands)
        if not self.eq_enabled:
            for index in range(self.eq_num_bands):
                band = self.eq_element.get_child_by_index(index)
                if not band:
                    continue
                band.set_property("gain", 0.0)
            self._logger.debug(
                "EQ configured: enabled=%s, bands=%s",
                self.eq_enabled,
                self.eq_num_bands,
            )
            return
        for index, config in enumerate(
            self.eq_band_configs[: self.eq_num_bands]
        ):
            band = self.eq_element.get_child_by_index(index)
            if not band:
                continue
            band.set_property("freq", config["freq"])
            band.set_property("bandwidth", config["bandwidth"])
            band.set_property("gain", config["gain"])
        self._logger.debug(
            "EQ configured: enabled=%s, bands=%s",
            self.eq_enabled,
            self.eq_num_bands,
        )

    def get_eq_state(self) -> dict:
        return {
            "enabled": self.eq_enabled,
            "num_bands": self.eq_num_bands,
            "band_configs": [
                config.copy() for config in self.eq_band_configs
            ],
        }
