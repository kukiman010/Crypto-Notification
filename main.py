import schedulertimer
import telebot, sys, re
import api_coinmarketcap

from queue import Empty



f = open("./configs/telegram.key")
TOKEN_TG = f.read()
f = open("./configs/coinmarketcap.key")
TOKEN_COIN = f.read()


_bot = telebot.TeleBot( TOKEN_TG )
_coinApi = api_coinmarketcap.CoinMarketCapAPI(TOKEN_COIN)
symbols = ["BTC", "ETH", "TAC"]
_prices_info = None
notifications = {}


def on_get_price(signal=None):
    if signal != None:
        print("[callback] Signal received:", signal['fired_time'], "since_last:", signal['since_last_seconds'])

    # prices = _coinApi.get_prices(symbols, convert="USD")
    # for s, p in prices.items():
        # print(f"{s} -> {p:.8f} USD")

    global _prices_info 
    _prices_info = _coinApi.get_prices_info(symbols, convert="USD")
    print("Результаты:")
    for sym, data in _prices_info.items():
        print(f"{sym}: base_price={data['base_price']} | converted_price={data['converted_price']} {data['convert_currency']}")

        coin = sym.lower()
        current_price = data['converted_price']
        for user_id in notifications:
            check_and_notify(user_id, coin, current_price)

    print('\n\n')


@_bot.message_handler(commands=['start'])
def send_welcome(message):
    # user = user_verification(message)
    username = str(message.chat.username)
    # _db.delete_user_context(message.from_user.id, message.chat.id)
    # t_mes = locale.find_translation(user.get_language(), 'TR_START_MESSAGE')
    _bot.reply_to(message, 'hi'.format(username) )


@_bot.message_handler(commands=['price'])
def send_price(message):

    text = ''
    for sym, data in _prices_info.items():
        text += '{} -> {} {}\n'.format(sym, data['converted_price'], data['convert_currency'])

    _bot.send_message(message.chat.id, 'Курс валют:\n' + text )


@_bot.message_handler(commands=['notify'])
def handle_notify(message):
    pattern = r'^/notify\s+(\w+)\s+([\d.]+)\s+(.+)$'
    match = re.match(pattern, message.text.strip(), re.IGNORECASE)
    if not match:
        bot.reply_to(message, "Правильный формат: /notify btc 117380.50 зайди на биржу")
        r_eturn

    coin, price_str, note = match.groups()
    try:
        price = float(price_str)
        if price <= 0:
            raise ValueError
    except ValueError:
        _bot.reply_to(message, "Цена должна быть положительным числом.")
        return

    user_id = message.from_user.id
    notif = {'coin': coin.lower(), 'price': price, 'note': note, 'sent': False}
    notifications.setdefault(user_id, []).append(notif)
    _bot.reply_to(message, f"Добавлено уведомление: {coin.upper()} при цене {price} — {note}")

def check_and_notify(user_id, coin, current_price):
    user_notifs = notifications.get(user_id, [])
    # Берём уведомления с этой монетой и не отправленные
    relevant = [n for n in user_notifs if n['coin'] == coin and not n['sent']]
    # Только те, которые можно сработать по текущей цене
    candidates = [n for n in relevant if current_price >= n['price']]
    if not candidates:
        return
    # Самое большое значение, не превышающее курс (ближе всего)
    best = max(candidates, key=lambda n: n['price'])
    best['sent'] = True
    _bot.send_message(user_id, f" {coin.upper()} достиг {best['price']}! {best['note']}")

if __name__ == "__main__":
    LIMIT = 10000 # лимит 2000/мес
    TZ = 'UTC'  # можно 'America/New_York' или 'Europe/Berlin'

    sched = schedulertimer.generate_schedule(limit_per_month=LIMIT, days_in_month=31, tz_out=TZ)
    times = sched['daily_times_flat']
    window_indices = sched['daily_times_window_index']

    print("Daily requests:", sched['daily_requests'], "monthly_used:", sched['monthly_used'], "residual:", sched['residual_monthly'])
    print("Times today sample (first 10):", times[:10])

    scheduler = schedulertimer.TimerScheduler(daily_times=times, daily_window_indices=window_indices, callback=on_get_price, tz_out=TZ, name="MyScheduler")
    scheduler.start(daemon=True)

    on_get_price(None)
    _bot.infinity_polling()    



