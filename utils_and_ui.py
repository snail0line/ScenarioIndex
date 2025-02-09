from PyQt5.QtGui import QIcon, QPixmap, QImage
from PyQt5.QtWidgets import QPushButton
from PyQt5.QtCore import QSize
import os
import image_data


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
