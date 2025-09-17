
from systems.logger         import LoggerSingleton


_logger = LoggerSingleton.new_instance('logs/log_cripto_notify.log')

class Environment():
    def __init__(self):
        self.tariff = ''
        self.global_payment = ''
        self.last_activity_autoupdate = ''
        self.support_chat = ''
        self.time_zone = ''
        self.autoupdate_currency = ''
        self.check_premium = ''


    def is_valid(self) -> bool:
        if self.tariff and self.support_chat and self.check_premium:
            return True
        else:
            return False

    def update(self, data_dict) -> bool:
        if data_dict is None:
            _logger.add_critical('Нет данных для обновления.')
            return False

        self.tariff =                       data_dict.get("tariff", self.tariff)
        self.global_payment =               data_dict.get("global_payment", self.global_payment)
        self.last_activity_autoupdate =     data_dict.get("last_activity_autoupdate", self.last_activity_autoupdate)
        self.support_chat =                 data_dict.get("support_chat", self.support_chat)
        self.time_zone =                    data_dict.get("time_zone", self.time_zone)
        self.autoupdate_currency =          data_dict.get("autoupdate_currency", self.autoupdate_currency)
        self.check_premium =                data_dict.get("check_premium", self.check_premium)

        return self.is_valid()
    
    def show_differences(self, data_dict, template) -> str:
        if data_dict is None:
            _logger.add_error('Нет данных для сверки.')
            return ""

        mes =''
        for key, new_value in data_dict.items():
            current_value = getattr(self, f'_{key}', None)
            if current_value != new_value:
                mes += str(template.format(key,current_value, new_value) +'\n')
        
        return mes



    def get_tariff(self) -> int:
        return int(self.tariff)
    def get_global_payment(self) -> bool:
        if self.global_payment.lower() == 'true' :
            return True
        else:
            return False
    def get_last_activity_autoupdate(self) -> int:
        return int(self.last_activity_autoupdate)
    def get_support_chat(self) -> str:
        return self.support_chat
    def get_time_zone(self) -> str:
        return self.time_zone
    def get_autoupdate_currency(self) -> int:
        return int(self.autoupdate_currency)
    def get_check_premium(self) -> str:
        return self.check_premium


