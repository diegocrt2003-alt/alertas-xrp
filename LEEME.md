# Freqtrade en modo prueba (dry-run)

Este bot opera con **dinero simulado** (20 USDT de mentira) en Binance spot.
No necesita claves API. **Nunca pongas tus claves de Binance aquí** sin entender bien lo que haces.

## Qué hay en la carpeta

- `docker-compose.yml`: le dice a Docker cómo arrancar Freqtrade.
- `user_data/config.json`: la configuración (dry-run, 6 USDT por operación, máx. 3 a la vez).
- `user_data/strategies/CazaRebotes.py`: **la estrategia activa**. Compra caídas con pico de volumen, mira Fear & Greed, y en vivo revisa noticias y el libro de órdenes. Vende sola con ROI, stoploss -4% y trailing.
- `user_data/strategies/MiEstrategia.py`: la estrategia de ejemplo (RSI + EMAs).

## Probar una estrategia con datos pasados (backtest)

```
docker compose run --rm freqtrade download-data --config /freqtrade/user_data/config.json --timeframes 5m 1h --timerange 20260401-
docker compose run --rm freqtrade backtesting --config /freqtrade/user_data/config.json --strategy-list CazaRebotes MiEstrategia --timeframe 5m --timerange 20260501-
```
- `user_data/logs/`: aquí se guardan los registros.

## Cómo arrancarlo

1. Abre **Docker Desktop** y espera a que diga "Engine running".
2. En VS Code abre esta carpeta y abre una terminal (menú Terminal > New Terminal).
3. Descarga la imagen (solo la primera vez):
   ```
   docker compose pull
   ```
4. Arranca el bot:
   ```
   docker compose up -d
   ```
5. Abre en el navegador: http://localhost:8080
   - Usuario y contraseña: están en `user_data/config.json`, sección `api_server`.

## Comandos útiles

- Ver qué está pasando: `docker compose logs -f` (sal con Ctrl+C)
- Parar el bot: `docker compose down`
- Reiniciar tras cambiar config o estrategia: `docker compose restart`

## Próximos pasos (más adelante)

- Backtesting para probar la estrategia con datos pasados.
- FreqAI (aprendizaje automático) y señal de sentimiento / Fear & Greed.
