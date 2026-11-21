# Estrategia de ejemplo para aprender (NO es una recomendacion de inversion).
# Idea simple:
#   - Compra cuando el precio esta en tendencia alcista (EMA rapida > EMA lenta)
#     y el RSI viene de estar "barato" (cruza hacia arriba el nivel 30).
#   - Vende cuando el RSI esta "caro" (por encima de 70) o por ROI / stoploss.

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.strategy import IStrategy


class MiEstrategia(IStrategy):
    INTERFACE_VERSION = 3

    # Velas de 5 minutos
    timeframe = "5m"
    can_short = False  # spot: solo compras

    # Toma ganancias: 4% al instante, 2% tras 30 min, 1% tras 60 min, 0% tras 120 min
    minimal_roi = {
        "0": 0.04,
        "30": 0.02,
        "60": 0.01,
        "120": 0.0,
    }

    # Corta perdidas al -5%
    stoploss = -0.05
    trailing_stop = False

    process_only_new_candles = True
    startup_candle_count: int = 60

    use_exit_signal = True
    exit_profit_only = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=50)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema_fast"] > dataframe["ema_slow"])
                & (qtpylib.crossed_above(dataframe["rsi"], 30))
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] > 70)
                & (dataframe["volume"] > 0)
            ),
            "exit_long",
        ] = 1
        return dataframe
