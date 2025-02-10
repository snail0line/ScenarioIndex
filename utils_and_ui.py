from PyQt5.QtGui import QIcon, QPixmap, QImage
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import QSize
import os
import image_data
import re
import zipfile
from loguru import logger


class JapaneseZipHandler:
    # 한글, 일본어 문자 범위 정의
    HANGUL_RANGE = re.compile(r'[\uAC00-\uD7AF]')
    HIRAGANA_RANGE = re.compile(r'[\u3040-\u309F]')
    KATAKANA_RANGE = re.compile(r'[\u30A0-\u30FF]')
    KANJI_RANGE = re.compile(r'[\u4E00-\u9FFF]')
    VALID_FILENAME = re.compile(r'^[\u0020-\u007E\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]+$')

    def __init__(self, zip_path):
        self.zip_path = zip_path
        self._zip_ref = None
        self.encoding = None

    def __enter__(self):
        self._zip_ref = zipfile.ZipFile(self.zip_path, 'r')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._zip_ref:
            self._zip_ref.close()

    def detect_filename_encoding(self):
        """ZIP 파일의 파일명 인코딩을 감지"""
        try:
            # UTF-8 플래그 확인
            for info in self._zip_ref.filelist:
                if info.flag_bits & 0x800:
                    logger.debug("ZIP uses UTF-8 for filenames")
                    self.encoding = 'utf-8'
                    return 'utf-8'

            # 테스트용 샘플 파일명 추출
            sample_name = self._zip_ref.namelist()[0]
            raw_bytes = sample_name.encode('cp437')  # ZIP의 기본 인코딩으로 변환

            # 일본어 인코딩 우선 시도
            for enc in ['cp932', 'shift_jis', 'euc_jp']:
                try:
                    decoded = raw_bytes.decode(enc)
                    if any([
                        self.HIRAGANA_RANGE.search(decoded),
                        self.KATAKANA_RANGE.search(decoded),
                        self.KANJI_RANGE.search(decoded)
                    ]):
                        logger.debug(f"Detected {enc} encoding")
                        self.encoding = enc
                        return enc
                except UnicodeDecodeError:
                    continue

            logger.debug("Falling back to cp437")
            self.encoding = 'cp437'
            return 'cp437'

        except Exception as e:
            logger.error(f"Error detecting encoding: {e}")
            self.encoding = 'cp437'
            return 'cp437'

    def get_real_filename(self, filename):
        """실제 파일명 가져오기 (wsm, summary.xml만 확인)"""
        # 필요한 확장자만 처리
        if not filename.lower().endswith(('.wsm', 'summary.xml')):
            return filename  # 원래 이름 그대로 반환

        if not self.encoding:
            self.detect_filename_encoding()

        try:
            # cp437로 인코딩된 바이트로 변환 후 실제 인코딩으로 디코딩
            raw_bytes = filename.encode('cp437')
            decoded = raw_bytes.decode(self.encoding)
            
            if self.VALID_FILENAME.match(decoded):
                return decoded

            # 백업 인코딩 시도
            for backup_enc in ['cp932', 'shift_jis', 'euc_jp', 'utf-8']:
                if backup_enc == self.encoding:
                    continue
                try:
                    backup_decoded = raw_bytes.decode(backup_enc)
                    if self.VALID_FILENAME.match(backup_decoded):
                        logger.debug(f"Backup decode successful with {backup_enc}: {backup_decoded}")
                        return backup_decoded
                except UnicodeDecodeError:
                    continue

        except UnicodeDecodeError as e:
            logger.error(f"Decoding error: {e}")
        
        return filename  # 디코딩 실패 시 원래 이름 반환

    def get_real_filename_for_txt(self, filename):
        """.txt 파일만 디코딩하여 실제 파일명 반환"""
        if not filename.lower().endswith(".txt"):
            return None  # .txt 파일이 아니면 무시

        if not self.encoding:
            self.detect_filename_encoding()

        try:
            # ✅ cp437로 인코딩된 바이트로 변환 후 self.encoding으로 디코딩
            raw_bytes = filename.encode('cp437')  # cp437로 인코딩 시도
            decoded = raw_bytes.decode(self.encoding)
            
            if self.VALID_FILENAME.match(decoded):
                return decoded

            # ✅ 백업 인코딩 순차적으로 시도
            for backup_enc in ['cp932', 'shift_jis', 'euc_jp', 'utf-8']:
                if backup_enc == self.encoding:
                    continue
                try:
                    backup_decoded = raw_bytes.decode(backup_enc)
                    if self.VALID_FILENAME.match(backup_decoded):
                        logger.debug(f"Backup decode successful with {backup_enc}: {backup_decoded}")
                        return backup_decoded
                except UnicodeDecodeError:
                    continue

        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            pass

        return filename  # 디코딩 실패 시 원래 이름 반환



    def list_contents(self):
        """ZIP 내용물 리스트 반환"""
        return [(name, self.get_real_filename(name)) for name in self._zip_ref.namelist()]


def to_half_width(text: str) -> str:
    """전각 문자를 반각 문자로 변환."""
    return ''.join(
        chr(ord(c) - 0xFEE0) if 0xFF01 <= ord(c) <= 0xFF5E else c
        for c in text
    )

def to_full_width(text: str) -> str:
    return ''.join(
        chr(ord(c) + 0xFEE0) if 0x21 <= ord(c) <= 0x7E else c
        for c in text
    )

def get_icon(keyword):
    """키워드에 따라 QIcon 객체를 반환합니다."""
    base_path = os.path.abspath(".")
    assets_path = os.path.join(base_path, "assets")  # ✅ assets 폴더 포함
    icon_paths = {
        "summary": "Summary.png",
        "coupon": "Coupon.png", 
        "folder": "Folder.png", 
        "info": "Info.png",
        "comp": "Compstamp.png",
        "search": "Search.png",
        "settings": "Settings.png",
        "refresh": "Refresh.png",
        "filter": "Filter.png"
    }

    if keyword in icon_paths:
        icon_path = os.path.join(assets_path, icon_paths[keyword])  # ✅ _MEIPASS/assets/파일.png 찾기
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        else:
            print(f"[WARNING] Icon file not found: {icon_path}")
            return QIcon()
    else:
        print(f"[DEBUG] Icon for '{keyword}' not found.")
        return QIcon()

def create_icon_button(
    icon_source,
    size=(38, 38),
    icon_size=(32, 32),
    tooltip="",
    on_click=None,
    get_icon_func=None
):
    """
    아이콘 버튼을 생성하는 유틸리티 함수

    Args:
        icon_source (str): 아이콘 리소스 이름
        size (tuple): 버튼 크기 (width, height)
        icon_size (tuple): 아이콘 크기 (width, height)
        tooltip (str): 버튼 툴팁
        on_click (function): 클릭 이벤트 핸들러
        get_icon_func (function): 아이콘을 가져오는 함수 (get_icon)

    Returns:
        QPushButton: 설정된 아이콘 버튼
    """
    button = QPushButton()
    
    # 아이콘 설정
    if get_icon_func:
        icon = get_icon_func(icon_source)
        if isinstance(icon, QPixmap):
            button.setIcon(QIcon(icon.scaled(icon_size[0], icon_size[1])))
        elif isinstance(icon, str):  # 문자열 경로인 경우 QIcon 생성
            button.setIcon(QIcon(icon))
        elif isinstance(icon, QIcon):  # 이미 QIcon 객체인 경우
            button.setIcon(icon)
        else:
            raise ValueError(f"Unsupported icon type: {type(icon)}")
    
    # 버튼 속성 설정
    button.setIconSize(QSize(icon_size[0], icon_size[1]))
    button.setFixedSize(size[0], size[1])
    
    if tooltip:
        button.setToolTip(tooltip)
    
    if on_click:
        button.clicked.connect(lambda: on_click())
    
    return button

def get_mark_pixmap(mark_id):
    """
    mark_id (int): 00~30 사이의 마크 ID
    -> 해당 마크 이미지를 QPixmap으로 변환하여 반환
    """
    key = f"mark{mark_id:02d}"
    if key in image_data.image_data:
        byte_data = bytes(image_data.image_data[key])  # 리스트를 바이트로 변환
        image = QImage()
        image.loadFromData(byte_data)
        return QPixmap.fromImage(image)
    else:
        return None  # 이미지가 없으면 None 반환
