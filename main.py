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
from control.currencies     import Currencies_api, CurrencyRatesWrapper

from api_coinmarketcap      import CoinMarketCapApi
from api_coin_history       import CoinGeckoHistory
from systems.schedulertimer import generate_schedule, TimerScheduler
from tools.tools            import get_time_string, send_text, get_current_time_with_utc_offset, crypto_trim, is_between




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
LIMIT_MAX_MES = 3
AUTOUPDATE_CURRENCY=4 # hour


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
_coinHistoreApi = CoinGeckoHistory()
_time_zone_api = TimeZone_api( _db.get_time_zones() )
_languages_api = languages_api( _db.get_languages() )

list_curr = _db.get_currencies()
_curr_api = Currencies_api( list_curr )
_curr_price_api = CurrencyRatesWrapper( _curr_api.get_list_codes() )



if __name__ == "__main__":
    try:
        _bot = telebot.TeleBot( TOKEN_TG )
    except requests.exceptions.ConnectionError as e:
        _logger.add_error('{} - Нет соединения с сервером telegram bot: {}'.format(get_time_string() ,e))





def on_update_users_price():
    user_ids =  _db.get_last_active_users()

    for id in user_ids:
        balance_user(id)


def on_check_notifications():
    notifications = _db.get_notifications()
    user:User = None
    list_coin = set()
    for notify in notifications:
        list_coin.add(notify.symbol)
        

    coins = _coinApi.get_by_symbols(list_coin)

    for coin in coins:
        price_now = coin.price
        price_old = coin.previous_price

        if price_old == -1 or price_old == None:
            continue

        for notify in notifications:
            if coin.symbol == notify.symbol:
                if is_between(notify.price, price_now, price_old, notify.trigger):
                    if not user.is_valid() and user.get_user_id() != notify.user_id:
                        user = user_verification_easy(notify.user_id)

                    send_text(_bot, notify.user_id, _locale.find_translation(user.get_language(), 'TR_NOTIFY_NOW').format(notify.symbol, crypto_trim(_curr_price_api.convert( price_now, user.get_currency())), user.get_currency(), notify.coment) )
                    _db.increment_balance_mes(notify.user_id)
                    _db.del_notification(notify.id)
                    continue





def on_get_price(signal=None):
    if signal != None:
        print("[callback] Signal received:", signal['fired_time'], "since_last:", signal['since_last_seconds'])

    if _curr_price_api.is_updated_more_than(AUTOUPDATE_CURRENCY):
        _curr_price_api.update_rates( _curr_api.get_list_codes() )

    _coinApi.force_refresh()

    favorit_coins = _db.get_favorit_coins_list(30)
    if favorit_coins != None:
        _coinApi.add_symbols_to_cache(favorit_coins, convert="USD", replace_existing=False)

    thread_price = threading.Thread(target=on_update_users_price)
    thread_notify = threading.Thread(target=on_check_notifications)

    thread_price.start()
    thread_notify.start()


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
def get_time_zone_tg(message):
    user = user_verification(message)

    if user.is_valid():
        get_time_zone(user)



@_bot.message_handler(commands=['set_language'])
def get_language_tg(message):
    user = user_verification(message)

    if user.is_valid():
        get_language(user)


@_bot.message_handler(commands=['set_currency'])
def get_currency_tg(message):
    user = user_verification(message)

    if user.is_valid():
        get_currency(user)




@_bot.message_handler(commands=['price'])
def send_price(message):
    user = user_verification(message)

    if user.is_valid():
        balance_user(user.get_user_id(), False)





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

    add_notify_coin = r'^add_notify_(\S+)$'
    add_notify_match = re.match(add_notify_coin, key)

    set_currencie = r'^set_currencies_(\S+)$'
    set_currencie_match = re.match(set_currencie, key)
    


    if key == 'menu':
        _bot.answer_callback_query(call.id, text = '')
        # main_menu(user, chat_id, message_id)

    elif key == 'find_coin':
        _bot.answer_callback_query(call.id, text = '')
        _db.update_user_action(chat_id, 'find_coin')
        _db.increment_balance_mes(user.get_user_id())
        send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_FIND_COIN_LABEL'))


    elif timezone_match:
        _bot.answer_callback_query(call.id, text = '')
        id = int(timezone_match.group(1))
        time_zone = _time_zone_api.find_botton(id)
        _db.set_timezone(user.get_user_id(), time_zone)
        _db.increment_balance_mes(user.get_user_id())
        send_text(_bot, user.get_user_id(), _locale.find_translation(user.get_language(), 'TR_SUCCESSFUL_TIMEZONE'), id_message_for_edit= message_id)

    elif language_match:
        id = int(language_match.group(1))
        code_lang = _languages_api.find_bottom(id)
        _db.increment_balance_mes(user.get_user_id())
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
        _db.increment_balance_mes(user.get_user_id())
        send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_MES_ADD_FAVORIT_COIN').format(coin_symbol))

    elif del_favorit_match:
        _bot.answer_callback_query(call.id, text = '')
        coin_symbol = del_favorit_match.group(1)
        _db.remove_favorit_coin(user.get_user_id(), coin_symbol)
        _db.increment_balance_mes(user.get_user_id())
        send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_MES_DEL_FAVORIT_COIN').format(coin_symbol))

    elif add_notify_match:
        _bot.answer_callback_query(call.id, text = '')
        coin_symbol = add_notify_match.group(1)
        send_text(_bot, chat_id, _locale.find_translation(user.get_language(), 'TR_ADD_NOTIFICATION_MES').format(coin_symbol))
        _db.update_user_action(chat_id, 'add_notify_' + coin_symbol)

    elif set_currencie_match:
        _bot.answer_callback_query(call.id, text = '')
        id = int(set_currencie_match.group(1))
        code_currency = _curr_api.find_botton(id)
        _db.set_currency(user.get_user_id(), code_currency)
        _db.increment_balance_mes(user.get_user_id())
        send_text(_bot, user.get_user_id(), _locale.find_translation(user.get_language(), 'TR_SUCCESSFUL_CURRENCY'), id_message_for_edit= message_id)

    else:
        t_mes = _locale.find_translation(user.get_language(), 'TR_ERROR')
        _bot.answer_callback_query(call.id, text = t_mes)



@_bot.message_handler(func=lambda message: True)
def handle_user_message(message):
    user = user_verification(message)
    text = message.text
    _db.increment_balance_mes(user.get_user_id())

    action = user.get_action()
    if action != '' and action != None:
        action_handler(user.get_user_id(), user, action, text)
        return
    else:
        is_coin_rx = r'^\/\b([A-Z0-9]{2,5})\b$'
        is_coint_match = re.match(is_coin_rx, text)

        if is_coint_match:
            coin_symbol = is_coint_match.group(1)
            action_handler(user.get_user_id(), user, 'find_coin', coin_symbol)




def balance_user(userId, automatically_call:bool = True):
    user = user_verification_easy(userId)

    # if not user.is_valid():
        # return

    t_mes = _locale.find_translation(user.get_language(), 'TR_BALANCE_MES')
    pattern_coin = '1 /{} -> {} {} {}'

    coins = _coinApi.get_top(10)
    coins_mes = ''

    for node in coins:
        s = node.symbol + '   '
        
        coins_mes += str( pattern_coin.format( s, node.price_change, crypto_trim( _curr_price_api.convert( node.price, user.get_currency()) ), user.get_currency()) + '\n' )

    favorites = ''
    user_favorit_coins =  user.get_favorit_coins()
    if user_favorit_coins != None:
        nodes = _coinApi.get_by_symbols(user_favorit_coins)

        for i in nodes:
            favorites += str( pattern_coin.format( i.symbol.ljust(6)  + '   ', i.price_change, crypto_trim(_curr_price_api.convert( i.price, user.get_currency())), user.get_currency()) + '\n' )

    if not favorites:
        favorites = _locale.find_translation(user.get_language(), 'TR_NO_FAVORITES')

    isNew = False

    if user.get_count_post_balance_mes() > LIMIT_MAX_MES :
        isNew = True
    elif user.get_last_balance_mes_id() == 0:
        isNew = True
        
    last_update_coin = get_current_time_with_utc_offset( user.get_code_time() )

    markup = types.InlineKeyboardMarkup()
    markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_FIND_COIN'),    callback_data='find_coin') )

        
    if isNew or automatically_call == False:
        message_id = send_text(_bot, userId, t_mes.format(coins_mes, favorites, last_update_coin), reply_markup=markup  )
        _db.update_count_post_balance_mes(user.get_user_id(), 0)
    else:
        message_id = send_text(_bot, userId, t_mes.format(coins_mes, favorites, last_update_coin), reply_markup=markup, id_message_for_edit = user.get_last_balance_mes_id() )

    if message_id != None:
        _db.update_last_balance_mes_id(userId, message_id)




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



def get_currency(user: User, message_id:int = -1):
    label = _locale.find_translation(user.get_language(), 'TR_SET_CURRENCY').format( user.get_currency())
    
    buttons = _curr_api.available_by_status()
    markup = types.InlineKeyboardMarkup()
    for key, value in buttons.items():
        markup.add(types.InlineKeyboardButton(value, callback_data=key))

    if message_id >= 0:
        markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_MENU'),    callback_data='menu') )
        send_text(_bot, user.get_user_id(), label, reply_markup=markup, id_message_for_edit=message_id)
    else:
        send_text(_bot, user.get_user_id(), label, reply_markup=markup)




def action_handler(chatId, user:User, action, text):

    add_notify_coin = r'^add_notify_(\S+)$'
    add_notify_match = re.match(add_notify_coin, action)

    if action == 'find_coin':
        _db.update_user_action(user.get_user_id(), '')
        coin = _coinApi.find_coin(text)

        if coin == None:
            send_text(_bot, chatId, _locale.find_translation(user.get_language(), 'TR_NOT_FIND_COIN').format(text))
            _db.increment_balance_mes(user.get_user_id())
            _logger.add_warning('пользователь {} не смог найти монету: {}'.format(user.get_user_id(), text))
            return

        notifications = _db.get_notification_by_userid(user.get_user_id(), coin.symbol)
        notify_mes:str = ""
        for notify in notifications:
            if notify.trigger == '>':
                simvol = ' ↗️'
            else:
                simvol = ' ↘️'

            notify_mes += str(crypto_trim(notify.price,4)) + simvol + '\n'
        
        if len(notifications) < 0:
            notify_mes = _locale.find_translation(user.get_language(), 'TR_NOTIFY_IS_NOT_ADD')

        last_update_coin = get_current_time_with_utc_offset( user.get_code_time() )
        mes = _locale.find_translation(user.get_language(), 'TR_COIN_INFO').format( coin.name, coin.symbol, coin.id, crypto_trim(_curr_price_api.convert( coin.price, user.get_currency())), user.get_currency(), coin.symbol, notify_mes, last_update_coin )
        photo_byte = _coinHistoreApi.plot_history( coin.symbol, 7, coin.convert_currency.lower() )
        markup = types.InlineKeyboardMarkup()
        have_in_favorit = False



        user_favorit_coins =  user.get_favorit_coins()
        if user_favorit_coins != None:
            for i in user.get_favorit_coins():
                if str(i).upper() == coin.symbol.upper():
                    have_in_favorit = True
                    markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_DEL_FAVORIT_COIN'),    callback_data='del_favorit_coin_{}'.format(coin.symbol)) )
                    break

        if not have_in_favorit:
            markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_ADD_FAVORIT_COIN'),    callback_data='add_favorit_coin_{}'.format(coin.symbol)) )
        
        markup.add( types.InlineKeyboardButton(_locale.find_translation(user.get_language(), 'TR_ADD_NOTIFICATION'),        callback_data='add_notify_{}'.format(coin.symbol)) )

        send_text(_bot, chatId, mes, markup, photo=photo_byte)
        return

    elif add_notify_match:
        coin_symbol = add_notify_match.group(1)
        _db.update_user_action(user.get_user_id(), '')
        
        rx = r"^(\d+)(?:(?:[.,']|[ \t])(\d*)[ \t]*(.*))?$"

        array = []
        coin = _coinApi.get_by_symbol(coin_symbol)

        if coin == None:
            return
        
        price_now = coin.price

        for line in str(text).split('\n'):
            rx_match =re.match(rx, line)
            if rx_match:
                number:float

                if rx_match.group(2) != None and rx_match.group(2) != '':
                    number = float(rx_match.group(1) + '.' + rx_match.group(2))
                else:
                    number = float( rx_match.group(1) )

                comment = ''
                if rx_match.group(3) != None:
                    comment = rx_match.group(3)

                trend:str
                if number == price_now:
                    trend = '='
                elif number > price_now:
                    trend = '>'
                elif number < price_now:
                    trend = '<'

                array.append( (number, comment, trend) )


        for p, c, t in array:
            _db.add_notification( user.get_user_id(), coin_symbol, p, t, c)
        

        _db.increment_balance_mes(user.get_user_id())
        if len(array) > 0:
            send_text(_bot, chatId, _locale.find_translation(user.get_language(), 'TR_NOTIFICATION_ADD_OK').format(len(array), coin_symbol))
        else:
            send_text(_bot, chatId, _locale.find_translation(user.get_language(), 'TR_NOTIFICATION_ADD_NOT'))

        return
                
        

        


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
