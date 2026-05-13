import configparser
import os
from typing import List, Tuple


def parse_coinmarketcap_key_text(text: str) -> List[Tuple[str, bool]]:
    """
    Одна строка файла: «API_KEY true|false» (регистр флага не важен).
    Строка без флага — ключ с is_detail=False (пул обновлений).
    Пустые строкы и строки, начинающиеся с #, пропускаются.
    """
    out: List[Tuple[str, bool]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lower() in ("true", "false"):
            is_detail = parts[-1].lower() == "true"
            api_key = " ".join(parts[:-1]).strip()
        else:
            api_key = line
            is_detail = False
        if api_key:
            out.append((api_key, is_detail))
    return out


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
        """Первый ключ из файла (совместимость со старым кодом)."""
        entries = self.get_coinmarketcap_key_entries()
        return entries[0][0] if entries else ""

    def get_coinmarketcap_key_entries(self) -> List[Tuple[str, bool]]:
        path = self.base_way + "configs/coinmarketcap.key"
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return parse_coinmarketcap_key_text(f.read())





