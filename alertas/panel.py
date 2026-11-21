"""Genera docs/datos.json para el panel web (GitHub Pages)."""
import json
import xml.etree.ElementTree as ET
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import senal

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "datos.json"


def noticias(maximo=10):
    """Titulares recientes de Cointelegraph; marca los que hablan de XRP o son negativos."""
    try:
        req = urllib.request.Request("https://cointelegraph.com/rss", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raiz = ET.fromstring(r.read())
    except Exception:
        return []
    out = []
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").strip()
        t = titulo.lower()
        palabras = t.replace(",", " ").replace(":", " ").split()
        try:
            fecha = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        except Exception:
            fecha = None
        out.append({
            "titulo": titulo,
            "link": (item.findtext("link") or "").strip(),
            "fecha": fecha,
            "xrp": "xrp" in palabras or "ripple" in palabras,
            "negativa": any(m in t for m in senal.PALABRAS_MALAS),
        })
    xrp = [n for n in out if n["xrp"]]
    resto = sorted([n for n in out if not n["xrp"]], key=lambda n: n["fecha"] or "", reverse=True)
    return (xrp + resto)[:maximo]


def filtros_nuevos(v5, btc, deriv):
    out = []
    c1, c4 = senal.btc_cambios(btc, v5[-1]["fin"]) if btc else (None, None)
    if c1 is not None:
        ok = senal.btc_ok((c1, c4))
        out.append({
            "nombre": "Bitcoin no se está cayendo", "ok": ok,
            "valor": {"1h": round(c1, 4), "4h": round(c4, 4)},
            "detalle": f"BTC {c1:+.1%} en 1 h y {c4:+.1%} en 4 h. "
                       + ("Tranquilo: cuando BTC no cae, XRP tiene más chance de subir." if ok
                          else "BTC está cayendo fuerte y XRP casi siempre lo sigue: mejor esperar."),
        })
    f = deriv.get("funding") if deriv else None
    if f is not None:
        ok = f <= senal.FUNDING_MAX
        oi = deriv.get("oi_cambio_24h")
        extra = f" El dinero apostado en futuros cambió {oi:+.1%} en 24 h." if oi is not None else ""
        out.append({
            "nombre": "Futuros sin euforia (funding)", "ok": ok, "valor": f,
            "detalle": f"Funding {f:+.3%} ({deriv['fuente']}). "
                       + ("Normal: no hay demasiada gente apostando al alza." if ok
                          else "Muy alto: demasiados apostando a que sube; suele venir una bajada.")
                       + extra,
        })
    return out


def filtros(v5, v1h, fng):
    """Estado de cada condicion en la ultima vela cerrada, explicado en simple."""
    cierres = [x["c"] for x in v5]
    rsi = senal.rsi(cierres)
    ev = senal.renko_eventos(cierres, senal.LADRILLO_PCT)
    ladrillos = [b for e in ev for b in e]
    ult = v5[-1]
    vol_media = sum(x["v"] for x in v5[-21:-1]) / 20
    vol_x = ult["v"] / vol_media if vol_media else 0
    e50 = senal.ema([x["c"] for x in v1h], 50)[-1]
    e200 = senal.ema([x["c"] for x in v1h], 200)[-1]
    dia_ant = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    fng_val = fng.get(dia_ant) if fng else None
    hora = datetime.now(senal.PERU)
    en_hora = any(a <= hora.hour < b for a, b in senal.HORAS_PERU)
    dos_verdes = ladrillos[-2:] == [1, 1]
    mala = senal.noticia_mala()
    r = rsi[-1] or 0
    return [
        {"nombre": "Renko: 2 ladrillos verdes", "ok": dos_verdes,
         "detalle": "Los 2 últimos ladrillos son verdes: el precio viene subiendo." if dos_verdes
         else "Los últimos ladrillos no son 2 verdes seguidos: todavía no hay impulso de subida."},
        {"nombre": f"RSI entre {senal.RSI_MIN} y {senal.RSI_MAX}", "ok": senal.RSI_MIN <= r <= senal.RSI_MAX,
         "valor": round(r, 1),
         "detalle": f"RSI {r:.0f}. " + ("Ni muy caro ni en caída libre." if senal.RSI_MIN <= r <= senal.RSI_MAX
                                     else "Muy alto: ya subió mucho." if r > senal.RSI_MAX
                                     else "Muy bajo: sigue cayendo fuerte.")},
        {"nombre": f"Volumen ≥ {senal.VOL_MULT}x lo normal", "ok": vol_x >= senal.VOL_MULT, "valor": round(vol_x, 2),
         "detalle": f"Ahora se negocia {vol_x:.1f} veces lo normal. "
                    + ("Poco movimiento, nadie está comprando fuerte." if vol_x < senal.VOL_MULT
                       else "Hay compras fuertes (vela verde)." if ult["c"] >= ult["o"]
                       else "Mucho movimiento, pero de venta (vela roja).")},
        {"nombre": "Tendencia de 1 hora", "ok": e50 >= e200 * 0.97,
         "detalle": "El mercado de fondo no se está derrumbando." if e50 >= e200 * 0.97
         else "La tendencia de fondo es bajista fuerte: comprar es más riesgoso."},
        {"nombre": f"Fear & Greed ≤ {senal.FNG_MAX}", "ok": fng_val is None or fng_val <= senal.FNG_MAX,
         "valor": fng_val,
         "detalle": f"Índice {fng_val}. " + ("No hay codicia extrema." if (fng_val or 0) <= senal.FNG_MAX
                                           else "Codicia extrema: todo está caro, mejor esperar.")},
        {"nombre": "Sin noticias malas de XRP", "ok": not mala,
         "detalle": "No hay titulares negativos de XRP en 24 h." if not mala else f"Titular negativo: {mala}"},
        {"nombre": "Tu horario (9-12 y 15-20)", "ok": en_hora,
         "detalle": f"Son las {hora:%H:%M} en Perú. " + ("Estás en horario." if en_hora
                                                         else "Fuera de horario: no aviso compras.")},
    ]


def exportar(estado, v5, v1h, fng, btc=None, deriv=None, semanal=None):
    cierres = [x["c"] for x in v5]
    rsi = senal.rsi(cierres)
    ev = senal.renko_eventos(cierres, senal.LADRILLO_PCT)
    renko = [{"t": v5[i]["t"], "d": b} for i, e in enumerate(ev) for b in e][-60:]
    n = 288  # ultimas 24 h de velas de 5m
    velas = [{"t": x["t"], "o": x["o"], "h": x["h"], "l": x["l"], "c": x["c"], "v": round(x["v"])}
             for x in v5[-n:]]
    try:
        fng_hist = sorted(fng.items())[-30:] if fng else []
    except Exception:
        fng_hist = []
    pos = estado.get("posicion")
    datos = {
        "actualizado": datetime.now(timezone.utc).isoformat(),
        "precio": cierres[-1],
        "cambio_24h": cierres[-1] / v5[-n]["c"] - 1 if len(v5) >= n else None,
        "velas": velas,
        "rsi": [round(x, 1) if x is not None else None for x in rsi[-n:]],
        "renko": renko,
        "ladrillo_pct": senal.LADRILLO_PCT,
        "fng": [{"dia": d.isoformat(), "v": v} for d, v in fng_hist],
        "filtros": filtros(v5, v1h, fng) + filtros_nuevos(v5, btc, deriv),
        "noticias": noticias(),
        "posicion": None if not pos else {
            "precio": pos["precio"], "desde": pos["desde"],
            "tp": pos["precio"] * (1 + senal.TP_PCT), "sl": pos["precio"] * (1 - senal.SL_PCT),
        },
        "historial": estado.get("historial", [])[-20:],
        "semanal": semanal,
        "config": {"tp": senal.TP_PCT, "sl": senal.SL_PCT, "par": "XRP/USDT"},
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
