from PyQt5.QtWidgets import (
    QApplication, QWidget, QGridLayout, QDialog, QHBoxLayout, QSpacerItem, QSizePolicy, 
    QVBoxLayout, QLineEdit, QComboBox, QLabel, QMessageBox, QStackedWidget, QPushButton, 
    QFileDialog, QRadioButton, QButtonGroup
)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSettings
import sys
from loguru import logger
import os
import multiprocessing
import msvcrt
import traceback

from file_viewer import FileViewer
from search import SearchManager, AdvancedSearchWindow
from database import DatabaseManager
from settings import SettingsManager, open_settings_window
from languages import language_settings
from utils_and_ui import get_icon, create_icon_button


LOCK_FILE = os.path.join(os.path.dirname(sys.executable), "app.lock")
lock_file_handle = None  # 파일 핸들을 전역 변수로 저장

# Loguru 로깅 설정
logger.add(
    "app.log",  # 로그 파일 경로
    rotation="1 MB",  # 로그 파일 크기 제한 (1MB)
    retention="1 days",  # 로그 파일 보관 기간
    level="TRACE",  # 디버깅 메시지 기록
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
)


def exception_hook(exctype, value, traceback_obj):
    """예외 발생 시 호출될 핸들러"""
    # 전체 traceback을 문자열로 변환
    tb_string = ''.join(traceback.format_exception(exctype, value, traceback_obj))
    
    # 로그 파일에 기록
    logger.error(f"Unhandled exception occurred:\n{tb_string}")
    
    # 오류 메시지 박스 표시 (간단한 메시지 + 자세한 로그는 파일로)
    QMessageBox.critical(None, "Critical Error", f"An unexpected error occurred:\n{value}\nCheck the log file for details.")
    
    # 프로그램 종료
    sys.exit(1)

# 전역 예외 훅 설정
sys.excepthook = exception_hook

class MainApp(QWidget):
    def __init__(self):
        try:
            super().__init__()
            self.setWindowTitle("ScenarioIndex")
            # QSettings 인스턴스 생성
            self.settings = QSettings("SilliN", "ScenarioIndex")
            self.scenario_folder_path = self.settings.value("scenario_folder_path", None)
            logger.info(f"Loaded scenario folder path: {self.scenario_folder_path}")

            # 현재 언어 설정 초기화
            self.current_language = self.settings.value("language", "kr") 
            logger.info(f"Current language set to: {self.current_language}")

            # 창 크기 설정
            window_width = 984 if language_settings.current_locale == "kr" else 1074
            self.setGeometry(100, 100, window_width, 600)

            # Database와 Manager 초기화
            self.db = DatabaseManager()
            logger.info("DatabaseManager initialized")
            self.mark_manager = self.db.mark_manager

            # SettingsManager 초기화
            self.settings_manager = SettingsManager(
                settings=self.settings,
                db=self.db,
                file_viewer=None  # file_viewer는 나중에 설정
            )

            # SearchManager 초기화 시 LanguageSettings와 현재 언어 전달
            self.search_manager = SearchManager(
                self.db,
                language_settings, 
                current_language=self.current_language,  # 현재 언어 전달
                folder_path=self.scenario_folder_path
            )
            logger.info("SearchManager initialized.")

            # FileViewer 초기화 (데이터 로드는 초기화 후에 실행)
            self.file_viewer = FileViewer(
                self.scenario_folder_path,
                self.current_language,
                self.search_manager,
                self.db
            )
            logger.info("FileViewer initialized.")

            # FileViewer를 SettingsManager에 연결
            self.settings_manager.file_viewer = self.file_viewer
            # FileViewer와 SettingsManager 연동
            self.settings_manager.set_folder_operations_callback(
                folder_callback=self.update_folder_callback,
                reload_callback=self.reload_files_callback
            )

            # 메인 레이아웃 설정
            self.layout = QVBoxLayout(self)
            self.initialize_ui()

            # SettingsWindow 초기화
            self.settings_window = None  # 설정 창 참조 저장
            logger.info("SettingsWindow initialized.")

            # 폴더 경로 확인 및 파일 로드
            self.check_and_set_folder()
            logger.info("MainApp initialization completed successfully.")

        except Exception as e:
            logger.critical(f"Critical error during MainApp initialization: {e}", exc_info=True)
            QMessageBox.critical(
                None, 
                "Critical Error", 
                f"A critical error occurred during application initialization:\n{e}"
            )
            raise  # 예외를 다시 발생시켜 메인 예외 처리기에서 잡을 수 있도록 함

    def initialize_ui(self):
            """UI 초기화"""
            # 전체 UI를 담을 수직 레이아웃
            main_layout = QVBoxLayout()

            # 검색 관련 컨트롤들을 담을 그리드 레이아웃
            search_grid = QGridLayout()
            search_grid.setContentsMargins(10, 5, 10, 0)

            # 라벨 추가 (첫 번째 행)
            label_keyword = QLabel(language_settings.translate("main.search_keyword"))
            label_field = QLabel(language_settings.translate("main.search_field"))
            label_sort = QLabel(language_settings.translate("main.sort_field"))
            search_grid.addWidget(label_keyword, 0, 2)
            search_grid.addWidget(label_field, 0, 1)
            search_grid.addWidget(label_sort, 0, 0)

            # 정렬 조건
            self.sort_field_dropdown = QComboBox()
            sort_fields = [
                ("modification_time", "main.sort_order_time"),  # 기본값: 최근 파일 순
                ("title", "headers.title"),
                ("author", "headers.author"),
                ("level_min", "main.sort_level_min")
            ]
            for value, key in sort_fields:
                self.sort_field_dropdown.addItem(language_settings.translate(key), value)  # value는 데이터베이스 필드 값
            self.sort_field_dropdown.setFixedWidth(100)
            self.sort_field_dropdown.setCurrentIndex(0)  # "최근 파일 순"으로 초기화
            self.sort_field_dropdown.currentIndexChanged.connect(lambda :self.apply_sort())  # 정렬 조건 변경 시 이벤트 연결
            search_grid.addWidget(self.sort_field_dropdown, 1, 0)

            # 검색 조건
            self.search_field_dropdown = QComboBox()
            search_fields = [
                ("all", "main.search_field_all"),  # (내부값, 번역 키)
                ("title", "headers.title"),
                ("author", "headers.author"),
                ("description", "headers.summary")
            ]
            for value, key in search_fields:
                self.search_field_dropdown.addItem(language_settings.translate(key), value)
            self.search_field_dropdown.setFixedWidth(100)
            search_grid.addWidget(self.search_field_dropdown, 1, 1)

            # 검색어 입력
            self.search_input = QLineEdit()
            self.search_input.setFixedWidth(200)
            search_grid.addWidget(self.search_input, 1, 2)

            # 버튼들을 담을 수평 레이아웃
            button_layout = QHBoxLayout()
            
            # 검색 버튼
            self.search_button = create_icon_button(
                icon_source="search",
                tooltip=language_settings.translate("search.button"),
                on_click=self.perform_search,
                get_icon_func=get_icon
            )
            button_layout.addWidget(self.search_button)

            # 고급 검색 버튼
            self.advanced_search_button = create_icon_button(
                icon_source="filter",  # 또는 적절한 다른 아이콘
                tooltip=language_settings.translate("search.advanced_search"),
                on_click=self.open_advanced_search,
                get_icon_func=get_icon
            )
            button_layout.addWidget(self.advanced_search_button)

            # 새로고침 버튼
            self.refresh_button = create_icon_button(
                icon_source="refresh",  # 적절한 새로고침 아이콘
                tooltip=language_settings.translate("main.refresh_button"),
                on_click=self.refresh_files,
                get_icon_func=get_icon
            )
            button_layout.addWidget(self.refresh_button)

            # 버튼들을 그리드의 오른쪽에 배치
            search_grid.addLayout(button_layout, 0, 3, 2, 1)  # 2행을 모두 차지

            # 빈 공간 추가
            spacer = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
            search_grid.addItem(spacer, 0, 4, 2, 1)  # 2행을 모두 차지

            # 설정 버튼
            self.settings_button = create_icon_button(
                icon_source="settings",
                tooltip=language_settings.translate("settings.button"),  # translate 메서드 활용
                on_click=self.open_settings,
                get_icon_func=get_icon
            )
            search_grid.addWidget(self.settings_button, 0, 5, 2, 1)  # 2행을 모두 차지

            # 그리드 레이아웃을 메인 레이아웃에 추가
            main_layout.addLayout(search_grid)
            main_layout.addWidget(self.file_viewer)
            self.layout.addLayout(main_layout)

    
    def check_and_set_folder(self):
        """ 폴더 설정 후 첫 실행인지 확인하고, 파일 데이터를 초기화"""
        self.scenario_folder_path = self.settings.value("scenario_folder_path", None)

        #  'first_run' 설정값을 확인하여 최초 실행 여부 판단
        first_run = self.settings.value("first_run", "true")

        if first_run == "true":
            logger.info(" First launch after InitialSetupWindow. Updating folder and initializing file viewer.")

            #  최초 실행 시 폴더 업데이트
            success, message = self.settings_manager.update_folder(self.scenario_folder_path)
            if not success:
                logger.error(f" Failed to update folder: {message}")
                return

            #  최초 실행이므로, 이제 'first_run'을 'false'로 설정하여 이후 실행 시 폴더 업데이트 생략
            self.settings.setValue("first_run", "false")

        #  두 번째 실행 이후는 폴더 업데이트 없이 파일 데이터 로드만 수행
        logger.info("Initializing file viewer.")
        self.initialize_file_viewer()

    def initialize_file_viewer(self):
        """파일 뷰어와 관련된 데이터 초기화"""

        # 초기 정렬 필드 설정
        default_sort_field = "modification_time"
        self.file_viewer.sort_by_field(default_sort_field)  # 정렬 후 전체 데이터 로드

    def update_folder_callback(self, folder_path):
        """폴더 경로가 업데이트되었을 때 실행할 콜백"""
        self.scenario_folder_path = folder_path
        self.file_viewer.scenario_folder_path = folder_path
        self.search_manager.set_folder_path(folder_path)

    def reload_files_callback(self):
        """파일 목록을 새로고침할 때 실행할 콜백"""
        self.file_viewer.sort_by_field(self.file_viewer.current_sort_field)

    def refresh_files(self):
        """검색 조건 및 정렬 조건 초기화 후 파일 리스트 새로고침"""

        # 검색 상태 초기화
        self.file_viewer.is_search_active = False
        self.file_viewer.search_results = []  # 검색 결과 초기화
        self.search_input.clear()  # 검색어 초기화
        self.search_field_dropdown.setCurrentIndex(0)  # 검색 조건 초기화
        self.sort_field_dropdown.setCurrentIndex(0)  # 정렬 조건 초기화
        self.initialize_file_viewer()

    def perform_search(self):
        """Perform search based on selected field and search term."""

        if not self.search_manager.folder_path:
            QMessageBox.warning(self, "Search Error", "Folder path is not set. Please select a folder first.")
            return

        search_term = self.search_input.text()
        selected_field = self.search_field_dropdown.currentData()  # ComboBox 내부 값 가져오기

        # "All" 선택 시 None으로 설정
        field = None if selected_field == "all" else selected_field

        try:
            # 검색 수행
            search_results = self.search_manager.basic_search(search_term, field)

            # 검색 결과 처리
            if not search_results:  #  total_results 대신 직접 검색 결과 리스트 확인
                QMessageBox.information(self, "Search Results", "No results found.")
                self.file_viewer.update_table([])  # 테이블 초기화
                return

            # 검색 결과 전달
            self.file_viewer.apply_search_results(search_results)  # 전체 검색 결과 전달
        except ValueError as e:
            # 검색어가 없을 경우 메시지 표시
            QMessageBox.warning(self, "Search Error", str(e))   

    def apply_sort(self):
        try:
            sort_field = self.sort_field_dropdown.currentData()
            if not sort_field:
                logger.error("Invalid sort field selected. No sorting applied.")
                QMessageBox.warning(self, "Sort Error", "Invalid sort field selected. Please try again.")
                return

            # 정렬 필드 확인
            logger.info(f"Applying sort by field: {sort_field}")

            self.file_viewer.sort_by_field(sort_field)
            logger.info(f"Sort applied successfully by field: {sort_field}")
        except Exception as e:
            logger.error("Error while applying sort", exc_info=True)
            QMessageBox.critical(self, "Sort Error", f"An error occurred while applying the sort:\n{e}")

    def open_advanced_search(self):
        """고급 검색 다이얼로그를 열고 검색을 수행하는 메서드"""
        try:
            # 고급 검색 창 생성 및 표시
            advanced_search_dialog = AdvancedSearchWindow(self, search_manager=self.search_manager)
            advanced_search_dialog.searchCompleted.connect(self.file_viewer.apply_search_results)

            if advanced_search_dialog.exec_() == QDialog.Accepted:
                logger.info("Advanced search completed successfully.")
            else:
                logger.info("Advanced search canceled.")

        except Exception as e:
            logger.error(f"An error occurred during advanced search: {str(e)}", exc_info=True)
            # 사용자에게 에러 메시지 표시
            QMessageBox.critical(
                self,
                "Advanced Search Error",  # 제목
                "An error occurred while performing the advanced search. Please try again later."  # 내용
            )
   
    def open_settings(self, *args, **kwargs):
        """설정 창 열기"""
        try:
            # 기존 창이 유효하지 않을 경우 초기화
            if hasattr(self, 'settings_window') and self.settings_window is not None:
                if not self.settings_window.isVisible():
                    self.settings_window = None

            if self.settings_window is None:
                # 새 설정창 생성
                self.settings_window = open_settings_window(
                    db=self.db,
                    file_viewer=self.file_viewer,
                    initial_folder_path=self.scenario_folder_path,
                    settings_manager=self.settings_manager,
                    update_folder_callback=self.update_folder_callback,
                    reload_callback=self.reload_files_callback
                )
                self.settings_window.destroyed.connect(lambda: setattr(self, "settings_window", None))
            else:
                # 이미 창이 열려 있을 경우
                self.settings_window.activateWindow()
                self.settings_window.raise_()
        except RuntimeError:
            # 참조가 유효하지 않을 경우 재설정
            self.settings_window = None
            self.open_settings()
        except Exception as e:
            logger.error("Error in open_settings", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to open settings window:\n{e}")

    def closeEvent(self, event):
        """앱 종료 시 데이터베이스 연결 종료"""
        QApplication.quit()
        event.accept()

class InitialSetupWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("SilliN", "ScenarioIndex")  #  QSettings 직접 사용
        self.setWindowTitle("Initial Setup")
        self.setFixedSize(300,200)

        self.layout = QVBoxLayout(self)
        self.stack = QStackedWidget(self)  # 여러 페이지를 전환할 수 있도록 설정

        # 각 페이지 생성
        self.page_welcome_language = self.create_welcome_language_page()
        self.page_folder = self.create_folder_page()

        # 페이지 스택에 추가
        self.stack.addWidget(self.page_welcome_language)
        self.stack.addWidget(self.page_folder)

        self.layout.addWidget(self.stack)
        self.setLayout(self.layout)

    def create_welcome_language_page(self):
        """언어 선택 페이지 (라디오 버튼 사용)"""
        page = QWidget()
        layout = QVBoxLayout(page)

        label = QLabel("언어를 선택해주세요.\n\n言語を選択してください。")
        
        # 라디오 버튼 생성
        self.radio_kr = QRadioButton("한국어")
        self.radio_jp = QRadioButton("日本語")

        # 버튼 그룹 생성 (하나만 선택되도록 설정)
        self.language_group = QButtonGroup()
        self.language_group.addButton(self.radio_kr)
        self.language_group.addButton(self.radio_jp)

        # 저장된 언어 불러오기 (기본값 "kr")
        selected_language = self.settings.value("language", "kr")

        if selected_language == "kr":
            self.radio_kr.setChecked(True)
        else:
            self.radio_jp.setChecked(True)

        # ✅ 라디오 버튼 클릭 시 언어 변경 (True일 때만 실행)
        def update_language():
            selected_button = self.sender()
            if selected_button.isChecked():  # 선택된 버튼만 실행
                new_locale = "kr" if selected_button == self.radio_kr else "jp"
                language_settings.set_language(new_locale)  # `set_language()` 사용하여 설정 저장
                self.update_ui_texts()

        self.radio_kr.toggled.connect(update_language)
        self.radio_jp.toggled.connect(update_language)

        # 다음 버튼
        next_button = QPushButton("Next")
        next_button.clicked.connect(lambda: self.stack.setCurrentIndex(1))  # 다음 페이지로 이동

        # 레이아웃 배치
        layout.addWidget(label)
        layout.addWidget(self.radio_kr)
        layout.addWidget(self.radio_jp)
        layout.addWidget(next_button)

        page.setLayout(layout)
        return page

    def update_ui_texts(self):
        """UI 텍스트를 현재 선택된 언어로 업데이트"""
        selected_language = self.settings.value("language", "kr")
        
        # 두 번째 페이지의 텍스트 업데이트
        if selected_language == "kr":
            self.folder_select_label.setText("시나리오 폴더를 선택해주세요.")
            self.folder_label.setText("경로:")
            self.select_folder_button.setText("폴더 선택")
        else:
            self.folder_select_label.setText("シナリオフォルダーを選択してください。")
            self.folder_label.setText("パス:")
            self.select_folder_button.setText("フォルダー選択")

    def create_folder_page(self):
        """폴더 선택 페이지"""
        page = QWidget()
        layout = QVBoxLayout(page)

        self.folder_select_label = QLabel()
        self.folder_label = QLabel()
        self.folder_path_display = QLabel()
        self.folder_path_display.setWordWrap(True)
        self.select_folder_button = QPushButton()
        
        # 초기 텍스트 설정
        self.update_ui_texts()

        self.select_folder_button.clicked.connect(self.select_folder)

        # 초기에는 완료 버튼 비활성화
        self.complete_button = QPushButton("Next")
        self.complete_button.setEnabled(False)  # 폴더 선택 전까지 비활성화
        self.complete_button.clicked.connect(self.save_settings)

        # 경로 레이블과 경로를 가로로 배치하기 위한 수평 레이아웃
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.folder_label)
        path_layout.addWidget(self.folder_path_display)
        path_layout.addStretch()  # 남는 공간을 채움

        layout.addWidget(self.folder_select_label)
        layout.addLayout(path_layout)
        layout.addWidget(self.select_folder_button)
        layout.addWidget(self.complete_button)

        page.setLayout(layout)
        return page

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Scenario Folder")

        if not folder_path:
            return

        self.settings.setValue("scenario_folder_path", folder_path)
        self.folder_path_display.setText(folder_path)  # 경로만 업데이트
        self.complete_button.setEnabled(True)

    def save_settings(self):
        """설정 저장 후 프로그램 자동 재시작"""
        # 'first_run'을 'true'로 설정하여, MainApp에서 최초 실행 여부를 확인할 수 있도록 함
        self.settings.setValue("first_run", "true")

        # 프로그램 자동 재시작
        if language_settings.current_locale == "kr":
            QMessageBox.information(self, "설정 완료", "설정이 적용됩니다. 프로그램이 재시작됩니다.")
        elif language_settings.current_locale == "jp":
            QMessageBox.information(self, "設定完了", "設定が適用されます。プログラムが再起動します。")

        self.close()

        python = sys.executable
        os.execl(python, python, *sys.argv)  # 프로그램 재시작

@logger.catch
def main():
    """프로그램의 진입점"""
    logger.info("Starting application...")

    # QApplication 생성
    app = QApplication(sys.argv)

    #  QSettings에서 저장된 언어를 먼저 불러오기
    settings = QSettings("SilliN", "ScenarioIndex")
    selected_language = settings.value("language", "kr")  # 기본값 'KR'

    #  LanguageSettings에 언어 동기화
    language_settings.current_locale = selected_language  
    logger.info(f" Current language set to: {language_settings.current_locale}")

    #  프로그램 전체 폰트 설정 (언어별 적용)
    app.setFont(language_settings.get_current_font())  
    logger.info(f"Font applied for language: {language_settings.current_locale}")

    #  실행 파일이 있는 폴더를 기준으로 아이콘 경로 설정
    base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(".")
    icon_path = os.path.join(base_path, "assets", "icon.ico")

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))  #  모든 창에 동일한 아이콘 적용
        logger.info(f" Icon applied: {icon_path}")
    else:
        logger.warning(f" Icon not found: {icon_path}")

    try:
        # MainApp 실행
        main_app = MainApp()
        main_app.show()

        # Qt 메인 루프 실행
        sys.exit(app.exec_())
    except Exception as e:
        # 메인 루프에서 발생한 예외를 로깅하고 사용자에게 알림
        logger.critical(" Critical error during application startup", exc_info=True)
        QMessageBox.critical(None, "Critical Error", f"Failed to start application:\n{e}")
        sys.exit(1)

def is_another_instance_running():
    """Windows에서 중복 실행 방지 (파일 잠금 방식)"""
    global lock_file_handle
    try:
        lock_file_handle = open(LOCK_FILE, "w")  # 파일 열기
        msvcrt.locking(lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)  # 파일 잠금 시도 (비블로킹)
        return False  # 실행 가능
    except OSError:
        return True  # 이미 실행 중

if __name__ == "__main__":
    multiprocessing.freeze_support()

    if is_another_instance_running():
        logger.error("Another instance is already running. Exiting...")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setFont(language_settings.get_current_font())

    #  실행 파일이 있는 폴더를 기준으로 아이콘 경로 설정
    base_path = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.abspath(".")
    icon_path = os.path.join(base_path, "assets", "icon.ico")

    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))  #  모든 창에 동일한 아이콘 적용
        logger.info(f"Global icon applied: {icon_path}")
    else:
        logger.warning(f"Icon not found: {icon_path}")

    settings = QSettings("SilliN", "ScenarioIndex")

    if not settings.value("scenario_folder_path"):
        logger.info("First-time setup required. Launching InitialSetupWindow...")
        setup_window = InitialSetupWindow()
        setup_window.show()
        sys.exit(app.exec_())  # 초기 설정 후 종료 → 다시 실행해야 함

    logger.info("Launching main application.")
    main_window = MainApp()
    main_window.show()

    sys.exit(app.exec_())
