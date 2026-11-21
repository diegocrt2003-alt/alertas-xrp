"""Prueba la senal con datos pasados: que hubiera pasado si comprabas en cada alerta
y ponias TP y SL. Uso:  python alertas/probar_pasado.py
"""
import time
from datetime import datetime, timezone

import senal

COMISION = 0.002  # 0.1% al comprar + 0.1% al vender


def bajar(intervalo, desde_ms):
    todas, fin = [], None
    while True:
        lote = senal.velas(intervalo, 1000, fin)
        if not lote:
            break
        todas = lote + todas
        if lote[0]["t"] <= desde_ms:
            break
        fin = lote[0]["t"] - 1
        time.sleep(0.2)
    ahora = int(time.time() * 1000)
    return [x for x in todas if x["t"] >= desde_ms and x["fin"] < ahora]


def simular(v5, senales):
    resultados, libre_desde = [], -1
    for i, _, _ in senales:
        if i <= libre_desde or i + 1 >= len(v5):
            continue
        entrada = v5[i]["c"]
        tp, sl = entrada * (1 + senal.TP_PCT), entrada * (1 - senal.SL_PCT)
        for k in range(i + 1, len(v5)):
            if v5[k]["l"] <= sl:
                resultados.append(-senal.SL_PCT - COMISION); libre_desde = k; break
            if v5[k]["h"] >= tp:
                resultados.append(senal.TP_PCT - COMISION); libre_desde = k; break
        else:
            libre_desde = len(v5)
    return resultados


def resumen(nombre, res):
    if not res:
        print(f"{nombre:38s} sin operaciones"); return
    gan = sum(1 for x in res if x > 0)
    total = 1.0
    for x in res:
        total *= 1 + x
    print(f"{nombre:38s} ops={len(res):3d}  aciertos={gan / len(res):5.1%}  "
          f"resultado={total - 1:+6.1%}")


if __name__ == "__main__":
    desde = int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp() * 1000)
    print("Bajando datos de Binance...")
    v5, v1h = bajar("5m", desde), bajar("1h", desde - 250 * 3600_000)
    fng = senal.fear_greed_historial()
    print(f"Velas 5m: {len(v5)}  desde {datetime.fromtimestamp(v5[0]['t']/1000, timezone.utc):%Y-%m-%d}")
    cambio = v5[-1]["c"] / v5[0]["c"] - 1
    print(f"XRP en ese tiempo: {cambio:+.1%}\n")

    print("Bajando BTC y funding...")
    btc = {"velas": [x for x in []]}
    original = senal.PAR
    senal.PAR = "BTCUSDT"
    btc["velas"] = bajar("5m", desde - 5 * 3600_000)
    senal.PAR = original
    funding = senal.funding_historial(desde - 8 * 3600_000)
    print(f"Funding: {len(funding)} registros, maximo {max(f for _, f in funding):.4%}\n")

    senal.LADRILLO_PCT, senal.USAR_TENDENCIA = 0.005, False
    resumen("tu bot original (ladrillo 0.5%)", simular(v5, senal.calcular_senales(v5, v1h, None)))
    senal.USAR_TENDENCIA = True
    for nombre, b, f in (("+ tendencia 1h + Fear&Greed", None, None),
                         ("  + filtro BTC", btc, None),
                         ("  + filtro funding", None, funding),
                         ("  + BTC + funding (todo)", btc, funding)):
        resumen(nombre, simular(v5, senal.calcular_senales(v5, v1h, fng, b, f)))
