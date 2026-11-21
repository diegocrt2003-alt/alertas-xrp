"""Backtest del modo SEMANAL. Uso: python alertas/probar_semanal.py
Muestra 2019-2023 (donde se eligieron las reglas) y 2024-hoy (prueba limpia)."""
from datetime import datetime, timezone

import semanal

COMISION = 0.002
ms = lambda y: int(datetime(y, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)


def simular(d, btc, desde, hasta):
    idx, rsi = semanal.senales(d, btc)
    res, libre = [], -1
    for i in idx:
        if i <= libre or not (desde <= d[i]["t"] < hasta) or i + 1 >= len(d):
            continue
        e, maxp = d[i]["c"], d[i]["c"]
        for k in range(i + 1, len(d)):
            x = d[k]
            stop = e * (1 - semanal.SL_SEM)
            if maxp >= e * (1 + semanal.TRAIL_ACTIVA):
                stop = max(stop, maxp * (1 - semanal.TRAIL))
            if x["l"] <= stop:
                g, m = stop / e - 1, "stop/trailing"
            elif k - i >= semanal.DIAS_MAX:
                g, m = x["c"] / e - 1, "tiempo"
            else:
                maxp = max(maxp, x["h"]); continue
            f = datetime.fromtimestamp(d[i]["t"] / 1000, timezone.utc)
            print(f"   {f:%Y-%m-%d} compra {e:.4f} -> {m:13s} {g - COMISION:+6.1%} en {k - i:2d} dias")
            res.append(g - COMISION); libre = k; break
    tot = 1
    for g in res:
        tot *= 1 + g
    gan = sum(g > 0 for g in res)
    print(f"  => {len(res)} operaciones, {gan} ganadas, resultado {tot - 1:+.0%}\n")


if __name__ == "__main__":
    btc = semanal.velas_diarias("BTCUSDT", ms(2018))
    d = semanal.velas_diarias("XRPUSDT", ms(2018))
    print("2019-2023 (aqui se eligieron las reglas):")
    simular(d, btc, ms(2019), ms(2024))
    print("2024-hoy (prueba limpia):")
    simular(d, btc, ms(2024), ms(2100))
