"""Motor WebKitGTK para embeds: carga el player del servidor con anti-ads.

Muchos servidores no exponen un m3u8/mp4 directo, sino una pagina embed con
su propio reproductor (hls.js, etc.). Como en la app Android original
(PlayerScreen.kt), se carga esa pagina en un WebView embebido, se neutralizan
popups/alertas, se eliminan anuncios y se fuerza `video.play()`.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from player.adblock import domains_json, is_ad  # noqa: E402

_WEBKIT = None
_WEBKIT_READY = False

_START_JS = """
(function() {
    window.open = function() { return null; };
    window.alert = function() {};
    window.confirm = function() { return false; };
    window.prompt = function() { return null; };
})();
"""

_END_JS = """
(function() {
    var domains = [__AD_DOMAINS__];
    var isAdHost = function(host) {
        host = (host || '').toLowerCase();
        for (var j = 0; j < domains.length; j++) {
            if (host === domains[j] || host.endsWith('.' + domains[j])) return true;
        }
        return host.indexOf('1xbet') >= 0 || host.indexOf('1xstt') >= 0 ||
               host.indexOf('1xstavka') >= 0;
    };
    var kill = function(el) {
        if (!el || !el.parentNode) return;
        try { el.parentNode.removeChild(el); } catch (e) { el.style.display = 'none'; }
    };
    var paintBlack = function() {
        var h = document.documentElement;
        if (h) { h.style.background = '#000'; h.style.margin = '0'; h.style.padding = '0'; }
        var b = document.body;
        if (b) { b.style.background = '#000'; b.style.margin = '0'; b.style.padding = '0'; }
        var els = document.querySelectorAll('iframe, video');
        for (var i = 0; i < els.length; i++) {
            els[i].style.background = '#000';
            els[i].style.margin = '0';
            els[i].style.padding = '0';
            if (els[i].tagName === 'IFRAME') {
                els[i].style.width = '100%';
                els[i].style.height = '100%';
                els[i].style.border = '0';
                els[i].style.display = 'block';
            }
        }
    };
    window.__killAds = function() {
        var i, el, src, host;
        var nodes = document.querySelectorAll('iframe, embed, object');
        for (i = 0; i < nodes.length; i++) {
            el = nodes[i];
            src = el.src || (el.getAttribute && el.getAttribute('data-src')) || '';
            host = src.replace(/^https?:\\/\\//, '').split('/')[0].split(':')[0];
            if (host && isAdHost(host)) kill(el);
        }
        var sel = "[class*='advert'],[id*='advert'],[class*='advertisement']," +
            "[id*='advertisement'],[class*='adholder'],[class*='ad-holder']," +
            "[class*='adunit'],[class*='ad-unit'],[class*='adsbox'],[class*='adslot']," +
            "[class*='ad-container'],[class*='adContainer'],[class*='ad_wrap']," +
            "[class*='adwrap'],[class*='sponsor'],[id*='sponsor'],[class*='popunder']," +
            "[id*='popunder']";
        var els = document.querySelectorAll(sel);
        for (i = 0; i < els.length; i++) kill(els[i]);
    };
    var playVideo = function() {
        var v = document.querySelector('video');
        if (!v) return;
        try {
            var p = v.play();
            if (p && p.catch) {
                p.catch(function() {
                    v.muted = true;
                    var q = v.play();
                    if (q && q.catch) q.catch(function() {});
                });
            }
        } catch (e) {}
    };
    var clickPlay = function() {
        var sels = ['.jw-icon-playback', '.jw-display-icon-container',
            '.jw-icon-display', '.vjs-big-play-button', '.play-button',
            '.play', '[class*="play"][role="button"]', '[aria-label*="lay"]',
            '[aria-label*="eproducir"]'];
        for (var i = 0; i < sels.length; i++) {
            var el = document.querySelector(sels[i]);
            if (el) { try { el.click(); } catch (e) {} }
        }
        try {
            if (window.jwplayer) {
                var pl = window.jwplayer();
                if (pl && pl.play) pl.play();
            }
        } catch (e) {}
    };
    var kick = function() {
        try { window.__killAds(); } catch (e) {}
        try { paintBlack(); } catch (e) {}
        var v = document.querySelector('video');
        if (v && v.readyState >= 2 && !v.paused) return;
        try { clickPlay(); } catch (e) {}
        try { playVideo(); } catch (e) {}
    };
    var scheduleKill = function() {
        if (window.__killTimer) return;
        window.__killTimer = setTimeout(function() {
            window.__killTimer = 0;
            try { window.__killAds(); } catch (e) {}
        }, 800);
    };
    if (window.__adObserver) { try { window.__adObserver.disconnect(); } catch (e) {} }
    kick();
    try {
        window.__adObserver = new MutationObserver(scheduleKill);
        window.__adObserver.observe(document.documentElement, {childList: true, subtree: true});
    } catch (e) {}
    setTimeout(function() {
        if (window.__adObserver) {
            try { window.__adObserver.disconnect(); } catch (e) {}
            window.__adObserver = null;
        }
    }, 20000);
    var delays = [600, 1500, 2500, 4000, 6000, 9000];
    for (var d = 0; d < delays.length; d++) setTimeout(kick, delays[d]);
})();
""".replace("__AD_DOMAINS__", domains_json())


def webkit_available() -> bool:
    global _WEBKIT, _WEBKIT_READY
    if _WEBKIT_READY:
        return _WEBKIT is not None
    _WEBKIT_READY = True
    for version in ("6.0", "5.0"):
        try:
            gi.require_version("WebKit", version)
            from gi.repository import WebKit

            _WEBKIT = WebKit
            break
        except Exception:
            _WEBKIT = None
    return _WEBKIT is not None


class WebViewEngine:
    """WebView embebido para reproducir paginas embed de servidores."""

    def __init__(self, on_load_failed=None, on_fullscreen=None):
        if _WEBKIT is None:
            webkit_available()
        self._webkit = _WEBKIT
        self.uri = ""
        self.on_load_failed = on_load_failed
        self.on_fullscreen = on_fullscreen
        self._root_window = None
        ucm = self._webkit.UserContentManager()
        for source, when in ((_START_JS, "START"), (_END_JS, "END")):
            try:
                ucm.add_script(self._webkit.UserScript.new(
                    source,
                    self._webkit.UserContentInjectedFrames.ALL_FRAMES,
                    getattr(self._webkit.UserScriptInjectionTime, when),
                    None, None))
            except Exception:
                pass
        self.widget = self._webkit.WebView(user_content_manager=ucm)
        self.widget.set_hexpand(True)
        self.widget.set_vexpand(True)
        try:
            self.widget.set_background_color(Gdk.RGBA(0, 0, 0, 1))
        except Exception:
            pass
        settings = self.widget.get_settings()
        for setter, value in (
            ("set_enable_javascript", True),
            ("set_media_playback_requires_user_gesture", False),
            ("set_media_playback_allows_inline", True),
            ("set_enable_media", True),
            ("set_enable_mediasource", True),
            ("set_enable_media_stream", True),
            ("set_enable_webaudio", True),
            ("set_enable_fullscreen", True),
            ("set_enable_page_cache", True),
            ("set_javascript_can_open_windows_automatically", False),
        ):
            try:
                getattr(settings, setter)(value)
            except Exception:
                pass
        try:
            settings.set_hardware_acceleration_policy(
                self._webkit.HardwareAccelerationPolicy.ALWAYS)
        except Exception:
            pass
        try:
            settings.set_enable_accelerated_2d_canvas(True)
        except Exception:
            pass
        self._handlers = [
            self.widget.connect("create", self._on_create),
            self.widget.connect("decide-policy", self._on_decide_policy),
            self.widget.connect("load-failed", self._on_load_failed),
            self.widget.connect("enter-fullscreen", self._on_enter_fullscreen),
            self.widget.connect("leave-fullscreen", self._on_leave_fullscreen),
        ]

    def destroy(self):
        """Detiene la pagina y rompe referencias para matar el WebProcess."""
        self.on_load_failed = None
        self.on_fullscreen = None
        self._root_window = None
        for handler in self._handlers:
            try:
                self.widget.disconnect(handler)
            except Exception:
                pass
        self._handlers = []
        try:
            self.widget.stop_loading()
        except Exception:
            pass
        try:
            self.widget.load_uri("about:blank")
        except Exception:
            pass
        try:
            self.widget.set_visible(False)
        except Exception:
            pass
        try:
            parent = self.widget.get_parent()
            if parent is not None:
                parent.remove(self.widget)
            self.widget.unparent()
        except Exception:
            pass

    def _on_create(self, _view, _nav_action):
        return None

    def _on_enter_fullscreen(self, _view):
        root = self.widget.get_root()
        if root is not None:
            self._root_window = root
        if self._root_window is not None:
            try:
                self._root_window.fullscreen()
            except Exception:
                pass
        if self.on_fullscreen:
            try:
                self.on_fullscreen(True)
            except Exception:
                pass
        return True

    def _on_leave_fullscreen(self, _view):
        root = self._root_window or self.widget.get_root()
        if root is not None:
            try:
                root.unfullscreen()
            except Exception:
                pass
        if self.on_fullscreen:
            try:
                self.on_fullscreen(False)
            except Exception:
                pass
        return True

    def _on_load_failed(self, _view, _load_event, failing_uri, error):
        if self.on_load_failed:
            try:
                self.on_load_failed(
                    failing_uri, getattr(error, "message", str(error)))
            except Exception:
                pass
        return False

    def _on_decide_policy(self, _view, decision, decision_type):
        try:
            nav_types = (self._webkit.PolicyDecisionType.NAVIGATION_ACTION,
                         self._webkit.PolicyDecisionType.NEW_WINDOW_ACTION)
            if decision_type in nav_types:
                action = decision.get_navigation_action()
                request = action.get_request() if action else None
                uri = request.get_uri() if request else ""
                if uri and is_ad(uri):
                    decision.ignore()
                    return True
        except Exception:
            pass
        return False

    def load(self, uri: str):
        self.uri = uri or ""
        if self.uri:
            self.widget.load_uri(self.uri)

    def stop(self):
        self.uri = ""
        try:
            self.widget.stop_loading()
        except Exception:
            pass
        try:
            self.widget.load_uri("about:blank")
        except Exception:
            pass

    def has_media(self) -> bool:
        return bool(self.uri)

    def exit_fullscreen(self):
        try:
            self.widget.evaluate_javascript(
                "(function(){if(document.fullscreenElement){"
                "document.exitFullscreen();}})()",
                -1, None, None, None, None, None)
        except Exception:
            pass
        root = self._root_window or self.widget.get_root()
        if root is not None:
            try:
                root.unfullscreen()
            except Exception:
                pass
        if self.on_fullscreen:
            try:
                self.on_fullscreen(False)
            except Exception:
                pass

    def is_playing_audio(self) -> bool:
        try:
            return bool(self.widget.is_playing_audio())
        except Exception:
            return False
