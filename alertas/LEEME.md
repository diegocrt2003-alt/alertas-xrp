# Alertas "COMPRA AHORA" de XRP

Un script que revisa XRP/USDT cada 10 minutos (en horario Perú 9-12 y 15-20) y te manda un
mensaje por Telegram con precio de entrada, TP y SL cuando hay señal. Tú compras en la app de
Binance. **No opera solo ni necesita tus claves de Binance.**

## La señal
Tu bot Renko + filtros nuevos:
- 2 ladrillos Renko verdes seguidos (ladrillo de 0.5% del precio)
- RSI(14) entre 35 y 65
- Volumen al menos 1.2 veces el promedio
- Horario Perú 9-12 y 15-20
- Tendencia de 1 hora no en derrumbe
- Fear & Greed no en codicia extrema (75 o menos)
- Sin noticias negativas de XRP en las últimas 24 h

TP +2.5% y SL -1.2%. En Binance pon una orden **OCO** con esos dos precios para que venda sola.

## Avisos de venta
Escríbele a tu bot: `/compre` (o `/compre 0.9100`) cuando compres, `/vendi` cuando vendas,
`/estado` para ver cómo vas. Con posición abierta te avisa "VENDE AHORA" si toca TP o SL,
salen 2 ladrillos Renko rojos, se derrumba la tendencia de 1 hora o hay noticia mala.
Revisa cada 10 minutos todo el día (las compras solo en tu horario).

## Archivos
- `senal.py`: la lógica de la señal (los números se cambian arriba del archivo)
- `alerta.py`: revisa ahora y manda el aviso
- `probar_pasado.py`: prueba la señal con datos pasados
- `../.github/workflows/alertas-xrp.yml`: lo que corre gratis en GitHub cada 10 min

## Probar en tu PC
```
python alertas/alerta.py
python alertas/probar_pasado.py
```
