# CazaRebotes: compra caidas que muestran senales de rebote y vende sola.
# Es una estrategia para APRENDER en modo prueba (dry-run). No es consejo de inversion.
#
# Senales que usa:
#   1. Velas e indicadores: RSI bajo + precio bajo la banda de Bollinger = "cayo fuerte".
#   2. Volumen: vela verde con mucho mas volumen que lo normal = posible compra fuerte / ballenas.
#   3. Tendencia de 1 hora: evita comprar cuando el mercado se esta derrumbando.
#   4. Fear & Greed Index (alternative.me, gratis): no compra en codicia extrema.
#   5. Solo en vivo / dry-run (no en backtest):
#        - Libro de ordenes: exige mas compradores que vendedores esperando.
#        - Noticias (RSS de Cointelegraph): no compra una moneda con titulares de hack, demanda, etc.
#
# Venta automatica: tabla ROI + stoploss + trailing stop + senal de salida (RSI alto).

import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd
import requests
import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.strategy import IStrategy, informative

logger = logging.getLogger(__name__)

FNG_URL = "https://api.alternative.me/fng/?limit=0&format=json"
NEWS_URLS = ["https://cointelegraph.com/rss"]
PALABRAS_MALAS = [
    "hack", "hacked", "exploit", "stolen", "lawsuit", "sues", "sued", "fraud",
    "delist", "delisting", "ban", "bankrupt", "insolvent", "outage", "halt",
]
NOMBRES = {
    "BTC": ["bitcoin", "btc"],
    "ETH": ["ethereum", "eth", "ether"],
    "SOL": ["solana", "sol"],
    "BNB": ["bnb", "binance"],
    "XRP": ["xrp", "ripple"],
}


class CazaRebotes(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = "5m"
    can_short = False

    # Venta automatica por ganancia: 3% al inicio, luego se conforma con menos con el tiempo
    minimal_roi = {
        "0": 0.03,
        "60": 0.02,
        "180": 0.01,
        "360": 0.005,
    }
    stoploss = -0.04

    # Trailing: cuando la ganancia pasa el 2%, protege dejando 1% de margen
    trailing_stop = True
    trailing_stop_positive = 0.01
    trailing_stop_positive_offset = 0.02
    trailing_only_offset_is_reached = True

    use_exit_signal = True
    exit_profit_only = True  # la senal de salida solo vende si hay ganancia
    process_only_new_candles = True
    startup_candle_count: int = 200

    # Parametros faciles de tocar
    rsi_compra = 32
    volumen_pico = 2.0       # veces el volumen promedio
    fng_maximo = 75          # no comprar con codicia extrema (>75)
    libro_ratio_min = 1.0    # compradores / vendedores en el libro

    # Cache interna
    _fng: pd.DataFrame | None = None
    _fng_time: float = 0
    _news: list = []
    _news_time: float = 0

    # ---------------- Fear & Greed ----------------
    def _cargar_fng(self) -> pd.DataFrame:
        ahora = time.time()
        if self._fng is not None and ahora - self._fng_time < 3600:
            return self._fng
        cache = Path(self.config["user_data_dir"]) / "data" / "fear_greed.json"
        datos = None
        try:
            r = requests.get(FNG_URL, timeout=15)
            r.raise_for_status()
            datos = r.json()["data"]
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(datos))
        except Exception as e:
            logger.warning(f"No pude descargar Fear & Greed ({e}), uso la copia guardada")
            if cache.exists():
                datos = json.loads(cache.read_text())
        if not datos:
            self._fng = pd.DataFrame(columns=["dia", "fng"])
        else:
            df = pd.DataFrame(datos)
            df["dia"] = pd.to_datetime(df["timestamp"].astype(int), unit="s", utc=True).dt.floor("D")
            df["fng"] = df["value"].astype(int)
            self._fng = df[["dia", "fng"]].drop_duplicates("dia").sort_values("dia")
        self._fng_time = ahora
        return self._fng

    # ---------------- Noticias ----------------
    def _cargar_noticias(self) -> list:
        ahora = time.time()
        if ahora - self._news_time < 600:
            return self._news
        titulares = []
        for url in NEWS_URLS:
            try:
                r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                raiz = ET.fromstring(r.content)
                for item in raiz.iter("item"):
                    titulo = (item.findtext("title") or "").lower()
                    fecha_txt = item.findtext("pubDate")
                    try:
                        fecha = parsedate_to_datetime(fecha_txt) if fecha_txt else None
                    except Exception:
                        fecha = None
                    titulares.append((titulo, fecha))
            except Exception as e:
                logger.warning(f"No pude leer noticias de {url}: {e}")
        self._news = titulares
        self._news_time = ahora
        return titulares

    def _noticia_mala(self, moneda: str) -> str | None:
        limite = datetime.now(timezone.utc) - timedelta(hours=24)
        nombres = NOMBRES.get(moneda, [moneda.lower()])
        for titulo, fecha in self._cargar_noticias():
            if fecha and fecha < limite:
                continue
            palabras = titulo.replace(",", " ").replace(":", " ").split()
            if any(n in palabras for n in nombres) and any(m in titulo for m in PALABRAS_MALAS):
                return titulo
        return None

    # ---------------- Indicadores ----------------
    @informative("1h")
    def populate_indicators_1h(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_inferior"] = bb["lower"]
        dataframe["bb_medio"] = bb["mid"]
        dataframe["vol_media"] = dataframe["volume"].rolling(20).mean()
        dataframe["vela_verde"] = dataframe["close"] > dataframe["open"]
        # Cuanto cayo en las ultimas 12 velas (1 hora)
        dataframe["caida_1h"] = dataframe["close"] / dataframe["high"].rolling(12).max() - 1

        # Fear & Greed del dia (se usa el del dia anterior para no "ver el futuro")
        fng = self._cargar_fng()
        if len(fng):
            dia = (dataframe["date"] - pd.Timedelta(days=1)).dt.floor("D")
            mapa = fng.set_index("dia")["fng"]
            dataframe["fng"] = dia.map(mapa).ffill().fillna(50)
        else:
            dataframe["fng"] = 50
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Senal: cayo fuerte recientemente + aparece compra fuerte con volumen
        cayo = (
            (dataframe["rsi"].rolling(3).min() < self.rsi_compra)
            & (dataframe["low"].rolling(3).min() < dataframe["bb_inferior"])
            & (dataframe["caida_1h"] < -0.015)
        )
        compra_fuerte = (
            dataframe["vela_verde"]
            & (dataframe["volume"] > dataframe["vol_media"] * self.volumen_pico)
        )
        tendencia_ok = dataframe["ema50_1h"] > dataframe["ema200_1h"] * 0.97
        sentimiento_ok = dataframe["fng"] <= self.fng_maximo

        dataframe.loc[
            cayo & compra_fuerte & tendencia_ok & sentimiento_ok & (dataframe["volume"] > 0),
            ["enter_long", "enter_tag"],
        ] = (1, "rebote_volumen")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["rsi"] > 72) & (dataframe["close"] > dataframe["bb_medio"]),
            ["exit_long", "exit_tag"],
        ] = (1, "rsi_alto")
        return dataframe

    # ---------------- Filtros en vivo (no se usan en backtest) ----------------
    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        if self.dp.runmode.value not in ("live", "dry_run"):
            return True
        moneda = pair.split("/")[0]

        mala = self._noticia_mala(moneda)
        if mala:
            logger.info(f"{pair}: no compro por noticia negativa: {mala}")
            return False

        try:
            libro = self.dp.orderbook(pair, 20)
            compras = sum(p * q for p, q in libro["bids"])
            ventas = sum(p * q for p, q in libro["asks"])
            ratio = compras / ventas if ventas else 0
            if ratio < self.libro_ratio_min:
                logger.info(f"{pair}: no compro, libro con mas vendedores (ratio {ratio:.2f})")
                return False
            logger.info(f"{pair}: compro, libro ratio {ratio:.2f}")
        except Exception as e:
            logger.warning(f"{pair}: no pude leer el libro de ordenes ({e}), compro igual")
        return True
