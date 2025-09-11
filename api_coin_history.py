import io
import requests
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as ticker

from systems.logger         import LoggerSingleton
from tools.tools            import multi_number_processing_to_str



class CoinGeckoHistory:
    API_BASE = "https://api.coingecko.com/api/v3"
    _coins_cache = None  # Статический кеш на весь runtime
    _logger = LoggerSingleton.new_instance('logs/log_cripto_notify.log')

    def __init__(self):
        pass

    def get_coin_id(self, symbol: str) -> str:
        r = requests.get(f"{self.API_BASE}/search", params={"query": symbol})
        r.raise_for_status()
        coins = r.json().get("coins", [])
        # Фильтруем по точному совпадению символа (без учета регистра)
        exact = [c for c in coins if c.get("symbol", "").lower() == symbol.lower()]
        if not exact:
            raise ValueError(f"Не нашел монет с символом '{symbol}'. Попробуйте другой запрос или укажите id.")
        # Выбираем монету с лучшим (меньшим) market_cap_rank, если доступно
        def rank_key(c):
            rank = c.get("market_cap_rank")
            return rank if isinstance(rank, int) else 10**9
        best = sorted(exact, key=rank_key)[0]
        return best["id"]


    def get_history(self, symbol: str, days: str = '30', vs_currency: str = 'usd'):
        coin_id = self.get_coin_id(symbol)
        url = f"{self.API_BASE}/coins/{coin_id}/market_chart"
        params = {"vs_currency": vs_currency, "days": days}
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()["prices"]
        result = [
            (datetime.fromtimestamp(ts / 1000), price)
            for ts, price in data
        ]
        return result


    def plot_history(self, symbol: str, days: str = '30', vs_currency: str = 'usd', rate: float = 1.0, rate_currency: str = None):
        try:
            history = self.get_history(symbol, days, vs_currency)
            xs, ys = zip(*history)

            # Преобразуем значения согласно курсу
            ys = [y * rate for y in ys]
            display_currency = rate_currency.upper() if rate_currency else vs_currency.upper()

            fig, ax = plt.subplots(figsize=(11, 5))
            ax.plot(xs, ys, label=f"{symbol.upper()} ({display_currency})")

            # Форматируем ось дат
            if days in ['1', '1.0', 1]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b.%d %H:%M'))
            elif days in ['7', '14', '30', '90', '180', '365']:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            else:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y, %b %d'))

            # Форматируем ось цен
            ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f'{multi_number_processing_to_str(y, 2)}'))



            plt.xticks(rotation=40)
            plt.xlabel("Дата")
            plt.ylabel(f"Цена, {display_currency}")
            plt.title(f"История {symbol.upper()} за {days} дней")
            plt.legend()
            plt.grid(True)
            plt.tight_layout()

            # Аннотация: цена последней точки
            last_x = xs[-1]
            last_y = ys[-1]
            ax.text(
                last_x, last_y, f"{multi_number_processing_to_str(last_y, 3)} {display_currency}",
                fontsize=11, color='red', ha='right', va='bottom',
                fontweight='bold',
                bbox=dict(facecolor='white', edgecolor='red', boxstyle='round,pad=0.3', alpha=0.7)
            )

            bio = io.BytesIO()
            plt.savefig(bio, format='png', bbox_inches='tight')
            plt.close(fig)
            bio.seek(0)
            return bio

        except Exception as e:
            import traceback
            error_message = f'Ошибка в plot_history: {e}\n{traceback.format_exc()}'
            self._logger.add_error(error_message)
            return None



        

# # Пример использования:
# if __name__ == "__main__":
#     cg = CoinGeckoHistory()
#     # cg.plot_history("BTC", days="1", vs_currency="usd")
#     cg.plot_history("BTC", days="7", vs_currency="usd")
# #     # cg.plot_history("BTC", days="180", vs_currency="usd")
# #     # cg.plot_history("BTC", days="max", vs_currency="usd")


