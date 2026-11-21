"""Modo SEMANAL: comprar XRP en una caida fuerte y aguantar dias hasta el rebote.

Reglas validadas (elegidas con 2019-2023 y probadas en 2024-2026):
  Compra (al cierre diario, 19:00 hora Peru):
    - XRP cae 20% o mas desde su maximo de 14 dias
    - RSI diario por debajo de 35
    - BTC no cayo mas de 10% en 3 dias
    - sin noticias malas de XRP (solo en vivo)
  Venta:
    - trailing: cuando ganas 5%, vende si baja 5% desde el maximo alcanzado
    - stop loss -12%
    - maximo 20 dias
Solo libreria estandar.
"""
from datetime import datetime, timezone

import senal

CAIDA_MIN = -0.20
RSI_MAX = 35
BTC_3D_MIN = -0.10
TRAIL_ACTIVA = 0.05
TRAIL = 0.05
SL_SEM = 0.12
DIAS_MAX = 20
DIA_MS = 86_400_000


def velas_diarias(par, desde_ms=None, limite=1000):
    original, senal.PAR = senal.PAR, par
    try:
        if desde_ms is None:
            return senal.velas("1d", limite)
        todas, fin = [], None
        while True:
            lote = senal.velas("1d", 1000, fin)
            if not lote:
                break
            todas = lote + todas
            if lote[0]["t"] <= desde_ms:
                break
            fin = lote[0]["t"] - 1
        return [x for x in todas if x["t"] >= desde_ms]
    finally:
        senal.PAR = original


def evaluar(d, i, rsi, btc):
    """Condiciones de compra al cierre del dia i: lista de dicts para panel y alertas."""
    x = d[i]
    maximo = max(y["h"] for y in d[max(0, i - 13):i + 1])
    caida = x["c"] / maximo - 1
    bidx = {y["t"]: k for k, y in enumerate(btc)}
    k = bidx.get(x["t"])
    b3 = btc[k]["c"] / btc[k - 3]["c"] - 1 if k is not None and k >= 3 else None
    r = rsi[i]
    return [
        {"nombre": "Caída fuerte (20% o más)", "ok": caida <= CAIDA_MIN, "valor": round(caida, 4),
         "detalle": f"XRP está {caida:+.1%} desde su máximo de 14 días ({maximo:.4f}). "
                    + ("Es una caída fuerte: posible oportunidad." if caida <= CAIDA_MIN
                       else "Todavía no cayó lo suficiente para este modo.")},
        {"nombre": f"RSI diario bajo {RSI_MAX}", "ok": r is not None and r < RSI_MAX,
         "valor": round(r, 1) if r is not None else None,
         "detalle": f"RSI diario {r:.0f}. " + ("Está barato (sobrevendido)." if r is not None and r < RSI_MAX
                                              else "No está lo bastante barato.")},
        {"nombre": "Bitcoin sin desplome (3 días)", "ok": b3 is None or b3 >= BTC_3D_MIN,
         "valor": round(b3, 4) if b3 is not None else None,
         "detalle": (f"BTC {b3:+.1%} en 3 días. " if b3 is not None else "")
                    + ("Bitcoin no está en caída libre." if b3 is None or b3 >= BTC_3D_MIN
                       else "Bitcoin se está desplomando: mejor esperar.")},
    ]


def senales(d, btc):
    rsi = senal.rsi([x["c"] for x in d])
    out = []
    for i in range(30, len(d)):
        if rsi[i] is not None and all(c["ok"] for c in evaluar(d, i, rsi, btc)):
            out.append(i)
    return out, rsi


def revisar_salida(entrada, maximo, precio, desde_ms, ahora_ms):
    """Devuelve lista de (clave, texto) con motivos para vender."""
    motivos = []
    if precio <= entrada * (1 - SL_SEM):
        motivos.append(("sl", f"Toco el stop loss de -{SL_SEM:.0%} ({entrada * (1 - SL_SEM):.4f})."))
    if maximo >= entrada * (1 + TRAIL_ACTIVA) and precio <= maximo * (1 - TRAIL):
        motivos.append(("trailing", f"Llego hasta {maximo:.4f} (+{maximo / entrada - 1:.1%}) y ya bajo "
                                    f"{TRAIL:.0%} desde ahi: asegura la ganancia."))
    dias = (ahora_ms - desde_ms) / DIA_MS
    if dias >= DIAS_MAX:
        motivos.append(("tiempo", f"Ya pasaron {dias:.0f} dias (maximo {DIAS_MAX}): el rebote no llego."))
    return motivos
