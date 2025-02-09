from lxml import etree
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtCore import QSettings
from loguru import logger

class LanguageSettings:
    _instance = None  #  싱글톤 인스턴스 저장

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LanguageSettings, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """실제 초기화 (한 번만 실행)"""
        if hasattr(self, "_initialized") and self._initialized:
            return  #  이미 초기화된 경우 실행하지 않음
        self._initialized = True  #  초기화 완료 표시

        # 언어별 폰트 설정
        self.fonts = {
            'kr': QFont("Gulim", 9),
            'jp': QFont("MS Gothic", 9),
        }

        self.translations = {}

        # QSettings를 이용해 저장된 언어 로드
        self.settings = QSettings("SilliN", "ScenarioIndex")
        saved_locale = self.settings.value("language", "kr")  # 저장된 언어를 불러오고 기본값은 'kr'
        self.current_locale = saved_locale

        # 언어 데이터 로드
        self.load_language(self.current_locale)

    def load_language(self, locale):
        """XML 파일을 읽어 번역 데이터 로드"""
        try:
            file_path = f"lang/{locale}.xml"
            tree = etree.parse(file_path)
            root = tree.getroot()

            #  <translations> 태그 내부 데이터만 사용하도록 설정
            if root.tag != "translations":
                logger.error(f"Invalid XML structure: Root element should be <translations> but found <{root.tag}>")
                return
            
            self.translations = self._parse_xml(root)
            self.current_locale = locale

        except etree.XMLSyntaxError as e:
            logger.critical(f"Critical Error loading default language file: {e} ({file_path})")
        except FileNotFoundError:
            logger.warning(f"Language file not found: {locale}. Defaulting to 'kr'.")
            self.current_locale = "kr"
            self.load_language("kr")
        except Exception as e:
            logger.error(f"Error loading language file: {e}. Defaulting to 'kr'.")
            self.current_locale = "kr"
            self.load_language("kr")

    def _parse_xml(self, root):
        """XML 데이터를 파싱하여 딕셔너리로 변환 (빈 값도 포함)"""
        translations = {}
        for child in root:
            if len(child):  #  자식 노드가 있는 경우 (재귀 호출)
                translations[child.tag] = self._parse_xml(child)
            else:  #  텍스트 노드 (빈 값도 저장)
                translations[child.tag] = child.text.strip() if child.text and child.text.strip() else ""  
        return translations

    def set_language(self, locale):
        """언어를 변경하고 QSettings에 저장"""
        if locale == self.current_locale:
            logger.info(f"Language is already set to {locale}, skipping reload.")
            return  #  이미 같은 언어라면 로드할 필요 없음

        if locale in self.fonts:
            self.current_locale = locale  # `language_settings` 업데이트
            self.settings.setValue("language", locale)  # `QSettings` 업데이트
            self.load_language(locale)  # 언어 로드
            logger.info(f" Language changed to: {locale}")

        else:
            logger.warning(f"Unsupported locale: {locale}. Defaulting to 'kr'.")
            if self.current_locale != "kr":  #  이미 기본 언어면 다시 로드할 필요 없음
                self.current_locale = "kr"
                self.settings.setValue("language", "kr")  # 기본값 설정 저장
                self.load_language("kr")
                logger.info("Language reset to Korean ('kr').")

    def translate(self, key: str, default: str = "") -> str:
        """Translate a given key to the appropriate text."""
        keys = key.split(".")
        data = self.translations

        try:
            for k in keys:
                data = data[k]
            return data
        except KeyError:
            logger.error(f"KeyError: {key} not found in translations.")
            return default or key  # 기본값 반환

    def is_font_available(font_name):
        """폰트 설치되어 있는지 확인"""
        return font_name in QFontDatabase().families()

    def get_current_font(self):
        """현재 언어의 기본 폰트 반환 (설치된 폰트가 없으면 Arial 사용)"""
        logger.info(f"Fetching font for language: {self.current_locale}")
        
        # 기본 폰트 설정
        preferred_font = self.fonts.get(self.current_locale, QFont("Arial", 9))  # 기본값 Arial
        available_fonts = QFontDatabase().families()  # 시스템에 설치된 폰트 목록

        # Gulim을 찾지 못하면 굴림을 시도
        if self.current_locale == "kr":
            if "Gulim" in available_fonts:
                preferred_font = QFont("Gulim", 9)
            elif "굴림" in available_fonts:
                logger.warning("Preferred font 'Gulim' not found. Using '굴림' instead.")
                preferred_font = QFont("굴림", 9)
            else:
                logger.warning("Preferred font 'Gulim' and '굴림' not found. Falling back to Arial.")
                preferred_font = QFont("Arial", 9)

        # 일본어의 경우 MS Gothic 사용
        elif self.current_locale == "jp":
            if "MS Gothic" in available_fonts:
                preferred_font = QFont("MS Gothic", 9)
            else:
                logger.warning("Preferred font 'MS Gothic' not found. Falling back to Arial.")
                preferred_font = QFont("Arial", 9)

        logger.info(f"Using font: {preferred_font.family()}")
        return preferred_font


    def get_languages(self):
        """지원하는 언어 목록 반환"""
        return list(self.fonts.keys())

    def get_font_for_language(self, language):
        """주어진 언어 코드에 맞는 QFont 반환"""
        language = language.lower() if language else ""
        return self.fonts.get(language, self.fonts.get('en', QFont("Arial", 9)))

    def get_play_time_options(self) -> dict:
        """언어별 플레이 타임 옵션 반환"""
        play_time_keys = ["null", "under10", "about15", "about20", "about30", "under60", "over60", "over120", "unknown"]
        return {key: self.translate(f"play_time.{key}") for key in play_time_keys}


#  전역적으로 language_settings 객체를 생성하여 사용 가능
language_settings = LanguageSettings()