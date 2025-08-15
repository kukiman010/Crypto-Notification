# Пример: get_cmc_price.py
import os
import requests
from typing import List, Dict

API_BASE = "https://pro-api.coinmarketcap.com/v1"
API_ENDPOINT = "/cryptocurrency/quotes/latest"

def get_cmc_prices(symbols: List[str], convert: str = "USD") -> Dict[str, float]:
    """
    Возвращает словарь вида { 'BTC': 47200.12, 'ETH': 3200.5 }
    symbols: список символов (например ['BTC','ETH']) или можно передать один символ.
    convert: валюта конвертации, по умолчанию 'USD'.
    Требует переменную окружения COINMARKETCAP_API_KEY с вашим ключом.
    """
    # api_key = os.environ.get("COINMARKETCAP_API_KEY")
    api_key = 'key'
    if not api_key:
        raise RuntimeError("Не найден COINMARKETCAP_API_KEY в переменных окружения")

    headers = {
        "Accepts": "application/json",
        "X-CMC_PRO_API_KEY": api_key
    }

    params = {
        "symbol": ",".join(symbols),
        "convert": convert,
        "skip_invalid": "true"  # пропустить неверные символы, если есть
    }

    url = API_BASE + API_ENDPOINT
    resp = requests.get(url, headers=headers, params=params, timeout=10)

    # Проверка HTTP-статуса
    resp.raise_for_status()

    data = resp.json()

    # Проверяем структуру ответа и возможные ошибки в поле status
    if "status" in data and data["status"].get("error_code", 0) != 0:
        raise RuntimeError(f"API error: {data['status'].get('error_message')}")

    prices = {}
    for sym, info in data.get("data", {}).items():
        # info['quote'][convert]['price'] содержит цену
        quote = info.get("quote", {}).get(convert)
        if quote and "price" in quote:
            prices[sym] = float(quote["price"])
    return prices

if __name__ == "__main__":
    # Пример использования
    try:
        symbols = ["BTC", "ETH", "TAC"]  # замените на нужные символы
        prices = get_cmc_prices(symbols, convert="USD")
        for s, p in prices.items():
            print(f"{s} -> {p:.8f} USD")
    except Exception as e:
        print("Ошибка:", e)




