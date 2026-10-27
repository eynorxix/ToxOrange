"""Motor de video: GStreamer playbin (si hay sink embebible) o Gtk.Video.

Preferencia (skill): playbin en la ventana. En GTK4 se necesita
`gtk4paintablesink` (gst-plugins-rs); si no está, se cae a Gtk.MediaFile
(GStreamer por debajo) mostrado en un Gtk.Video.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gio, Gtk  # noqa: E402

_GST_READY = False
_GST = None


def _gst():
    global _GST_READY, _GST
    if not _GST_READY:
        _GST_READY = True
        try:
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst

            Gst.init(None)
            _GST = Gst
        except Exception:
            _GST = None
    return _GST


def paintablesink_available() -> bool:
    gst = _gst()
    if gst is None:
        return False
    return gst.ElementFactory.find("gtk4paintablesink") is not None


US_PER_SECOND = 1_000_000


class PlayerEngine:
    """Envoltorio de reproducción con interfaz unica."""

    def __init__(self, on_error=None, on_eos=None, on_state=None):
        self.on_error = on_error
        self.on_eos = on_eos
        self.on_state = on_state
        self.uri = ""
        self.paintable = None
        self._gst = None
        self._playbin = None
        self._media = None
        self._using_paintable = paintablesink_available()
        if self._using_paintable:
            self._init_gst()
        else:
            self._init_mediafile()

    # -- inicializacion ------------------------------------------------------
    def _init_gst(self):
        gst = _gst()
        self._gst = gst
        self._playbin = gst.ElementFactory.make("playbin", "gonty-player")
        sink = gst.ElementFactory.make("gtk4paintablesink", "gonty-sink")
        self.paintable = sink.get_property("paintable")
        self._playbin.set_property("video-sink", sink)
        bus = self._playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self._on_bus_message)
        self.widget = Gtk.Picture()
        self.widget.set_paintable(self.paintable)
        self.widget.set_hexpand(True)
        self.widget.set_vexpand(True)

    def _init_mediafile(self):
        self.widget = Gtk.Video()
        self.widget.set_hexpand(True)
        self.widget.set_vexpand(True)
        self.widget.set_autoplay(False)

    # -- API comun -----------------------------------------------------------
    def set_uri(self, uri: str):
        self.uri = uri or ""
        if self._using_paintable:
            gst = self._gst
            self._playbin.set_state(gst.State.READY)
            self._playbin.set_property("uri", self.uri)
        else:
            media = Gtk.MediaFile.new_for_file(Gio.File.new_for_uri(self.uri))
            media.connect("notify::error", self._on_media_error)
            media.connect("notify::ended", self._on_media_ended)
            media.connect("notify::playing", self._on_media_playing)
            self._media = media
            self.widget.set_media_stream(media)

    def play(self):
        if self._using_paintable:
            self._playbin.set_state(self._gst.State.PLAYING)
        elif self._media is not None:
            self._media.set_playing(True)

    def pause(self):
        if self._using_paintable:
            self._playbin.set_state(self._gst.State.PAUSED)
        elif self._media is not None:
            self._media.set_playing(False)

    def toggle(self):
        if self.is_playing():
            self.pause()
        else:
            self.play()

    def stop(self):
        if self._using_paintable:
            self._playbin.set_state(self._gst.State.READY)
        elif self._media is not None:
            self._media.set_playing(False)

    def is_playing(self) -> bool:
        if self._using_paintable:
            _ret, state, _pending = self._playbin.get_state(0)
            return state == self._gst.State.PLAYING
        return bool(self._media.get_playing()) if self._media else False

    def has_media(self) -> bool:
        return bool(self.uri)

    def position_us(self) -> int:
        if self._using_paintable:
            ok, value = self._playbin.query_position(self._gst.Format.TIME)
            return value // 1000 if ok else 0
        return int(self._media.get_timestamp()) if self._media else 0

    def duration_us(self) -> int:
        if self._using_paintable:
            ok, value = self._playbin.query_duration(self._gst.Format.TIME)
            return value // 1000 if ok else 0
        return int(self._media.get_duration()) if self._media else 0

    def is_seekable(self) -> bool:
        if self._using_paintable:
            return True
        return bool(self._media.is_seekable()) if self._media else False

    def seek_fraction(self, fraction: float):
        fraction = min(1.0, max(0.0, fraction))
        total = self.duration_us()
        if total <= 0:
            return
        target = int(total * fraction)
        if self._using_paintable:
            self._playbin.seek_simple(
                self._gst.Format.TIME,
                self._gst.SeekFlags.FLUSH | self._gst.SeekFlags.KEY_UNIT,
                target * 1000)
        elif self._media is not None:
            self._media.seek(target)

    def seek_relative(self, seconds: float):
        total = self.duration_us()
        if total <= 0:
            return
        current = self.position_us()
        self.seek_fraction((current + seconds * US_PER_SECOND) / total)

    def set_volume(self, volume: float):
        volume = min(1.0, max(0.0, volume))
        if self._using_paintable:
            self._playbin.set_property("volume", volume)
        elif self._media is not None:
            self._media.set_volume(volume)

    def set_muted(self, muted: bool):
        if self._using_paintable:
            self._playbin.set_property("mute", bool(muted))
        elif self._media is not None:
            self._media.set_muted(bool(muted))

    # -- callbacks -----------------------------------------------------------
    def _on_media_error(self, media, _pspec):
        err = media.get_property("error")
        if self.on_error and err is not None:
            self.on_error(err.message if hasattr(err, "message") else str(err))

    def _on_media_ended(self, media, _pspec):
        if self.on_eos and media.get_property("ended"):
            self.on_eos()

    def _on_media_playing(self, media, _pspec):
        if self.on_state:
            self.on_state(media.get_playing())

    def _on_bus_message(self, _bus, message):
        gst = self._gst
        if message.type == gst.MessageType.EOS:
            if self.on_eos:
                self.on_eos()
        elif message.type == gst.MessageType.ERROR:
            err, _debug = message.parse_error()
            if self.on_error:
                self.on_error(err.message)
        elif message.type == gst.MessageType.STATE_CHANGED:
            if message.src == self._playbin and self.on_state:
                _old, new, _pending = message.parse_state_changed()
                self.on_state(new == gst.State.PLAYING)
