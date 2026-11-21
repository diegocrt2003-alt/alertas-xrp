"""Alertas de XRP/USDT por Telegram: "COMPRA AHORA" y "VENDE AHORA".
No opera ni necesita claves de Binance: solo lee datos publicos.

Le escribes a tu bot de Telegram:
  /compre            -> anota que compraste (al precio de la ultima alerta)
  /compre 0.9100     -> anota que compraste a ese precio
  /vendi             -> anota que vendiste
  /estado            -> te dice si tienes posicion abierta y como va

Variables de entorno (en GitHub van como "Secrets"):
  TELEGRAM_TOKEN    token del bot que te da @BotFather
  TELEGRAM_CHAT_ID  tu numero de chat
Uso:  python alerta.py            (revisa ahora)
      python alerta.py --prueba   (manda un mensaje de prueba)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import panel
import semanal
import senal

MONTO_USDT = 18
VENTANA_MIN = 30   # avisa si la senal salio en los ultimos 30 min
ESTADO = Path(__file__).with_name("estado.json")


# ---------------- Telegram ----------------
def _cred():
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    return (token.strip(), chat.strip()) if token and chat else (None, None)


def _telegram(metodo, params):
    token, _ = _cred()
    datos = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{metodo}", datos,
                                    timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="ignore")
        print(f"ERROR de Telegram ({e.code}): {detalle}")
        if e.code == 401:
            print("-> El TELEGRAM_TOKEN esta mal. Copialo de nuevo desde @BotFather.")
        elif e.code in (400, 403):
            print("-> Revisa TELEGRAM_CHAT_ID (solo el numero) y que hayas presionado Iniciar en tu bot.")
        sys.exit(1)


def enviar(texto):
    print(texto)
    token, chat = _cred()
    if not token:
        print("(Sin TELEGRAM_TOKEN / TELEGRAM_CHAT_ID: no se envio a Telegram)")
        return
    _telegram("sendMessage", {"chat_id": chat, "text": texto})
    print("Mensaje enviado a Telegram.")


def leer_mensajes(estado):
    """Devuelve los textos nuevos que Diego le escribio al bot."""
    token, chat = _cred()
    if not token:
        return []
    r = _telegram("getUpdates", {"offset": estado.get("update_id", 0) + 1, "timeout": 0})
    textos = []
    for u in r.get("result", []):
        estado["update_id"] = u["update_id"]
        m = u.get("message") or {}
        if str(m.get("chat", {}).get("id")) == chat and m.get("text"):
            textos.append(m["text"].strip())
    return textos


# ---------------- Estado ----------------
def cargar_estado():
    return json.loads(ESTADO.read_text()) if ESTADO.exists() else {}


def guardar_estado(estado):
    ESTADO.write_text(json.dumps(estado, indent=1))


def anotar(estado, tipo, texto, precio):
    estado.setdefault("historial", []).append(
        {"t": int(time.time() * 1000), "tipo": tipo, "texto": texto, "precio": precio})
    estado["historial"] = estado["historial"][-50:]


def niveles(precio):
    return precio * (1 + senal.TP_PCT), precio * (1 - senal.SL_PCT)


def procesar_comandos(estado, precio_actual):
    for texto in leer_mensajes(estado):
        partes = texto.lower().replace(",", ".").split()
        cmd = partes[0].lstrip("/").replace("é", "e").split("@")[0] if partes else ""
        if cmd in ("compre_semanal", "compresemanal"):
            try:
                precio = float(partes[1])
            except (IndexError, ValueError):
                precio = estado.get("sem_ultima_alerta_precio") or precio_actual
            estado["posicion_semanal"] = {"precio": precio, "desde": int(time.time() * 1000),
                                          "maximo": precio, "avisos": []}
            anotar(estado, "compre", "SEMANAL: anotaste una compra", precio)
            enviar(f"Anotado (SEMANAL): compraste XRP a {precio:.4f}.\n"
                   f"SL {precio * (1 - semanal.SL_SEM):.4f} (-{semanal.SL_SEM:.0%}). Trailing: cuando llegue a "
                   f"{precio * (1 + semanal.TRAIL_ACTIVA):.4f} (+5%), vende si baja 5% desde el maximo.\n"
                   "Cuando vendas escribe /vendi_semanal")
        elif cmd in ("vendi_semanal", "vendisemanal"):
            ps = estado.get("posicion_semanal")
            if ps:
                g = precio_actual / ps["precio"] - 1
                enviar(f"Anotado (SEMANAL): vendiste. Resultado aprox. {g:+.2%} (sin comisiones).")
                anotar(estado, "vendi", f"SEMANAL: anotaste la venta ({g:+.2%})", precio_actual)
            else:
                enviar("No tenia anotada ninguna compra SEMANAL, pero ok.")
            estado["posicion_semanal"] = None
        elif cmd in ("compre", "compra"):
            try:
                precio = float(partes[1])
            except (IndexError, ValueError):
                precio = estado.get("ultima_alerta_precio") or precio_actual
            estado["posicion"] = {"precio": precio, "desde": int(time.time() * 1000), "avisos": []}
            anotar(estado, "compre", "Anotaste una compra", precio)
            tp, sl = niveles(precio)
            enviar(f"Anotado: compraste XRP a {precio:.4f}.\nTP {tp:.4f} | SL {sl:.4f}\n"
                   "Te aviso si conviene vender. Cuando vendas escribe /vendi")
        elif cmd in ("vendi", "vende", "vendido"):
            if estado.get("posicion"):
                p = estado["posicion"]["precio"]
                enviar(f"Anotado: vendiste. Resultado aprox. {precio_actual / p - 1:+.2%} "
                       "(sin comisiones). Vuelvo a buscar compras.")
                anotar(estado, "vendi", f"Anotaste la venta ({precio_actual / p - 1:+.2%})", precio_actual)
            else:
                enviar("No tenia anotada ninguna compra, pero ok.")
            estado["posicion"] = None
        elif cmd == "estado":
            p = estado.get("posicion")
            if p:
                tp, sl = niveles(p["precio"])
                enviar(f"Posicion abierta a {p['precio']:.4f}. Ahora {precio_actual:.4f} "
                       f"({precio_actual / p['precio'] - 1:+.2%}).\nTP {tp:.4f} | SL {sl:.4f}")
            else:
                enviar(f"Sin posicion. XRP ahora {precio_actual:.4f}. Buscando compras en tu horario.")
            ps = estado.get("posicion_semanal")
            if ps:
                enviar(f"SEMANAL abierta a {ps['precio']:.4f}. Ahora {precio_actual:.4f} "
                       f"({precio_actual / ps['precio'] - 1:+.2%}). Maximo {ps['maximo']:.4f}.")
        else:
            enviar("Comandos: /compre [precio], /vendi, /estado\n"
                   "Modo SEMANAL: /compre_semanal [precio], /vendi_semanal")


# ---------------- Venta ----------------
def revisar_venta(estado, v5, v1h, btc):
    p = estado["posicion"]
    entrada, desde = p["precio"], p["desde"]
    tp, sl = niveles(entrada)
    despues = [x for x in v5 if x["t"] >= desde]
    ahora_precio = v5[-1]["c"]
    motivos = []

    for x in despues:  # lo que toco primero: SL o TP
        if x["l"] <= sl:
            motivos.append(("sl", f"Toco el SL ({sl:.4f}). Si tu OCO ya vendio, escribe /vendi."))
            break
        if x["h"] >= tp:
            motivos.append(("tp", f"Llego al TP ({tp:.4f}). Si tu OCO ya vendio, escribe /vendi."))
            break

    # 2 ladrillos Renko rojos seguidos formados despues de la compra
    ev = senal.renko_eventos([x["c"] for x in v5], senal.LADRILLO_PCT)
    ladrillos = [(v5[i]["t"], b) for i, e in enumerate(ev) for b in e]
    if len(ladrillos) >= 2 and [b for _, b in ladrillos[-2:]] == [-1, -1] \
            and ladrillos[-1][0] >= desde:
        motivos.append((f"renko{ladrillos[-1][0]}", "2 ladrillos Renko rojos seguidos (como tu bot)."))

    e50 = senal.ema([x["c"] for x in v1h], 50)
    e200 = senal.ema([x["c"] for x in v1h], 200)
    if len(v1h) > 200 and e50[-1] < e200[-1] * 0.97:
        motivos.append(("tendencia", "La tendencia de 1 hora se esta derrumbando."))

    c1, _ = senal.btc_cambios(btc, v5[-1]["fin"]) if btc else (None, None)
    if c1 is not None and c1 <= senal.BTC_VENTA_1H:
        hora = int(v5[-1]["t"] // 3_600_000)
        motivos.append((f"btc{hora}", f"Bitcoin se esta derrumbando ({c1:+.1%} en 1 hora); XRP suele seguirlo."))

    mala = senal.noticia_mala()
    if mala:
        motivos.append((f"noticia:{mala[:60]}", f"Noticia negativa: {mala}"))

    nuevos = [(k, t) for k, t in motivos if k not in p["avisos"]]
    if not nuevos:
        print(f"Posicion abierta a {entrada:.4f}, ahora {ahora_precio:.4f}. Nada que avisar.")
        return
    texto = (f"VENDE AHORA XRP/USDT\n\nCompraste a {entrada:.4f}, ahora {ahora_precio:.4f} "
             f"({ahora_precio / entrada - 1:+.2%}).\n\nPor que:\n"
             + "\n".join(f"- {t}" for _, t in nuevos)
             + "\n\nCuando vendas escribe /vendi")
    enviar(texto)
    p["avisos"].extend(k for k, _ in nuevos)
    anotar(estado, "vende", "VENDE AHORA: " + " ".join(t for _, t in nuevos), ahora_precio)


# ---------------- Compra ----------------
def revisar_compra(estado, v5, v1h, fng, ahora, btc, deriv):
    funding = [(0, deriv["funding"])] if deriv.get("funding") is not None else None
    senales = senal.calcular_senales(v5, v1h, fng, btc, funding)
    if not senales:
        print("Sin senal de compra por ahora."); return
    i, rsi_val, vol_x = senales[-1]
    vela = v5[i]
    if ahora - vela["fin"] > VENTANA_MIN * 60_000:
        print("La ultima senal ya es vieja, no aviso."); return
    if estado.get("ultima_senal") == vela["t"]:
        print("Ya avise de esta senal."); return
    mala = senal.noticia_mala()
    if mala:
        print(f"Habia senal pero hay noticia negativa: {mala}"); return

    precio = vela["c"]
    tp, sl = niveles(precio)
    fng_hoy = fng.get(datetime.now(timezone.utc).date()) if fng else None
    hora = datetime.fromtimestamp(vela["fin"] / 1000, senal.PERU).strftime("%H:%M")
    enviar(
        f"COMPRA AHORA XRP/USDT ({hora} hora Peru)\n\n"
        f"Entrada: ~{precio:.4f} USDT\n"
        f"Tomar ganancia (TP): {tp:.4f} (+{senal.TP_PCT:.1%})\n"
        f"Stop loss (SL): {sl:.4f} (-{senal.SL_PCT:.1%})\n"
        f"Monto sugerido: {MONTO_USDT} USDT (una sola posicion)\n\n"
        f"Por que: 2 ladrillos Renko verdes, RSI {rsi_val:.0f}, volumen {vol_x:.1f}x lo normal"
        + (f", Fear&Greed {fng_hoy}" if fng_hoy is not None else "") + ".\n\n"
        "En Binance: compra y pon una orden OCO con ese TP y SL para que venda sola.\n"
        "Si el precio ya subio mas de 0.5% desde la entrada, mejor no persigas.\n"
        "Si compras, escribeme /compre (o /compre PRECIO)."
    )
    estado["ultima_senal"] = vela["t"]
    estado["ultima_alerta_precio"] = precio
    anotar(estado, "compra", f"COMPRA AHORA (RSI {rsi_val:.0f}, volumen {vol_x:.1f}x)", precio)


# ---------------- Modo SEMANAL ----------------
def revisar_semanal(estado, v5, ahora):
    """Devuelve info para el panel: condiciones del ultimo dia cerrado."""
    d = [x for x in semanal.velas_diarias("XRPUSDT", limite=200) if x["fin"] < ahora]
    btc_d = [x for x in semanal.velas_diarias("BTCUSDT", limite=10) if x["fin"] < ahora]
    rsi = senal.rsi([x["c"] for x in d])
    conds = semanal.evaluar(d, len(d) - 1, rsi, btc_d)
    precio = v5[-1]["c"]
    ps = estado.get("posicion_semanal")

    if ps:
        nuevos_max = [x["h"] for x in v5 if x["t"] >= ps["desde"]]
        ps["maximo"] = max([ps["maximo"]] + nuevos_max)
        motivos = semanal.revisar_salida(ps["precio"], ps["maximo"], precio, ps["desde"], ahora)
        nuevos = [(k, t) for k, t in motivos if k not in ps["avisos"]]
        if nuevos:
            enviar(f"VENDE AHORA (SEMANAL) XRP/USDT\n\nCompraste a {ps['precio']:.4f}, ahora {precio:.4f} "
                   f"({precio / ps['precio'] - 1:+.2%}).\n\nPor que:\n"
                   + "\n".join(f"- {t}" for _, t in nuevos)
                   + "\n\nCuando vendas escribe /vendi_semanal")
            ps["avisos"].extend(k for k, _ in nuevos)
            anotar(estado, "vende", "SEMANAL VENDE: " + " ".join(t for _, t in nuevos), precio)
    else:
        dia = d[-1]
        if all(c["ok"] for c in conds) and estado.get("sem_ultima_senal") != dia["t"] \
                and ahora - dia["fin"] < 3 * 3_600_000:
            mala = senal.noticia_mala()
            if mala:
                print(f"SEMANAL: habia senal pero hay noticia negativa: {mala}")
            else:
                e = dia["c"]
                enviar(
                    "COMPRA AHORA (SEMANAL) XRP/USDT\n\n"
                    f"Entrada: ~{e:.4f} USDT\n"
                    f"Stop loss: {e * (1 - semanal.SL_SEM):.4f} (-{semanal.SL_SEM:.0%})\n"
                    f"Trailing: cuando suba a {e * (1 + semanal.TRAIL_ACTIVA):.4f} (+5%), vende si baja 5% "
                    "desde el maximo. Maximo 20 dias.\n"
                    f"Monto sugerido: {MONTO_USDT} USDT\n\n"
                    "Por que: " + " ".join(c["detalle"] for c in conds) + "\n\n"
                    "En Binance puedes usar una orden 'Trailing Stop' de 5% para que venda sola.\n"
                    "Si compras, escribeme /compre_semanal (o /compre_semanal PRECIO)."
                )
                estado["sem_ultima_senal"] = dia["t"]
                estado["sem_ultima_alerta_precio"] = e
                anotar(estado, "compra", "COMPRA AHORA (SEMANAL)", e)
        else:
            print("SEMANAL: sin senal.")
    return {
        "dia": d[-1]["t"],
        "filtros": conds,
        "posicion": None if not ps else {
            "precio": ps["precio"], "desde": ps["desde"], "maximo": ps["maximo"],
            "sl": ps["precio"] * (1 - semanal.SL_SEM),
            "trail_activa": ps["precio"] * (1 + semanal.TRAIL_ACTIVA),
            "trail_stop": ps["maximo"] * (1 - semanal.TRAIL)
            if ps["maximo"] >= ps["precio"] * (1 + semanal.TRAIL_ACTIVA) else None,
            "dias": (ahora - ps["desde"]) / semanal.DIA_MS,
        },
        "reglas": {"caida": semanal.CAIDA_MIN, "rsi": semanal.RSI_MAX, "sl": semanal.SL_SEM,
                   "trail": semanal.TRAIL, "dias": semanal.DIAS_MAX},
    }


def main():
    if "--prueba" in sys.argv:
        enviar("Prueba OK: las alertas de XRP funcionan.\n"
               "Comandos: /compre [precio], /vendi, /estado\n"
               "Modo SEMANAL: /compre_semanal [precio], /vendi_semanal")
        return

    ahora = int(time.time() * 1000)
    v5 = [x for x in senal.velas("5m", 1000) if x["fin"] < ahora]   # solo velas cerradas
    v1h = [x for x in senal.velas("1h", 300) if x["fin"] < ahora]
    try:
        fng = senal.fear_greed_historial()
    except Exception:
        fng = None

    try:
        btc = {"velas": [x for x in senal.velas_btc("5m", 100) if x["fin"] < ahora]}
    except Exception:
        btc = None
    deriv = senal.derivados_ahora()

    estado = cargar_estado()
    procesar_comandos(estado, v5[-1]["c"])
    if estado.get("posicion"):
        revisar_venta(estado, v5, v1h, btc)
    else:
        revisar_compra(estado, v5, v1h, fng, ahora, btc, deriv)
    try:
        info_sem = revisar_semanal(estado, v5, ahora)
    except Exception as e:
        print(f"SEMANAL: error {e}")
        info_sem = None
    # Cambia una vez al dia: asi GitHub ve actividad y no apaga el horario a los 60 dias
    estado["ultimo_dia_revisado"] = datetime.now(senal.PERU).date().isoformat()
    guardar_estado(estado)
    try:
        panel.exportar(estado, v5, v1h, fng, btc, deriv, info_sem)
        print("Panel actualizado (docs/datos.json).")
    except Exception as e:
        print(f"No pude actualizar el panel: {e}")


if __name__ == "__main__":
    main()
