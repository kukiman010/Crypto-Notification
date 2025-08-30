import io
import requests
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

class CoinGeckoHistory:
    API_BASE = "https://api.coingecko.com/api/v3"
    _coins_cache = None  # Статический кеш на весь runtime

    def __init__(self):
        pass

    def get_coin_id(self, symbol: str) -> str:
        # Используем общий static кеш на сессию
        if CoinGeckoHistory._coins_cache is None:
            url = f"{self.API_BASE}/coins/list"
            resp = requests.get(url)
            resp.raise_for_status()
            coins = resp.json()
            # Кешируем весь список
            CoinGeckoHistory._coins_cache = {c["symbol"].lower(): c["id"] for c in coins}
        coin_id = CoinGeckoHistory._coins_cache.get(symbol.lower())
        if not coin_id:
            raise ValueError(f"Не удалось найти монету по тикеру '{symbol}'")
        return coin_id

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

    def plot_history(self, symbol: str, days: str = '30', vs_currency: str = 'usd'):
        history = self.get_history(symbol, days, vs_currency)
        xs, ys = zip(*history)
        fig, ax = plt.subplots(figsize=(11, 5))
        ax.plot(xs, ys, label=f"{symbol.upper()} ({vs_currency.upper()})")

        # Форматируем ось дат
        if days in ['1', '1.0', 1]:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b.%d %H:%M'))
        elif days in ['7', '14', '30', '90', '180', '365']:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y, %b %d'))

        plt.xticks(rotation=40)
        plt.xlabel("Дата")
        plt.ylabel(f"Цена, {vs_currency.upper()}")
        plt.title(f"История {symbol.upper()} за {days} дней")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        # Аннотация: просто текст цены у последней точки
        last_x = xs[-1]
        last_y = ys[-1]
        ax.text(
            last_x, last_y, f"{last_y:.2f} {vs_currency.upper()}",
            fontsize=11, color='red', ha='right', va='bottom',
            fontweight='bold',
            bbox=dict(facecolor='white', edgecolor='red', boxstyle='round,pad=0.3', alpha=0.7)
        )

        bio = io.BytesIO()
        plt.savefig(bio, format='png', bbox_inches='tight')
        plt.close(fig)
        bio.seek(0)
        return bio

        

# # Пример использования:
# if __name__ == "__main__":
#     cg = CoinGeckoHistory()
#     # cg.plot_history("BTC", days="1", vs_currency="usd")
#     cg.plot_history("BTC", days="7", vs_currency="usd")
# #     # cg.plot_history("BTC", days="180", vs_currency="usd")
# #     # cg.plot_history("BTC", days="max", vs_currency="usd")


