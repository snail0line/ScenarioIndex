from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QMessageBox, QHBoxLayout, QComboBox, QPushButton, QTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QImage, QColor
from loguru import logger
import chardet
import zipfile
import os
import json
import traceback
from file_scanner import load_image_data
from languages import language_settings
from utils_and_ui import JapaneseZipHandler

def sanitize_path(image_path):
    # Windows 경로에서 \을 /로 변환하되, 유니코드 문자가 손상되지 않도록 처리
    return image_path.replace("\\", "/") if "\\" in image_path and not image_path.startswith("\\u") else image_path

def set_font(family_kr, family_jp, size, lang):
    font_family = "batang" if lang == "kr" else "MS Mincho" if lang == "jp" else "Arial"
    font = QFont(font_family, size)
    font.setBold(True)
    return font

def make_background_transparent(pixmap):
    """
    이미지에서 배경색과 정확히 일치하는 픽셀만 투명화합니다.
    
    :param pixmap: 투명화할 QPixmap 객체
    :return: 투명화된 QPixmap
    """
    image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
    if image.isNull():
        logger.error("Failed to convert image.")
        return pixmap

    # 배경색을 왼쪽 상단 픽셀의 색상으로 설정
    background_color = QColor(image.pixel(0, 0))

    width, height = image.width(), image.height()

    # 모든 픽셀을 순회하면서 배경색과 정확히 일치하는 픽셀만 투명하게 만듭니다.
    for x in range(width):
        for y in range(height):
            if QColor(image.pixel(x, y)) == background_color:
                image.setPixelColor(x, y, QColor(255, 255, 255, 0))  # 투명화

    return QPixmap.fromImage(image)

def extract_images_from_wsn(file_path, image_paths):

    # JSON 문자열일 경우, 리스트로 변환
    if isinstance(image_paths, str):
        try:
            image_paths = json.loads(image_paths)
        except json.JSONDecodeError:
            logger.error("Error: Invalid JSON format for image_paths")
            return []

    images = []
    with zipfile.ZipFile(file_path, 'r') as wsn_file:
        for image_path in image_paths:
            if image_path in wsn_file.namelist():
                with wsn_file.open(image_path) as image_file:
                    image_data = image_file.read()
                    pixmap = QPixmap()
                    pixmap.loadFromData(image_data)
                    images.append(pixmap)
            else:
                logger.warning(f"Image not found: {image_path}")
    return images

def get_pixmap_from_image_data(file_path):
    """
    특정 파일의 이미지 데이터를 로드하여 QPixmap으로 반환합니다.
    """
    pixmap = QPixmap()
    
    # file_path가 파일인지 확인
    if not os.path.isfile(file_path):
        logger.error(f"Error: {file_path} is not a valid file path.")
        return None
    
    try:
        with open(file_path, 'rb') as file:
            image_data = file.read()
            pixmap.loadFromData(image_data)    
        return pixmap
    except Exception as e:
        logger.error(f"Error loading image data from {file_path}: {e}")
        return None

def detect_encoding(file_data):
    """파일 데이터를 기반으로 인코딩을 감지하는 함수"""
    result = chardet.detect(file_data)  
    encoding = result['encoding']

    if encoding is None:
        encoding = "utf-8"

    return encoding

class ScenarioDetailViewer(QDialog):
    def __init__(self, file_path, level_min, level_max, title, description, image_paths, position_types, lang, master=None):
        super().__init__(master)

        # description이 None인 경우 빈 문자열로 초기화
        if description is None:
            description = ''

        self.file_path = file_path
        self.level_min = level_min
        self.level_max = level_max
        self.title = title
        self.description = description
        self.image_paths = image_paths
        self.position_types = position_types
        self.lang = lang
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(400, 370)
        
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        base_path = os.path.abspath(".") 
        background_image_path = os.path.join(base_path, "assets", "Bill.png")  # 배경 이미지 경로 설정
        self.background_label = QLabel(self)  # 인스턴스 변수로 설정
        background_pixmap = QPixmap(background_image_path)
        self.background_label.setPixmap(background_pixmap)
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        self.background_label.setAlignment(Qt.AlignCenter)

        if isinstance(self.position_types, str):
            try:
                self.position_types = json.loads(self.position_types)  # JSON 문자열을 리스트로 변환
            except json.JSONDecodeError:
                logger.error("Error: Invalid JSON format for position_types")
                self.position_types = []

        if level_min and level_max and (level_min != "0" or level_max != "0"):
            translated_label = language_settings.translate("summary.level_label")  
            level_text = f"{translated_label} {level_min}" if level_min == level_max else f"{translated_label} {level_min}~{level_max}"
            
            level_label = QLabel(level_text, self)

            if language_settings.current_locale == "kr":
                font = QFont("batang", 10, QFont.Bold, italic=True)  # 한국어 폰트
            elif language_settings.current_locale == "jp":
                font = QFont("MS Mincho", 10, QFont.Bold, italic=True)  # 일본어 폰트
            else:
                font = QFont("Arial", 10, QFont.Bold, italic=True)  # 기본 폰트 (기타 언어)

            level_label.setFont(font)
            logger.debug(f"Applying font: {font.family()}")
            level_label.setStyleSheet("color: teal;")
            level_label.adjustSize()
            level_label.move((400 - level_label.width()) // 2, 15)
            level_label.show()

        title_label = QLabel(title, self)
        font = set_font("batang", "MS Mincho", 16, lang)
        font.setLetterSpacing(QFont.AbsoluteSpacing, -2)
        title_label.setFont(font)
        title_label.setStyleSheet("color: black;")
        title_label.adjustSize()
        title_label.move((400 - title_label.width()) // 2, 35)
        title_label.show()

        line_height = 15
        start_x, start_y = 65, 180
        description_lines = description.split('\\n')
        for i, line in enumerate(description_lines):
            description_label = QLabel(line, self)
            description_label.setFont(set_font("batang", "MS Mincho", 10, lang))
            description_label.setStyleSheet("color: black;")
            description_label.adjustSize()
            description_label.move(start_x, start_y + i * line_height)
            description_label.show()

        self.display_images()
        
    def display_images(self):
        overlay_photos = []

        # JSON 문자열일 경우, 리스트로 변환
        if isinstance(self.image_paths, str):
            try:
                self.image_paths = json.loads(self.image_paths)
            except json.JSONDecodeError:
                logger.error("Error: Invalid JSON format for image_paths")
                return

        # file_path가 폴더일 경우
        if os.path.isdir(self.file_path):
            for image_path in self.image_paths:
                sanitized_path = sanitize_path(image_path)
                full_image_path = os.path.join(self.file_path, sanitized_path)

                if os.path.isfile(full_image_path):
                    pixmap = get_pixmap_from_image_data(full_image_path)
                    if pixmap:
                        # PNG 파일이 투명하지 않으면 배경 투명화 처리
                        if full_image_path.lower().endswith('.png') and not pixmap.hasAlphaChannel():
                            transparent_image = make_background_transparent(pixmap)
                        else:
                            transparent_image = pixmap
                        overlay_photos.append(transparent_image)
                    else:
                        logger.error(f"[ERROR] Failed to load pixmap for {full_image_path}")
                else:
                    logger.warning(f"Image not found in folder: {full_image_path}")

        elif self.file_path.lower().endswith('.wsn') and self.image_paths:
            try:
                overlay_images = extract_images_from_wsn(self.file_path, self.image_paths)
                for overlay_image, image_path in zip(overlay_images, self.image_paths):
                    if image_path.lower().endswith(('.bmp', '.gif')):
                        transparent_image = make_background_transparent(overlay_image)
                    elif image_path.lower().endswith('.png') and not overlay_image.hasAlphaChannel():
                        transparent_image = make_background_transparent(overlay_image)
                    else:
                        transparent_image = overlay_image
                    overlay_photos.append(transparent_image)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to extract image from WSN file: {e}")
                return

        elif self.file_path.lower().endswith('.wsm'):
            image_data = load_image_data(self.file_path)

            if image_data:
                pixmap = QPixmap()
                load_success = pixmap.loadFromData(image_data)

                if load_success:
                    logger.info("Image loaded successfully from image_data.")
                    transparent_image = make_background_transparent(pixmap) if not pixmap.hasAlphaChannel() else pixmap
                    overlay_photos.append(transparent_image)
                else:
                    logger.error(f"Failed to create pixmap from image_data in file {self.file_path}.")
                    QMessageBox.critical(self, "Error", "Failed to load image data from WSM file.")
                    return
            else:
                logger.warning(f"Image data could not be loaded from {self.file_path}.")

        if not overlay_photos:
            logger.warning("No images to display.")
            return

        for i, overlay_photo in enumerate(overlay_photos):
            position_type = self.position_types[i] if i < len(self.position_types) else None
            image_label = QLabel(self)
            image_label.setPixmap(overlay_photo)
            image_label.setParent(self.background_label)
            if position_type == "Center":
                x = (400 - overlay_photo.width()) // 2
                y = (370 - overlay_photo.height()) // 2
            else:
                x, y = 163, 70
            image_label.move(x, y)
            image_label.show()

    def show_details(self):
        self.exec_()

class InfoDetailViewer(QDialog):
    def __init__(self, parent, file_name, file_path, lang):
        super().__init__(parent)
        self.file_name = file_name
        self.file_path = file_path
        self.scenario_folder = os.path.dirname(file_path)
        self.scenario_ext = os.path.splitext(file_path)[1]
        self.lang = lang
        self.txt_files = self.get_all_txt_files()
        self.font_size = 10
        self._setup_ui()

    def _setup_ui(self):
        """UI 설정"""
        self.setWindowTitle(f"Info - {self.file_name}")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(400, 300)

        layout = QVBoxLayout(self)

        # 상단 컨트롤 레이아웃
        top_layout = QHBoxLayout()

        # 파일 선택 드롭다운
        self.dropdown = QComboBox(self)
        self.populate_txt_list()  # 드롭다운에 파일 추가
        self.dropdown.currentIndexChanged.connect(self.on_file_selected)
        top_layout.addWidget(self.dropdown)

        # 폰트 크기 조절 버튼
        self.plus_button = QPushButton("+", self)
        self.plus_button.setFixedSize(20, 20)
        self.plus_button.clicked.connect(self.increase_font_size)
        top_layout.addWidget(self.plus_button)

        self.minus_button = QPushButton("-", self)
        self.minus_button.setFixedSize(20, 20)
        self.minus_button.clicked.connect(self.decrease_font_size)
        top_layout.addWidget(self.minus_button)

        layout.addLayout(top_layout)

        # 텍스트 영역
        self.text_area = QTextEdit(self)
        self.text_area.setReadOnly(True)
        self.set_font_by_lang()
        layout.addWidget(self.text_area)

        # 첫 번째 파일 자동 선택
        if self.dropdown.count() > 0:
            self.on_file_selected(0)
        else:
            self.text_area.setPlainText("No text files found.")

    def get_all_txt_files(self):
        """시나리오 폴더 또는 ZIP 내부의 모든 .txt 파일 반환"""
        txt_files = []

        if ".zip!" in self.file_path:
            zip_path, inner_file = self.file_path.split("!", 1)
            txt_files.extend(self._get_txt_files_from_zip(zip_path))

        elif self.scenario_ext == ".wsn":
            txt_files.extend(self._get_txt_files_from_zip(self.file_path))

        elif self.scenario_ext == ".wsm":
            txt_files.extend(self._get_txt_files_from_folder(self.scenario_folder))

        elif os.path.isdir(self.file_path):
            txt_files.extend(self._get_txt_files_from_folder(self.file_path))

        # ✅ 정렬 기준을 display 값으로 변경
        txt_files.sort(key=lambda x: ('read' not in x["display"].lower(), x["display"].lower()))
        return txt_files



    def _get_txt_files_from_zip(self, zip_path):
        """ZIP 파일 내 .txt 파일만 반환 (파일명 디코딩 적용)"""
        txt_files = []
        if zipfile.is_zipfile(zip_path):
            logger.debug(f"Scanning ZIP file for .txt files: {zip_path}")
            with JapaneseZipHandler(zip_path) as zip_handler:
                for orig_name in zip_handler._zip_ref.namelist():
                    if orig_name.lower().endswith(".txt"):  # ✅ .txt 파일만 필터링
                        decoded_name = zip_handler.get_real_filename_for_txt(orig_name)
                        if decoded_name:
                            logger.debug(f"Decoded name: {decoded_name}")
                            txt_files.append({
                                "original": f"{zip_path}!{orig_name}",
                                "display": decoded_name
                            })
        else:
            logger.warning(f"{zip_path} is not a valid ZIP file.")
        return txt_files


    def _get_txt_files_from_folder(self, folder_path):
        """폴더 내 .txt 파일 반환 (dict 형식으로 original과 display 분리)"""
        txt_files = []
        folder_path = os.path.normpath(folder_path)
        
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            for file in os.listdir(folder_path):
                if file.lower().endswith(".txt"):
                    full_path = os.path.join(folder_path, file).replace("\\", "/")
                    txt_files.append({
                        "original": full_path,       # 내부에서 사용할 전체 경로
                        "display": file              # 사용자에게 보여줄 파일명
                    })
        return txt_files

    def on_file_selected(self, index):
        """TXT 파일 선택 시 내용 로드"""
        selected_file = self.dropdown.itemData(index)  # 내부 경로 가져오기

        if ".zip!" in selected_file or ".wsn!" in selected_file:
            self.load_zip_txt_content(selected_file)
        else:
            self.load_file_content(selected_file)



    def populate_txt_list(self):
        """TXT 파일 리스트를 QComboBox에 추가"""
        txt_files = self.txt_files
        self.dropdown.clear()

        for file_info in txt_files:
            file_name = os.path.basename(file_info["display"])  # 파일명만 추출
            self.dropdown.addItem(file_name, file_info["original"])  # 파일명은 사용자에게 표시, original은 내부 데이터로 저장



    def load_zip_txt_content(self, file_path):
        """ZIP 내부의 TXT 파일을 불러오기"""
        try:
            path_parts = file_path.split("!")
            zip_path = path_parts[0]
            inner_file = path_parts[1]

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                with zip_ref.open(inner_file) as txt_file:
                    file_data = txt_file.read()
                    content = self.decode_file_data(file_data)  # 여러 인코딩 자동 감지
                    self.text_area.setPlainText(content)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Failed to open ZIP TXT file: {e}\nTraceback:\n{tb}")
            QMessageBox.critical(self, "Error", f"Failed to open ZIP TXT file: {e}")

    def load_file_content(self, file_path):
        """파일 내용을 불러와 텍스트 영역에 표시"""
        try:
            # ZIP 파일 내부일 경우 처리
            if "!" in file_path:
                zip_path, inner_file = file_path.split("!", 1)  # ZIP 경로와 내부 파일 경로 분리
                zip_path = os.path.normpath(zip_path).replace("\\", "/")  # 경로 정리

                if zipfile.is_zipfile(zip_path):
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        if inner_file.lower().endswith(".txt"):
                            with zip_ref.open(inner_file) as file:
                                file_data = file.read()
                                content = self.decode_file_data(file_data)  # 여러 인코딩 자동 감지
                                self.text_area.setPlainText(content)
                else:
                    logger.error(f"ZIP 파일을 열 수 없습니다: {zip_path}")
                    QMessageBox.critical(self, "Error", f"Failed to open ZIP file: {zip_path}")
                    return

            else:
                # 일반 파일일 경우
                with open(file_path, 'rb') as file:
                    file_data = file.read()
                    content = self.decode_file_data(file_data)  # 여러 인코딩 자동 감지
                    self.text_area.setPlainText(content)

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"Failed to open file: {e}\nTraceback:\n{tb}")
            QMessageBox.critical(self, "Error", f"Failed to open file: {e}")

    @staticmethod
    def decode_file_data(file_data):
        """파일 데이터를 여러 인코딩으로 디코딩"""
        encodings = ["utf-8", "shift_jis", "cp932", "euc-jp", "gb18030", "latin-1"]
        
        # 🔍 파일에서 BOM 확인 후 인코딩 결정
        if file_data.startswith(b'\xef\xbb\xbf'):
            return file_data.decode("utf-8-sig")  # UTF-8 BOM 제거
        elif file_data.startswith(b'\xff\xfe'):
            return file_data.decode("utf-16-le")  # UTF-16 LE
        elif file_data.startswith(b'\xfe\xff'):
            return file_data.decode("utf-16-be")  # UTF-16 BE
        
        # 🔍 기본 인코딩 감지 후 시도
        try:
            detected_encoding = detect_encoding(file_data)
            return file_data.decode(detected_encoding)
        except (UnicodeDecodeError, TypeError):
            pass

        # 🔄 여러 인코딩을 순차적으로 시도
        for enc in encodings:
            try:
                return file_data.decode(enc)
            except UnicodeDecodeError:
                continue

        # 🔴 모든 인코딩이 실패하면 오류 반환
        raise UnicodeDecodeError("모든 인코딩 시도 실패")

    def set_font_by_lang(self):
        """언어 코드에 따라 폰트를 설정하는 함수"""
        font = QFont("gulim" if self.lang == "kr" else "MS Gothic", self.font_size)
        self.text_area.setFont(font)
        self.dropdown.setFont(font)

    def increase_font_size(self):
        if self.font_size < 18:
            self.font_size += 2
            self.set_font_by_lang()

    def decrease_font_size(self):
        if self.font_size > 8:
            self.font_size -= 2
            self.set_font_by_lang()

    def show_details(self):
        """Info 창을 표시"""
        self.show()

class CouponDetailViewer(QDialog):
    def __init__(self, coupon_name):
        super().__init__()
        self.setWindowTitle(language_settings.translate("detail.coupon_title"))
        self.resize(200, 100)
        # 최대화 금지 적용
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)

        layout = QVBoxLayout()
        
        # 쿠폰 이름을 줄바꿈하여 라벨에 표시
        coupon_label = QLabel("\n".join(coupon_name.split('\\n')), self)
        coupon_label.setFont(QFont("Arial", 10))
        coupon_label.setAlignment(Qt.AlignCenter)  # 가운데 정렬
        coupon_label.setTextInteractionFlags(Qt.TextSelectableByMouse)  # 텍스트 복사 가능
        
        layout.addWidget(coupon_label)
        self.setLayout(layout)

