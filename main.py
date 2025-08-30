import threading
import requests
import telebot
import sys
import re

from telebot                import types

from systems.configure      import Settings
_setting = Settings()

from systems.databaseapi    import dbApi
from systems.logger         import LoggerSingleton
from systems.translator     import Locale
from control.timezone       import TimeZone_api
from control.languages      import languages_api
from control.user           import User

from api_coinmarketcap      import CoinMarketCapApi
from api_coin_history       import CoinGeckoHistory
from systems.schedulertimer import generate_schedule, TimerScheduler
from tools.tools            import get_time_string, send_text, get_current_time_with_utc_offset, crypto_trim




sys.stdout.reconfigure(encoding='utf-8')
_logger = LoggerSingleton.new_instance('logs/log_cripto_notify.log')
_locale = Locale('locale/')
# _env = Environment()
_db = dbApi( _setting.get_db_dbname(), _setting.get_db_user(), _setting.get_db_pass(), _setting.get_db_host(), _setting.get_db_port() )


# LIMIT = _coinApi.get
# TZ = _env.get_timeZone()

# LIMIT = 44640 # лимит 2000/мес
LIMIT = 10000 # лимит 2000/мес
TZ = 'UTC'  # можно 'America/New_York' или 'Europe/Berlin'


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
_coinHistoreApi = CoinGeckoHistory()
# _coinApi.force_refresh()
_time_zone_api = TimeZone_api( _db.get_time_zones() )
_languages_api = languages_api( _db.get_languages() )

notifications = {}

if __name__ == "__main__":
    try:
        _bot = telebot.TeleBot( TOKEN_TG )
    except requests.exceptions.ConnectionError as e:
        _logger.add_error('{} - Нет соединения с сервером telegram bot: {}'.format(get_time_string() ,e))

# _bot = telebot.TeleBot( TOKEN_TG )





def on_update_users_price():
    # users = _db.get_users_balance_mes()
    
    user_ids =  _db.get_last_active_users()

    for id in user_ids:
        balance_user(id)


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


    _coinApi.force_refresh()

    thread_price = threading.Thread(target=on_update_users_price)
    # thread_notify = threading.Thread(target=on_check_notifications)

    thread_price.start()
    # thread_notify.start()


@_bot.message_handler(commands=['start'])
def send_welcome(message):
    user = user_verification(message)

    language = _languages_api.code_to_description(user.get_language())

    zone_str = ''
    if user.get_code_time() > 0:
        zone_str = 'UTC +{}'.format(user.get_code_time())
    else:
        zone_str = 'UTC {}'.format(user.get_code_time())
    
    send_text(_bot, user.get_user_id(), _locale.find_translation(user.get_language(), 'TR_START_MESSAGE').format(user.get_name(), language, zone_str) )

    balance_user(user.get_user_id(), False)



@_bot.message_handler(commands=['set_time_zone'])
def get_time_zone(message):
    user = user_verification(message)

    if user.is_valid():
        get_time_zone(user)



@_bot.message_handler(commands=['set_language'])
def get_language(message):
    user = user_verification(message)

    if user.is_valid():
        get_language(user)



@_bot.message_handler(commands=['price'])
def send_price(message):
    user = user_verification(message)

    if user.is_valid():
        balance_user(user.get_user_id(), False)



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



@_bot.callback_query_handler(func=lambda call: True)
def debug_callback(call):
    user = user_verification_easy(call.message.chat.id)
    key = call.data
    message_id = call.message.message_id
    chat_id = call.message.chat.id

    timezone_pattern = r'^set_timezone_model_(\d+)$'
    timezone_match = re.match(timezone_pattern, key)

    language_pattern = r'^set_lang_model_(\d+)$'
    language_match = re.match(language_pattern, key)

    add_favorit_coin = r'^add_favorit_coin_(\S+)$'
    add_favorit_match = re.match(add_favorit_coin, key)

    del_favorit_coin = r'^del_favorit_coin_(\S+)$'
    del_favorit_match = re.match(del_favorit_coin, key)
    


    if key == 'menu':
        _bot.answer_callback_query(call.id, text = '')
        # main_menu(user, chat_id, message_id)

    elif key == 'find_coin':
        _bot.answer_callback_query(call.id, text = '')
        _db.update_user_action(chat_id, 'find_coin')

        send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_FIND_COIN_LABEL'))


    elif timezone_match:
        _bot.answer_callback_query(call.id, text = '')
        id = int(timezone_match.group(1))
        time_zone = _time_zone_api.find_botton(id)
        _db.set_timezone(user.get_user_id(), time_zone)
        send_text(_bot, user.get_user_id(), _locale.find_translation(user.get_language(), 'TR_SUCCESSFUL_TIMEZONE'), id_message_for_edit= message_id)

    elif language_match:
        id = int(language_match.group(1))
        code_lang = _languages_api.find_bottom(id)
        if _locale.islanguage( code_lang ):
            _db.set_user_lang(user.get_user_id(), code_lang)
            user._lang_code = code_lang
            send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_SYSTEM_LANGUAGE_CHANGE'), id_message_for_edit= message_id)
            _bot.answer_callback_query(call.id, _locale.find_translation(code_lang, 'TR_SUCCESS'))
        else:
            send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_SYSTEM_LANGUAGE_SUPPORT'), id_message_for_edit= message_id)
            _bot.answer_callback_query(call.id, _locale.find_translation(user.get_language(), 'TR_FAILURE'))

    
    elif add_favorit_match:
        _bot.answer_callback_query(call.id, text = '')
        coin_symbol = add_favorit_match.group(1)
        _db.add_favorit_coin(user.get_user_id(), coin_symbol)
        send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_MES_ADD_FAVORIT_COIN').format(coin_symbol), id_message_for_edit= message_id)

    elif del_favorit_match:
        _bot.answer_callback_query(call.id, text = '')
        coin_symbol = del_favorit_match.group(1)
        _db.remove_favorit_coin(user.get_user_id(), coin_symbol)
        send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_MES_DEL_FAVORIT_COIN').format(coin_symbol), id_message_for_edit= message_id)


    else:
        t_mes = _locale.find_translation(user.get_language(), 'TR_ERROR')
        _bot.answer_callback_query(call.id, text = t_mes)



@_bot.message_handler(func=lambda message: True)
def handle_user_message(message):
    user = user_verification(message)

    action = user.get_action()
    if action != '' and action != None:
        action_handler(user.get_user_id(), user, action, message.text)
        return


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


def balance_user(userId, automatically_call:bool = True):
    user = user_verification_easy(userId)

    # if not user.is_valid():
        # return

    t_mes = _locale.find_translation(user.get_language(), 'TR_BALANCE_MES')
    pattern_coin = _locale.find_translation(user.get_language(), 'TR_PARENT_COIN')

    coins = _coinApi.get_top(10)
    coins_mes = ''

    for node in coins:
        s = node.symbol
        if len(node.symbol) == 3:
            s += ' '
        coins_mes += str( pattern_coin.format( s, crypto_trim(node.price), node.convert_currency) + '\n' )

    favorites = ''
    # for coint in user.get_favorites_coins()
        # favorites =

    if not favorites:
        favorites = _locale.find_translation(user.get_language(), 'TR_NO_FAVORITES')

    isNew = False

    if user.get_count_post_balance_mes() > 5 :
        isNew = True
    elif user.get_last_balance_mes_id() == 0:
        isNew = True
        
    last_update_coin = get_current_time_with_utc_offset( user.get_code_time() )

    markup = types.InlineKeyboardMarkup()
    markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_FIND_COIN'),    callback_data='find_coin') )

        
    if isNew or automatically_call == False:
        message_id = send_text(_bot, userId, t_mes.format(coins_mes, favorites, last_update_coin), reply_markup=markup  )
    else:
        message_id = send_text(_bot, userId, t_mes.format(coins_mes, favorites, last_update_coin), reply_markup=markup, id_message_for_edit = user.get_last_balance_mes_id() )

    if message_id != None:
        _db.update_last_balance_mes_id(userId, message_id)

    # print()



def user_verification(message) -> User:
    user = User()

    if _db.find_user(message.from_user.id) == False:
        # user.set_default_data(_env.get_language(), _env.get_permission(), _env.get_company_ai(), _env.get_assistant_model(), _env.get_recognizes_photo_model(), _env.get_generate_photo_model(), _env.get_text_to_audio(), _env.get_audio_to_text(), _env.get_speakerName(), _env.get_prompt())
        name = message.chat.username
        if not name:
            name = message.chat.first_name

        lang_code = message.from_user.language_code
        time_zone = 0
        if lang_code == 'ru':
            time_zone = 3
        elif lang_code == 'en':
            time_zone = 0
        elif lang_code == 'es':
            time_zone = -6
        elif lang_code == '0':
            time_zone = -4
        elif lang_code == 'fr':
            time_zone = 1
        

        _db.add_user(message.from_user.id, name, message.chat.type, lang_code, time_zone )
        _logger.add_info('Cоздан новый пользователь {} {}'.format(message.from_user.id, name))
    
    user = _db.get_user(message.from_user.id)
    _db.update_last_login(user.get_user_id())

    if user.get_tariff() == 0: # block
        return None

    return user



def user_verification_easy(userId) -> User:
    user = User()
    if _db.find_user(userId) == False:
        return None
    else:
        user = _db.get_user(userId)
        _db.update_last_login(user.get_user_id())
        return user
    


def get_time_zone(user: User, message_id:int = -1):
    label = _locale.find_translation(user.get_language(), 'TR_MENU_TIMEZONE')
    
    buttons = _time_zone_api.available_by_status()
    markup = types.InlineKeyboardMarkup()
    for key, value in buttons.items():
        markup.add(types.InlineKeyboardButton(value, callback_data=key))

    if message_id >= 0:
        markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_MENU'),    callback_data='menu') )
        send_text(_bot, user.get_user_id(), label, reply_markup=markup, id_message_for_edit=message_id)
    else:
        send_text(_bot, user.get_user_id(), label, reply_markup=markup)



def get_language(user: User, message_id:int = -1):
    # _bot.answer_callback_query(call.id, text = '')
    if user == None or _languages_api.size() == 0:
        send_text(user.get_language(), _locale.find_translation(user.get_language(), 'TR_ERROR_NOT_CHANGE_LANGUAGE'))
        return
    t_mes = _locale.find_translation(user.get_language(), 'TR_SELECT_LANGUAGE')
    
    buttons = _languages_api.available_by_status()
    markup = types.InlineKeyboardMarkup()
    for key, value in buttons.items():
        markup.add(types.InlineKeyboardButton(value, callback_data=key))

    if message_id >= 0:
        markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_MENU'),    callback_data='menu') )
        send_text(_bot, user.get_language(), t_mes, reply_markup=markup, id_message_for_edit=message_id)
    else:
        send_text(_bot, user.get_user_id(), t_mes, reply_markup=markup)



def action_handler(chatId, user:User, action, text):

    if action == 'find_coin':
        _db.update_user_action(user.get_user_id(), '')

        coin = _coinApi.find_coin(text)

        if coin == None:
            print('error in action_handler')

        last_update_coin = get_current_time_with_utc_offset( user.get_code_time() )

        # mes = _locale.find_translation('ru', 'TR_COIN_INFO').format( coin.name, coin.symbol, coin.id, coin.price, coin.symbol, coin.convert_currency, coin.last_updated )
        mes = _locale.find_translation('ru', 'TR_COIN_INFO').format( coin.name, coin.symbol, coin.id, crypto_trim(coin.price), coin.symbol, coin.convert_currency, last_update_coin )

        photo_byte = _coinHistoreApi.plot_history( coin.symbol, 7, coin.convert_currency.lower() )

        markup = types.InlineKeyboardMarkup()
        markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_ADD_FAVORIT_COIN'),    callback_data='add_favorit_coin_{}'.format(coin.symbol)) )
        markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_DEL_FAVORIT_COIN'),    callback_data='del_favorit_coin_{}'.format(coin.symbol)) )

        send_text(_bot, chatId, mes, markup, photo=photo_byte)


    else:
        _db.update_user_action( user.get_user_id(), '' )
        _logger.add_critical('There is no processing of such a scenario: {}, the action will be reset from user {}'.format(action, chatId))







if __name__ == "__main__":
    _coinApi.parse_cmc_api_limits( _coinApi.get_cmc_api_limits() )

    sched = generate_schedule(limit_per_month=LIMIT, days_in_month=31, tz_out=TZ)
    times = sched['daily_times_flat']
    window_indices = sched['daily_times_window_index']

    print("Daily requests:", sched['daily_requests'], "monthly_used:", sched['monthly_used'], "residual:", sched['residual_monthly'])
    print("Times today sample (first 10):", times[:10])

    scheduler = TimerScheduler(daily_times=times, daily_window_indices=window_indices, callback=on_get_price, tz_out=TZ, name="MyScheduler")
    scheduler.start(daemon=True)

    on_get_price(None)
    


_bot.infinity_polling()    
