"""Lista de dominios de anuncios y utilidades (port de AdBlocker.kt)."""
from __future__ import annotations

import urllib.parse

AD_DOMAINS: frozenset[str] = frozenset({
    "1xbetjap.com", "1xbet.com", "1xbet.xyz", "1xbet.club", "1xbet.info",
    "1xbet.vip", "1xbet.es", "1xbet.fr", "1xbet.de", "1xbet.it", "1xbet.pt",
    "1xbet.br", "1xbet.ar", "1xbet.mx", "1xbet.co", "1xbet.kz", "1xbet.ua",
    "1xbet.uz", "1xbet.su", "1xbet.by", "1xbet.sport", "1xbet.at", "1xbet.ch",
    "1xbet.pe", "1xbet.cl", "1xbet.ec", "1xbet.ve", "1xbet.gl", "1xbet.mobi",
    "1xbet.download", "1xbet.finance", "1xstt.com", "1xstt.ru", "1xstavka.ru",
    "1x-slots.com", "1x-gon.xyz", "go.1xbet.com", "ad.1xbet.com",
    "1xbetaffiliates.com", "1xbetpartners.com", "melbet.com", "melbet.news",
    "melbet.partners", "mostbet.com", "mostbetpartners.com", "vavada.com",
    "1win.com", "1winsports.com", "betwinner.com", "betwinnerpartners.com",
    "winwin.bet", "playamo.com", "popads.net", "popadscdn.net",
    "propellerads.com", "propellerclick.com", "adsterra.com", "adsterra.net",
    "adsterra.co", "adsterra.org", "adsterra3.com", "adsterra4.com",
    "adtng.com", "exoclick.com", "exosrv.com", "juicyads.com", "popunder.ru",
    "popunder.net", "trafficjunky.com", "trafficfactory.biz", "adf.ly",
    "shorte.st", "ouo.io", "adfoc.us", "mgid.com", "admicro.vn",
    "hilltopads.net", "clickadilla.com", "hitcpm.com", "admixer.net",
    "onclickads.net", "onclickprediction.com", "popcash.net", "popcash.sbs",
    "popcash.pw", "pumpads.com", "adpop.cc", "adpop.me", "popclick.io",
    "popclick.me", "popmnd.com", "adremedy.com", "7hjt.com", "getmubank.com",
    "muqut.net", "tonnic.com", "clickadu.com", "feedads.io", "propel.link",
    "propush.me", "realsrv.com", "intradaytg.com", "doubleclick.net",
    "googlesyndication.com", "googleadservices.com", "googletagservices.com",
    "scorecardresearch.com", "adnxs.com", "rubiconproject.com", "pubmatic.com",
    "openx.net", "taboola.com", "outbrain.com", "criteo.com",
    "smartadserver.com", "casalemedia.com", "adsrvr.org", "bidswitch.net",
    "indexww.com", "teads.tv", "spotxchange.com", "sharethrough.com",
    "contextweb.com", "rlcdn.com", "quantserve.com", "media.net", "lijit.com",
    "gumgum.com", "adform.net", "sovrn.com", "adkernel.com", "cpx.to",
    "cpmaffiliation.com",
})

_PATTERNS = ("1xbet", "1xstt", "1xstavka")


def host_of(url: str) -> str:
    if not url:
        return ""
    try:
        netloc = urllib.parse.urlparse(url).netloc
        return (netloc or "").split("@")[-1].split(":")[0].lower()
    except ValueError:
        return ""


def is_ad(url: str) -> bool:
    host = host_of(url)
    if not host:
        return False
    if any(p in host for p in _PATTERNS):
        return True
    return any(host == d or host.endswith("." + d) for d in AD_DOMAINS)


def domains_json() -> str:
    return ",".join('"%s"' % d for d in sorted(AD_DOMAINS))
