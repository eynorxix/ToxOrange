"""Página Reproductor: GStreamer embebido con controles de reproducción."""
from __future__ import annotations

import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from models import ContentItem, ServerInfo  # noqa: E402
from player.engine import PlayerEngine  # noqa: E402
from player.stream import looks_like_media, resolve_stream_url  # noqa: E402
from player.webview import WebViewEngine, webkit_available  # noqa: E402
from providers import build_registry  # noqa: E402
from store import Store  # noqa: E402

TICK_MS = 500


def _fmt_time(us: int) -> str:
    seconds = max(0, us) // 1_000_000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


class PlayerPage(Gtk.Box):
    """Página del Stack que reproduce el stream de un servidor."""

    def __init__(self, store: Store, on_back=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.store = store
        self.on_back = on_back
        self.providers = build_registry()
        self.item: ContentItem | None = None
        self.server: ServerInfo | None = None
        self.stream_url = ""
        self.busy = False
        self._generation = 0
        self._tick_id = 0
        self._updating = False
        self._direct_media = False
        self._servers = []
        self._server_index = 0
        self._play_check_id = 0
        self._fullscreen = False

        self.engine = PlayerEngine(
            on_error=self._on_engine_error,
            on_eos=self._on_engine_eos,
            on_state=self._on_engine_state,
        )
        self.webview = None

        self.header = self._build_header()
        self.append(self.header)

        self.video_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.video_area.add_css_class("player-video")
        self.video_area.set_vexpand(True)
        self.video_area.set_hexpand(True)

        self.video_stack = Gtk.Stack()
        self.video_stack.set_vexpand(True)
        self.video_stack.set_hexpand(True)
        self.engine.widget.set_halign(Gtk.Align.FILL)
        self.engine.widget.set_valign(Gtk.Align.FILL)
        self.video_stack.add_named(self.engine.widget, "gst")
        self.video_area.append(self.video_stack)
        self.append(self.video_area)

        self.controls = self._build_controls()
        self.append(self.controls)

        self.status = Gtk.Label(label="")
        self.status.add_css_class("catalog-status")
        self.status.set_xalign(0)
        self.status.set_margin_start(14)
        self.status.set_margin_end(14)
        self.status.set_margin_bottom(10)
        self.append(self.status)

    # -- ciclo de vida del proceso del reproductor web ----------------------
    def _ensure_webview(self) -> bool:
        """Crea el WebView (proceso propio) para esta reproduccion."""
        if self.webview is not None:
            return True
        if not webkit_available():
            return False
        self.webview = WebViewEngine(
            on_load_failed=self._on_web_load_failed,
            on_fullscreen=self._on_web_fullscreen)
        self.video_stack.add_named(self.webview.widget, "web")
        self.engine_btn.set_sensitive(self._direct_media)
        return True

    def _destroy_webview(self):
        """Mata el proceso del reproductor web de esta publicacion."""
        if self.webview is None:
            return
        try:
            self.webview.destroy()
        except Exception:
            try:
                self.video_stack.remove(self.webview.widget)
            except Exception:
                pass
        self.webview = None
        self.engine_btn.set_sensitive(False)
        try:
            self.video_stack.set_visible_child_name("gst")
        except Exception:
            pass


    # -- cabecera ------------------------------------------------------------
    def _build_header(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.add_css_class("titlebar")
        back = Gtk.Button(label="←")
        back.add_css_class("icon-btn")
        back.set_tooltip_text("Volver al detalle (Esc)")
        back.connect("clicked", lambda *_: self._go_back())
        bar.append(back)
        self.header_title = Gtk.Label(label="REPRODUCTOR")
        self.header_title.add_css_class("titlebar-title")
        self.header_title.set_xalign(0)
        self.header_title.set_ellipsize(Pango.EllipsizeMode.END)
        bar.append(self.header_title)
        sp = Gtk.Box()
        sp.set_hexpand(True)
        bar.append(sp)
        self.engine_btn = Gtk.Button(label="⇄")
        self.engine_btn.add_css_class("icon-btn")
        self.engine_btn.set_tooltip_text(
            "Cambiar reproductor (GStreamer / WebKit)")
        self.engine_btn.set_sensitive(self.webview is not None)
        self.engine_btn.connect("clicked", lambda *_: self._toggle_engine())
        bar.append(self.engine_btn)
        self.external_btn = Gtk.Button(label="↗")
        self.external_btn.add_css_class("icon-btn")
        self.external_btn.set_tooltip_text("Abrir stream en el navegador")
        self.external_btn.set_sensitive(False)
        self.external_btn.connect("clicked", lambda *_: self._open_external())
        bar.append(self.external_btn)
        return bar

    def _go_back(self):
        if self.on_back:
            self.on_back()

    # -- controles -----------------------------------------------------------
    def _build_controls(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.add_css_class("player-controls")

        self.play_btn = Gtk.Button(label="▶")
        self.play_btn.add_css_class("icon-btn")
        self.play_btn.set_tooltip_text("Reproducir / pausar (Espacio)")
        self.play_btn.connect("clicked", lambda *_: self.toggle())
        bar.append(self.play_btn)

        stop_btn = Gtk.Button(label="■")
        stop_btn.add_css_class("icon-btn")
        stop_btn.set_tooltip_text("Detener")
        stop_btn.connect("clicked", lambda *_: self.stop_playback())
        bar.append(stop_btn)

        self.time_lbl = Gtk.Label(label="0:00 / 0:00")
        self.time_lbl.add_css_class("player-time")
        bar.append(self.time_lbl)

        self.seek = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.001)
        self.seek.set_hexpand(True)
        self.seek.set_draw_value(False)
        self.seek.set_valign(Gtk.Align.CENTER)
        self.seek.set_sensitive(False)
        self.seek.connect("change-value", self._on_seek)
        self.seek.connect("value-changed", self._on_seek_value)
        bar.append(self.seek)

        self.mute_btn = Gtk.Button(label="🔊")
        self.mute_btn.add_css_class("icon-btn")
        self.mute_btn.set_tooltip_text("Silenciar")
        self.mute_btn.connect("clicked", self._on_mute)
        bar.append(self.mute_btn)

        volume = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.01)
        volume.set_size_request(110, -1)
        volume.set_draw_value(False)
        volume.set_valign(Gtk.Align.CENTER)
        volume.set_value(1.0)
        volume.connect("value-changed", self._on_volume)
        bar.append(volume)
        self.volume = volume
        self._muted = False

        self.fs_btn = Gtk.Button(label="⛶")
        self.fs_btn.add_css_class("icon-btn")
        self.fs_btn.set_tooltip_text("Pantalla completa (F / Esc para salir)")
        self.fs_btn.connect("clicked", lambda *_: self.toggle_fullscreen())
        bar.append(self.fs_btn)
        return bar

    def toggle_fullscreen(self):
        win = self.get_root()
        if win is None:
            return
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            win.fullscreen()
        else:
            win.unfullscreen()
        self._apply_fullscreen(self._fullscreen)

    def exit_fullscreen(self):
        win = self.get_root()
        self._fullscreen = False
        if win is not None and win.is_fullscreen():
            win.unfullscreen()
        if self.webview is not None:
            self.webview.exit_fullscreen()
        self._apply_fullscreen(False)

    def is_fullscreen(self) -> bool:
        return self._fullscreen

    # -- reproduccion --------------------------------------------------------
    def play_item(self, item: ContentItem, server: ServerInfo, *,
                  servers=None, index=None, push_history=True):
        self.item = item
        self.server = server
        if servers:
            self._servers = list(servers)
        elif item is not None and getattr(item, "servers", None):
            self._servers = list(item.servers)
        else:
            self._servers = [server]
        if isinstance(index, int):
            self._server_index = index
        else:
            self._server_index = 0
            for i, cand in enumerate(self._servers):
                if cand is server or cand.player_url == server.player_url:
                    self._server_index = i
                    break
        self._cancel_play_check()
        self._generation += 1
        generation = self._generation
        title = item.title or "Reproductor"
        self.header_title.set_text(title.upper()[:40])
        self._set_status(f"Resolviendo stream · {server.name or 'servidor'}…")
        self.busy = True
        self._reset_controls()
        if not self._fullscreen:
            self._apply_fullscreen(False)
        if push_history:
            self.store.push_history(item)

        provider = self.providers.get(item.provider)
        player_url = server.player_url

        if looks_like_media(player_url):
            self.stream_url = player_url
            self.external_btn.set_sensitive(True)
            self._direct_media = True
            if self._ensure_webview():
                self.engine_btn.set_sensitive(True)
            self._play_gst(player_url)
            return

        if self._ensure_webview():
            # Como el navegador: cargar el embed directamente, sin esperar a
            # resolver el stream (eso agrega latencia). La resolucion se hace
            # en segundo plano solo para el boton externo / cambio a GStreamer.
            self.stream_url = player_url
            self.external_btn.set_sensitive(True)
            self._direct_media = False
            self.busy = False
            self._play_embed(player_url)
            self._resolve_background(provider, player_url, generation)
            return

        def worker():
            try:
                url = resolve_stream_url(provider, player_url)
                error = None
            except Exception as exc:
                url = player_url
                error = str(exc)
            GLib.idle_add(self._on_resolved, url, error, generation)

        threading.Thread(target=worker, daemon=True).start()

    def _resolve_background(self, provider, player_url, generation):
        def worker():
            try:
                url = resolve_stream_url(provider, player_url)
            except Exception:
                url = ""
            GLib.idle_add(self._on_bg_resolved, url, generation)

        threading.Thread(target=worker, daemon=True).start()

    def _on_bg_resolved(self, url, generation):
        if generation != self._generation or not url:
            return False
        self.stream_url = url
        self.external_btn.set_sensitive(True)
        self._direct_media = looks_like_media(url)
        if self.webview is not None:
            self.engine_btn.set_sensitive(self._direct_media)
        return False

    def _on_resolved(self, url, error, generation):
        self.busy = False
        if generation != self._generation:
            return False
        if error:
            self._set_status(f"Error al resolver: {error}")
            return False
        if not url:
            self._set_status("El servidor no devolvió un stream reproducible")
            return False
        self.stream_url = url
        self.external_btn.set_sensitive(True)
        player_url = self.server.player_url if self.server else url
        self._direct_media = looks_like_media(url)
        # Como en la app Android, se prefiere el reproductor propio del servidor
        # (WebKit): los CDN suelen bloquear el m3u8 fuera de su pagina embed.
        # GStreamer queda como alternativa con el boton ⇄.
        if self.webview is not None:
            embed_url = player_url if self._direct_media else (url or player_url)
            self._play_embed(embed_url)
        elif self._direct_media:
            self._play_gst(url)
        else:
            self.seek.set_sensitive(False)
            self._set_status(
                "Este servidor usa su propio reproductor (embed). "
                "Instala webkitgtk-6.0 para verlo aquí (↗ para abrirlo fuera).")
        self.engine_btn.set_sensitive(
            self.webview is not None and self._direct_media)
        return False

    def _play_gst(self, url: str):
        self._cancel_play_check()
        self.video_stack.set_visible_child_name("gst")
        self.engine.set_uri(url)
        self.engine.set_volume(self.volume.get_value())
        self.engine.play()
        self.seek.set_sensitive(True)
        self._set_play_icon(True)
        name = self.server.name if self.server else "servidor"
        self._set_status(f"Reproduciendo · {name}")
        self._start_tick()

    def _play_embed(self, url: str):
        self._stop_tick()
        self.engine.stop()
        self.video_stack.set_visible_child_name("web")
        self.webview.load(url)
        self.seek.set_sensitive(False)
        self._set_play_icon(False)
        name = self.server.name if self.server else "servidor"
        self._set_status(f"Embed · {name} (reproductor propio del servidor)")
        self._schedule_play_check()

    # -- auto-fallback de servidores ----------------------------------------
    def _cancel_play_check(self):
        if self._play_check_id:
            try:
                GLib.source_remove(self._play_check_id)
            except Exception:
                pass
            self._play_check_id = 0

    def _schedule_play_check(self):
        self._cancel_play_check()
        if self.webview is None or len(self._servers) <= 1:
            return
        self._play_check_id = GLib.timeout_add(14000, self._check_playback)

    def _check_playback(self):
        self._play_check_id = 0
        if self.webview is None:
            return False
        if self.video_stack.get_visible_child_name() != "web":
            return False
        if self.webview.is_playing_audio():
            return False
        self._advance_server("El servidor no inició la reproducción.")
        return False

    def _on_web_load_failed(self, uri, message):
        GLib.idle_add(self._handle_web_load_failed, uri, message)

    def _handle_web_load_failed(self, uri, message):
        if self.webview is None:
            return False
        if self.video_stack.get_visible_child_name() != "web":
            return False
        if uri and self.webview.uri and uri != self.webview.uri:
            return False
        self._cancel_play_check()
        if self._server_index + 1 < len(self._servers):
            self._advance_server(f"No se pudo cargar el servidor ({message}).")
        else:
            self._set_status(
                f"No se pudo cargar el reproductor del servidor: {message}")
        return False

    def _on_web_fullscreen(self, active):
        self._fullscreen = bool(active)
        GLib.idle_add(self._apply_fullscreen, active)

    def _apply_fullscreen(self, active):
        for widget in (self.header, self.controls, self.status):
            if widget is not None:
                widget.set_visible(not active)
        return False

    def _advance_server(self, reason=""):
        nxt = self._server_index + 1
        if nxt >= len(self._servers):
            self._set_status(
                "Ningún servidor disponible pudo iniciar la reproducción")
            return
        server = self._servers[nxt]
        total = len(self._servers)
        prefix = f"{reason} " if reason else ""
        self._set_status(
            f"{prefix}Probando servidor {nxt + 1}/{total} · "
            f"{server.name or 'servidor'}")
        self.play_item(self.item, server, servers=self._servers, index=nxt,
                       push_history=False)

    def _toggle_engine(self):
        if self.webview is None or not self.stream_url:
            return
        if self.video_stack.get_visible_child_name() == "gst":
            player_url = self.server.player_url if self.server else self.stream_url
            self._play_embed(player_url)
        else:
            self._play_gst(self.stream_url)

    def toggle(self):
        if self.video_stack.get_visible_child_name() != "gst":
            return
        if not self.engine.has_media():
            return
        self.engine.toggle()
        self._set_play_icon(self.engine.is_playing())

    def stop_playback(self):
        self._stop_tick()
        self._generation += 1
        self._cancel_play_check()
        self.engine.stop()
        if self._fullscreen:
            self.exit_fullscreen()
        self._destroy_webview()
        self._apply_fullscreen(False)
        self._set_play_icon(False)

    def is_active(self) -> bool:
        return bool(self._tick_id) or self.engine.has_media()

    # -- callbacks del motor -------------------------------------------------
    def _on_engine_error(self, message):
        GLib.idle_add(self._apply_error, message)

    def _apply_error(self, message):
        self._stop_tick()
        self._set_play_icon(False)
        try:
            on_gst = self.video_stack.get_visible_child_name() == "gst"
        except Exception:
            on_gst = False
        if on_gst and self.webview is not None and self.server is not None:
            self._play_embed(self.server.player_url)
            self._set_status(
                f"GStreamer falló; usando reproductor del servidor · "
                f"{self.server.name or 'servidor'}")
            return False
        low = (message or "").lower()
        if "autoaudiosink" in low or "autovideosink" in low or "not found" in low:
            message = (f"{message} · Instala los plugins de GStreamer: "
                       "sudo pacman -S gst-plugins-good")
        self._set_status(f"Error de reproducción: {message}")
        return False

    def _on_engine_eos(self):
        GLib.idle_add(self._apply_eos)

    def _apply_eos(self):
        self._stop_tick()
        self._set_play_icon(False)
        self._set_status("Reproducción finalizada")
        return False

    def _on_engine_state(self, playing):
        GLib.idle_add(self._set_play_icon, bool(playing))

    def _set_play_icon(self, playing):
        self.play_btn.set_label("⏸" if playing else "▶")
        return False

    # -- controles -----------------------------------------------------------
    def _on_volume(self, scale):
        self.engine.set_volume(scale.get_value())

    def _on_mute(self, _btn):
        self._muted = not self._muted
        self.engine.set_muted(self._muted)
        self.mute_btn.set_label("🔇" if self._muted else "🔊")

    def _on_seek(self, _scale, _scroll, value):
        self.engine.seek_fraction(value)
        return False

    def _on_seek_value(self, scale):
        if self._updating or not self.engine.has_media():
            return
        duration = self.engine.duration_us()
        if duration > 0:
            self.time_lbl.set_text(
                f"{_fmt_time(int(scale.get_value() * duration))} / {_fmt_time(duration)}")

    def _reset_controls(self):
        self.stream_url = ""
        self.external_btn.set_sensitive(False)
        self.seek.set_sensitive(False)
        self._updating = True
        self.seek.set_value(0.0)
        self._updating = False
        self.time_lbl.set_text("0:00 / 0:00")
        self._set_play_icon(False)

    def _open_external(self):
        if not self.stream_url:
            return
        try:
            Gtk.UriLauncher.new(self.stream_url).launch(self.get_root(), None, None)
        except Exception:
            gi.require_version("Gio", "2.0")
            from gi.repository import Gio

            Gio.AppInfo.launch_default_for_uri(self.stream_url, None)

    # -- tick de posicion ----------------------------------------------------
    def _start_tick(self):
        if self._tick_id:
            return
        self._tick_id = GLib.timeout_add(TICK_MS, self._tick)

    def _stop_tick(self):
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = 0

    def _tick(self):
        if not self.engine.has_media():
            self._tick_id = 0
            return False
        position = self.engine.position_us()
        duration = self.engine.duration_us()
        self.time_lbl.set_text(f"{_fmt_time(position)} / {_fmt_time(duration)}")
        if duration > 0:
            self._updating = True
            self.seek.set_value(min(1.0, position / duration))
            self._updating = False
        return True

    def _set_status(self, text):
        self.status.set_text(text or "")
