from PyQt5.QtWidgets import (
    QWidget, QTableWidget, QFileDialog, QTableWidgetItem, QHBoxLayout, QHeaderView, QSpacerItem,
    QVBoxLayout, QLabel, QGridLayout, QPushButton, QComboBox, QMessageBox, QTextBrowser, QDialog, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QIcon, QColor
from PyQt5.QtCore import QSettings, Qt, QSize
from loguru import logger
from languages import language_settings
from database import TagManager, MarkManager, LimitManager, TimeManager, CompManager

# 기본 언어 설정
DEFAULT_LANGUAGE = "kr"


def open_settings_window(db, file_viewer, initial_folder_path, settings_manager, update_folder_callback, reload_callback):
    settings_window = SettingsWindow(
        db=db,
        settings_manager=settings_manager,
        file_viewer=file_viewer,
        initial_folder_path=initial_folder_path
    )

    # 창 플래그 설정
    settings_window.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

    # SettingsManager를 통해 MainApp의 콜백 설정
    settings_manager.set_folder_operations_callback(
        folder_callback=update_folder_callback,
        reload_callback=reload_callback
    )

    # 창 반환 전에 상태 확인
    if not settings_window:
        raise RuntimeError("Failed to create SettingsWindow.")
    
    settings_window.show()
    return settings_window

class SettingsWindow(QWidget): 
    def __init__(self, db, file_viewer, settings_manager, initial_folder_path=None):
        super().__init__()
        self.db = db
        self.file_viewer = file_viewer
        self.settings_manager = settings_manager

        self.folder_path = initial_folder_path
        self.settings = QSettings("SilliN", "ScenarioIndex")
        self.current_language = language_settings.current_locale

        self.tag_management_window = None
        self.mark_management_window = None
        self.data_reset_window = None
        self.about_window = None

        self.tag_manager = TagManager(self.db)
        self.mark_manager = MarkManager(self.db)
        self.limit_manager = LimitManager(self.db)
        self.time_manager = TimeManager(self.db)
        self.comp_manager = CompManager(self.db)

        self.init_ui()

    def create_button(self, text_key, callback):
        """버튼 생성 헬퍼 메서드"""
        button = QPushButton(language_settings.translate(text_key))
        button.clicked.connect(lambda: callback())
        self.layout.addWidget(button)

    
    def init_ui(self):
        """UI 초기화"""
        self.setWindowTitle(language_settings.translate("settings.button"))

        self.layout = QVBoxLayout(self)

        # 폴더 선택 버튼
        self.create_button("settings.select_folder", self.select_folder)

        # 폴더 재스캔 버튼
        self.create_button(
            "settings.rescan_button", 
            lambda: self.settings_manager.rescan_files(self.folder_path)  # 래퍼 함수
        )

        # 태그 관리 버튼
        self.create_button("settings.tag_management", self.open_tag_management)

        # 마크 관리 버튼
        self.create_button("settings.mark_management", self.open_mark_management)

        # 데이터 리셋 버튼
        self.create_button("settings.data_reset", self.open_data_reset)

        # 제작자 정보 버튼
        self.create_button("settings.about", self.open_about)

        self.setLayout(self.layout)

    def open_sub_window(self, window_attr, window_class, *args):
        """서브 윈도우를 열거나 기존 창을 활성화"""
        if getattr(self, window_attr, None) is None or not getattr(self, window_attr).isVisible():
            setattr(self, window_attr, window_class(*args))
            window = getattr(self, window_attr)
            window.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
            window.show()
        else:
            window = getattr(self, window_attr)
            window.raise_()
            window.activateWindow()
    
    def select_folder(self, *args, **kwargs):
        """폴더 선택 창을 띄우고 경로 설정 및 파일 목록 업데이트"""
        try:
            folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")

            if not folder_path:
                QMessageBox.information(self, "No Folder Selected", "No folder was selected.")
                logger.warning("Folder selection cancelled by the user.")
                return

            # SettingsManager의 update_folder 메서드 호출
            success, message = self.settings_manager.update_folder(folder_path)

            if success:
                QMessageBox.information(self, "Success", "Folder updated and files scanned successfully.")
            else:
                QMessageBox.critical(self, "Error", message)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to select folder: {str(e)}")
            logger.error(f"Error during folder selection: {e}", exc_info=True)

    def open_tag_management(self):
        """태그 관리 창 열기"""
        self.open_sub_window('tag_management_window', TagManagementWindow, self, self.db)

    def open_mark_management(self):
        """마크 관리 창 열기"""
        self.open_sub_window('mark_management_window', MarkManagementWindow, self)

    def open_data_reset(self):
        """데이터 리셋 창 열기"""
        self.open_sub_window('data_reset_window', DataResetWindow, self)

    def open_about(self):
        """제작자 정보 창 열기"""
        self.open_sub_window('about_window', AboutWindow, self)

    def on_data_reset(self):
        """데이터 리셋 완료 후 처리"""
        QMessageBox.information(
            self,
            language_settings.translate("settings.reset_done_title"),
            language_settings.translate("settings.reset_done_message")
        )
        # FileViewer 파일 목록 새로고침 (필요 시)
        if hasattr(self.file_viewer, "load_file_list"):
            self.file_viewer.load_file_list()

class SettingsManager:
    is_restarting = False
    def __init__(self, settings, db, file_viewer):
        self.settings = settings
        self.db = db
        self.file_viewer = file_viewer
        self.folder_callback = None
        self.reload_callback = None
    
    def set_folder_operations_callback(self, folder_callback=None, reload_callback=None):
        """폴더 작업 관련 콜백 설정"""
        self.folder_callback = folder_callback
        self.reload_callback = reload_callback

    def update_folder(self, folder_path):
        """
        폴더 경로를 업데이트하고 데이터베이스 및 파일 목록을 갱신합니다.
        """
        try:
            self.settings.setValue("scenario_folder_path", folder_path)
            logger.info(f"New folder path set: {folder_path}")

            # 폴더 콜백 실행
            if self.folder_callback:
                self.folder_callback(folder_path)

            # 데이터베이스 업데이트
            self.db.update_files_for_folder(folder_path)

            # 파일 목록 새로고침
            if self.reload_callback:
                self.reload_callback()

            return True, "Folder updated successfully."

        except Exception as e:
            logger.error(f"Error during folder update: {e}", exc_info=True)
            return False, f"Failed to update folder: {str(e)}"

    def rescan_files(self, folder_path):
        """현재 폴더를 재스캔"""
        logger.info(f"Rescanning folder: {folder_path}")
        if folder_path:
            self.db.update_files_for_folder(folder_path)
            self.file_viewer.load_file_list()
            QMessageBox.information(None, "Rescan Complete", "Files have been rescanned successfully.")
        else:
            QMessageBox.warning(None, "No Folder", "Please set a folder path first.")

class TagManagementWindow(QWidget):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.current_language = parent.current_language  # 현재 언어

        self.setWindowTitle(language_settings.translate("tag_management.title"))
        self.db = db
        self.pending_deletions = []  # 삭제 대기 목록 초기화
        self.original_tags = {}  # 원래 태그 키 저장용 딕셔너리
    
        self.layout = QHBoxLayout(self)

        # 태그 목록을 위한 QTableWidget 생성
        self.tag_table = QTableWidget()
        self.tag_table.setColumnCount(2)
        self.tag_table.setHorizontalHeaderLabels([
            language_settings.translate("tag_management.tag_key_header"),
            language_settings.translate("tag_management.translation_header"),
        ])
        self.tag_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.tag_table)

        # 버튼을 위한 수직 레이아웃 추가
        button_layout = QVBoxLayout()

        # 태그 추가 버튼
        self.add_button = QPushButton(language_settings.translate("tag_management.add_tag"))
        self.add_button.clicked.connect(lambda: self.add_tag())
        button_layout.addWidget(self.add_button)

        # 태그 삭제 버튼
        self.delete_button = QPushButton(language_settings.translate("tag_management.delete_tag"))
        self.delete_button.clicked.connect(lambda: self.delete_tag())
        button_layout.addWidget(self.delete_button)

        # 전체 삭제 버튼
        self.delete_all_button = QPushButton(language_settings.translate("tag_management.delete_all_tags"))
        self.delete_all_button.clicked.connect(lambda: self.delete_all_tags())
        button_layout.addWidget(self.delete_all_button)

        # 변경 등록 버튼
        self.register_button = QPushButton(language_settings.translate("save_changes"))
        self.register_button.clicked.connect(lambda: self.register_changes())
        button_layout.addWidget(self.register_button)

        # 취소 버튼
        self.cancel_button = QPushButton(language_settings.translate("cancel"))
        self.cancel_button.clicked.connect(lambda: self.cancel_changes())
        button_layout.addWidget(self.cancel_button)

        # 레이아웃 설정
        self.layout.addLayout(button_layout)
        self.setLayout(self.layout)

        # 초기화
        self.load_tags()

        # 더블 클릭 시 수정 모드 전환
        self.tag_table.itemDoubleClicked.connect(self.edit_tag)

    
    def load_tags(self):
        """현재 태그 목록을 언어 설정에 맞게 불러옴"""
        self.tag_table.setRowCount(0)  # 기존 데이터 제거
        self.db.cursor.execute("SELECT tag, {}_translation FROM tags_list".format(self.parent().current_language))
        tags = self.db.cursor.fetchall()  # 태그 목록 가져오기

        for tag_key, tag_name in tags:  # tags는 (태그, 번역) 튜플의 리스트
            row_position = self.tag_table.rowCount()
            self.tag_table.insertRow(row_position)  # 새로운 행 추가
            self.tag_table.setItem(row_position, 0, QTableWidgetItem(tag_key))  # 첫 번째 열에 태그 키
            self.tag_table.setItem(row_position, 1, QTableWidgetItem(tag_name))  # 두 번째 열에 번역

            # 원래 태그 키 저장
            self.original_tags[row_position] = tag_key

            # 디폴트 태그는 배경색 설정 및 수정 불가
            if tag_key in self.parent().db.tag_manager.default_tags:
                tag_key_item = self.tag_table.item(row_position, 0)
                tag_name_item = self.tag_table.item(row_position, 1)

                # 연노랑색으로 배경색 설정 (RGB 값으로 설정)
                if tag_key_item and tag_name_item:  # 아이템이 존재하는지 확인
                    tag_key_item.setBackground(QColor(255, 255, 224))  # 연노랑색
                    tag_name_item.setBackground(QColor(255, 255, 224))  # 연노랑색

                    # 수정 불가 설정
                    tag_key_item.setFlags(tag_key_item.flags() & ~Qt.ItemIsEditable)
                    tag_name_item.setFlags(tag_name_item.flags() & ~Qt.ItemIsEditable)

    
    def add_tag(self):
        """새 태그 추가"""
        row_position = self.tag_table.rowCount()  # 마지막 행의 위치
        self.tag_table.insertRow(row_position)
        self.tag_table.setItem(row_position, 0, QTableWidgetItem("new_tag"))  # 기본값으로 'new_tag' 입력
        self.tag_table.setItem(row_position, 1, QTableWidgetItem(""))  # 번역은 빈칸으로 설정
        self.tag_table.editItem(self.tag_table.item(row_position, 0))  # 첫 번째 열에 포커스 맞추기

        # 새로운 행을 보이도록 스크롤
        self.tag_table.scrollToBottom()  # 테이블을 스크롤하여 하단으로 이동

    
    def edit_tag(self, item):
        """태그 수정 모드로 전환"""
        row = item.row()
        tag_key = self.tag_table.item(row, 0).text()  # 현재 태그 키

        # 디폴트 태그일 경우 수정 불가 경고
        if tag_key in self.parent().db.tag_manager.default_tags:
            QMessageBox.warning(self, "Warning", "Default tags cannot be modified.")
            return

        # 태그 키와 번역 수정
        if item.column() == 0:  # Tag Key 열에서 더블 클릭한 경우
            self.tag_table.editItem(self.tag_table.item(row, 0))  # Tag Key 열을 편집 가능 상태로 변경
        elif item.column() == 1:  # Translation 열에서 더블 클릭한 경우
            self.tag_table.editItem(self.tag_table.item(row, 1))  # Translation 열을 편집 가능 상태로 변경

    
    def delete_tag(self):
        """선택된 태그 삭제"""
        selected_row = self.tag_table.currentRow()
        if selected_row >= 0:
            tag_key = self.tag_table.item(selected_row, 0).text()  # 선택된 태그의 키
            if tag_key in self.parent().db.tag_manager.default_tags:
                QMessageBox.warning(self, "Warning", "Default tags cannot be deleted.")
            else:
                # 대기 리스트에 추가하기 전에 즉시 목록에서 제거
                self.tag_table.removeRow(selected_row)  # 태그를 목록에서 제거
                self.pending_deletions.append(tag_key)  # 대기 리스트에 추가
        else:
            QMessageBox.warning(self, "Warning", "No tag selected.")

    
    def delete_all_tags(self):
        """모든 사용자 정의 태그 삭제"""
        confirm = QMessageBox.question(self, "Confirm Delete", "Are you sure you want to delete all custom tags?", 
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm == QMessageBox.Yes:
            # 목록에서 사용자 정의 태그 제거
            for row in range(self.tag_table.rowCount() - 1, -1, -1):  # 뒤에서부터 삭제
                tag_key = self.tag_table.item(row, 0).text()  # 태그 키 가져오기
                if tag_key not in self.parent().db.tag_manager.default_tags:
                    self.tag_table.removeRow(row)  # 목록에서 사용자 정의 태그 제거
                    self.pending_deletions.append(tag_key)  # 대기 리스트에 추가
            QMessageBox.information(self, "Success", "All custom tags have been marked for deletion.")

    
    def register_changes(self):
        """변경 사항을 등록하여 데이터베이스에 저장"""

        # 삭제된 태그 처리
        for tag_key in self.pending_deletions:
            self.db.tag_manager.delete_custom_tag(tag_key)  # 태그 테이블에서 삭제

        # 변경된 태그가 있는지 여부 확인
        has_changes = False

        # 새 태그와 수정된 태그를 추가 및 업데이트
        for row in range(self.tag_table.rowCount()):
            current_tag = self.tag_table.item(row, 0).text().strip()
            current_translation = self.tag_table.item(row, 1).text().strip()
            original_tag = self.original_tags.get(row)

            # 새로 추가된 태그
            if original_tag is None and current_tag and current_translation:
                logger.debug(f"Adding new tag: {current_tag} - {current_translation}")
                self.db.tag_manager.add_custom_tag(current_tag, current_translation)
                has_changes = True  # 변경 발생

            # 태그 키가 변경된 경우
            elif original_tag and current_tag != original_tag and current_translation:
                logger.debug(f"Updating tag key: {original_tag} -> {current_tag}")
                self.db.tag_manager.update_custom_tag(original_tag, current_tag, current_translation)
                self.db.tag_manager.update_file_tags_after_changes(original_tag, current_tag)
                has_changes = True  # 변경 발생

            # 번역만 수정된 경우
            elif original_tag and current_tag == original_tag and current_translation and current_translation != self.db.tag_manager.get_tag_translation(original_tag):
                logger.debug(f"Updating tag translation: {current_tag} - {current_translation}")
                self.db.tag_manager.update_custom_tag(current_tag, current_tag, current_translation)
                has_changes = True  # 변경 발생

        # 변경사항이 있을 때만 UI 업데이트 및 메시지 출력
        if has_changes:
            if hasattr(self.parent(), 'file_viewer'):
                self.parent().file_viewer.load_file_list()

            # 삭제 리스트와 원래 태그 목록 초기화
            self.pending_deletions.clear()
            self.original_tags.clear()

            QMessageBox.information(self, "Success", "Changes have been successfully saved.")
            self.load_tags()  # 태그 목록 다시 로드


    def cancel_changes(self):
        """변경 사항을 저장하지 않고 창을 닫음"""
        self.close()

class MarkManagementWindow(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.current_language = parent.current_language
        self.mark_manager = parent.mark_manager
        self.setWindowTitle(language_settings.translate("mark_management.title"))

        self.layout = QVBoxLayout(self)
        self.grid_layout = QGridLayout()  # 그리드 레이아웃 생성
        self.layout.addLayout(self.grid_layout)

        self.mark_buttons = []  # 버튼을 저장할 리스트
        self.selected_mark = None  # 현재 선택된 마크
        self.temp_image_path = None  # 임시 이미지 경로 추가

        # 미리보기 레이블을 위한 수평 레이아웃
        self.preview_layout = QVBoxLayout()

        # 문자 표시 레이블
        self.preview_label = QLabel("Image size: 32x32 (png, gif, ico)")  # 미리보기 레이블 수정
        self.preview_label.setAlignment(Qt.AlignCenter)  # 레이블 가운데 정렬
        self.preview_layout.addWidget(self.preview_label)

        # 현재 아이콘과 임시 아이콘을 보여줄 레이아웃
        self.icon_layout = QHBoxLayout()

        self.preview_icon = QLabel()  # 선택된 마크를 보여줄 추가 레이블
        self.preview_icon.setFixedSize(32, 32)
        self.preview_icon.setAlignment(Qt.AlignCenter)
        self.icon_layout.addWidget(self.preview_icon)  # 현재 아이콘 레이아웃에 추가

        self.preview_temp_icon = QLabel()  # 임시 아이콘을 보여줄 추가 레이블
        self.preview_temp_icon.setFixedSize(32, 32)
        self.preview_temp_icon.setAlignment(Qt.AlignCenter)
        self.icon_layout.addWidget(self.preview_temp_icon)  # 임시 아이콘 레이아웃에 추가

        self.preview_layout.addLayout(self.icon_layout)  # 아이콘 레이아웃 추가
        self.layout.addLayout(self.preview_layout)  # 미리보기 레이아웃 추가

        # 마크 버튼 생성
        self.create_mark_buttons()

        # 변경 버튼
        self.change_image_button = QPushButton(language_settings.translate("mark_management.change_mark_image"))
        self.change_image_button.clicked.connect(lambda: self.change_mark_image())
        self.layout.addWidget(self.change_image_button)

        # 저장 버튼
        self.save_changes_button = QPushButton(language_settings.translate("save_changes"))
        self.save_changes_button.clicked.connect(lambda: self.save_changes())
        self.layout.addWidget(self.save_changes_button)

        # 취소 버튼
        self.cancel_button = QPushButton(language_settings.translate("cancel"))
        self.cancel_button.clicked.connect(lambda: self.cancel_changes())
        self.layout.addWidget(self.cancel_button)

        self.setLayout(self.layout)

    
    def create_mark_buttons(self):
        """마크 버튼을 6x5 그리드 형식으로 생성 및 이미지 설정"""
        for i in range(1, 31):  # 01부터 30까지
            mark_name = f"mark{i:02d}"
            button = QPushButton()  # 텍스트 없이 버튼 생성
            button.setFixedSize(32, 32)  # 버튼 크기를 32x32로 설정
            button.clicked.connect(lambda _, m=mark_name: self.select_mark(m))  # 버튼 클릭 시 선택 기능
            self.mark_buttons.append(button)

            # 사용자 마크 이미지 우선 적용
            mark_image = self.mark_manager.get_mark_image(mark_name)

            # 이미지가 없으면 기본 마크로 대체
            if mark_image is None or mark_image.isNull():
                mark_image = self.mark_manager.get_mark_image("mark00")

            # 최종적으로 마크 이미지가 있으면 아이콘 설정, 없으면 버튼 비활성화
            if mark_image and not mark_image.isNull():
                button.setIcon(QIcon(mark_image.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                button.setIconSize(QSize(32, 32))  # 아이콘 크기 설정
            else:
                button.setEnabled(False)  # 이미지가 없으면 버튼 비활성화

            row = (i - 1) // 6  # 행 계산
            col = (i - 1) % 6   # 열 계산
            self.grid_layout.addWidget(button, row, col)  # 그리드 레이아웃에 버튼 추가

    
    def select_mark(self, mark_name):
        """선택된 마크를 설정"""
        self.selected_mark = mark_name
        self.update_preview()  # 미리보기 업데이트

    
    def update_preview(self):
        """선택된 마크의 이미지를 미리보기 레이블에 표시"""
        if self.selected_mark:
            # MarkManager를 통해 마크 이미지 가져오기
            mark_image = self.mark_manager.get_mark_image(self.selected_mark)

            if mark_image and not mark_image.isNull():
                self.preview_icon.setPixmap(mark_image.scaled(32, 32, Qt.KeepAspectRatio))
                self.preview_temp_icon.setPixmap(mark_image.scaled(32, 32, Qt.KeepAspectRatio))

                # 선택된 버튼의 아이콘을 임시 이미지로 설정
                if self.temp_image_path:
                    temp_pixmap = QPixmap(self.temp_image_path)
                    self.preview_temp_icon.setPixmap(temp_pixmap.scaled(32, 32, Qt.KeepAspectRatio))
            else:
                self.preview_label.setText("No image found for this mark.")

    
    def change_mark_image(self):
        """이미지 파일을 선택하여 마크 이미지 변경"""
        if not self.selected_mark:
            QMessageBox.warning(self, "Warning", "No mark selected.")
            return

        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Mark Image", "", "Images (*.png *.gif *.ico);;All Files (*)", options=options)

        if file_name:
            self.temp_image_path = file_name
            self.update_preview()

    
    def save_changes(self):
        """변경 사항을 데이터베이스에 저장"""
        if self.selected_mark and self.temp_image_path:
            self.mark_manager.set_mark_image(self.selected_mark, self.temp_image_path)

            QMessageBox.information(self, "Success", f"Mark image for {self.selected_mark} has been changed.")

            # 마크 버튼 새로고침 (업데이트된 이미지 반영)
            self.create_mark_buttons()
            self.update_preview()  # 변경된 이미지가 바로 반영되도록

            self.temp_image_path = None  # 임시 경로 초기화
            self.close()  # 창 닫기
        else:
            QMessageBox.warning(self, "Warning", "No changes to save.")

    
    def cancel_changes(self):
        """변경 사항을 저장하지 않고 창을 닫음"""
        self.temp_image_path = None  # 임시 이미지 경로 초기화
        self.close()

class AboutWindow(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.current_language = parent.current_language
        
        self.setWindowTitle(language_settings.translate("settings.about"))

        self.layout = QVBoxLayout(self)

        self.info_label = QLabel(self.get_program_info())
        self.layout.addWidget(self.info_label)

        button_layout = QHBoxLayout()

        button_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.license_button = QPushButton(language_settings.translate("settings.license"))
        self.license_button.clicked.connect(self.show_license)
        button_layout.addWidget(self.license_button)

        button_layout.addItem(QSpacerItem(40, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))


        self.credits_button = QPushButton(language_settings.translate("settings.credits"))
        self.credits_button.clicked.connect(self.get_credits_info)
        button_layout.addWidget(self.credits_button)

        button_layout.addItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.layout.addLayout(button_layout)
        self.setLayout(self.layout)  

    def get_program_info(self):
        if self.current_language == "kr":
            return (
                "<h2>ScenarioIndex</h2>"
                "<p><b>버전:</b> 0.1.2</p>"
                "<b>제작자:</b> SilliN<br>"
                "<b>이메일:</b> snail0line@gmail.com<br>"
                "<b>GitHub:</b> <a href='https://github.com/snail0line/ScenarioIndex'>ScenarioIndex</a>"
            )
        elif self.current_language == "jp":        
            return (
                "<h2>ScenarioIndex</h2>"
                "<p><b>バージョン:</b> 0.1.2</p>"
                "<b>制作者:</b> SilliN<br>"
                "<b>メール:</b> snail0line@gmail.com<br>"
                "<b>GitHub:</b> <a href='https://github.com/snail0line/ScenarioIndex'>ScenarioIndex</a>"
            )

    def get_credits_info(self):
        """제작자 정보 (크레딧)"""
        if self.current_language == "kr":
            credits_text = (
            "<h3>사용 소재 출처</h3>"

            "<div><b>소스 코드:</b></div>"
            "<div style='margin-left: 15px;'>"
            "<p>이 프로그램은 <a href='https://github.com/snail0line/ScenarioIndex'>GitHub 저장소</a>에서 확인할 수 있습니다.</p>"
            "<p><a href='https://bitbucket.org/k4nagatsuki/cardwirthpy-reboot'>CardWirthPy</a>의 코드를 일부 사용했습니다. (MIT License)</p>"
            "</div>"
            "<br>"
            "<div><b>아이콘:</b></div>"
            "<div style='margin-left: 15px;'>"
            "<p><a href='https://bitbucket.org/k4nagatsuki/cwxeditor/'>CWXEditor</a> (Public Domain)</p>"
            "<p><a href='https://bitbucket.org/k4nagatsuki/cardwirthpy-reboot/wiki/Home'>CardWirthPy</a> (Public Domain)</p>"
            "<p><a href='https://dot-illust.net/'>Dot-Illust.net</a></p>"
            "<p><a href='https://opengameart.org/node/121232'>AntumDeluge</a> (CC0)</p>"
            "</div>"
        )
        elif self.current_language == "jp":
            credits_text = (
                "<h3>使用素材の出典</h3>"

                "<div><b>ソースコード:</b></div>"
                "<div style='margin-left: 15px;'>"
                "<p>このプログラムは<a href='https://github.com/snail0line/ScenarioIndex'>GitHubリポジトリ</a>で確認できます。</p>"
                "<p><a href='https://bitbucket.org/k4nagatsuki/cardwirthpy-reboot'>CardWirthPy</a>のコードを一部使用しています。(MITライセンス)</p>"
                "</div>"
                "<br>"
                "<div><b>アイコン:</b></div>"
                "<div style='margin-left: 15px;'>"
                "<p><a href='https://bitbucket.org/k4nagatsuki/cwxeditor/'>CWXEditor</a> (Public Domain)</p>"
                "<p><a href='https://bitbucket.org/k4nagatsuki/cardwirthpy-reboot/wiki/Home'>CardWirthPy</a> (Public Domain)</p>"
                "<p><a href='https://dot-illust.net/'>Dot-Illust.net</a></p>"
                "<p><a href='https://opengameart.org/node/121232'>AntumDeluge</a> (CC0)</p>"
                "</div>"
            )

        credits_window = QDialog(self)
        credits_window.setWindowTitle(language_settings.translate("settings.credits"))
        credits_window.setFixedSize(600, 400)
        credits_window.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        layout = QVBoxLayout(credits_window)

        credits_widget = QTextBrowser()
        credits_widget.setOpenExternalLinks(True)
        credits_widget.setHtml(credits_text)  # ✅ HTML 형식으로 표시 가능
        layout.addWidget(credits_widget)

        close_button = QPushButton(language_settings.translate("close"))
        close_button.clicked.connect(credits_window.close)
        layout.addWidget(close_button)

        credits_window.setLayout(layout)
        credits_window.exec_()

    def show_license(self):
        """라이선스 정보를 새로운 창에서 표시"""
        if self.current_language == "kr":
            license_text = (
                "<h2>라이선스 정보</h2>"
                "<p>이 프로그램은 <b>GPL-3.0</b> 라이센스로 배포됩니다."
                "<br>⚠ 중요: 이 프로그램은 비상업적 용도로만 사용해야 합니다."
                "<br>본 프로그램의 어떠한 부분도 상업적으로 이용(판매, 유료 배포, 유료 서비스 포함)할 수 없습니다.</p>"
                
                "<h3>프로그램 라이선스</h3>"
                "<p>이 프로그램은 GNU General Public License v3.0(GPL-3.0)을 따릅니다.<br>"
                "이 라이선스에 따라, 사용자는 프로그램을 자유롭게 사용, 수정, 배포할 수 있으며, "
                "<br>수정된 버전을 배포할 경우 동일한 GPL-3.0 라이선스를 따라야 합니다.<br>"
                "보다 자세한 내용은 <b>LICENSE.txt</b> 파일을 참고해 주세요.</p>"

                "<h3>소스 코드</h3>"
                "<p>이 프로그램의 소스 코드는 <a href='https://github.com/snail0line/ScenarioIndex'>GitHub 저장소</a>에서 확인할 수 있습니다.</p>"
            )

        elif self.current_language == "jp":
            license_text = (
                "<h2>ライセンス情報</h2>"
                "<p>このプログラムは<b>GPL-3.0</b>ライセンスで配布されています。</p>"
                "<p>⚠ 重要: 本プログラムは非商用目的でのみ使用する必要があります。</p>"
                "<p>本プログラムのいかなる部分も、商用利用（販売、有料配布、有料サービスを含む）は禁止されています。</p>"

                "<h3>プログラムのライセンス</h3>"
                "<p>このプログラムは GNU General Public License v3.0(GPL-3.0) に基づいています。<br>"
                "このライセンスにより、ユーザーはプログラムを自由に使用、改変、配布することができ、"
                "<br>改変したバージョンを配布する場合は同じGPL-3.0ライセンスを適用する必要があります。<br>"
                "詳しい情報は<b>LICENSE.txt</b>をご確認ください。</p>"

                "<h3>ソースコード</h3>"
                "<p>このプログラムのソースコードは<a href='https://github.com/snail0line/ScenarioIndex'>GitHubリポジトリ</a>で確認できます。</p>"
            )


        license_window = QDialog(self)
        license_window.setWindowTitle(language_settings.translate("settings.license"))
        license_window.setFixedSize(600, 400)
        license_window.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        layout = QVBoxLayout(license_window)

        license_widget = QTextBrowser()
        license_widget.setOpenExternalLinks(True)
        license_widget.setHtml(license_text)  # ✅ HTML 형식으로 표시 가능
        layout.addWidget(license_widget)

        close_button = QPushButton(language_settings.translate("close"))
        close_button.clicked.connect(license_window.close)
        layout.addWidget(close_button)

        license_window.setLayout(layout)
        license_window.exec_()

class DataResetWindow(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.current_language = parent.current_language
        self.db = parent.db  # DatabaseManager 참조

        self.setWindowTitle(language_settings.translate("settings.data_reset"))
        self.setMinimumWidth(200)

        # 메인 레이아웃
        self.layout = QVBoxLayout(self)

        # 설명 라벨
        description_label = QLabel(language_settings.translate("settings.data_reset_description"))
        self.layout.addWidget(description_label)

        # 드롭다운 생성
        self.reset_options = QComboBox()
        self.reset_options.addItem(language_settings.translate("settings.reset_mark"), "mark")
        self.reset_options.addItem(language_settings.translate("settings.reset_limit"), "limit")
        self.reset_options.addItem(language_settings.translate("settings.reset_time"), "time")        
        self.reset_options.addItem(language_settings.translate("settings.reset_tag"), "tag")
        self.reset_options.addItem(language_settings.translate("settings.reset_comp"), "comp")  
        self.reset_options.addItem(language_settings.translate("settings.reset_all"), "all")
        self.layout.addWidget(self.reset_options)

        # 버튼 레이아웃
        button_layout = QHBoxLayout()

        # 확인 버튼
        confirm_button = QPushButton(language_settings.translate("confirm"))
        confirm_button.clicked.connect(lambda :self.confirm_reset())
        button_layout.addWidget(confirm_button)

        # 취소 버튼
        cancel_button = QPushButton(language_settings.translate("cancel"))
        cancel_button.clicked.connect(lambda :self.close())
        button_layout.addWidget(cancel_button)

        self.layout.addLayout(button_layout)

    
    def confirm_reset(self):
        """선택된 리셋 작업을 수행"""
        selected_option = self.reset_options.currentData()
        logger.info(f"Reset operation selected: {selected_option}")
        if selected_option == "limit":
            self.reset_limit()
        elif selected_option == "mark":
            self.reset_mark()
        elif selected_option == "tag":
            self.reset_tag()
        elif selected_option == "time":
            self.reset_time()
        elif selected_option == "comp":
            self.reset_comp()            
        elif selected_option == "all":
            self.reset_all()

        # 리셋 완료 후 부모에게 알림
        self.parent.on_data_reset()
        logger.info("Reset operation completed successfully.")
        self.close()

    
    def refresh_file_viewer(self):
        """FileViewer의 파일 목록을 새로고침"""
        if hasattr(self.parent, "update_table"):
            self.parent.update_table(self.parent.file_data)

    def reset_limit(self):
        self.db.limit_manager.reset_limits()

    def reset_mark(self):
        self.db.mark_manager.reset_marks()

    def reset_tag(self):
        self.db.tag_manager.reset_file_tags()

    def reset_time(self):
        self.db.time_manager.reset_play_times()

    def reset_comp(self):
        self.db.comp_manager.reset_comps()

    def reset_all(self):
        self.db.limit_manager.reset_limits()
        self.db.mark_manager.reset_marks()
        self.db.tag_manager.reset_file_tags()
        self.db.time_manager.reset_play_times()
        self.db.comp_manager.reset_comps()