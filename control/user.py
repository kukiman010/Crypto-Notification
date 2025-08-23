class User:
    def __init__(self) -> None:
        self._user_id =                 0
        self._name =                    ''
        self._tariff =                  1  # 0-lock, 1-default user, 2 >= - donater
        self._lang_code =               ''
        self._favorit_coins =           '' # array
        self._status =                  ''
        self._last_balance_mes_id=      ''
        self._count_post_balance_mes =  ''
        self._last_login =              ''
        self._registration =            ''
        
        

    def is_valid(self):
        return self._user_id != 0 and self._name != ''
        
    def set_data(self, user_id, name, lang_code, tariff, favorit_coins, status, last_balance_mes_id, count_post_balance_mes, last_login, registration):
        self._user_id =                 user_id
        self._name =                    name
        self._tariff =                  tariff
        self._lang_code =               lang_code
        self._favorit_coins =           favorit_coins
        self._status =                  status
        self._last_balance_mes_id=      last_balance_mes_id
        self._count_post_balance_mes =  count_post_balance_mes
        self._last_login =              last_login
        self._registration =            registration


    def get_user_id(self):
        return self._user_id
    def get_name(self):
        return self._name
    def get_tariff(self):
        return self._tariff
    def get_lang_code(self):
        return self._lang_code
    def get_favorit_coins(self):
        return self._favorit_coins
    def get_status(self):
        return self._status
    def get_last_balance_mes_id(self):
        return self._last_balance_mes_id
    def get_count_post_balance_mes(self):
        return self._count_post_balance_mes
    def get_last_login(self):
        return self._last_login
    def get_registration(self):
        return self._registration