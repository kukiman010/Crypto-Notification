# from babel.messages.catalog import Catalog
import polib
import os
from systems.logger         import LoggerSingleton



class Locale:
    _instance = None

    def new_instance(cls, *args, **kwargs):
        if not cls.instance:
            cls.instance = cls(*args, **kwargs)
        return cls.instance
    
    def __init__(self, dir):  
        self._logger = LoggerSingleton.new_instance('logs/log_cripto_notify.log')
        self.dir_locales = dir      
        languages = set( self.collect_files(dir) )
        self.locales = self.read_files( languages )
    
    def find_locale(self):
        locaele_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locale')

    def collect_files(self, folder):
        files = []
        for file in os.listdir(folder):
            # Проверяем, является ли элемент файлом
            if os.path.isfile(os.path.join(folder, file)):
                # Обрезаем расширение файла
                file_name = os.path.splitext(file)[0]
                files.append(file_name)
        return files
    
    
    def read_files(self, file_names):
        translations = {}

        for file_name in file_names:
            try:
                file = str(self.dir_locales + file_name + '.po')
                po = polib.pofile(file)
                
                translations[file_name] = po

            except IOError as e:
                self._logger.add_critical('{} Ошибка: {}!'.format(str(self.__class__.__name__), str(e) ))

        return translations
    
    
    def find_translation(self, file_name, search_word) -> str:
        if file_name not in self.locales:
            self._logger.add_critical('{} The file {} did not load correctly or it does not exist.'.format(str(self.__class__.__name__), str(file_name) ))
            file_name = 'en' #default

        po = self.locales[file_name]
        for entry in po:
            if entry.msgid == search_word:
                return entry.msgstr

        return 'There is no translation for this code: {} word:{}'.format(file_name, search_word)
    
    def islanguage(self, codeLang)-> bool:
        if codeLang in self.locales:
            return True
        else:
            return False



# dir = 'locale/LC_MESSAGES/'
# locale = Locale(dir)

# print( locale.find_translation('ru_RU', 'No') )
# print(locale.find_translation('ru_RU', 'TR_START_MESSAGE').format("Lana"))



