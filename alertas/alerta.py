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


def niveles(precio):
    return precio * (1 + senal.TP_PCT), precio * (1 - senal.SL_PCT)


def procesar_comandos(estado, precio_actual):
    for texto in leer_mensajes(estado):
        partes = texto.lower().replace(",", ".").split()
        cmd = partes[0].lstrip("/").replace("é", "e") if partes else ""
        if cmd in ("compre", "compra"):
            try:
                precio = float(partes[1])
            except (IndexError, ValueError):
                precio = estado.get("ultima_alerta_precio") or precio_actual
            estado["posicion"] = {"precio": precio, "desde": int(time.time() * 1000), "avisos": []}
            tp, sl = niveles(precio)
            enviar(f"Anotado: compraste XRP a {precio:.4f}.\nTP {tp:.4f} | SL {sl:.4f}\n"
                   "Te aviso si conviene vender. Cuando vendas escribe /vendi")
        elif cmd in ("vendi", "vende", "vendido"):
            if estado.get("posicion"):
                p = estado["posicion"]["precio"]
                enviar(f"Anotado: vendiste. Resultado aprox. {precio_actual / p - 1:+.2%} "
                       "(sin comisiones). Vuelvo a buscar compras.")
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
        else:
            enviar("Comandos: /compre [precio], /vendi, /estado")


# ---------------- Venta ----------------
def revisar_venta(estado, v5, v1h):
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


# ---------------- Compra ----------------
def revisar_compra(estado, v5, v1h, fng, ahora):
    senales = senal.calcular_senales(v5, v1h, fng)
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


def main():
    if "--prueba" in sys.argv:
        enviar("Prueba OK: las alertas de XRP funcionan.\n"
               "Comandos: /compre [precio], /vendi, /estado")
        return

    ahora = int(time.time() * 1000)
    v5 = [x for x in senal.velas("5m", 1000) if x["fin"] < ahora]   # solo velas cerradas
    v1h = [x for x in senal.velas("1h", 300) if x["fin"] < ahora]
    try:
        fng = senal.fear_greed_historial()
    except Exception:
        fng = None

    estado = cargar_estado()
    procesar_comandos(estado, v5[-1]["c"])
    if estado.get("posicion"):
        revisar_venta(estado, v5, v1h)
    else:
        revisar_compra(estado, v5, v1h, fng, ahora)
    # Cambia una vez al dia: asi GitHub ve actividad y no apaga el horario a los 60 dias
    estado["ultimo_dia_revisado"] = datetime.now(senal.PERU).date().isoformat()
    guardar_estado(estado)


if __name__ == "__main__":
    main()
