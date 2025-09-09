from dataclasses import dataclass
from datetime import datetime, timedelta
from tools.tools import usd_to_currency

@dataclass(frozen=True)
class CurrencyModel:
    currency_name: str
    code: str
    isView: bool


class Currencies_api:
    def __init__(self, a_model: list[CurrencyModel] ):
        self._init_models(a_model)
    
    def _init_models(self, a_model: list[CurrencyModel]):
        self.model = a_model
        self.button_name = []
        self.text_to_button = {}

        for i in range(len(self.model)):
            self.button_name.append("set_currencies_" + str(i))
            self.text_to_button[i] = str(self.model[i].currency_name)
    
    def load_models(self, new_models: list[CurrencyModel]):
        self._init_models(new_models)

    def find_button(self, key):
        if self.button_name[key] != None:
            return self.button_name[key]
        else:
            return None

    def find_text_to_button(self, key):
        if key in self.text_to_button:
            return self.text_to_button[key]
        else:
            return None
        
    def size(self):
        return len( self.model )
    
    def available_by_status(self):
        button = {}
        for i in range(len(self.model)):
            if self.model[i].isView:
                button[ self.find_button(i) ] = self.find_text_to_button(i)
        return button
    
    def find_botton(self, button_key):
        return self.model[button_key].code

    def clear(self):
        self.model = []
        self.button_name = []
        self.text_to_button = {}

    def get_list_codes(self):
        list_curr_code= []
        for i in self.model:
            if i.isView == True:
                list_curr_code.append( i.code )
        return list_curr_code



# import requests
# import xml.etree.ElementTree as ET
# def usd_to_currency(target_code: str) -> float:
#     """
#     Возвращает курс USD к target_code (например, 'CNY', 'EUR', 'RUB')
#     по данным Центробанка РФ на сегодня.
#     """
#     url = 'https://www.cbr.ru/scripts/XML_daily.asp'
#     response = requests.get(url)
#     tree = ET.fromstring(response.content)
#     rates = {}
#     for code in ['USD', target_code]:
#         for valute in tree.findall('Valute'):
#             if valute.find('CharCode').text == code:
#                 value = float(valute.find('Value').text.replace(',', '.'))
#                 nominal = int(valute.find('Nominal').text)
#                 rates[code] = value / nominal
#                 break

#     if target_code == 'RUB':
#         return rates['USD']
#     elif target_code in rates:
#         return rates['USD'] / rates[target_code]
#     else:
#         raise ValueError(f"Валюта {target_code} не найдена в справочнике ЦБ РФ")





class CurrencyRatesWrapper:
    last_updated = None  # Класс-атрибут: последнее обновление любого курса

    class CurrencyRate:
        def __init__(self, code: str):
            self.code = code.upper()
            self.update()  # сразу подтянет rate и обновит last_updated

        def update(self):
            self.rate = usd_to_currency(self.code)
            # Обновляем время обновления для валюты
            CurrencyRatesWrapper.last_updated = datetime.now()

    def __init__(self, codes: list[str]):
        self.set_codes(codes)

    def set_codes(self, codes: list[str]):
        """Установить новый список валют и загрузить их курсы"""
        self.currencies = {code.upper(): self.CurrencyRate(code) for code in codes}

    def update_rates(self, codes: list[str] = None):
        """
        Если codes передан — пересобрать массив валют (drop + recreate).
        Иначе — просто обновить курсы у текущих.
        """
        if codes is not None:
            self.set_codes(codes)
        else:
            for currency in self.currencies.values():
                currency.update()

    def is_updated_more_than(self, hours: float) -> bool:
        """Возвращает True, если с последнего обновления прошло больше hours часов."""
        if not self.last_updated:
            return True
        now = datetime.now()
        return (now - self.last_updated) > timedelta(hours=hours)

    def convert(self, amount: float, to_code: str, from_code: str = 'USD') -> float:
        """Конвертировать сумму из одной валюты в другую (по актуальным курсам)"""
        from_cur = self.currencies.get(from_code.upper())
        to_cur = self.currencies.get(to_code.upper())
        if not from_cur:
            raise ValueError(f'Валюта {from_code} отсутствует!')
        if not to_cur:
            raise ValueError(f'Валюта {to_code} отсутствует!')
        amount_in_usd = amount / from_cur.rate
        return amount_in_usd * to_cur.rate

    def get_info(self):
        """Получить текущее состояние массива валют"""
        return [
            {
                "code": c.code,
                "rate": c.rate,
            }
            for c in self.currencies.values()
        ]




# --- Пример использования ---
# codes = ['USD', 'EUR', 'JPY', 'GBP', 'RUB']
# wrapper = CurrencyRatesWrapper(codes)

# print("Исходные курсы:", wrapper.get_info())
# print("12 USD в EUR:", wrapper.convert(12, 'USD', 'EUR'))
# wrapper.update_rates(['EUR', 'GBP', 'CHF'])   # Пересобирает список валют по-новому
# print("Обновленный состав:", wrapper.get_info())

# print(wrapper.get_info())
# print('Прошло больше 2 часов?', wrapper.is_updated_more_than(2))