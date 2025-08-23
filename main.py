import threading
import requests
import telebot
import sys
import re

from systems.configure      import Settings
_setting = Settings()

from systems.databaseapi    import dbApi
from systems.logger         import LoggerSingleton
from systems.translator     import Locale

from api_coinmarketcap      import CoinMarketCapApi
from control.data_models    import CryptoBrief
from control.user           import User
from systems.schedulertimer import generate_schedule, TimerScheduler
from tools.tools            import get_time_string, send_text



sys.stdout.reconfigure(encoding='utf-8')
_logger = LoggerSingleton.new_instance('logs/log_cripto_notify.log')
_locale = Locale('locale/')
# _env = Environment()
_db = dbApi( _setting.get_db_dbname(), _setting.get_db_user(), _setting.get_db_pass(), _setting.get_db_host(), _setting.get_db_port() )


TOKEN_TG = _setting.get_tgToken()
TOKEN_COIN_MARKET = _setting.get_coinMarketCapToken()

if TOKEN_TG == '':
    _logger.add_critical('No tg token!')
    sys.exit()

if TOKEN_COIN_MARKET == '':
    _logger.add_critical('No coinMarketCap token!')
    sys.exit()


# _env.update( _db.get_environment() )
# if not _env.is_valid():
#     _logger.add_critical('Environment is not corrected!')
#     exit 

_coinApi = CoinMarketCapApi( api_key=TOKEN_COIN_MARKET, default_convert="USD", cache_limit=200, verbose=True )
# _coinApi.force_refresh()

notifications = {}

if __name__ == "__main__":
    try:
        _bot = telebot.TeleBot( TOKEN_TG )
    except requests.exceptions.ConnectionError as e:
        _logger.add_error('{} - Нет соединения с сервером telegram bot: {}'.format(get_time_string() ,e))







def on_update_users_price():
    users = _db.get_users_balance_mes()

    for user in users:
        balance_user(user.get_chatId())


# def on_check_notifications():
#     # notifications = _db.users_notifications()

#     for user_id in notifications:
#         # check_and_notify(user_id, coin, current_price)

#         user_notifs = notifications.get(user_id, [])
#         # Берём уведомления с этой монетой и не отправленные
#         relevant = [n for n in user_notifs if n['coin'] == coin and not n['sent']]
#         # Только те, которые можно сработать по текущей цене
#         candidates = [n for n in relevant if current_price >= n['price']]
#         if not candidates:
#             return
#         # Самое большое значение, не превышающее курс (ближе всего)
#         best = max(candidates, key=lambda n: n['price'])
#         best['sent'] = True
#         _bot.send_message(user_id, f" {coin.upper()} достиг {best['price']}! {best['note']}")


def on_get_price(signal=None):
    if signal != None:
        print("[callback] Signal received:", signal['fired_time'], "since_last:", signal['since_last_seconds'])


    # _coinApi.force_refresh()

    # thread_price = threading.Thread(target=on_update_users_price)
    # thread_notify = threading.Thread(target=on_check_notifications)

    # thread_price.start()
    # thread_notify.start()


@_bot.message_handler(commands=['start'])
def send_welcome(message):
    # user = user_verification(message)
    username = str(message.chat.username)
    # _db.delete_user_context(message.from_user.id, message.chat.id)
    # t_mes = locale.find_translation(user.get_language(), 'TR_START_MESSAGE')
    _bot.reply_to(message, 'hi'.format(username) )

    balance_user()


@_bot.message_handler(commands=['price'])
def send_price(message):
    userId = message.chat.id

    balance_user(userId)


@_bot.message_handler(commands=['notify'])
def handle_notify(message):
    pattern = r'^/notify\s+(\w+)\s+([\d.]+)\s+(.+)$'
    match = re.match(pattern, message.text.strip(), re.IGNORECASE)
    if not match:
        _bot.reply_to(message, "Правильный формат: /notify btc 117380.50 зайди на биржу")
        return

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


# def check_and_notify(user_id, coin, current_price):
#     user_notifs = notifications.get(user_id, [])
#     # Берём уведомления с этой монетой и не отправленные
#     relevant = [n for n in user_notifs if n['coin'] == coin and not n['sent']]
#     # Только те, которые можно сработать по текущей цене
#     candidates = [n for n in relevant if current_price >= n['price']]
#     if not candidates:
#         return
#     # Самое большое значение, не превышающее курс (ближе всего)
#     best = max(candidates, key=lambda n: n['price'])
#     best['sent'] = True
#     _bot.send_message(user_id, f" {coin.upper()} достиг {best['price']}! {best['note']}")


def balance_user(userId):
    # users = _db.get_users_balance_mes()

    t_mes = _locale.find_translation('ru', 'TR_BALANCE_MES')
    pattern_coin = _locale.find_translation('ru', 'TR_PARENT_COIN')

    coins = _coinApi.get_top(10)
    last_update_coin = ''

    coins_mes = ''

    for node in coins:
        s = node.symbol
        if len(node.symbol) == 3:
            s += ' '

        coins_mes += str( pattern_coin.format( s, node.price, node.convert_currency) + '\n' )
        last_update_coin = node.last_updated

    favorites = ''
    # for coint in user.get_favorites_coins()
        # favorites =

    if not favorites:
        favorites = _locale.find_translation('ru', 'TR_NO_FAVORITES')


    send_text(_bot, userId, t_mes.format(coins_mes, favorites, last_update_coin) )



def user_verification(message) -> User:
    user = User()

    if _db.find_user(message.from_user.id) == False:
        # user.set_default_data(_env.get_language(), _env.get_permission(), _env.get_company_ai(), _env.get_assistant_model(), _env.get_recognizes_photo_model(), _env.get_generate_photo_model(), _env.get_text_to_audio(), _env.get_audio_to_text(), _env.get_speakerName(), _env.get_prompt())

        name = message.chat.username
        if not name:
            # name = message.chat.
            name = 'FIO'

        _db.add_user(message.from_user.id, message.chat.username, message.chat.type, message.from_user.language_code )
        _logger.add_info('создан новый пользователь {}'.format(message.chat.username))
    else:
        _db.add_users_in_groups(message.from_user.id, message.chat.id)
    
    user = _db.get_user_def(message.from_user.id)

    if user.get_status() == 0: 
        return None

    return user











if __name__ == "__main__":
    _coinApi.parse_cmc_api_limits( _coinApi.get_cmc_api_limits() )

    # LIMIT = _coinApi.get
    # TZ = _env.get_timeZone()

    LIMIT = 10000 # лимит 2000/мес
    TZ = 'UTC'  # можно 'America/New_York' или 'Europe/Berlin'
    


    sched = generate_schedule(limit_per_month=LIMIT, days_in_month=31, tz_out=TZ)
    times = sched['daily_times_flat']
    window_indices = sched['daily_times_window_index']

    print("Daily requests:", sched['daily_requests'], "monthly_used:", sched['monthly_used'], "residual:", sched['residual_monthly'])
    print("Times today sample (first 10):", times[:10])

    scheduler = TimerScheduler(daily_times=times, daily_window_indices=window_indices, callback=on_get_price, tz_out=TZ, name="MyScheduler")
    scheduler.start(daemon=True)

    on_get_price(None)
    _bot.infinity_polling()    



