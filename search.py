#2024-01-11 00:05 마지막 수정 - 고급 검색 완벽 구현!!!!!!!

from PyQt5.QtWidgets import (QDialog, QListWidget, QCheckBox, 
                           QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, 
                           QLineEdit, QLabel, QFrame, QScrollArea,
                           QWidget, QGridLayout, QMessageBox)
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QIcon, QImage, QPixmap
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from loguru import logger
from utils_and_ui import to_half_width, to_full_width
from languages import language_settings


class FilterType(Enum):
    TEXT = "text"
    CHOICES = "choices"
    BOOLEAN = "boolean"
    PATTERN = "pattern"
    TAGS = "tags"

@dataclass
class FilterValue:
    type: FilterType
    values: List[Any]
    enabled: bool = True
    operator: str = "contains"

    def is_empty(self) -> bool:
        return not bool(self.values)

class DatabaseError(Exception):
    """데이터베이스 관련 예외"""
    pass

@dataclass
class ColumnDefinition:
    """컬럼 정의를 위한 데이터 클래스"""
    label: str
    filter_type: FilterType
    choices: Optional[List[str]] = None
    description: Optional[str] = None
    patterns: Optional[List[str]] = None
    validation: Optional[callable] = None

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

class SearchManager:
    """검색 관리 클래스"""
    def __init__(self, db, language_settings, current_language, folder_path=None, page_size=30):
        self.db = db
        self.language_settings = language_settings
        self.current_language = current_language  # 현재 언어
        self.folder_path = folder_path
        self.page_size = page_size

        # 검색 결과 및 페이지 관련 데이터
        self.search_results = []  # 검색 결과 저장
        self.total_results = 0  # 검색된 전체 결과 수
        self.current_page = 1  # 현재 페이지
        self.total_pages = 1  # 전체 페이지 수


    def set_folder_path(self, folder_path: Path) -> None:
        self.folder_path = folder_path
        logger.debug(f"Folder path set to: {folder_path}")
    

    def run_query(self, query: str, params: tuple) -> List[Dict[str, Any]]:
        """SQL 쿼리를 실행하고 결과를 리스트로 반환합니다.""" 
        try:
            self.db.cursor.execute(query, params)
            results = [dict(row) for row in self.db.cursor.fetchall()]  # 결과를 리스트로 변환
            logger.debug(f"Query returned {len(results)} results.")
            return results
        except Exception as e:
            logger.error(f"Query execution failed: {query}, params: {params}, error: {str(e)}")
            raise DatabaseError(f"Database query failed: {str(e)}")


    def generate_transforms(self, value: str) -> List[str]:
        """입력 값을 기반으로 대소문자, 전각/반각 변환된 값의 리스트를 생성"""
        if not value:
            return []

        transforms = set([
            value,  # 원본
            to_half_width(value),  # 반각
            to_full_width(value),  # 전각
            value.lower(),  # 소문자
            value.upper(),  # 대문자
            to_half_width(value).lower(),
            to_half_width(value).upper(),
            to_full_width(value).lower(),
            to_full_width(value).upper()
        ])
        return [t for t in transforms if t]  # 빈 값 제거


    def basic_search(self, search_term: str, field: str = "all") -> List[Dict[str, Any]]:
        if not self.folder_path:
            raise ValueError("Folder path is not set")

        if not search_term:
            # 검색어가 없을 경우 예외 발생
            raise ValueError("Search term is required. Please enter a search term.")
        
        # 검색어가 있을 경우 검색 로직 실행
        search_value = f"%{search_term.lower()}%"
        query, params = self._build_basic_search_query(field, search_value)
        search_results = self.run_query(query, params)
        return search_results


    def _build_basic_search_query(self, field: str, search_value: str) -> Tuple[str, tuple]:
        # 모든 가능한 변환 생성
        transforms = self.generate_transforms(search_value)

        # 동적 쿼리 생성
        base_query = "SELECT * FROM file_data WHERE "
        fields = ["title", "author", "description"]
        
        # 복합 OR 조건 생성
        conditions = []
        params = []
        
        for transform in transforms:
            field_conditions = " OR ".join([f"{field} LIKE ?" for field in fields])
            conditions.append(f"({field_conditions})")
            params.extend([f"%{transform}%" for _ in fields])

        query = base_query + " OR ".join(conditions)
        return query, tuple(params)



    def advanced_search(self, filters: Dict[str, FilterValue]) -> List[Dict[str, Any]]:
        """필터를 사용하여 고급 검색을 수행하고 검색 결과를 페이지네이션에 맞게 관리합니다."""
        
        conditions = []
        values = []

        # 필터 조건 생성
        for field, filter_value in filters.items():
            if not filter_value.enabled or not filter_value.values:
                continue

            if field == 'file_tags':
                # 태그 필터 처리
                tag_query, tag_params = self.build_tag_query(filter_value.values, filter_value.operator)
                if tag_query:
                    conditions.append(tag_query)
                    values.extend(tag_params)
            else:
                query_part, params = self._build_filter_query(field, filter_value.values)
                logger.debug(f"Generated query part for Field: {field}: {query_part}, params: {params}")
                if query_part:
                    conditions.append(query_part)
                    values.extend(params)

        # 기본 SQL 쿼리 생성
        query = "SELECT * FROM file_data"
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"

        # 검색 결과 가져오기
        search_results = self.run_query(query, tuple(values))
        self.search_results = search_results
        return search_results


    def build_tag_query(self, tags: List[str], operator: str) -> tuple:
        """태그 검색을 위한 SQL 쿼리 생성"""
        logger.debug("Building tag query")
        if not tags:
            return "", []

        if operator == 'empty':
            # 태그가 비어 있는 경우 검색
            query = "file_tags IS NULL OR json_array_length(file_tags) = 0"
            logger.debug(f"Empty tag query: {query}")
            return query, []

        if operator == 'contains':
            # 태그가 JSON 배열 내에 존재하는 경우 검색
            conditions = []
            params = []
            for tag in tags:
                conditions.append("EXISTS (SELECT 1 FROM json_each(file_tags) WHERE json_each.value = ?)")
                params.append(tag)
            query = f"file_tags IS NOT NULL AND {' AND '.join(conditions)}"
            logger.debug(f"Contains tag query: {query} with params: {params}")
            return query, params

        elif operator == 'not_contains':
            # 태그가 JSON 배열 내에 없는 경우 검색
            conditions = []
            params = []
            for tag in tags:
                conditions.append("NOT EXISTS (SELECT 1 FROM json_each(file_tags) WHERE json_each.value = ?)")
                params.append(tag)
            query = f"file_tags IS NULL OR {' AND '.join(conditions)}"
            logger.debug(f"Not contains tag query: {query} with params: {params}")
            return query, params

        return "", []


    def _build_filter_query(self, field: str, values: List[Any]) -> Tuple[str, List[Any]]:
        if not values:
            return "", []
            
        field_conditions = []
        params = []
        
        for value in values:
            condition, value_params = self._build_single_value_query(field, value)
            if condition:
                field_conditions.append(condition)
                params.extend(value_params)
        
        if not field_conditions:
            return "", []
            
        return f"({' OR '.join(field_conditions)})", params
    
    
    def _build_single_value_query(self, field: str, value: Any) -> Tuple[str, List[Any]]:
        """단일 필터 값에 대한 SQL 쿼리 부분 생성"""
        logger.debug(f"Building query for field: {field}, value: {value}, type: {type(value)}")

        if field == 'mark':
            return "mark = ?", [value]
            
        elif field == 'level':
            if isinstance(value, str):
                if '~' in value:
                    # 범위 검색 처리
                    try:
                        min_level, max_level = map(int, value.split('~'))
                        return (
                            "(level_min <= ? AND level_max >= ?)",
                            [max_level, min_level]
                        )
                    except ValueError:
                        # 범위 값 오류 메시지
                        QMessageBox.warning(
                            None, 
                            language_settings.translate("search.error_title"), 
                            language_settings.translate("search.error_range")
                        )
                        return "", []
                else:
                    # 단일 값 검색 처리
                    try:
                        single_level = int(value)
                        return (
                            "(level_min <= ? AND level_max >= ?)",
                            [single_level, single_level]
                        )
                    except ValueError:
                        # 단일 값 오류 메시지
                        QMessageBox.warning(
                            None, 
                            language_settings.translate("search.error_title"), 
                            language_settings.translate("search.error_single")
                        )
                        return "", []
            
        elif field == 'coupon_number':
            # coupon_number 값 처리
            try:
                if int(value) == 0:
                    query = f"{field} = ?"
                    params = [0]
                else:
                    query = f"{field} > ?"
                    params = [0]
                logger.debug(f"Coupon query for {field}: {query}, params: {params}")  # 디버깅 출력
                return query, params
            except ValueError:
                logger.debug(f"Invalid value for {field}: {value}")  # 디버깅 출력
                return "", []

        elif field == 'is_completed':
            # Boolean 값 처리
            try:
                query = f"{field} = ?"
                params = [int(value)]
                logger.debug(f"Boolean query for {field}: {query}, params: {params}")  # 디버깅 출력
                return query, params
            except ValueError:
                logger.debug(f"Invalid value for {field}: {value}")  # 디버깅 출력
                return "", []
            
        elif field == 'version':
            if value == language_settings.translate("version.og"):
                value = "OG"
            return f"{field} = ?", [value]  

        elif field == 'play_time':
            # 플레이 타임 옵션 처리
            if value == "":
                # 빈값이 선택된 경우, NULL 값 처리
                return "play_time IS NULL OR play_time = ''", []
            else:
                return "play_time = ?", [value]
            
        elif field == 'limit_value':
            query, params = self._build_limit_value_query(value)
            return f"({query})", params
            
        elif field in ["title", "author", "description"]:
            transforms = self.generate_transforms(value)

            # OR 조건 생성
            conditions = [f"LOWER({field}) LIKE ?" for _ in transforms]
            query = f"({' OR '.join(conditions)})"
            params = [f"%{transform}%" for transform in transforms]

            return query, params

        
    def _build_limit_value_query(self, limit_value: str) -> Tuple[str, List[Any]]:
        """limit_value에 대한 SQL 쿼리 생성"""
        conditions = []
        params = []

        def add_condition(sql_condition: str, *sql_params: Any):
            """조건과 파라미터를 추가하는 헬퍼 함수"""
            conditions.append(sql_condition)
            params.extend(sql_params)

        try:
            if limit_value == "0" or limit_value == "99":
                # 정확한 값
                add_condition("limit_value = ?", limit_value)

            elif limit_value.startswith("~"):
                # ~n 형식
                max_value = int(limit_value[1:])
                add_condition("limit_value LIKE '~%' AND CAST(SUBSTR(limit_value, 2) AS INTEGER) >= ?", max_value)

            elif limit_value.endswith("~"):
                # n~ 형식
                min_value = int(limit_value[:-1])
                add_condition("limit_value LIKE '%~' AND CAST(SUBSTR(limit_value, 1, LENGTH(limit_value) - 1) AS INTEGER) <= ?", min_value)

            elif "~" in limit_value:
                # n~m 형식
                min_value, max_value = map(int, limit_value.split("~"))
                add_condition("""
                    (limit_value LIKE '%~%' AND
                        CAST(SUBSTR(limit_value, 1, INSTR(limit_value, '~') - 1) AS INTEGER) <= ? AND
                        CAST(SUBSTR(limit_value, INSTR(limit_value, '~') + 1) AS INTEGER) >= ?) OR
                    (limit_value LIKE '~%' AND CAST(SUBSTR(limit_value, 2) AS INTEGER) >= ?) OR
                    (limit_value LIKE '%~' AND CAST(SUBSTR(limit_value, 1, LENGTH(limit_value) - 1) AS INTEGER) <= ?) OR
                    (limit_value BETWEEN ? AND ?)
                """, max_value, min_value, max_value, min_value, min_value, max_value)

            else:
                # 단일 값 n
                single_value = int(limit_value)
                add_condition("""
                    (limit_value = ?) OR
                    (limit_value LIKE '~%' AND CAST(SUBSTR(limit_value, 2) AS INTEGER) >= ?) OR
                    (limit_value LIKE '%~%' AND
                        CAST(SUBSTR(limit_value, 1, INSTR(limit_value, '~') - 1) AS INTEGER) <= ? AND
                        CAST(SUBSTR(limit_value, INSTR(limit_value, '~') + 1) AS INTEGER) >= ?) OR
                    (limit_value LIKE '%~' AND CAST(SUBSTR(limit_value, 1, LENGTH(limit_value) - 1) AS INTEGER) <= ?) OR
                    (limit_value BETWEEN ? AND ?)
                """, single_value, single_value, single_value, single_value, single_value, single_value, single_value)

        except ValueError as e:
            logger.error(f"Invalid limit_value format: {limit_value}. Error: {e}")
            return "", []

        query = " OR ".join(conditions)
        return query, params


class AdvancedSearchWindow(QDialog):
    searchCompleted = pyqtSignal(list)
    def __init__(self, parent=None, search_manager=None):
        super().__init__(parent)
        self.search_manager = search_manager
        self.file_viewer = parent.file_viewer if parent else None
        self.filter_widgets = []

        self.current_language = language_settings.current_locale
        self.SEARCH_LABELS = language_settings.translate("search.button")
        self.columns = self.get_columns()
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self._setup_ui()

    def _create_column(self, label_key: str, filter_type: FilterType, **kwargs):
        """
        ColumnDefinition 생성을 위한 헬퍼 메서드.
        언어별로 컬럼 이름, description, 그리고 특정 choices 번역 적용.
        """
        # 컬럼 이름 번역
        label = language_settings.translate(f"headers.{label_key}", label_key)

        # 특정 choices 번역
        if "choices" in kwargs:
            if label_key == "time":  # play_time의 경우 언어별 번역 적용
                play_time_options = language_settings.get_play_time_options()
                kwargs["choices"] = [
                    play_time_options.get(choice, choice) for choice in kwargs["choices"]
                ]
            else:
                translated_choices = []
                for choice in kwargs["choices"]:
                    if choice == "OG":
                        # "OG"만 version.og 키를 사용하여 번역
                        translated_choices.append(
                            language_settings.translate(f"version.og", choice)
                        )
                    else:
                        # 나머지는 그대로
                        translated_choices.append(choice)
                kwargs["choices"] = translated_choices

        return ColumnDefinition(label=label, filter_type=filter_type, **kwargs)


    def get_columns(self) -> dict:
        """컬럼 설정을 언어별로 가져오기"""
        return {
            "title": self._create_column("title", FilterType.TEXT),
            "author": self._create_column("author", FilterType.TEXT),
            "description": self._create_column("summary", FilterType.TEXT),
            "version": self._create_column("version", FilterType.CHOICES, choices=["OG", "NEXT", "Py"]),
            "level": self._create_column("level", FilterType.TEXT),
            "limit_value": self._create_column("limit", FilterType.PATTERN, patterns=["n", "n~", "~n", "n~m"]),
            "play_time": self._create_column(
                "time",
                FilterType.CHOICES,
                choices=list(language_settings.get_play_time_options().keys()),  # 키만 가져옴
            ),
            "coupon_number": self._create_column("coupon", FilterType.BOOLEAN),
            "is_completed": self._create_column("completed", FilterType.BOOLEAN),
            "mark": self._create_column("mark", FilterType.PATTERN, patterns=["markNN"]),
            "file_tags": self._create_column("tags", FilterType.TAGS),
        }

    def _setup_ui(self):
        self.setWindowTitle(language_settings.translate("search.advanced_search"))
        self.resize(900, 650)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        scroll_container = QWidget()
        grid_layout = QGridLayout(scroll_container)
        grid_layout.setSpacing(10)
        grid_layout.setContentsMargins(10, 10, 10, 10)

        # 필터 위젯 생성
        columns_items = list(self.columns.items())
        for idx in range(len(columns_items)):
            field_name, column_def = columns_items[idx]
            filter_widget = FilterWidget(field_name, column_def, self)
            self.filter_widgets.append(filter_widget)
            grid_layout.addWidget(filter_widget, idx // 3, idx % 3)  # 3열 기준

        scroll_area = QScrollArea()
        scroll_area.setWidget(scroll_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        search_btn = QPushButton(language_settings.translate("search.button"))
        search_btn.clicked.connect(lambda : self.execute_search())
        search_btn.setFixedHeight(30)
        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
        """)

        main_layout.addWidget(scroll_area)
        main_layout.addWidget(search_btn)


    def get_filters(self) -> Dict[str, FilterValue]:
        """필터 값 수집"""
        logger.debug("Starting filter value collection")
        filters = {}

        for widget in self.filter_widgets:
            # 각 위젯에서 필터 값 가져오기
            filter_value = widget.get_filter_value()

            if filter_value:  # 값이 있는 경우 필터 추가
                filters[widget.field_name] = filter_value

        logger.debug(f"Collected filter values: {filters}")
        return filters


    def execute_search(self):
        try:
            filters = self.get_filters()
            self.search_manager.advanced_search(filters)

            # 검색 결과 전달
            if self.search_manager.search_results:
                logger.debug(f"Search completed with {len(self.search_manager.search_results)} results.")
                self.searchCompleted.emit(self.search_manager.search_results)  # 검색 결과 전달
            else:
                logger.debug("No search results found.")
                self.searchCompleted.emit([])  # 빈 리스트 전달
            self.accept()

        except AttributeError as e:
            logger.error(f"Search manager 오류: {str(e)}")
            QMessageBox.critical(
                self,
                "Search Error", 
                "The search manager is not properly configured."  
            )
        except Exception as e:
            logger.error(f"검색 실행 실패: {str(e)}")
            QMessageBox.critical(
                self,
                "Search Error", 
                "An error occurred while executing the search."  
            )

class FilterButton(QPushButton):
    """필터 활성화/비활성화 버튼"""
    BUTTON_STYLE = """
        QPushButton {
            background-color: #f0f0f0;
            border: 1px solid #ccc;
            border-radius: 4px;
            padding: 8px 6px;
            text-align: left;
        }
        QPushButton:checked {
            background-color: #e0e0e0;
            border: 2px solid #666;
            padding: 6px 6px;
        }
    """

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setMinimumWidth(100)
        self.setStyleSheet(self.BUTTON_STYLE)

class FilterWidget(QWidget):
    """개별 필터 위젯"""
    valueChanged = pyqtSignal()
      
    def __init__(self, field_name: str, column_def: 'ColumnDefinition', parent=None):
        super().__init__(parent)
        self.field_name = field_name
        self.column_def = column_def
        self.is_active = False
        self.parent_window = self._find_parent_window_with_search_manager()

        if not self.parent_window:
            logger.warning(f"{field_name}: 부모 창에서 SearchManager를 찾을 수 없습니다.")
        
        self._setup_ui()
        self.setMinimumWidth(280)
        self.setMaximumWidth(280)

    def _setup_ui(self):
        """UI 구성"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 필터 버튼
        self.filter_button = FilterButton(self.column_def.label, self)
        self.filter_button.clicked.connect(self._on_button_toggled)
        layout.addWidget(self.filter_button)

        # 입력 위젯 생성 및 초기 비활성화
        self.input_widget = self._create_input_widget()
        if self.input_widget:
            self.input_widget.setEnabled(False)
            layout.addSpacing(5)
            layout.addWidget(self.input_widget)
        layout.addStretch()

    def _create_input_widget(self) -> Optional[QWidget]:
        """필터 타입에 따라 입력 위젯 생성"""
        widget_creators = {
            FilterType.TEXT: self._create_text_widget,
            FilterType.CHOICES: self._create_choices_widget,
            FilterType.BOOLEAN: self._create_boolean_widget,
            FilterType.PATTERN: self._create_pattern_widget,
            FilterType.TAGS: self._create_tags_widget,
        }
        return widget_creators.get(self.column_def.filter_type, lambda: None)()

    def _on_button_toggled(self, checked: bool):
        """필터 활성화 버튼 상태 변경"""
        self.is_active = checked
        if self.input_widget:
            self.input_widget.setEnabled(checked)


    def get_filter_value(self) -> Optional[FilterValue]:
        """필터 값 반환"""
        if not self.is_active:
            return None

        # 입력 값 수집
        values = self._collect_input_values()
        logger.debug(f"Filter {self.field_name}: Collected values: {values}")  # 디버깅용 출력

        if not values:
            logger.warning(f"Filter {self.field_name}: No values collected.")
            return None

        # operator 기본값 설정
        operator = "contains"
        if hasattr(self, "operator"):
            operator = self.operator

        return FilterValue(
            type=self.column_def.filter_type,
            values=values,
            operator=operator
        )


    def _collect_input_values(self) -> list:
        """입력값 수집 로직"""
        if isinstance(self.input_widget, QLineEdit):
            # QLineEdit의 텍스트 값 수집
            return [self.input_widget.text().strip()]
        elif hasattr(self, 'choice_boxes'):
            # 여러 체크박스가 있는 경우 선택된 값 수집
            return [cb.property('value') for cb in self.choice_boxes if cb.isChecked()]
        elif hasattr(self, 'min_spin'):
            # 숫자 범위(min_spin, max_spin) 처리
            return [f"{self.min_spin.value()}~{self.max_spin.value()}"]
        elif isinstance(self.input_widget, MultiSelectTagComboBox):
            # MultiSelectTagComboBox에서 선택된 태그 수집
            selected_tags = self.input_widget.get_selected_tags()
            if not selected_tags:
                logger.warning(f"{self.field_name} MultiSelectTagComboBox: 선택된 태그가 없습니다.")
            return selected_tags
        elif isinstance(self.input_widget, MarkComboBox):
            # MarkComboBox에서 선택된 마크 수집
            selected_marks = self.input_widget.get_selected_marks()
            if not selected_marks:
                logger.warning(f"{self.field_name} MarkComboBox: 선택된 마크가 없습니다.")
            return selected_marks
        elif isinstance(self.input_widget, QComboBox):
            # QComboBox의 선택된 값 수집
            value = self.input_widget.property("value")
            return [value] if value is not None else []
        return []

    def _find_parent_window_with_search_manager(self):
        """부모 창에서 search_manager를 찾는 함수"""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'search_manager'):
                return parent
            parent = parent.parent()
        return None

    def _create_text_widget(self) -> QLineEdit:
        widget = QLineEdit()
        widget.textChanged.connect(lambda: self.valueChanged())
        return widget

    def _create_choices_widget(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)  # QGridLayout으로 변경
        self.choice_boxes = []

        # 플레이 타임 옵션 가져오기
        if self.field_name == 'play_time':
            play_time_options = self.parent_window.search_manager.language_settings.get_play_time_options()
        else:
            play_time_options = None  # 다른 필터에는 필요 없음

        for idx, choice in enumerate(self.column_def.choices or []):
            if self.field_name == 'play_time':
                # 플레이 타임의 경우 번역된 레이블 사용
                translated_label = play_time_options.get(choice, choice)
            else:
                # 다른 필터는 원래 값을 사용
                translated_label = choice

            checkbox = QCheckBox(translated_label)
            checkbox.setProperty('value', choice)
            checkbox.toggled.connect(self.valueChanged)
            self.choice_boxes.append(checkbox)

            # 그리드에 배치 (2열로 배치 예제)
            layout.addWidget(checkbox, idx // 2, idx % 2)  # 행, 열 배치
        return widget

    def _create_boolean_widget(self) -> QComboBox:
        widget = QComboBox()

        # XML에서 텍스트 가져오기
        none_text = language_settings.translate("boolean_options.none")
        yes_text = language_settings.translate("boolean_options.yes")

        widget.addItems([none_text, yes_text])  # 드롭다운 항목 추가
        widget.setProperty("value", 0)  # 초기값 설정
        widget.currentIndexChanged.connect(lambda index: widget.setProperty("value", index))
        return widget
       
    def _create_pattern_widget(self) -> QWidget:
        if self.field_name == 'mark':
            return self._create_mark_widget()
        widget = QLineEdit()
        widget.setPlaceholderText(self.column_def.patterns[0])
        widget.textChanged.connect(lambda: self.valueChanged())
        return widget

    def _create_mark_widget(self) -> QWidget:
        if hasattr(self.parent_window.search_manager.db, 'mark_manager'):
            return MarkComboBox(self, mark_manager=self.parent_window.search_manager.db.mark_manager)

        #  에러 메시지 출력
        QMessageBox.warning(
            self,
            "Mark Manager Not Found",  # 제목
            "The mark manager could not be found. Please check the database connection.",  # 메시지 내용
            QMessageBox.Ok
        )

    def _create_tags_widget(self) -> Optional[QWidget]:
        if not self.parent_window:
            logger.warning("TAGS 필터 초기화 실패: 부모 창 없음")
            return None
        try:
            tag_widget = MultiSelectTagComboBox(self, db=self.parent_window.search_manager.db)
            tag_widget.setEnabled(False)
            self.filter_button.toggled.connect(tag_widget.setEnabled)
            return tag_widget
        except Exception as e:
            logger.error(f"TAGS 필터 초기화 중 오류: {e}")
            return None

class MarkComboBox(QComboBox):
    MAX_MARKS = 7  # 최대 선택 가능한 마크 수 설정

    def __init__(self, parent=None, mark_manager=None):
        super().__init__(parent)
        self.mark_manager = mark_manager
        self.popup = None
        self.selected_marks = set()

        self.setup_ui()

    def setup_ui(self):
        self.setFixedHeight(34)  # 테두리를 위한 여유 공간 포함
        self.setMinimumWidth(200)
        self.setStyleSheet("""
            QComboBox {
                border: 1px solid #ced4da;
                border-radius: 3px;
                padding: 1px;
                background-color: white;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: url(assets/down-arrow.png);
                width: 12px;
                height: 12px;
            }
        """)
        self.addItem("Select Mark...")


    def update_display(self):
        """선택된 마크들의 표시를 업데이트"""
        self.clear()
        
        if not self.selected_marks:
            self.addItem("Select Mark...")
            return

        # 모든 선택된 마크들의 아이콘을 결합하여 하나의 아이템으로 표시
        combined_icon = QIcon()
        pixmaps = []
        
        for mark_name in sorted(self.selected_marks):
            mark_image = self.mark_manager.get_mark_image(mark_name)
            if isinstance(mark_image, QImage):
                pixmap = QPixmap.fromImage(mark_image)
                pixmaps.append(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        if pixmaps:
            # 모든 마크를 하나의 pixmap에 그리기
            total_width = len(pixmaps) * 34  # 32px + 2px spacing
            result_pixmap = QPixmap(total_width, 32)
            result_pixmap.fill(Qt.transparent)
            
            painter = QPainter(result_pixmap)
            x = 0
            for pixmap in pixmaps:
                painter.drawPixmap(x, 0, pixmap)
                x += 34
            painter.end()
            
            self.addItem(QIcon(result_pixmap), "")
            self.setIconSize(QSize(total_width, 32))


    def showPopup(self):
        self.popup = QDialog(self)
        self.popup.setWindowTitle("Select Mark")
        self.popup.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        layout = QVBoxLayout(self.popup)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)

        # 안내 메시지 추가
        info_label = QLabel(f"* You can select up to {self.MAX_MARKS} marks.")
        info_label.setStyleSheet("color: #666;")
        layout.addWidget(info_label)

        # 마크 버튼 그리드
        grid_layout = QGridLayout()
        grid_layout.setSpacing(4)
        self.mark_buttons = {}

        for i in range(31):
            mark_name = f"mark{i:02d}"
            button = QPushButton()
            button.setFixedSize(32, 32)
            button.setCheckable(True)
            button.setChecked(mark_name in self.selected_marks)
            
            # 선택 제한 체크
            button.clicked.connect(lambda: self.check_mark_limit())
            
            mark_image = self.mark_manager.get_mark_image(mark_name)
            if isinstance(mark_image, QImage):
                pixmap = QPixmap.fromImage(mark_image)
                button.setIcon(QIcon(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                button.setIconSize(QSize(32, 32))

            self.mark_buttons[mark_name] = button
            grid_layout.addWidget(button, i // 6, i % 6)

        layout.addLayout(grid_layout)

        # 버튼 영역
        button_layout = QHBoxLayout()
        
        save_btn = QPushButton(language_settings.translate("save_changes"))
        save_btn.clicked.connect(lambda: self.save_selection())
        
        delete_btn = QPushButton(language_settings.translate("delete"))
        delete_btn.clicked.connect(lambda: self.clear_selection())
        
        cancel_btn = QPushButton(language_settings.translate("cancel"))
        cancel_btn.clicked.connect(lambda: self.popup.reject())
        
        button_layout.addWidget(save_btn)
        button_layout.addWidget(delete_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)

        self.popup.setFixedSize(self.popup.sizeHint())
        self.popup.exec_()


    def save_selection(self):
        """선택 사항 저장"""
        # 선택된 마크 개수 확인
        selected = {
            mark_name for mark_name, button in self.mark_buttons.items()
            if button.isChecked()
        }
        
        if len(selected) > self.MAX_MARKS:
            QMessageBox.warning(
                self.popup,
                "Selection Limit",
                f"You can select up to {self.MAX_MARKS} marks only."
            )
            return
            
        self.selected_marks = selected
        self.update_display()
        self.popup.accept()


    def clear_selection(self):
        """선택 초기화"""
        for button in self.mark_buttons.values():
            button.setChecked(False)


    def get_selected_marks(self) -> List[str]:
        """선택된 마크들 반환"""
        return list(self.selected_marks)


    def check_mark_limit(self):
        """Check mark selection limit"""
        selected_count = sum(1 for button in self.mark_buttons.values() if button.isChecked())
        if selected_count > self.MAX_MARKS:
            button = self.sender()
            if isinstance(button, QPushButton):
                button.setChecked(False)

class MultiSelectTagComboBox(QComboBox):
    tag_toggled = pyqtSignal()  # 태그 변경 시그널 정의

    def __init__(self, parent=None, db=None):
        super().__init__(parent)
        self.db = db
        self.selected_tags = set()
        self.temp_selected_tags = set()
        self.all_tags = []
        self.setup_ui()
        self.popup = None

    def setup_ui(self):
        self.setFixedHeight(34)  # 테두리를 위한 여유 공간 포함
        self.setMinimumWidth(200)
        self.setStyleSheet("""
            QComboBox {
                border: 1px solid #ced4da;
                border-radius: 3px;
                padding: 1px;
                background-color: white;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: url(assets/down-arrow.png);
                width: 12px;
                height: 12px;
            }
        """)
        self.addItem("Select Tag...")


    def load_tags(self):
        try:
            logger.debug("Starting to load tags...")
            if hasattr(self.db, 'tag_manager'):
                tags_data = self.db.tag_manager.fetch_tag_keys_with_translations()
                if not tags_data:  # 태그 데이터가 비어 있는 경우
                    logger.warning("Tag data is empty!")  # 디버깅 출력
                    self.all_tags = []
                    self.update_tag_list(self.all_tags)
                    return
                self.all_tags = [(tag_key, translation or tag_key) for tag_key, translation in tags_data]
                self.update_tag_list(self.all_tags)
                logger.debug(f"Successfully loaded {len(self.all_tags)} tags.")
            else:
                raise ValueError("TagManager does not exist in the database.")
        except Exception as e:
            logger.error(f"Error occurred while loading tags: {str(e)}")
            self.all_tags = []
            self.update_tag_list(self.all_tags)


    def update_tag_list(self, tags):
        """태그 목록 업데이트"""
        try:
            self.tag_selector.clear()
            for tag_key, translation in tags:
                self.tag_selector.addItem(translation)
        except Exception as e:
            logger.error(f"Error occurred while filtering tags: {str(e)}")


    def filter_tags(self, text):
        """검색어에 따라 태그 필터링"""
        try:
            # 대소문자 구분 없이 검색어 포함 여부 확인
            filtered_tags = [
                (tag_key, translation)
                for tag_key, translation in self.all_tags
                if text.lower() in translation.lower()
            ]
            self.update_tag_list(filtered_tags)
        except Exception as e:
            logger.error(f"Error occurred while updating the tag list: {str(e)}")


    def on_tag_clicked(self, item):
        """태그 목록에서 항목을 클릭할 때 호출"""
        try:
            tag_name = item.text()
            tag_key = next(
                (key for key, translation in self.all_tags if translation == tag_name),
                None
            )
            if tag_key:
                self.add_selected_tag(tag_key)
        except Exception as e:
            logger.error(f"Error occurred while processing tag click: {str(e)}")


    def showPopup(self):
        """기본 드롭다운 대신 커스텀 팝업을 표시"""
        if not self.popup:
            self.create_popup()  # 팝업 창 생성
        else:
            self.popup.show()


    def create_popup(self):
        try:
            self.popup = QDialog(self)
            self.popup.setWindowTitle("Select Tag")
            self.popup.setWindowFlags(Qt.Window | Qt.WindowCloseButtonHint)  # 독립적인 새 창 설정
            self.popup.setAttribute(Qt.WA_InputMethodEnabled, True)  # IME 활성화

            # 레이아웃 설정
            layout = QVBoxLayout(self.popup)
            layout.setSpacing(8)
            layout.setContentsMargins(10, 10, 10, 10)

            # 검색 필터 LineEdit 설정
            self.filter_input = QLineEdit(self.popup)
            self.filter_input.setPlaceholderText(language_settings.translate("tag_management.filter_placeholder"))
            self.filter_input.textChanged.connect(lambda: self.filter_tags())
            self.filter_input.setStyleSheet("""
                QLineEdit {
                    padding: 4px;
                    border: 1px solid #ced4da;
                    border-radius: 3px;
                    background: white;
                }
                QLineEdit:focus {
                    border: 1px solid #80bdff;
                    outline: none;
                }
            """)
            layout.addWidget(self.filter_input)

            # 태그 영역
            tag_area_layout = QHBoxLayout()

            # 태그 목록
            self.tag_selector = QListWidget(self.popup)
            self.tag_selector.setFixedWidth(200)
            self.tag_selector.setStyleSheet("""
                QListWidget {
                    border: 1px solid #ced4da;
                    background: white;
                }
                QListWidget::item {
                    padding: 4px;
                }
                QListWidget::item:hover {
                    background: #f8f9fa;
                }
            """)
            self.tag_selector.itemClicked.connect(lambda:self.on_tag_clicked())
            tag_area_layout.addWidget(self.tag_selector)

            # 선택된 태그 영역
            scroll_area = QScrollArea(self.popup)
            scroll_area.setWidgetResizable(True)
            self.selected_tags_container = QWidget()
            self.selected_tags_layout = QFlowLayout(self.selected_tags_container, h_spacing=8, v_spacing=8)
            scroll_area.setWidget(self.selected_tags_container)
            tag_area_layout.addWidget(scroll_area)

            layout.addLayout(tag_area_layout)

            # 버튼
            button_layout = QHBoxLayout()
            confirm_button = QPushButton(language_settings.translate("confirm"), self.popup)
            confirm_button.clicked.connect(lambda: self.on_confirm())
            cancel_button = QPushButton(language_settings.translate("cancel"), self.popup)
            cancel_button.clicked.connect(lambda: self.on_cancel())
            button_layout.addWidget(confirm_button)
            button_layout.addWidget(cancel_button)
            layout.addLayout(button_layout)

            logger.debug("Loading tag data...")

            # 태그 데이터 로드
            if self.db and hasattr(self.db, 'tag_manager'):
                self.load_tags()
                self.restore_selected_tags()
            else:
                raise ValueError("Tag manager not found.")

            # 새 창 크기 설정
            self.popup.resize(600, 400)
            self.popup.show()
            logger.debug("Popup displayed successfully.")

        except Exception as e:
            logger.error(f"Error occurred while creating popup: {str(e)}") 
            QMessageBox.warning(self, "Error", f"An error occurred while creating the popup: {str(e)}") 


    def cleanup_popup(self):
        """팝업 창이 닫힐 때 호출되는 정리 메서드""" 
        if hasattr(self, 'selected_tags_container'):
            self.selected_tags_container.deleteLater()
        if hasattr(self, 'filter_input'):
            self.filter_input.deleteLater()
        if hasattr(self, 'tag_selector'):
            self.tag_selector.deleteLater()


    def restore_selected_tags(self):
        """선택된 태그들을 팝업에 복원"""
        try:
            for tag_key in self.temp_selected_tags:
                self.display_tag_in_popup(tag_key)
        except Exception as e:
            logger.error(f"Error occurred while restoring tags: {str(e)}")


    def display_tag_in_popup(self, tag_key):
        """팝업에 태그 표시"""
        try:
            tag_label = QLabel(self.db.tag_manager.get_tag_display_name(tag_key))
            tag_label.setObjectName(tag_key)
            tag_label.setStyleSheet("""
                QLabel {
                    background-color: #ffdd94;
                    border-radius: 10px;
                    padding: 5px;
                    font-weight: bold;
                    color: black;
                }
            """)
            remove_button = QPushButton("×")
            remove_button.setFixedSize(10, 10)
            remove_button.setStyleSheet("background: transparent; color: black;")
            remove_button.clicked.connect(lambda: self.remove_selected_tag(tag_key))

            tag_container = QWidget(self.selected_tags_container)
            layout = QHBoxLayout(tag_container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(tag_label)
            layout.addWidget(remove_button)
            self.selected_tags_layout.addWidget(tag_container)
            
        except Exception as e:
            logger.error(f"Error occurred while displaying tags: {str(e)}")


    def on_confirm(self):
        """확인 버튼 클릭 시 호출"""
        try:
            if not hasattr(self, 'popup') or not self.popup:
                logger.error("Popup does not exist or has already been closed.")
                return

            if not self.temp_selected_tags:
                logger.warning("No tags selected.")
                QMessageBox.warning(self.popup, "Tag Selection", "No tags selected.")
                return

            # Update selected tags
            self.selected_tags = self.temp_selected_tags.copy()
            logger.debug(f"Selected tags updated: {self.selected_tags}")  #  Debugging added

            # Update display
            try:
                self.updateDisplay()
                logger.debug("Display update completed.")  #  Debugging added
            except Exception as e:
                logger.error(f"Error occurred while updating display: {str(e)}")
                QMessageBox.critical(self.popup, "Error", "An error occurred while updating the display.")
                return

            # Emit tag change event
            self.tag_toggled.emit()

            # Close popup
            self.popup.accept()
        except Exception as e:
            logger.error(f"Error occurred during confirmation: {str(e)}")
            QMessageBox.critical(self.popup, "Error", f"An error occurred during confirmation: {str(e)}")

            
    def on_cancel(self):
        """취소 버튼 클릭 시 호출"""
        self.temp_selected_tags = self.selected_tags.copy()
        self.popup.reject()


    def add_selected_tag(self, tag_key):
        """태그 선택"""
        if len(self.temp_selected_tags) >= 7:
            QMessageBox.warning(
                self.popup,
                "Selection Limit",
                "You can select up to 7 tags only."
            )
            return

        if tag_key in self.temp_selected_tags:
            return

        try:
            self.temp_selected_tags.add(tag_key)
            self.display_tag_in_popup(tag_key)
        except Exception as e:
            logger.error(f"Error occurred while adding tag: {str(e)}")


    def remove_selected_tag(self, tag_key):
            """태그 제거"""
            try:
                # 선택된 태그 위젯 제거
                for i in range(self.selected_tags_layout.count()):
                    widget = self.selected_tags_layout.itemAt(i).widget()
                    if widget and widget.findChild(QLabel).objectName() == tag_key:
                        self.selected_tags_layout.removeWidget(widget)
                        widget.deleteLater()
                        break
                # 선택된 태그 목록에서 제거
                self.temp_selected_tags.discard(tag_key)
                # 디스플레이 업데이트
                self.updateDisplay()
            except Exception as e:
                logger.error(f"Error occurred while removing tag: {str(e)}")


    def get_selected_tags(self) -> List[str]:
        """선택된 태그들을 반환"""
        return list(self.selected_tags)
    
    
    def updateDisplay(self):
        """선택된 태그를 콤보박스에 업데이트"""
        try:
            if not self.selected_tags:
                QMessageBox.warning(
                    None, 
                    "No Tags Selected", "No tags selected. Setting to default text."
                )
                self.setItemText(0, "Select Tag...")  # 첫 번째 항목 텍스트 변경
            else:
                # 선택된 태그 이름 리스트 생성
                tag_names = [
                    self.db.tag_manager.get_tag_display_name(tag) if self.db.tag_manager else tag
                    for tag in self.selected_tags
                ]
                logger.debug(f"Tag name list: {tag_names}")

                # 콤마로 구분된 문자열 생성
                display_text = ", ".join(tag_names)
                logger.debug(f"Text to be set in display: {display_text}")

                # 첫 번째 항목 텍스트를 업데이트
                self.setItemText(0, display_text)
        except Exception as e:
            logger.error(f"Error occurred while updating display: {str(e)}")