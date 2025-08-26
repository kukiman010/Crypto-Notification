from systems.database import Database
# from data_models import assistent_model
# from data_models import languages_model
# from data_models import payments_model
# from data_models import tariffs_model
# from Control.user import User
from typing import List
# from Control.subscription_data import SubscriptionData

# import Control.context_model
from control.user       import User

class dbApi:
    def __init__(self, dbname, user, password, host, port):
        self.db = Database(dbname,user, password, host, port)


    def add_user(self, user_id, username, type, language_code):
        query = 'SELECT add_user(%s, %s, %s, %s);'
        values = (user_id, username, type, language_code)
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
            user.set_data(i[0], i[1], i[2], i[3], i[4], i[5], i[6], i[7], i[8], i[9] , i[10])

            return user

        return None

    def update_last_login(self, userId):
        query = 'SELECT update_last_login({})'.format(userId)
        self.db.execute_query(query)

    def update_last_balance_mes_id(self, userId, mesId):
        query = 'SELECT update_last_balance_mes_id({}, {})'.format(userId, mesId)
        self.db.execute_query(query)

    def update_count_post_balance_mes(self, userId, index):
        query = 'SELECT update_count_post_balance_mes({}, {})'.format(userId, index)
        self.db.execute_query(query)

    def add_favorit_coin(self, userId, coin):
        query = 'SELECT add_favorit_coin({}, {})'.format(userId, coin)
        self.db.execute_query(query)

    def remove_favorit_coin(self, userId, coin):
        query = 'SELECT remove_favorit_coin({}, {})'.format(userId, coin)
        self.db.execute_query(query)

    def get_last_active_users(self) -> list[int]:
        query = "SELECT * FROM get_active_user_ids();"
        data = self.db.execute_query(query)
        array = []

        for id in data:
            array.append(id[0])

        return array
    

    # def update_user_lang_code(self, userId, code): 
    #     query = "UPDATE users SET language_code=%s WHERE user_id=%s;"
    #     values = (code, userId)
    #     self.db.execute_query(query, values)
        
    # def get_languages(self):
        # query = "select * from languages;"
        # data = self.db.execute_query(query)
        # array = []

        # for i in data:
    #         lm = languages_model()
    #         lm.set_model(i[0],i[1],i[2])
    #         array.append( lm )
    #     return array




    def __del__(self):
        self.db.close_pool()
