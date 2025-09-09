import time
import requests
from decimal import Decimal, getcontext, localcontext
from datetime import datetime, timezone, timedelta
from systems.logger         import LoggerSingleton
import xml.etree.ElementTree as ET

_logger = LoggerSingleton.new_instance('logs/log_cripto_notify.log')

def get_time_string(self):
        current_time = time.time()
        time_struct = time.localtime(current_time)
        milliseconds = int((current_time - int(current_time)) * 1000)
        return time.strftime("%Y%m%d_%H%M%S", time_struct) + f"_{milliseconds:03d}"



def send_text(
    telegram_bot, 
    chat_id, 
    text, 
    reply_markup=None, 
    id_message_for_edit=None, 
    photo=None,  # <-- добавлен параметр для фото
    photo_caption=None  # <-- опционально свой текст для фото 
):
    max_message_length = 4050
    hard_break_point = 3700
    soft_break_point = 3300
    results = []

    while len(text) > max_message_length:
        offset = text[soft_break_point:hard_break_point].rfind('\n')
        if offset == -1:
            offset = text[soft_break_point:max_message_length].rfind(' ')
        if offset == -1:
            results.append(text[:max_message_length])
            text = text[max_message_length:]
        else:
            original_index = offset + soft_break_point
            results.append(text[:original_index])
            text = text[original_index:]

    if text:
        results.append(text)

    sent_message_id = None

    for i, chunk in enumerate(results):
        try:
            # Если edit и первый чанк (здесь нельзя вставить фото)
            if id_message_for_edit and i == 0:
                msg = telegram_bot.edit_message_text(
                    chat_id=chat_id, 
                    message_id=id_message_for_edit, 
                    text=chunk, 
                    reply_markup=reply_markup
                )
                sent_message_id = msg.message_id
                id_message_for_edit = None

            elif photo is not None and i == 0:
                # Первый чанк с фото!
                msg = telegram_bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=photo_caption if photo_caption is not None else chunk,
                    reply_markup=reply_markup
                )
                sent_message_id = msg.message_id
                photo = None  # фото отправлено только 1 раз

            else:
                # Обычный текст
                msg = telegram_bot.send_message(
                    chat_id, 
                    chunk, 
                    reply_markup=reply_markup
                )
                if sent_message_id is None:
                    sent_message_id = msg.message_id

        except Exception as e:
            _logger.add_critical(
                f"Ошибка для chat_id:{chat_id} при отправке сообщения. Ошибка: {e}\n В этом тексте: \n{chunk}"
            )
            msg = telegram_bot.send_message(chat_id, chunk, reply_markup=reply_markup)
            if sent_message_id is None:
                sent_message_id = msg.message_id

    return sent_message_id



def get_current_time_with_utc_offset(offset_hours: int) -> str:
    tz = timezone(timedelta(hours=offset_hours))
    dt = datetime.now(tz)

    zone_str = ''
    if offset_hours > 0:
        zone_str = '(UTC +{})'.format(offset_hours)
    else:
        zone_str = '(UTC {})'.format(offset_hours)

    return dt.strftime("%Y-%m-%d %H:%M:%S") +'  ' + zone_str



def crypto_trim(number, significant_digits=2):
    """
    Обрезает число после ведущих нулей и первой значимой цифры,
    оставляя заданное количество значимых знаков.

    Пример: crypto_trim(0.000121332423, 1) -> 0.0001
            crypto_trim(0.000121332423, 3) -> 0.000121
            crypto_trim(3.1346343759531092, 2) -> 3.13
    """
    if number == 0:
        return 0.0

    # Строгий контроль числа знаков (много больше, чем надо)
    getcontext().prec = 50
    d = Decimal(str(number)).normalize()

    # Преобразуем к виду с фиксированной точкой (не экспоненте)
    s = format(d, 'f')
    if '.' not in s:
        return float(s)

    integer, fraction = s.split('.')
    # Если целая часть не нулевая — обычное округление
    if int(integer) != 0:
        out = f"{integer}.{fraction[:significant_digits]}"
        return float(out)

    # Для малых чисел — ищем первые significant_digits в дробной части после незначащих нулей
    sig_count = 0
    trim = ''
    for c in fraction:
        trim += c
        if c != '0':
            sig_count += 1
        if sig_count == significant_digits:
            break
    out = f"0.{trim}"
    return float(out)

def sci_to_plain(value) -> str:
    """
    Преобразует число (в т.ч. в научной нотации) в обычную десятичную строку без 'e/E'.
    Рекомендуется передавать строку для точного сохранения всех цифр.
    """
    # Если пришёл float — сначала переводим в строку с безопасным количеством значимых цифр
    if isinstance(value, float):
        # 17 значимых цифр гарантируют корректный раунд-трип IEEE-754 double
        value = format(value, '.17g')

    # Преобразуем к Decimal через строку (это важно для точности)
    d = Decimal(str(value))

    # Увеличиваем precision хотя бы до количества цифр мантиссы,
    # чтобы избежать ненужных округлений при форматировании
    with localcontext() as ctx:
        ctx.prec = max(50, len(d.as_tuple().digits))
        out = format(d, 'f')  # фиксированный формат без экспоненты

    # Если нужно убирать хвостовые нули — раскомментируйте:
    # if '.' in out:
    #     out = out.rstrip('0').rstrip('.')
    return out


def is_between(x, now, old, triger):
    if triger == '>' and now > x:
        return True
    elif triger == '<' and now < x:
        return True

    return False

def get_simvol(prev, price):
    if price > prev:
        return "↗️"
    elif price < prev:
        return  "↘️"
    else:
        return "⏺️"


def usd_to_currency(target_code: str) -> float:
    """
    Возвращает курс USD к target_code (например, 'CNY', 'EUR', 'RUB')
    по данным Центробанка РФ на сегодня.
    """
    url = 'https://www.cbr.ru/scripts/XML_daily.asp'
    response = requests.get(url)
    tree = ET.fromstring(response.content)
    rates = {}
    for code in ['USD', target_code]:
        for valute in tree.findall('Valute'):
            if valute.find('CharCode').text == code:
                value = float(valute.find('Value').text.replace(',', '.'))
                nominal = int(valute.find('Nominal').text)
                rates[code] = value / nominal
                break

    if target_code == 'RUB':
        return rates['USD']
    elif target_code in rates:
        return rates['USD'] / rates[target_code]
    else:
        raise ValueError(f"Валюта {target_code} не найдена в справочнике ЦБ РФ")



