from dataclasses import dataclass
from datetime import datetime

class languages_model:
    def __init__(self) -> None:
        self.language = ""
        self.code = ""
        self.isView = False

    def set_model(self, language, code, isView):
        self.language = language
        self.code = code
        self.isView = isView

    def get_language(self):
        return self.language
    def get_code(self):
        return self.code
    def get_isView(self):
        return self.isView
    

class languages_api:
    def __init__(self, a_model):
        self._init_models(a_model)
    
    def _init_models(self, a_model):
        self.model = a_model
        self.button_name = []
        self.text_to_button = {}

        for i in range(len(self.model)):
            self.button_name.append("set_lang_model_" + str(i))
            self.text_to_button[i] = str(self.model[i].get_language())
    
    def load_models(self, new_models):
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
            if self.model[i].get_isView():
                button[ self.find_button(i) ] = self.find_text_to_button(i)

        return button
    
    def find_bottom(self, button_key):
        return self.model[button_key].get_code() 
    
    # def isAvailable(self, button_key, user_status):
    #     if self.model[button_key].get_status_lvl() <= user_status :
    #         return True
    #     else:
    #         return False
        
    # def getToken(self, model):
    #     for i in range(len(self.model)):
    #         if self.model[i].get_model_name() == model:
    #             return self.model[i].get_token_size()
    #     return 0

    def clear(self):
        self.model = []
        self.button_name = []
        self.text_to_button = {}



class tariffs_model:
    def __init__(self) :
        self.tariff_id = 0
        self.tariff_name = ''
        self.activity_day = 0
        self.price_usd = 0
        self.price_rub = 0
        self.price_stars = 0
        self.description_code = ''
        self.rules_json = '{}'
        self.isView = False

    def set_model(self, tariff_id, tariff_name, activity_day, usd, rub, stars, description_code, rules_json, isView):
        self.tariff_id = tariff_id
        self.tariff_name = tariff_name
        self.activity_day = activity_day
        self.price_usd = usd
        self.price_rub = rub
        self.price_stars = stars
        self.description_code = description_code
        self.rules_json = rules_json
        self.isView = isView    


class tariffs_api:
    def __init__(self, a_model ):
        self._init_models(a_model)
    
    def _init_models(self, a_model: list[tariffs_model]):
        self.model = a_model
        self.button_name = []
        self.text_to_button = {}

        for i in range(len(self.model)):
            self.button_name.append("set_tariff_model_" + str(i))
            self.text_to_button[i] = str(self.model[i].tariff_name)
    
    def load_models(self, new_models):
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
    
    def find_bottom(self, button_key):
        return self.model[button_key].tariff_id 

    def clear(self):
        self.model = []
        self.button_name = []
        self.text_to_button = {}




@dataclass(frozen=True)
class CryptoBrief:
    """
    Иммутабельный снэпшот краткой информации по монете.
    """
    id: int
    name: str
    symbol: str
    price: float
    convert_currency: str
    last_updated: str
    price_change: str
    previous_price: float



@dataclass(frozen=True)
class AlertCrypto:
    id: int
    user_id: int
    symbol: str
    price: float
    trigger: str
    coment: str
    date: datetime



