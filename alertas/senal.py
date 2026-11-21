"""Logica de la senal "COMPRA AHORA" para XRP/USDT (solo lee datos publicos, no opera).

Combina el bot Renko de Diego con filtros de CazaRebotes:
  - Renko: 2 ladrillos verdes seguidos (se acaba de formar el 2do en la ultima vela de 5m)
  - RSI(14) entre 35 y 65
  - Volumen >= 1.2x el promedio de 20 velas
  - Horario Peru: 9-12 y 15-20
  - Tendencia de 1 hora no en derrumbe (EMA50 >= 97% de EMA200)
  - Fear & Greed <= 75 (no comprar con codicia extrema)
  - Sin noticias negativas de XRP en las ultimas 24 h (solo en vivo)
Solo usa la libreria estandar de Python.
"""

import json
import urllib.request
from datetime import datetime, timedelta, timezone

PAR = "XRPUSDT"
LADRILLO_PCT = 0.005      # tamano del ladrillo Renko: 0.5% del precio
RSI_MIN, RSI_MAX = 35, 65
VOL_MULT = 1.2
HORAS_PERU = [(9, 12), (15, 20)]
FNG_MAX = 75
TP_PCT = 0.025
SL_PCT = 0.012
USAR_TENDENCIA = True

BINANCE = "https://data-api.binance.vision/api/v3/klines"  # API publica de Binance
PERU = timezone(timedelta(hours=-5))
PALABRAS_MALAS = ["hack", "exploit", "stolen", "lawsuit", "sues", "sued", "fraud",
                  "delist", "ban", "bankrupt", "outage", "halt"]


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def velas(intervalo, limite=1000, fin_ms=None):
    url = f"{BINANCE}?symbol={PAR}&interval={intervalo}&limit={limite}"
    if fin_ms:
        url += f"&endTime={fin_ms}"
    return [{"t": int(k[0]), "o": float(k[1]), "h": float(k[2]), "l": float(k[3]),
             "c": float(k[4]), "v": float(k[5]), "fin": int(k[6])} for k in http_json(url)]


def rsi(cierres, n=14):
    out = [None] * len(cierres)
    if len(cierres) <= n:
        return out
    ganancias = perdidas = 0.0
    for i in range(1, n + 1):
        d = cierres[i] - cierres[i - 1]
        ganancias += max(d, 0)
        perdidas += max(-d, 0)
    g, p = ganancias / n, perdidas / n
    out[n] = 100 if p == 0 else 100 - 100 / (1 + g / p)
    for i in range(n + 1, len(cierres)):
        d = cierres[i] - cierres[i - 1]
        g = (g * (n - 1) + max(d, 0)) / n
        p = (p * (n - 1) + max(-d, 0)) / n
        out[i] = 100 if p == 0 else 100 - 100 / (1 + g / p)
    return out


def ema(valores, n):
    out, k, e = [], 2 / (n + 1), None
    for v in valores:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def renko_eventos(cierres, ladrillo_pct):
    """Para cada vela devuelve la lista de ladrillos nuevos (+1 verde, -1 rojo)."""
    eventos = [[] for _ in cierres]
    base = cierres[0]
    paso = base * ladrillo_pct
    ultimo = 0
    for i, c in enumerate(cierres):
        while True:
            if ultimo >= 0 and c >= base + paso:
                base += paso; ultimo = 1; eventos[i].append(1)
            elif ultimo <= 0 and c <= base - paso:
                base -= paso; ultimo = -1; eventos[i].append(-1)
            elif ultimo == 1 and c <= base - 2 * paso:
                base -= 2 * paso; ultimo = -1; eventos[i].append(-1)
            elif ultimo == -1 and c >= base + 2 * paso:
                base += 2 * paso; ultimo = 1; eventos[i].append(1)
            else:
                break
    return eventos


def fear_greed_historial():
    datos = http_json("https://api.alternative.me/fng/?limit=0&format=json")["data"]
    return {datetime.fromtimestamp(int(d["timestamp"]), timezone.utc).date(): int(d["value"])
            for d in datos}


def noticia_mala():
    """Busca titulares recientes de XRP con palabras negativas (Cointelegraph RSS)."""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    try:
        req = urllib.request.Request("https://cointelegraph.com/rss",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raiz = ET.fromstring(r.read())
    except Exception:
        return None
    limite = datetime.now(timezone.utc) - timedelta(hours=24)
    for item in raiz.iter("item"):
        titulo = (item.findtext("title") or "").lower()
        try:
            fecha = parsedate_to_datetime(item.findtext("pubDate"))
        except Exception:
            fecha = None
        if fecha and fecha < limite:
            continue
        palabras = titulo.replace(",", " ").replace(":", " ").split()
        if ("xrp" in palabras or "ripple" in palabras) and any(m in titulo for m in PALABRAS_MALAS):
            return titulo
    return None


def en_horario(ms):
    h = datetime.fromtimestamp(ms / 1000, PERU).hour
    return any(a <= h < b for a, b in HORAS_PERU)


def calcular_senales(v5, v1h, fng):
    """Devuelve los indices de velas de 5m donde hay senal de compra."""
    cierres = [x["c"] for x in v5]
    r = rsi(cierres)
    ev = renko_eventos(cierres, LADRILLO_PCT)
    # ultimos 2 ladrillos acumulados hasta cada vela
    historia, ult2 = [], []
    for e in ev:
        historia.extend(e)
        ult2.append(historia[-2:] if len(historia) >= 2 else [])
    e50 = ema([x["c"] for x in v1h], 50)
    e200 = ema([x["c"] for x in v1h], 200)
    tend = {}  # hora (cerrada) -> tendencia ok
    for i, x in enumerate(v1h):
        tend[x["fin"]] = i >= 200 and e50[i] >= e200[i] * 0.97

    senales = []
    j, tend_actual = 0, False
    fins_1h = sorted(tend)
    for i, x in enumerate(v5):
        while j < len(fins_1h) and fins_1h[j] <= x["fin"]:
            tend_actual = tend[fins_1h[j]]; j += 1
        if i < 30 or r[i] is None:
            continue
        nuevo_verde = bool(ev[i]) and ev[i][-1] == 1
        if not (nuevo_verde and ult2[i] == [1, 1]):
            continue
        vol_media = sum(y["v"] for y in v5[i - 20:i]) / 20
        if not (RSI_MIN <= r[i] <= RSI_MAX and x["v"] >= vol_media * VOL_MULT):
            continue
        if not en_horario(x["t"]):
            continue
        if USAR_TENDENCIA and not tend_actual:
            continue
        dia_ant = (datetime.fromtimestamp(x["t"] / 1000, timezone.utc) - timedelta(days=1)).date()
        if fng is not None and fng.get(dia_ant, 50) > FNG_MAX:
            continue
        senales.append((i, r[i], x["v"] / vol_media))
    return senales
