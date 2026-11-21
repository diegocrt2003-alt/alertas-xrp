"""Revisa XRP/USDT y manda "COMPRA AHORA" por Telegram si hay senal.
No opera ni necesita claves de Binance: solo lee datos publicos.

Variables de entorno (en GitHub van como "Secrets"):
  TELEGRAM_TOKEN    token del bot que te da @BotFather
  TELEGRAM_CHAT_ID  tu numero de chat
Sin esas variables solo imprime el mensaje en pantalla.
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


def enviar(texto):
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    print(texto)
    if not (token and chat):
        print("(Sin TELEGRAM_TOKEN / TELEGRAM_CHAT_ID: no se envio a Telegram)")
        return
    token, chat = token.strip(), chat.strip()
    datos = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", datos, timeout=20)
        print("Mensaje enviado a Telegram.")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode(errors="ignore")
        print(f"ERROR de Telegram ({e.code}): {detalle}")
        if e.code == 401:
            print("-> El TELEGRAM_TOKEN esta mal. Copialo de nuevo desde @BotFather.")
        elif e.code in (400, 403):
            print("-> Revisa TELEGRAM_CHAT_ID (solo el numero) y que hayas presionado Iniciar en tu bot.")
        sys.exit(1)


def main():
    if "--prueba" in sys.argv:
        enviar("Prueba OK: las alertas de XRP funcionan.")
        return

    v5 = senal.velas("5m", 1000)
    v1h = senal.velas("1h", 300)
    ahora = int(time.time() * 1000)
    v5 = [x for x in v5 if x["fin"] < ahora]      # solo velas cerradas
    v1h = [x for x in v1h if x["fin"] < ahora]
    try:
        fng = senal.fear_greed_historial()
    except Exception:
        fng = None

    senales = senal.calcular_senales(v5, v1h, fng)
    if not senales:
        print("Sin senal por ahora."); return
    i, rsi_val, vol_x = senales[-1]
    vela = v5[i]
    if ahora - vela["fin"] > VENTANA_MIN * 60_000:
        print("La ultima senal ya es vieja, no aviso."); return

    estado = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    if estado.get("ultima_senal") == vela["t"]:
        print("Ya avise de esta senal."); return

    mala = senal.noticia_mala()
    if mala:
        print(f"Habia senal pero hay noticia negativa: {mala}"); return

    precio = vela["c"]
    tp = precio * (1 + senal.TP_PCT)
    sl = precio * (1 - senal.SL_PCT)
    hoy = datetime.now(timezone.utc).date()
    fng_hoy = fng.get(hoy) if fng else None
    hora = datetime.fromtimestamp(vela["fin"] / 1000, senal.PERU).strftime("%H:%M")
    texto = (
        f"COMPRA AHORA XRP/USDT ({hora} hora Peru)\n\n"
        f"Entrada: ~{precio:.4f} USDT\n"
        f"Tomar ganancia (TP): {tp:.4f} (+{senal.TP_PCT:.1%})\n"
        f"Stop loss (SL): {sl:.4f} (-{senal.SL_PCT:.1%})\n"
        f"Monto sugerido: {MONTO_USDT} USDT (una sola posicion)\n\n"
        f"Por que: 2 ladrillos Renko verdes, RSI {rsi_val:.0f}, volumen {vol_x:.1f}x lo normal"
        + (f", Fear&Greed {fng_hoy}" if fng_hoy is not None else "") + ".\n\n"
        "En Binance: compra y luego pon una orden OCO con ese TP y SL para que venda sola.\n"
        "Si el precio ya subio mas de 0.5% desde la entrada, mejor no persigas."
    )
    enviar(texto)
    estado["ultima_senal"] = vela["t"]
    ESTADO.write_text(json.dumps(estado))


if __name__ == "__main__":
    main()
