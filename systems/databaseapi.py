from systems.database   import Database
# from typing             import List
from control.timezone   import TimeZone_model
from control.languages  import languages_model
from control.user       import User
from control.data_models import AlertCrypto
from control.currencies import CurrencyModel


class dbApi:
    def __init__(self, dbname, user, password, host, port):
        self.db = Database(dbname,user, password, host, port)


    def add_user(self, user_id, username, type, language_code, time_zone):
        query = 'SELECT add_user(%s, %s, %s, %s, %s);'
        values = (user_id, username, type, language_code, time_zone)
        self.db.execute_query(query, values)

    def find_user(self, userId:int):
        query = "SELECT user_find({});".format(userId)
        data = self.db.execute_query(query)
        return bool(data and data[0][0])
        
    def get_user(self, userId) -> User:
        query = "select * from users where user_id={};".format(userId)
        data = self.db.execute_query(query)

        for i in data:
            user = User()
            user.set_data(i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7], i[8], i[9] , i[10], i[11], i[12])
            return user

        return None

    def update_last_login(self, userId):
        query = 'SELECT update_last_login({});'.format(userId)
        self.db.execute_query(query)

    def update_last_balance_mes_id(self, userId, mesId):
        query = 'SELECT update_last_balance_mes_id({}, {});'.format(userId, mesId)
        self.db.execute_query(query)

    def update_count_post_balance_mes(self, userId, index):
        query = 'SELECT update_count_post_balance_mes({}, {});'.format(userId, index)
        self.db.execute_query(query)

    def add_favorit_coin(self, userId, coin):
        query = "SELECT add_favorit_coin({}, '{}');".format(userId, coin)
        self.db.execute_query(query)

    def remove_favorit_coin(self, userId, coin):
        query = "SELECT remove_favorit_coin({}, '{}');".format(userId, coin)
        self.db.execute_query(query)

    def get_last_active_users(self) -> list[int]:
        query = "SELECT * FROM get_active_user_ids();"
        data = self.db.execute_query(query)
        array = []

        for id in data:
            array.append(id[0])

        return array
    
    def get_time_zones(self):
        query = "select * from time_zone"
        data = self.db.execute_query(query)
        array = []

        for i in data:
            timezones = TimeZone_model( code_time= int(i[0]), is_View= bool(i[1]), def_lang_code= str(i[2]), description=str(i[3]) )
            array.append( timezones )

        return array
    
    def set_timezone(self, userId, timezone):
        query = "update users set code_time={} where user_id={};".format(timezone, userId)
        self.db.execute_query(query)

    def get_languages(self):
        query = "select * from languages;"
        data = self.db.execute_query(query)
        array = []

        for i in data:
            lm = languages_model(language=str(i[0]), code=str(i[1]), isView=bool(i[2]) )
            array.append( lm )
        return array
    
    def set_user_lang(self, userId, lang_code):
        query = "update users set language_code='{}' where user_id={};".format(lang_code, userId)
        self.db.execute_query(query)

    def update_user_action(self, userId, action):
        query = "SELECT update_wait_action({}, '{}'); ".format(userId, action)
        self.db.execute_query(query)

    def increment_balance_mes(self, userId):
        query = "SELECT increment_post_balance_mes({});".format(userId)
        self.db.execute_query(query)

    def get_favorit_coins_list(self, days = 0):
        query = "SELECT get_unique_favorit_coins({}); ".format(days)
        data = self.db.execute_query(query)
        return data[0][0]
    


    def add_notification(self, userId, symbol, price, trigger, comment):
        query = "SELECT add_crypto_notification({}, '{}', {}, '{}', '{}');".format(userId, symbol, price, trigger, comment)
        self.db.execute_query(query)

    def del_notification(self, id):
        query = "SELECT delete_crypto_notification({});".format(id)
        self.db.execute_query(query)

    def get_notification_by_userid(self, userId, symbol = None) -> list[AlertCrypto]:
        if symbol == None:
            query = "SELECT get_crypto_notifications_by_user({}); ".format(userId)
        else:
            query = "select * from crypto_notifications where user_id={} and crypto_symbol='{}';".format(userId, symbol)
        data = self.db.execute_query(query)
        array = []

        for i in data:
            ac = AlertCrypto(id=i[0], user_id=i[1], symbol=i[2], price=i[3], trigger=i[4], coment=i[5], date=i[6])
            array.append( ac )
        return array

    def get_notifications(self) -> list[AlertCrypto]:
        query = "select * from crypto_notifications;"
        data = self.db.execute_query(query)
        array = []

        for i in data:
            ac = AlertCrypto(id=i[0], user_id=i[1], symbol=i[2], price=i[3], trigger=i[4], coment=i[5], date=i[6])
            array.append( ac )
        return array
    
    def get_currencies(self):
        query = "select * from currencies;"
        data = self.db.execute_query(query)
        array = []

        for i in data:
            cm = CurrencyModel(currency_name=i[0], code=i[1], isView=i[2])
            array.append( cm )
        return array

    def set_currency(self, userId, code):
        query = "update users set currency_code='{}' where user_id={};".format(code, userId)
        self.db.execute_query(query)



    def __del__(self):
        self.db.close_pool()
