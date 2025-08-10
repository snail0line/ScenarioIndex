from PyQt5.QtWidgets import QDialogButtonBox, QWidget, QComboBox, QMessageBox, QTextEdit, QHeaderView, QApplication, QLineEdit, QSizePolicy, QScrollArea, QStyledItemDelegate, QHBoxLayout, QVBoxLayout, QTableView, QPushButton, QLabel, QListWidget, QDialog, QGridLayout
from PyQt5.QtCore import QAbstractTableModel, Qt, QSize, QRect, QRegExp, QModelIndex
from PyQt5.QtGui import QFont, QIcon, QRegExpValidator, QFontMetrics, QTextOption
from typing import List, Dict, Any
from loguru import logger
import json
import os
import subprocess
import traceback

from detail_viewer import ScenarioDetailViewer, CouponDetailViewer, InfoDetailViewer
from utils_and_ui import get_icon, to_half_width
from languages import language_settings





class IconDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        icon = index.data(Qt.DecorationRole)
        if icon:
            # 아이콘을 32x32로 고정하고, 셀의 중앙에 배치
            pixmap = icon.pixmap(32, 32)
            x = option.rect.x() + (option.rect.width() - 32) // 2
            y = option.rect.y() + (option.rect.height() - 32) // 2
            painter.drawPixmap(x, y, pixmap)
        else:
            super().paint(painter, option, index)


class FileTableModel(QAbstractTableModel):  
    def __init__(self, data: list, db_manager, current_language: str):
        super(FileTableModel, self).__init__()
        self._data = data
        self.db = db_manager
        self.mark_manager = self.db.mark_manager
        self.tag_manager = self.db.tag_manager
        self.current_language = current_language

        #  헤더 키 리스트만 저장 (초기 번역 X)
        self.headers = [
            "headers.mark",
            "headers.title",
            "headers.author",
            "headers.version",
            "headers.level",
            "headers.limit",
            "headers.time",
            "headers.tags",
            "headers.completed",
            "headers.summary",
            "headers.info",
            "headers.coupon",
            "headers.folder"
        ]

    def process_display_value(self, limit_value):
        """
        DB에서 가져온 limit_value를 화면 표시용 텍스트로 변환
        """
        limit_value = str(limit_value)
        
        if limit_value == "0":
            return ""  # 빈 칸
        elif limit_value == "99":
            return language_settings.translate("limit.none")  # 제한 없음
        elif "~" in limit_value:
            if limit_value.startswith("~"):
                return f"{limit_value[1:]}↓"  # ~n -> n↓
            elif limit_value.endswith("~"):
                return f"{limit_value[:-1]}↑"  # n~ -> n↑
        return limit_value  # n 또는 n~m 그대로 반환

    def data(self, index, role):
        try:
            if index.isValid():  # 유효한 인덱스인지 확인
                row = self._data[index.row()]  # 현재 행의 데이터를 가져옴
                column = index.column()
                
                if role == Qt.FontRole:
                    font = QFont()
                    font.setPointSize(10)

                    if column in [1, 2]:  # title과 author 열
                        file_lang = row.get('lang')
                        font.setFamily(language_settings.get_font_for_language(file_lang).family())
                    else:
                        font.setFamily(language_settings.get_font_for_language(self.current_language).family())
                    return font

                if role == Qt.DisplayRole or role == Qt.EditRole:  # 텍스트 반환
                    column = index.column()
                    if column == 1:
                        return row['title']
                    elif column == 2:
                        return row['author']
                    elif column == 3:
                        version = row['version']
                        if version == "OG":
                            # "OG"에 대해서만 언어별 번역 적용
                            return language_settings.translate("version.og")
                        return version  # 나머지 값은 그대로 반환
                    elif column == 4:
                        level_min = str(row['level_min'])  # Level Min
                        level_max = str(row['level_max'])  # Level Max
                        
                        # 조건에 따라 level_text 생성
                        if (level_min == "0" and level_max == "0") or (level_min == "1" and level_max in ["10", "15"]):
                            level_text = "All"
                        elif level_min == level_max:
                            level_text = level_min  # 레벨이 같을 경우 그 레벨을 텍스트로 사용
                        else:
                            level_text = f"{level_min}~{level_max}"  # 범위로 표시
                        
                        return level_text
                    
                    elif column == 5:  # 인원
                        limit_value = row.get('limit_value', "0")  # DB 값 가져오기
                        return self.process_display_value(limit_value)

                    elif column == 6:  # 시간
                        play_time = row.get('play_time', None)
                        if play_time is None:  # NULL 값 처리
                            return language_settings.translate("play_time.null")
                        return language_settings.translate(f"play_time.{play_time}")
                    
                    elif column == 7:  # 태그 열
                        # 태그 키를 현재 언어의 번역으로 변환
                        tags = row.get('file_tags', [])
                        # JSON 문자열을 리스트로 변환
                        if isinstance(tags, str):
                            try:
                                tags = json.loads(tags)
                            except json.JSONDecodeError:
                                tags = []
                        
                        if tags:  # 태그가 존재하면
                            translated_tags = [self.tag_manager.get_tag_display_name(tag) for tag in tags]
                            return ', '.join(translated_tags) if translated_tags else "No tags"
                        return "No tags"     

                if role == Qt.ToolTipRole and column == 7:
                    tags = row.get('file_tags', [])
                    if tags:
                        # 문자열로 저장된 태그 목록을 파싱
                        if isinstance(tags, str):
                            try:
                                tags = json.loads(tags)
                            except json.JSONDecodeError:
                                tags = []
                        
                        # 모든 태그의 번역된 이름을 가져와서 툴팁으로 표시
                        translated_tags = []
                        for tag in tags:
                            display_name = self.tag_manager.get_tag_display_name(tag)
                            if display_name:
                                translated_tags.append(display_name)
                        
                        # HTML 형식으로 툴팁 생성 - 자동 줄바꿈 적용
                        if translated_tags:
                            tooltip_text = "<div style='max-width: 300px; white-space: normal;'>"
                            tooltip_text += ", ".join(translated_tags)
                            tooltip_text += "</div>"
                            return tooltip_text


                if role == Qt.TextAlignmentRole and 3 <= column <= 7:
                    return Qt.AlignCenter  # 텍스트를 가운데 정렬

                if role == Qt.DecorationRole:
                    if column == 0:  # Mark 열에서 아이콘을 반환
                        # 사용자 마크 이미지 우선 로드
                        mark_image = self.mark_manager.get_mark_image(row['mark'])

                        # 이미지가 없으면 기본 마크 이미지 사용
                        if mark_image is None or mark_image.isNull():
                            mark_image = self.mark_manager.get_mark_image('mark00')  # 기본 마크 이미지

                        # 아이콘 크기 32x32로 조정
                        if mark_image and not mark_image.isNull():
                            scaled_mark_image = mark_image.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            return QIcon(scaled_mark_image)  # 아이콘 반환
                        else:
                            return None  # 이미지가 없으면 None 반환


                    elif column == 8:  # Comp 열
                        is_completed = row.get('is_completed', 0)
                        if is_completed:  # 1이면 완료 아이콘 표시
                            comp_icon = get_icon("comp")
                            return comp_icon
                        return None                
                    elif column == 9:  # Summary 열
                        summary_icon = get_icon("summary")
                        return summary_icon
                    elif column == 10:  # Info 열
                        info_icon = get_icon("info")
                        return info_icon                
                    elif column == 11:  # Coupon 열
                        coupon_number = row.get('coupon_number', 0)  # coupon_number가 없으면 0을 기본값으로 사용
                        if coupon_number > 0:  # coupon_number가 1 이상일 때만 아이콘 표시
                            coupon_icon = get_icon("coupon")
                            return coupon_icon
                        return None  # coupon_number가 0이면 빈 칸 표시    
                    elif column == 12:  # folder 열
                        folder_icon = get_icon("folder")
                        return folder_icon                              
                return None
        except Exception as e:
            logger.error(f"Error in data method: {e}")
            return None


    def rowCount(self, index):
        return len(self._data) if self._data else 0

    def columnCount(self, index):
        return len(self.headers) if self.headers else 0

    def headerData(self, section, orientation, role):
        """ 동적으로 헤더를 번역하여 반환"""
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(self.headers):
                return language_settings.translate(self.headers[section])  # ✅ 실행 시 번역 적용
        return None

# QFlowLayout 구현: 자동 줄바꿈이 가능한 레이아웃에 간격 추가
class QFlowLayout(QVBoxLayout):
    def __init__(self, parent=None, h_spacing=10, v_spacing=10):
        super().__init__(parent)
        self.items = []
        self.h_spacing = h_spacing
        self.v_spacing = v_spacing

    def addWidget(self, widget):
        self.items.append(widget)
        super().addWidget(widget)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        x, y = 0, 0
        rowHeight = 0
        for item in self.items:
            if not item:
                continue
            itemSize = item.sizeHint()
            # 줄 바꿈 조건
            if x + itemSize.width() + self.h_spacing > rect.width():
                x = 0
                y += rowHeight + self.v_spacing
                rowHeight = 0
            # 위젯 위치 설정
            item.setGeometry(QRect(x, y, itemSize.width(), itemSize.height()))
            x += itemSize.width() + self.h_spacing  # 수평 간격 추가
            rowHeight = max(rowHeight, itemSize.height())

    def sizeHint(self):
        valid_items = [item for item in self.items if item]
        width = sum(item.sizeHint().width() + self.h_spacing for item in valid_items) // max(1, len(valid_items))
        height = sum(item.sizeHint().height() + self.v_spacing for item in valid_items) // max(1, len(valid_items))
        return QSize(width, height)

    def removeWidget(self, widget):
        if widget in self.items:
            self.items.remove(widget)
        super().removeWidget(widget)

class TagSelector(QDialog):
    def __init__(self, all_tags, selected_tags, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Tags")
        self.setMinimumWidth(400)

        # 메인 레이아웃 설정
        main_layout = QVBoxLayout(self)

        # 태그 검색 필터 입력 추가
        self.filter_input = QLineEdit(self)
        self.filter_input.setPlaceholderText(language_settings.translate("tag_management.filter_placeholder"))
        self.filter_input.textChanged.connect(self.filter_tags)  # 텍스트 변경 시 필터링 메소드 호출
        main_layout.addWidget(self.filter_input)

        # 태그 목록과 선택된 태그 레이어를 양옆으로 배치할 수 있는 수평 레이아웃 생성
        tag_area_layout = QHBoxLayout()

        # 태그 목록 생성
        self.tag_selector = QListWidget(self)
        self.tag_selector.setFixedWidth(120)
        self.all_tags = all_tags  # 필터링에 사용할 태그 전체 목록 저장
        for tag, translation in all_tags:
            self.tag_selector.addItem(translation)
        self.tag_selector.itemClicked.connect(lambda item: self.on_tag_clicked(item))
        tag_area_layout.addWidget(self.tag_selector)

        # 스크롤 영역으로 선택된 태그 표시 영역을 감싸기 (외곽선 제거)
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.NoFrame)  # 외곽선 제거
        self.selected_tags_container = QWidget()
        self.selected_tags_layout = QFlowLayout(self.selected_tags_container, h_spacing=8, v_spacing=8)
        scroll_area.setWidget(self.selected_tags_container)
        tag_area_layout.addWidget(scroll_area)

        # 태그 목록과 선택된 태그 표시 영역을 메인 레이아웃에 추가
        main_layout.addLayout(tag_area_layout)

        # 이미 선택된 태그 표시
        for tag in selected_tags:
            self.add_tag(tag)

        # 확인 및 취소 버튼 추가
        button_layout = QHBoxLayout()
        confirm_button = QPushButton(language_settings.translate("confirm"))
        confirm_button.clicked.connect(lambda: self.confirm_selection())
        cancel_button = QPushButton(language_settings.translate("cancel"))
        cancel_button.clicked.connect(lambda: self.reject())
        button_layout.addWidget(confirm_button)
        button_layout.addWidget(cancel_button)
        main_layout.addLayout(button_layout)

    def filter_tags(self, text):
        self.tag_selector.clear()  # 기존 목록 초기화
        filtered_tags = [translation for tag, translation in self.all_tags if text.lower() in translation.lower()]
        self.tag_selector.addItems(filtered_tags)

    def add_tag(self, tag_key):
        """태그를 추가하는 메소드."""
        for i in range(self.selected_tags_layout.count()):
            widget = self.selected_tags_layout.itemAt(i).widget()
            label = widget.findChild(QLabel) if widget else None
            if label and label.objectName() == tag_key:
                return  # 이미 추가된 태그라면 추가하지 않음

        # 현재 언어에 맞는 태그 번역 가져오기
        display_name = self.parent().db.tag_manager.get_tag_display_name(tag_key)

        # 태그 컨테이너 위젯 생성
        tag_container = QWidget(self)
        tag_layout = QHBoxLayout(tag_container)
        tag_layout.setContentsMargins(0, 0, 0, 0)  # 여백 설정

        # 태그 텍스트 라벨을 QLabel로 생성
        tag_label = QLabel(display_name)
        tag_label.setObjectName(tag_key)
        tag_label.setWordWrap(True)
        tag_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)  # 세로 크기 자동 조정
        tag_label.setStyleSheet("""
            QLabel {
                background-color: #ffdd94;
                border-radius: 10px;
                padding: 5px;
                font-weight: bold;
                color: black;
            }
        """)

        # 닫기 버튼 생성
        close_button = QPushButton("×", self)
        close_button.setFixedSize(10, 10)
        close_button.setStyleSheet("background: transparent; color: black;")
        close_button.clicked.connect(lambda: self.remove_tag(tag_container))

        # 레이아웃에 라벨과 닫기 버튼 추가
        tag_layout.addWidget(tag_label)
        tag_layout.addWidget(close_button)

        # 태그 컨테이너를 selected_tags_layout에 추가
        self.selected_tags_layout.addWidget(tag_container)

    def on_tag_clicked(self, item):
        """태그 목록에서 항목을 클릭할 때 호출되는 메소드."""
        tag_name = item.text()

        # 태그 키와 번역 쌍을 가져옴
        tag_translations = self.parent().db.tag_manager.fetch_tag_keys_with_translations()

        # 태그 이름으로 태그 키 찾기
        tag_key = next((key for key, translation in tag_translations if translation == tag_name), None)

        if tag_key:
            self.add_tag(tag_key)

    def confirm_selection(self):
        """선택된 태그를 파일에 붙이는 메소드."""
        selected_tags = [self.selected_tags_layout.itemAt(i).widget().findChild(QLabel).objectName()
                        for i in range(self.selected_tags_layout.count())]

        if self.parent().current_row >= 0:
            file_path = self.parent().file_data[self.parent().current_row]['file_path']
            self.parent().db.tag_manager.update_tags_for_file(file_path, selected_tags)

            # ✅ UI 즉시 갱신
            self.parent().update_ui_after_edit(file_path, "file_tags", json.dumps(selected_tags))

        self.accept()


    def remove_tag(self, tag_button):
        """태그 버튼 클릭 시 태그를 제거합니다."""
        self.selected_tags_layout.removeWidget(tag_button)
        tag_button.deleteLater()

class MarkSelector(QDialog):
    def __init__(self, mark_manager, current_mark, parent=None):
        logger.info("Initializing MarkSelector...")
        super().__init__(parent)
        self.setWindowTitle("Select Mark")
        self.layout = QGridLayout(self)

        self.mark_manager = mark_manager
        self.selected_mark = current_mark  # 현재 선택된 마크 저장
        logger.info(f"Current mark: {self.selected_mark}")

        # 마크 버튼 추가 (01부터 30까지)
        for i in range(1, 31):  # 01부터 30까지
            mark_name = f"mark{i:02d}"
            button = QPushButton()
            button.setFixedSize(32, 32)

            # 사용자 아이콘을 우선적으로 로드
            mark_image = self.mark_manager.get_mark_image(mark_name)

            if mark_image is None or mark_image.isNull():  # 이미지가 없으면 기본 마크 사용
                logger.warning(f"Mark image not found: {mark_name}. Using default mark.")
                mark_image = self.mark_manager.get_mark_image('mark00')  # 기본 마크 사용

            # 최종적으로 이미지가 있으면 아이콘 설정, 없으면 버튼 비활성화
            if mark_image and not mark_image.isNull():
                button.setIcon(QIcon(mark_image.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                button.setIconSize(QSize(32, 32))  # 아이콘 크기 설정
            else:
                button.setEnabled(False)  # 이미지가 없으면 버튼 비활성화

            # 클릭 시 정확히 해당 마크를 선택하도록 `partial` 사용
            button.clicked.connect(lambda _, m=mark_name: self.select_mark(m))

            self.layout.addWidget(button, (i - 1) // 6, (i - 1) % 6)  # 6x5 그리드 형식으로 추가


        # 저장, 삭제, 취소 버튼 추가
        button_layout = QHBoxLayout()  # 수평 레이아웃 추가
        save_button = QPushButton(language_settings.translate("save_changes"))
        save_button.clicked.connect(lambda: self.save_selected_mark())  # 저장 후 창 닫기
        delete_button = QPushButton(language_settings.translate("delete"))
        delete_button.clicked.connect(lambda: self.delete_selected_mark())  # 삭제 후 창 닫기
        cancel_button = QPushButton(language_settings.translate("cancel"))
        cancel_button.clicked.connect(lambda: self.close())  # 취소 시 창 닫기

        # 버튼 추가
        button_layout.addWidget(save_button)
        button_layout.addWidget(delete_button)
        button_layout.addWidget(cancel_button)

        self.layout.addLayout(button_layout, 5, 0, 1, 6)  # 버튼 레이아웃 추가
        self.setLayout(self.layout)

    def select_mark(self, mark):
        """선택된 마크를 업데이트하는 함수."""        
        self.selected_mark = mark  # 선택된 마크 업데이트
        logger.info(f"Mark selected: {self.selected_mark}")

    def save_selected_mark(self):
        """선택된 마크를 저장합니다."""        
        if self.parent().current_row >= 0:  # 부모 클래스의 current_row를 확인
            file_path = self.parent().file_data[self.parent().current_row]['file_path']  # 현재 파일 경로 가져오기
            logger.info(f"Saving selected mark '{self.selected_mark}' for file: {file_path}")
            self.mark_manager.update_mark(file_path, self.selected_mark)  # 선택된 마크 업데이트
            self.parent().update_ui_after_edit(file_path, "mark", self.selected_mark)
            logger.info(f"Mark '{self.selected_mark}' successfully saved.")
            self.close()  # 다이얼로그 닫기


    def delete_selected_mark(self):
        """선택된 마크를 삭제하고 mark00으로 설정합니다."""        
        if self.parent().current_row >= 0:  # 부모 클래스의 current_row를 확인
            file_path = self.parent().file_data[self.parent().current_row]['file_path']  # 현재 파일 경로 가져오기
            logger.info(f"Deleting selected mark for file: {file_path}")
            self.mark_manager.update_mark(file_path, 'mark00')  # 마크를 mark00으로 설정
            self.parent().update_ui_after_edit(file_path, "mark", 'mark00')
            self.close()  # 다이얼로그 닫기

class LimitValueEditor(QDialog): 
    def __init__(self, file_path, current_value, limit_manager, parent):
        super().__init__(parent)
        self.file_path = file_path
        self.current_value = current_value
        self.limit_manager = limit_manager
        self.current_language = parent.current_language
        self.processed_value = None
        self.setWindowTitle(language_settings.translate("edit_field.limit_edit_title"))

        # 레이아웃 설정
        layout = QVBoxLayout(self)

        # 설명 라벨
        self.label = QLabel(language_settings.translate("edit_field.limit_edit_label"))
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        # QLineEdit에 입력 제한 설정
        self.limit_input = QLineEdit(self)
        # 정규식: 0, 99, [1-6], ~[1-6], [2-6]~, [1-6]~[2-6]
        validator = QRegExpValidator(QRegExp(r"^(?:0|99|[1-6]|~[1-6]|[1-6]~|[1-6]~[1-6])$"), self)
        self.limit_input.setValidator(validator)
        layout.addWidget(self.limit_input)

        # 확인 버튼
        self.confirm_button = QPushButton(language_settings.translate("confirm"))
        self.confirm_button.clicked.connect(lambda: self.on_confirm())
        layout.addWidget(self.confirm_button)
  
    def on_confirm(self):
        input_value = self.limit_input.text()
        self.processed_value = self.process_input_value(input_value)

        if self.processed_value is not None:
            try:
                # LimitManager를 사용해 DB 업데이트
                self.limit_manager.update_limit(self.file_path, self.processed_value)
                self.accept()
            except Exception as e:
                self.label.setText(f"Error saving to DB: {e}")  # DB 저장 실패 시 에러 메시지 표시
        else:
            self.label.setText("Invalid input. Please try again.")  # 에러 메시지 표시
   
    def process_input_value(self, input_value: str) -> str:
        """
        입력값을 처리하여 DB에 저장할 값으로 변환.
        """
        input_value = to_half_width(input_value)

        if input_value in ("0", "99"):  # 초기값과 제한 없음
            return input_value
        elif input_value in ("1~", "~6", "1~6"):  # 1명 이상, 6명 이하, 1~6은 제한 없음으로 처리
            return "99"
        elif '~' in input_value:
            if input_value.startswith('~') or input_value.endswith('~'):
                return input_value  # 이미 ~n 또는 n~ 형태면 그대로 반환
            
            # n1~n2 형태 처리
            try:
                start, end = map(int, input_value.split('~'))
                if start > end:
                    self.label.setText("Invalid range: start value cannot be greater than end value.")
                    return None
                    
                # 최적화: 1~n을 ~n으로, n~6을 n~로 변환
                if start == 1:
                    return f"~{end}"
                elif end == 6:
                    return f"{start}~"
                else:
                    return input_value
                    
            except ValueError:
                self.label.setText("Invalid input format.")
                return None
                
        return input_value  # 그 외의 유효한 값은 그대로 반환
    
    def convert_to_half_width(self):
        """입력값의 전각 문자를 반각 문자로 변환"""
        text = self.limit_input.text()
        converted_text = to_half_width(text)  # ✅ 전각 → 반각 변환 적용
        if text != converted_text:
            self.limit_input.setText(converted_text)  # ✅ 변환된 값으로 업데이트

class FileViewer(QWidget):
    def __init__(self, scenario_folder_path, current_language, search_manager, db_manager):
        super().__init__()

        # 페이징 및 검색 상태 변수
        self.search_results = []  # 검색 결과 저장
        self.is_search_active = False  # 검색 활성화 여부
        self.current_page = 1
        self.page_size = 30
        self.total_files = 0
        self.total_pages = 1
        self.file_data = []  # 현재 표시 중인 파일 데이터
        self.table_model = None  # 테이블 모델 초기화
        self.current_sort_field = "modification_time"

        self.db = db_manager
        self.mark_manager = self.db.mark_manager
        self.time_manager = self.db.time_manager
        self.limit_manager = self.db.limit_manager
        self.search_manager = search_manager

        self.scenario_folder_path = scenario_folder_path
        self.current_language = current_language

        # 하나의 IconDelegate 인스턴스를 공유
        self.icon_delegate = IconDelegate()
        self._setup_ui()

    def _setup_ui(self):
        try:
            # UI 컴포넌트 설정
            self.layout = QVBoxLayout(self)

            # 테이블 뷰 설정
            self.file_table_view = CustomTableView(self)
            self.file_table_view.clicked.connect(self.on_file_clicked)
            self.file_table_view.verticalHeader().setDefaultSectionSize(36)
            self.file_table_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            self.layout.addWidget(self.file_table_view)

            # 모델 설정
            self.table_model = FileTableModel(self.file_data, self.db, self.current_language)  # FileTableModel 초기화
            self.file_table_view.setModel(self.table_model)

            # 버튼 및 라벨을 가로로 나열하기 위한 레이아웃
            button_layout = QHBoxLayout()

            # 맨 앞으로 버튼
            self.first_page_button = QPushButton("<<")
            self.first_page_button.clicked.connect(lambda: self.first_page())
            button_layout.addWidget(self.first_page_button)

            # 이전 페이지 버튼
            self.prev_button = QPushButton("<")
            self.prev_button.clicked.connect(lambda: self.previous_page())
            button_layout.addWidget(self.prev_button)

            # 페이지 표시 라벨
            self.page_label = QLabel("Page 1")
            self.page_label.setAlignment(Qt.AlignCenter)
            button_layout.addWidget(self.page_label)

            # 페이지 점프 입력 필드
            self.page_jump_input = QLineEdit()
            self.page_jump_input.setFixedWidth(50)
            self.page_jump_input.returnPressed.connect(lambda: self.jump_to_page())
            self.page_jump_input.setToolTip(language_settings.translate("main.jump_tooltip"))
            button_layout.addWidget(self.page_jump_input)

            # 다음 페이지 버튼
            self.next_button = QPushButton(">")
            self.next_button.clicked.connect(lambda: self.next_page())
            button_layout.addWidget(self.next_button)

            # 맨 뒤로 버튼
            self.last_page_button = QPushButton(">>")
            self.last_page_button.clicked.connect(lambda: self.last_page())
            button_layout.addWidget(self.last_page_button)

            # 버튼 레이아웃 추가
            self.layout.addLayout(button_layout)

            # IconDelegate를 사용할 열 번호 리스트
            icon_columns = [0, 8, 9, 10, 11, 12]  # 아이콘을 표시할 모든 열 번호

            # 모든 아이콘 열에 대해 한 번에 delegate 설정
            for col in icon_columns:
                self.file_table_view.setItemDelegateForColumn(col, self.icon_delegate)

            # 열 너비를 초기화 시점에 설정
            self._initialize_column_widths()

        except Exception as e:
            logger.error(f"_setup_ui 에러 발생: {e}")
            traceback.print_exc()

    def on_file_clicked(self, index, event=None):
        """파일 테이블에서 행 클릭 시 호출되는 메소드."""
        if not index.isValid():
            return  # 유효하지 않은 인덱스는 무시

        self.current_row = index.row()  # 클릭한 행 저장
        current_file_data = self.file_data[self.current_row]  # 파일 데이터 가져오기
        column = index.column()  # 선택된 열

        # 이벤트가 없는 경우 기본적으로 좌클릭 처리로 가정
        mouse_button = event.button() if event else Qt.LeftButton

        if column == 1:  # title 열
            if mouse_button == Qt.LeftButton:  # 좌클릭 시 텍스트 복사
                text_to_copy = current_file_data.get('title', "")
                clipboard = QApplication.clipboard()
                clipboard.setText(text_to_copy)
                logger.info(f"Copied to clipboard: {text_to_copy}")
                QMessageBox.information(
                    self,
                    language_settings.translate("main.copy_success_title"),
                    language_settings.translate("main.copy_success_message").format(text=text_to_copy)
                )
            elif mouse_button == Qt.RightButton:  # 우클릭 시 데이터 수정
                logger.debug(f"Right-click detected on 'title' column for row {index.row()}.")
                self.edit_title(index.row())

        elif column == 2:  # author 열
            if mouse_button == Qt.LeftButton:  # 좌클릭 시 텍스트 복사
                text_to_copy = current_file_data.get('author', "Unknown")
                clipboard = QApplication.clipboard()
                clipboard.setText(text_to_copy)
                logger.info(f"Copied to clipboard: {text_to_copy}")
                QMessageBox.information(
                    self,
                    language_settings.translate("main.copy_success_title"),
                    language_settings.translate("main.copy_success_message").format(text=text_to_copy)
                )
            elif mouse_button == Qt.RightButton:  # 우클릭 시 데이터 수정
                logger.debug(f"Right-click detected on 'author' column for row {index.row()}.")
                self.edit_author(index.row())

        elif column == 4:  # level 열
            if mouse_button == Qt.RightButton:  # 우클릭 시 데이터 수정
                logger.debug(f"Right-click detected on 'level' column for row {index.row()}.")
                self.edit_level(index.row())

        elif column == 9:  # Summary 열 (아이콘 클릭 시)
            if mouse_button == Qt.LeftButton:  # 좌클릭 시 텍스트 복사    
                self.on_Summary_icon_clicked(self.current_row)  # 포스터 아이콘 클릭 시 처리
            elif mouse_button == Qt.RightButton and language_settings.current_locale == "kr" :  # 우클릭 시 데이터 수정
                logger.debug(f"Right-click detected on 'description' column for row {index.row()}.")
                self.edit_description(index.row())

        elif column == 5:  # 인원수 열
            file_path = current_file_data['file_path']
            current_value = current_file_data.get('limit_value', "0")  # 현재 limit_value 가져오기
            editor = LimitValueEditor(file_path, current_value, self.limit_manager, self)
            editor.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
            if editor.exec_():  # 제한값 수정 후
                new_limit = editor.processed_value
                self.update_ui_after_edit(file_path, "limit_value", new_limit)   
        elif column == 6:  # Time 열
            self.show_time_selector(index, current_file_data)                            
        elif column == 7:  # 태그 열
            # 태그 선택기 바로 실행
            current_tags = current_file_data.get('file_tags', [])
            # 문자열로 저장된 태그를 리스트로 변환
            if isinstance(current_tags, str):
                try:
                    current_tags = json.loads(current_tags)
                except json.JSONDecodeError:
                    current_tags = []
                    
            all_tags = self.db.tag_manager.fetch_tag_keys_with_translations()
            tag_selector = TagSelector(all_tags, current_tags, self)
            tag_selector.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
            tag_selector.exec_()
        elif column == 8:  # 완료 열     
            current_completed = self.file_data[self.current_row].get('is_completed', 0)
            new_completed = 0 if current_completed else 1
            self.file_data[self.current_row]['is_completed'] = new_completed  # 토글 상태 변경
            file_path = self.file_data[self.current_row]['file_path']
            self.db.update_completed_status(file_path, new_completed)  # DB 업데이트
            self.update_ui_after_edit(file_path, "is_completed", new_completed)  # 테이블 새로고침                           
        elif column == 10:  
            if hasattr(self, 'info_detail_viewer') and self.info_detail_viewer is not None:
                self.info_detail_viewer.raise_()  # 기존 창을 앞으로 가져옴
                return

            # 새 InfoDetailViewer 열기
            file_path = current_file_data.get('file_path')
            title = current_file_data.get('title')
            lang = current_file_data.get('lang')
            
            self.info_detail_viewer = InfoDetailViewer(
                parent=self,
                file_name=title,
                file_path=file_path,
                lang=lang
            )

            self.info_detail_viewer.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
            # 창이 닫힐 때 None으로 설정하기 위한 시그널 연결
            self.info_detail_viewer.finished.connect(lambda: self.cleanup_info_viewer())
            self.info_detail_viewer.show_details()
        elif column == 0:  # 마크 열
            current_mark = current_file_data['mark']  # 현재 마크
            mark_selector = MarkSelector(self.mark_manager, current_mark, self)  # MarkSelector 인스턴스 생성
            mark_selector.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
            mark_selector.exec_()
        elif column == 11:  # 쿠폰 열 클릭 시
            coupon_status = self.file_data[self.current_row].get('coupon_number', 0)
            if coupon_status > 0:  # 쿠폰이 있을 때만 창 열기
                coupon_name = self.file_data[self.current_row].get('coupon_name', '')
                self.show_coupon_details(coupon_name)                 
        elif column == 12:
            file_path = current_file_data.get('file_path')  # 현재 행의 파일 경로 가져오기

            # ✅ ZIP 파일 내부 경로인지 확인
            if ".zip!" in file_path:
                zip_path, inner_file = file_path.split("!", 1)
                folder_path = os.path.abspath(os.path.dirname(zip_path))  # ZIP 파일이 있는 폴더 반환
            else:
                folder_path = os.path.abspath(os.path.dirname(file_path))  # 일반 파일의 폴더 경로 반환

            if os.path.exists(folder_path):
                try:
                    subprocess.Popen(['explorer', folder_path])  # Windows 탐색기로 폴더 열기
                    logger.info(f"Opened folder: {folder_path}")
                except Exception as e:
                    logger.error(f"Failed to open folder: {folder_path}, Error: {e}")
                    QMessageBox.critical(self, "Error", f"Failed to open folder:\n{e}")
            else:
                logger.warning(f"Folder does not exist: {folder_path}")
                QMessageBox.warning(self, "Warning", f"The folder does not exist:\n{folder_path}")


    def show_time_selector(self, index, current_file_data):
        """Time 열에서 시간 선택용 콤보박스를 표시하는 메서드"""
        combo = QComboBox(self.file_table_view.viewport())  # 부모 위젯을 viewport로 변경

        # LanguageSettings에서 시간 옵션 가져오기
        time_options = {
            key: language_settings.translate(f"play_time.{key}")
            for key in ["null", "under10", "about15", "about20", "about30", "under60", "over60", "over120", "unknown"]
        }

        # 콤보박스에 아이템 추가
        for key, display_text in time_options.items():
            combo.addItem(display_text, key)

        # 현재 값 설정
        current_time = current_file_data.get('play_time', '')
        if current_time:
            for i in range(combo.count()):
                if combo.itemData(i) == current_time:
                    combo.setCurrentIndex(i)
                    break

        # 콤보박스 위치 설정
        rect = self.file_table_view.visualRect(index)
        combo.move(rect.topLeft())  # 클릭한 셀의 좌상단 모서리에 맞춤

        # 선택 시 이벤트 처리
        combo.activated.connect(lambda: self.on_time_selected(
            combo,
            current_file_data['file_path']
        ))
        combo.showPopup()  # 바로 드롭다운 표시

    def on_time_selected(self, combo, file_path):
        """콤보박스에서 시간이 선택되었을 때 호출되는 메서드"""
        selected_time = combo.currentData()  # 선택된 시간 값 가져오기
        self.time_manager.update_play_time(file_path, selected_time)  # play_time 업데이트
        self.update_ui_after_edit(file_path, "play_time", selected_time)
        combo.deleteLater()  # 콤보박스 제거

    def show_coupon_details(self, coupon_name):
        """필요한 쿠폰 세부 정보를 표시하는 새 창을 엽니다."""
        self.coupon_viewer = CouponDetailViewer(coupon_name)
        self.coupon_viewer.show()

    def on_Summary_icon_clicked(self, row):
        row_data = self.table_model._data[row]
        file_path = row_data.get('file_path')
        level_min = row_data.get('level_min')
        level_max = row_data.get('level_max')
        title = row_data.get('title')
        description = row_data.get('description')
        image_paths = row_data.get('image_paths', [])
        position_types = row_data.get('position_types', [])
        lang = row_data.get('lang')

        # image_paths가 문자열일 경우 JSON 형식으로 파싱하여 리스트로 변환
        if isinstance(image_paths, str):
            try:
                image_paths = json.loads(image_paths)
            except json.JSONDecodeError:
                logger.error("Error: Invalid JSON format for image_paths")
                image_paths = []

        # 폴더일 경우 각 이미지 경로를 절대 경로로 변환합니다.
        if os.path.isdir(file_path):
            absolute_image_paths = [os.path.normpath(os.path.join(file_path, image_path)) for image_path in image_paths]
        else:
            # 폴더가 아닐 경우 원래 이미지 경로 유지
            absolute_image_paths = image_paths

        viewer = ScenarioDetailViewer(file_path, level_min, level_max, title, description, absolute_image_paths, position_types, lang)
        viewer.show_details()

    def load_file_list(self):
        logger.info(f"Loading data from page {self.current_page} / Total pages: {self.total_pages}")
        
        # 페이지네이션 계산
        self.calculate_total_files_and_pages()

        if self.is_search_active and self.search_results:
            # 검색 상태에서 검색 결과를 로드
            logger.info("Loading data from search results...")
            page_data = self._load_from_search_results()
        else:
            # 비검색 상태에서 전체 데이터를 로드
            logger.info("Loading data from full dataset...")
            page_data = self._load_from_database(self.current_page)

        if not page_data:
            logger.info(f"No data fetched for page {self.current_page}.")
            self.update_table([])
            self.update_pagination_ui()  # 빈 페이지일 경우에도 UI 갱신
            return

        self.update_table(page_data)
        self._initialize_column_widths()
        self.update_pagination_ui()  # 페이지 정보 갱신

    def _load_from_search_results(self) -> List[Dict[str, Any]]:
        """검색 결과에서 현재 페이지에 해당하는 데이터를 로드합니다."""

        # 정렬 기준 설정 (기본값: modification_time)
        sort_field = self.current_sort_field or "modification_time"
        logger.debug(f"sort_field: {sort_field}")

        # 정렬 방향 결정
        if sort_field == "modification_time":
            sort_desc = True  # 최신순 (내림차순)
        else:
            sort_desc = False  # 제목, 저자 등은 오름차순

        try:
            self.search_results.sort(
                key=lambda x: (
                    x.get(sort_field, 0) if isinstance(x.get(sort_field), (int, float)) else str(x.get(sort_field, "")).lower()
                ),
                reverse=sort_desc  #  정렬 방향 적용
            )
            logger.info(f"Search results sorted by {sort_field} in {'descending' if sort_desc else 'ascending'} order")
        except Exception as e:
            logger.error(f"Error sorting search results: {e}")

        # 페이지네이션 처리
        start_index = (self.current_page - 1) * self.page_size
        end_index = start_index + self.page_size
        return self.search_results[start_index:end_index]

    def _load_from_database(self, page: int = 1):
        if not self.scenario_folder_path:
            raise ValueError("Folder path is not set")

        sort_field = self.current_sort_field or "modification_time"
        logger.debug(f"sort_field: {sort_field}")
        start_index = (page - 1) * self.page_size

        query = f"""
            SELECT * FROM file_data
            WHERE folder_path LIKE ?
            ORDER BY {sort_field}
            LIMIT ? OFFSET ?
        """
        try:
            result = self.db.fetch_sorted_file_data(
                folder_path=self.scenario_folder_path,
                sort_field=sort_field,
                page_size=self.page_size,
                start_index=start_index,
            )
            logger.info(f"Rows fetched for page {page}: {len(result)}")
            return result
        except Exception as e:
            logger.error(f"Error loading data from database: {e}")
            raise

    def update_ui_after_edit(self, file_path, updated_key, updated_value):
        """
        DB에서 수정된 데이터를 UI에 즉시 반영하는 함수
        - 검색 중이면 `self.search_results`를 업데이트하고 `apply_search_results()` 호출
        - 일반 목록이면 `load_file_list()` 호출
        """
        if self.is_search_active:
            for item in self.search_results:
                if item["file_path"] == file_path:
                    item[updated_key] = updated_value  # 변경된 데이터 적용
            self.apply_search_results(self.search_results)  # 검색 결과 갱신
        else:
            self.load_file_list()  # 일반 목록 새로고침

    def calculate_total_files_and_pages(self):
        """전체 파일 개수 및 페이지 수를 계산"""
        if self.is_search_active:
            # 검색 상태에서 total_files는 검색 결과의 개수
            self.total_files = len(self.search_results)
            logger.info(f"Search is active. Total search results: {self.total_files}")

        else:
            # 비검색 상태에서 total_files는 데이터베이스에서 가져온 전체 파일 개수
            self.total_files = self.db.fetch_file_data_count(self.scenario_folder_path)

        # 전체 페이지 수 계산 (올림)
        self.total_pages = max(1, (self.total_files + self.page_size - 1) // self.page_size)
        logger.info(f"Total files: {self.total_files}, Total pages: {self.total_pages}")

    def _process_tags(self, files):
        """파일 태그를 번역된 이름으로 처리."""
        for file_data in files:
            try:
                tags = file_data.get('file_tags', '[]')

                # 태그 데이터 타입 확인 및 변환
                if isinstance(tags, str):
                    tag_keys = json.loads(tags)  # JSON 문자열을 리스트로 변환
                elif isinstance(tags, list):
                    tag_keys = tags
                else:
                    raise ValueError("Invalid tag format")

                # 태그 번역
                file_data['translated_tags'] = [
                    self.db.tag_manager.get_tag_display_name(key) for key in tag_keys
                ]

            except json.JSONDecodeError:
                logger.error(f"Error decoding tags for file: {file_data.get('file_path', 'Unknown')}")
                file_data['translated_tags'] = []  # 태그 디코딩 실패 시 빈 리스트
            except Exception as e:
                logger.error(f"Unexpected error processing tags for file: {file_data.get('file_path', 'Unknown')} - {e}")
                file_data['translated_tags'] = []  # 기타 예외 처리

    def update_table(self, file_data):
        self.file_data = file_data

        # 항상 테이블 모델을 새로 생성하여 업데이트
        self.table_model = FileTableModel(
            self.file_data,
            self.db,
            self.current_language
        )
        self.file_table_view.setModel(self.table_model)
        logger.info("Table model updated.")

        if self.file_table_view.model():
            self.file_table_view.model().layoutChanged.emit()

    def sort_by_field(self, field: str):
        self.current_sort_field = field
        logger.debug(f"sort_field: {self.current_sort_field}")
        self.current_page = 1
        self.load_file_list()

    def edit_author(self, row):
        self.edit_field(row, "author")

    def edit_title(self, row):
        self.edit_field(row, "title")

    def edit_description(self, row):
        self.edit_field(row, "description")

    def edit_level(self, row):
        """레벨 필드 수정"""
        current_data = self.file_data[row]
        current_min = current_data.get('level_min', 0)
        current_max = current_data.get('level_max', 0)
        file_path = current_data['file_path']

        # 레벨 입력용 다이얼로그 생성
        dialog = QDialog(self)
        dialog.setWindowTitle(language_settings.translate("edit_field.title"))

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(language_settings.translate("edit_field.level_edit_label")))

        min_input = QLineEdit(str(current_min))
        max_input = QLineEdit(str(current_max))

        min_validator = QRegExpValidator(QRegExp(r"^\d+$"))  # 숫자만 입력 가능
        max_validator = QRegExpValidator(QRegExp(r"^\d+$"))
        
        min_input.setValidator(min_validator)
        max_input.setValidator(max_validator)

        layout.addWidget(QLabel(language_settings.translate("edit_field.level_min")))
        layout.addWidget(min_input)

        layout.addWidget(QLabel(language_settings.translate("edit_field.level_max")))
        layout.addWidget(max_input)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        if dialog.exec_() == QDialog.Accepted:
            try:
                new_min = int(min_input.text())
                new_max = int(max_input.text())

                if new_min > new_max:
                    QMessageBox.warning(self, "Error", "Minimum level cannot be greater than maximum level.")
                    return

                self.db.update_level(file_path, new_min, new_max)  # 새 함수 사용
                self.file_data[row]['level_min'] = new_min
                self.file_data[row]['level_max'] = new_max
                self.update_table(self.file_data)

            except ValueError:
                QMessageBox.warning(self, "Error", "Invalid level input. Please enter valid numbers.")

    def edit_field(self, row, field):
        """Edit a specific field for a file."""
        current_data = self.file_data[row]
        current_value = current_data.get(field, "")
        file_path = current_data['file_path']

        if isinstance(current_value, str):
            current_value_for_label = current_value.replace("\\n", "\n")
        else:
            current_value_for_label = current_value
    
        logger.debug(f"Editing field: {field}")
        logger.debug(f"Current value: {current_value_for_label}")
        
        field_translation_keys = {
            "title": "headers.title",
            "author": "headers.author",
            "description": "headers.summary",
        }
        field_translation_key = field_translation_keys.get(field, f"headers.{field}")
        title = language_settings.translate("edit_field.title")
        prompt = language_settings.translate("edit_field.prompt").format(
            field=language_settings.translate(field_translation_key),
            value="\n" + (current_value_for_label or language_settings.translate("edit_field.empty")))

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedWidth(280)  # 최소 너비 설정

        layout = QVBoxLayout()

        label = QLabel(prompt)
        label.setWordWrap(True)
        layout.addWidget(label)

        # QTextEdit 설정
        if field in ["title", "author"]:
            text_edit = QLineEdit()  # 한 줄 입력
            text_edit.setText(current_value)
            text_edit.setFixedHeight(30)  # 고정된 높이 설정
        else:
            text_edit = QTextEdit()  # 여러 줄 입력
            text_edit.setText(current_value.replace("\\n", "\n"))
            text_edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)  # 자동 줄바꿈 활성화

            # 텍스트 길이에 따른 동적 크기 조절
            font_metrics = QFontMetrics(text_edit.font())
            text_height = font_metrics.height()

            # 최소 크기 계산 (100px로 고정)
            min_height = 100

            # 실제 필요한 높이 계산
            needed_height = max(min_height, min(text_height * (len(current_value) // 30 + 1), 300))  # 최소/최대 높이 제한
            text_edit.setFixedHeight(needed_height)

        # 다이얼로그 내부에 경고 문구 추가
        if field == "description" and language_settings.current_locale == "kr":
            warning_label = QLabel("⚠️한국어 사용자는 번역된 텍스트를 넣어\n시나리오 정보를 쉽게 확인할 수 있도록\n벽보 수정 기능을 열어두었습니다.\n\n수정한 이미지는 인터넷에 공개하지 말고\n개인 확인용으로만 사용해 주세요.\n")
            warning_label.setStyleSheet("color: red; font-weight: bold;")  # 빨간색 강조
            warning_label.setAlignment(Qt.AlignCenter)
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)  # 레이아웃에 추가

        layout.addWidget(text_edit)

        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | 
            QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        if dialog.exec_() == QDialog.Accepted:
            if isinstance(text_edit, QLineEdit):
                new_value = text_edit.text()
            elif isinstance(text_edit, QTextEdit):
                new_value = text_edit.toPlainText()
            else:
                new_value = ""

            new_value = new_value.replace("\\n", "\n")

            if new_value:
                self.db.update_field(file_path, field, new_value)
                self.file_data[row][field] = new_value
                self.update_table(self.file_data)
                logger.info(f"{field.capitalize()} updated for {file_path}: {new_value}")
                
    def cleanup_info_viewer(self):
        """InfoDetailViewer 창이 닫힐 때 호출되는 메서드"""
        self.info_detail_viewer = None

    def previous_page(self):
        """이전 페이지로 이동."""      
        if self.current_page > 1:  # 1 기반으로 수정
            self.current_page -= 1
            self.load_file_list()

    def next_page(self):
        """다음 페이지로 이동."""        
        if self.current_page < self.total_pages:  # 1 기반으로 수정
            self.current_page += 1
            self.load_file_list()

    def first_page(self):
        """맨 첫 페이지로 이동"""
        if self.current_page != 1:  # 이미 첫 페이지라면 실행하지 않음
            self.current_page = 1
            self.load_file_list()

    def last_page(self):
        """맨 마지막 페이지로 이동"""
        if self.current_page != self.total_pages:  # 이미 마지막 페이지라면 실행하지 않음
            self.current_page = self.total_pages
            self.load_file_list()

    def jump_to_page(self):
        """사용자가 입력한 페이지로 정확히 이동"""
        try:
            page = int(self.page_jump_input.text().strip())  # 입력된 페이지 번호
            if 1 <= page <= self.total_pages:
                if self.current_page != page:  # 이미 해당 페이지라면 실행하지 않음
                    self.current_page = page
                    logger.info(f"Jumping to page: {self.current_page}")
                    self.load_file_list()  # 해당 페이지의 파일 목록 새로 로드
            else:
                QMessageBox.warning(
                    self, "Invalid Page", f"Please enter a number between 1 and {self.total_pages}."
                )
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid number.")

    def apply_search_results(self, search_results: List[Dict[str, Any]]):
        """검색 결과를 저장하고 검색 상태를 활성화"""
        # 검색 결과 저장 및 검색 상태 활성화
        self.search_results = search_results
        if not search_results:
            # 결과가 없을 때 메시지 박스 표시
            QMessageBox.information(
                self, 
                language_settings.translate("search.search_results"),  # 제목
                language_settings.translate("search.no_results_found")  # 내용
            )
            logger.info("No search results found.")
            return  # 기존 데이터를 유지
        self.is_search_active = True
        logger.info(f"Search activated with {len(self.search_results)} results.")

        # UI 및 검색 결과 첫 페이지 데이터 로드
        self.load_file_list()

    def update_pagination_ui(self):
        """페이지와 관련된 UI 업데이트"""
        self.page_label.setText(f"Page {self.current_page} of {self.total_pages}")
        self.page_jump_input.setPlaceholderText(f"1-{self.total_pages}")
         
    def closeEvent(self, event):
        """창이 닫힐 때 데이터베이스 연결을 닫습니다."""       
        self.db.close()
        super().closeEvent(event)

    def _initialize_column_widths(self):
        """초기 열 너비 설정."""
        if not self.table_model:
            logger.info("Table model is not initialized. Skipping column width initialization.")
            return

        header = self.file_table_view.horizontalHeader()

        # 열 개수 가져오기
        column_count = self.table_model.columnCount(QModelIndex())
        icon_size = 40 if language_settings.current_locale == "kr" else 55

        # 아이콘 열 고정 크기 설정
        icon_columns = [0, 8, 9, 10, 11, 12]
        for column in icon_columns:
            header.setSectionResizeMode(column, QHeaderView.Fixed)
            header.resizeSection(column, icon_size)

        # 나머지 열 기본 너비 설정
        self.file_table_view.setColumnWidth(1, 220)
        self.file_table_view.setColumnWidth(2, 100)
        self.file_table_view.setColumnWidth(3, 60)
        self.file_table_view.setColumnWidth(4, 50)
        self.file_table_view.setColumnWidth(5, 50)
        self.file_table_view.setColumnWidth(6, 100)
        self.file_table_view.setColumnWidth(7, 100)

        # 최소 너비, 이동 방지 설정
        header.setMinimumSectionSize(36)
        header.setSectionsMovable(False)  # 헤더 이동 방지
        header.setStretchLastSection(False)  # 마지막 열 확장 방지

        logger.info("Column widths successfully initialized.")

class CustomTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        
    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid():
            self.parent().on_file_clicked(index, event)