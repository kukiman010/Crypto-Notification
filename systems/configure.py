import configparser
import os


class Settings:
    def __init__(self):
        self.base_way = os.path.dirname(os.path.realpath(__file__)) + '/../'

        self.config = configparser.ConfigParser()
        self.sberConfig = configparser.ConfigParser()
        self.isInitDB = False
        self.isInitSber = False   

        self.config['Database'] = {'host': 'localhost', 'port': '5432', 'dbname': 'base', 'user': 'postgres', 'password': '123'}
        self.sberConfig['Conf'] = {'reg_data': -1, 'guid': -1, 'certificate': True}

        if self.folder_exist(self.base_way + 'configs/') == False:
            self.folder_create(self.base_way + 'configs')

        if self.folder_exist(self.base_way + 'locale/') == False:
            self.folder_create(self.base_way + 'locale')

        if self.folder_exist(self.base_way + 'logs/') == False:
            self.folder_create(self.base_way + 'logs')

        if self.file_exist(self.base_way + 'configs/telegram.key') == False:
            self.file_create(self.base_way + 'configs/telegram.key')

        if self.file_exist(self.base_way + 'configs/coinmarketcap.key') == False:
            self.file_create(self.base_way + 'configs/coinmarketcap.key')

        if self.file_exist(self.base_way + 'configs/db.conf') :
            self.isInitDB = self.db_conf_read()
        else:
            self.isInitDB = self.db_conf_create()



    def get_path(self):
        return self.base_way
    
    def file_exist(self, file_path):
        if os.path.exists(file_path):
            return True
        else:
            return False

    def file_create(self, file_path):
        with open(file_path, 'w') as file:
            file.write('')

    def folder_exist(self, folder_path):
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            return True
        else:
            return False

    def folder_create(self, folder_path):
        os.mkdir(folder_path)

    def get_db_host(self):
        return self.config['Database']['host']

    def get_db_port(self):
        return self.config['Database']['port']
    
    def get_db_dbname(self):
        return self.config['Database']['dbname']

    def get_db_user(self):
        return self.config['Database']['user']

    def get_db_pass(self):
        return self.config['Database']['password']
    



    



    def db_conf_create(self):
        with open(self.base_way + 'configs/db.conf', 'w') as configfile:
            self.config.write(configfile)
        
        return self.file_exist(self.base_way + 'configs/db.conf') 
            
    def db_conf_read(self):
        if self.base_way + 'configs/db.conf' in self.config.read(self.base_way + 'configs/db.conf'):
            return True
        else:
            return False


    # get telegram bot token
    def get_tgToken(self):
        TOKEN_TG = ""
        if not( os.path.exists(self.base_way + "configs/telegram.key") ):
            file = open(self.base_way + "configs/telegram.key", 'w')
            file.close()
            return TOKEN_TG
        else:
            file = open(self.base_way + "configs/telegram.key", 'r')
            TOKEN_TG = file.read()
            file.close()
            return TOKEN_TG
        

    # get chatgpt token
    def get_coinMarketCapToken(self):
        TOKEN_COIN = ""
        if not( os.path.exists(self.base_way + "configs/coinmarketcap.key") ):
            file = open(self.base_way + "configs/coinmarketcap.key", 'w')
            file.close()
            return TOKEN_COIN
        else:
            file = open(self.base_way + "configs/coinmarketcap.key", 'r')
            TOKEN_COIN = file.read()
            file.close()
            return TOKEN_COIN
    




