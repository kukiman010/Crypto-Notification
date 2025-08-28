from dataclasses import dataclass

@dataclass(frozen=True)
class TimeZone_model:
    code_time: int
    is_View : bool
    def_lang_code: str
    description: str



class TimeZone_api:
    def __init__(self, a_model: list[TimeZone_model] ):
        self._init_models(a_model)
    
    def _init_models(self, a_model: list[TimeZone_model]):
        self.model = a_model
        self.button_name = []
        self.text_to_button = {}

        for i in range(len(self.model)):
            self.button_name.append("set_timezone_model_" + str(i))
            self.text_to_button[i] = str(self.model[i].description)
    
    def load_models(self, new_models: list[TimeZone_model]):
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
            if self.model[i].is_View:
                button[ self.find_button(i) ] = self.find_text_to_button(i)
        return button
    
    def find_botton(self, button_key):
        return self.model[button_key].code_time 

    def clear(self):
        self.model = []
        self.button_name = []
        self.text_to_button = {}