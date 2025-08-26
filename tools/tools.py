import time
from systems.logger         import LoggerSingleton

_logger = LoggerSingleton.new_instance('logs/log_gpt.log')

def get_time_string(self):
        current_time = time.time()
        time_struct = time.localtime(current_time)
        milliseconds = int((current_time - int(current_time)) * 1000)
        return time.strftime("%Y%m%d_%H%M%S", time_struct) + f"_{milliseconds:03d}"


def send_text(telegram_bot, chat_id, text, reply_markup=None, id_message_for_edit=None):
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
            if id_message_for_edit and i == 0:
                msg = telegram_bot.edit_message_text(chat_id=chat_id, message_id=id_message_for_edit, text=chunk, reply_markup=reply_markup)
                sent_message_id = msg.message_id  # Вернет id отредактированного сообщения
                id_message_for_edit = None
            else:
                msg = telegram_bot.send_message(chat_id, chunk, reply_markup=reply_markup)
                # ID только первого отправленного сообщения (собственно, только оно может быть потом редактировано)
                if sent_message_id is None:
                    sent_message_id = msg.message_id

        except Exception as e:
            _logger.add_critical(f"Ошибка для chat_id:{chat_id} при отправке сообщения. Ошибка: {e}\n В этом тексте: \n{chunk}")
            msg = telegram_bot.send_message(chat_id, chunk, reply_markup=reply_markup)
            if sent_message_id is None:
                sent_message_id = msg.message_id

    return sent_message_id
