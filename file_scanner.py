#2024-11-10 22:11 마지막 수정 - file_path 형식 통일

import os
import zipfile
import xml.etree.ElementTree as ET
import chardet  # 인코딩 감지를 위한 라이브러리
import re
from typing import List, Union, Optional, Literal, Type, BinaryIO
import struct
import io
import types
from PyQt5.QtWidgets import QMessageBox
from loguru import logger

language_code = None


# ------------------------------------------------------------------------------
# k4nagatsuki님의 코드 사용
# ------------------------------------------------------------------------------


#MBCS = "mbcs" < 컴퓨터 언어가 한국어일 땐 안 돼서 인코딩을 CP932 (Shift-JIS)로 바꿔줌

def encodewrap(s: str) -> str:
    """改行コードを\nに置換する。"""
    r = []
    if not s:
        return ""
    for c in s:
        if c == '\\':
            r.append("\\\\")
        elif c == '\n':
            r.append("\\n")
        elif c == '\r':
            pass
        else:
            r.append(c)
    return "".join(r)

class CWFile(object):
    """CardWirthの生成したバイナリファイルを
    読み込むためのメソッドを追加したBufferedReader。
    import cwfile
    cwfile.CWFile("test/Area1.wid", "rb")
    とやるとインスタンスオブジェクトが生成できる。
    """
    def __init__(self, path: str, mode: str, decodewrap: bool = False,
                 f: Optional[BinaryIO] = None) -> None:
        if f:
            self._f: Union[BinaryIO, io.BufferedReader] = f
        else:
            self._f = io.BufferedReader(io.FileIO(path, mode))
        self.filename = path
        self.filedata: List[bytes] = []
        self.decodewrap = decodewrap

    def __enter__(self) -> "CWFile":
        self._f.__enter__()
        return self

    def __exit__(self, t: Optional[Type[BaseException]], value: Optional[BaseException],
                 traceback: Optional[types.TracebackType]) -> Literal[False]:
        self.close()
        return False

    def close(self) -> None:
        self._f.close()

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._f.seek(offset, whence)

    def boolean(self) -> bool:
        """byteの値を真偽値にして返す。"""
        if self.byte():
            return True
        else:
            return False

    def string(self, multiline: bool = False) -> str:
        """dwordの値で読み込んだバイナリをユニコード文字列にして返す。
        dwordの値が"0"だったら空の文字列を返す。
        改行コードはxml置換用のために"\\n"に置換する。
        multiline: メッセージテクストなど改行の有効なテキストかどうか。
        """
        s = self.rawstring()

        if multiline and not self.decodewrap:
            s = encodewrap(s)

        return s

    def rawstring(self) -> str:
        dword = self.dword()

        if dword:
            s = self.read(dword)
            return str(s, "cp932", "replace").strip("\x00")
        else:
            return ""

    def byte(self) -> int:
        """byteの値を符号付きで返す。"""
        raw_data = self.read(1)
        value: int = struct.unpack("b", raw_data)[0]
        return value

    def ubyte(self) -> int:
        """符号無しbyteの値を符号付きで返す。"""
        raw_data = self.read(1)
        value: int = struct.unpack("B", raw_data)[0]
        return value

    def dword(self) -> int:
        """dwordの値(4byte)を符号付きで返す。リトルエンディアン。"""
        raw_data = self.read(4)
        assert len(raw_data) == 4, len(raw_data)
        value: int = struct.unpack("<l", raw_data)[0]
        return value

    def word(self) -> int:
        """wordの値(2byte)を符号付きで返す。リトルエンディアン。"""
        raw_data = self.read(2)
        value: int = struct.unpack("<h", raw_data)[0]
        return value

    def image(self) -> Optional[bytes]:
        """dwordの値で読み込んだ画像のバイナリデータを返す。
        dwordの値が"0"だったらNoneを返す。
        """
        dword = self.dword()

        if dword:
            return self.read(dword)
        else:
            return None

    def read(self, n: Optional[int] = None) -> bytes:
        if n is None:
            assert self._f.seekable()
            pos = self._f.tell()
            self._f.seek(0, io.SEEK_END)
            endpos = self._f.tell()
            self._f.seek(pos, io.SEEK_SET)
            n = endpos - pos
        raw_data = self._f.read(n)
        self.filedata.append(raw_data)
        return raw_data


# SummaryFileReader 클래스 정의
from typing import List, Union, Optional

class SummaryFileReader:
    def __init__(self, f: "CWFile", file_path: str):
        self.file = f
        self.file_path = file_path  
        self.steps = [] 
        self.flags = []  

    def read_summary_data(self) -> List[Union[str, int]]:
        # 필수 데이터 추출
        image_data = self.file.image()
        name = self.file.string()
        description = self.file.string()
        author = self.file.string()
        required_coupons = self.file.string(True)
        required_coupons_num = self.file.dword()
        area_id = self.file.dword()

        # 버전 정보 및 area_id 조정
        if area_id <= 19999:
            version = 0
        elif area_id <= 39999:
            version = 2
            area_id -= 20000
        elif area_id <= 49999:
            version = 4
            area_id -= 40000
        else:
            version = 7
            area_id -= 70000

        # steps 데이터를 기존 방식으로 처리
        steps_num = self.file.dword()
        self.steps = [Step(self, self.file) for _ in range(steps_num)]  # 각 Step 객체 생성

        # flags 데이터를 기존 방식으로 처리
        flags_num = self.file.dword()
        self.flags = [Flag(self, self.file) for _ in range(flags_num)]  # 각 Flag 객체 생성

        # 불명 데이터 건너뛰기
        _ = self.file.dword()

        # level_min 및 level_max 읽기
        level_min = 0
        level_max = 0
        if version > 0:
            level_min = self.file.dword()
            level_max = self.file.dword()

        # extracted_info에 데이터 저장
        extracted_info = {
            'Name': name or 'Unknown',
            'Author': author or 'Unknown',
            'Level min': level_min,
            'Level max': level_max,
            'Version': "NEXT" if version == 7 else "OG",
            'description': description or '',
            'image_paths': [],  # wsm 파일의 경우 경로가 없으므로 빈 리스트
            'image': image_data,  # 이미지 데이터 직접 저장
            'position_types': [],  # 위치 타입 빈 리스트로 설정
            'RequiredCoupons': {
                'number': required_coupons_num,
                'name': required_coupons
            },
            'language_code': "jp"  # wsm 파일은 항상 jp
        }

        # 필요한 정보를 튜플로 반환
        return (
            extracted_info.get('Name', 'Unknown'),
            extracted_info.get('Author', 'Unknown'),
            extracted_info.get('Version', 'Py'),
            extracted_info.get('Level min', ''),
            extracted_info.get('Level max', ''),
            extracted_info['RequiredCoupons'].get('number', 0),  # 쿠폰 개수
            extracted_info['RequiredCoupons'].get('name', ''),   # 쿠폰 이름
            extracted_info['image_paths'],  # 이미지 경로 리스트로 반환
            extracted_info['position_types'],  # 위치 타입 리스트로 반환
            extracted_info['image'],  # 이미지 데이터 추가
            extracted_info.get('description', ''),
            extracted_info['language_code'],
            self.file_path  # file_path 추가
        )

# Step 및 Flag 클래스 정의 (이전과 동일하게 유지)
class Step:
    def __init__(self, parent: SummaryFileReader, f: "CWFile"):
        self.name = f.string()
        self.default = f.dword()
        self.variable_names = [f.string() for _ in range(10)]

class Flag:
    def __init__(self, parent: SummaryFileReader, f: "CWFile"):
        self.name = f.string()
        self.default = f.boolean()
        self.variable_names = [f.string() for _ in range(2)]


# ------------------------------------------------------------------------------
# ChatGPT 사용
# ------------------------------------------------------------------------------


# 한글, 히라가나, 가타카나 유니코드 범위
hangul_regex = re.compile(r'[\uAC00-\uD7AF]')
hiragana_regex = re.compile(r'[\u3040-\u309F]')
katakana_regex = re.compile(r'[\u30A0-\u30FF]')

def detect_language(text):
    # 문자 세트별 빈도 계산
    hangul_count = len(hangul_regex.findall(text))
    hiragana_count = len(hiragana_regex.findall(text))
    katakana_count = len(katakana_regex.findall(text))
    
    # 판별 로직
    if hangul_count > (hiragana_count + katakana_count):
        return "kr"
    elif hiragana_count > hangul_count or katakana_count > hangul_count:
        return "jp"
    else:
        return None

def decode_filename(name):
    try:
        encodings = ['utf-8', 'shift_jis', 'euc-jp', 'cp932']
        for encoding in encodings:
            try:
                result = name.encode('latin-1').decode(encoding, errors='replace')
                return result
            except (UnicodeDecodeError, UnicodeEncodeError):
                continue
        
        # chardet의 감지 결과를 시도
        detected = chardet.detect(name.encode('latin-1', errors='ignore'))
        if detected and detected['encoding']:
            detected_encoding = detected['encoding']
            try:
                return name.encode('latin-1', errors='ignore').decode(detected_encoding, errors='replace')
            except (UnicodeDecodeError, UnicodeEncodeError):
                logger.debug(f"[DEBUG] '{detected_encoding}' 인코딩 실패")
    except Exception as e:
        logger.error(f"파일명 디코딩 실패: {e}")
    
    return name  # 디코딩 실패 시 원본 그대로 반환

def read_with_encoding(file, file_path):
    raw_data = file.read()

    # XML 헤더에서 인코딩 추출
    header_text = raw_data[:100].decode("ascii", errors="ignore")  # ASCII로 인코딩 정보 추출
    encoding_match = re.search(r'encoding="([^"]+)"', header_text)
    
    if encoding_match:
        encoding = encoding_match.group(1)
    else:
        encoding = "utf-8"  # 기본 인코딩

    # 추출된 인코딩 또는 대체 인코딩 순차적으로 디코딩 시도
    try:
        decoded_text = raw_data.decode(encoding)
        return decoded_text
    except UnicodeDecodeError as e:
        try:
            decoded_text = raw_data.decode("CP932")
            return decoded_text
        except UnicodeDecodeError as e_cp932:
            return raw_data.decode("utf-8", errors="ignore")  # 최종 대체

def extract_info_from_scenario(file_path, file_name=None, zip_path=None, is_zip=False):
    """WSN, WSM 파일에서 정보를 추출 (ZIP 내부 포함)"""
    extracted_info = {}

    #  ZIP 내부 파일일 경우, zip_path를 사용하여 전체 경로 생성
    actual_file_path = f"{zip_path}!{file_name}" if is_zip else file_path

    is_wsn = file_name.lower().endswith('.wsn') if file_name else isinstance(file_path, str) and file_path.endswith('.wsn')
    is_wsm = file_name.lower().endswith('.wsm') if file_name else isinstance(file_path, str) and file_path.endswith('.wsm')

    #  WSN 파일 처리 (ZIP 내부가 아닌 경우만)
    if is_wsn and "!" not in file_path:  #  ZIP 내부 파일이면 무시
        try:
            with zipfile.ZipFile(file_path, 'r') as wsn_zip:
                xml_files = [decode_filename(name) for name in wsn_zip.namelist() if name.lower().endswith('.xml')]
                summary_file_name = next((f for f in xml_files if f.lower() == 'summary.xml'), None)

                if summary_file_name:
                    with wsn_zip.open(summary_file_name) as summary_file:
                        xml_data = read_with_encoding(summary_file, file_name)
                    extracted_info = parse_xml_data(xml_data)

                #  WSN 파일의 경우 version을 'Py'로 설정
                extracted_info['Version'] = 'Py'
                extracted_info['file_path'] = actual_file_path  #  WSN 파일 경로 유지
        except zipfile.BadZipFile:
            logger.error(f"[ERROR] '{file_path}'는 ZIP 형식이 아닙니다.")
            return {
                'Name': 'Unknown', 'Author': 'Unknown', 'Version': 'Py', 'Level min': '', 'Level max': '',
                'RequiredCoupons': {'number': 0, 'name': ''}, 'image_paths': [], 'position_types': [],
                'description': '', 'language_code': 'Unknown', 'file_path': actual_file_path
            }


    #  WSM 파일 처리 (ZIP 내부 또는 외부)
    elif is_wsm:
        try:
            if is_zip:
                # ZIP 내부의 WSM 파일을 바이너리로 읽음
                raw_data = file_path.read()
                f = CWFile(None, 'rb', f=io.BytesIO(raw_data))  # BytesIO로 변환 후 읽기
            else:
                # 일반 WSM 파일
                f = CWFile(file_path, 'rb')

            reader = SummaryFileReader(f, file_path)
            extracted_data = reader.read_summary_data()

            extracted_info = dict(zip(
                ['Name', 'Author', 'Version', 'Level min', 'Level max', 'RequiredCoupons_number', 
                 'RequiredCoupons_name', 'image_paths', 'position_types', 'image_data', 
                 'description', 'language_code', 'file_path'],
                extracted_data
            ))

            extracted_info['file_path'] = actual_file_path  #  ZIP 내부 파일이면 전체 경로 저장

        except Exception as e:
            logger.error(f"WSM 파일 처리 중 오류 발생: {e}")

    return extracted_info

def parse_summary_from_folder(folder_path: str, show_warning: bool = True) -> dict:
    external_summary_path = os.path.join(folder_path, 'Summary.xml')
    
    if not os.path.isfile(external_summary_path):
        # 경고 메시지 설정: show_warning이 True일 때는 QMessageBox, False일 때는 콘솔 출력
        if show_warning:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText(f"Unable to recognize the Summary.xml file in {folder_path}.")
            msg.setWindowTitle("File Recognition Error")
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
        else:
            logger.error(f"Unable to find the Summary.xml file in {folder_path}.")

        return default_extracted_info(folder_path)

    # Summary.xml 파일이 존재하는 경우: 데이터를 읽고 처리
    with open(external_summary_path, 'rb') as summary_file:
        xml_data = read_with_encoding(summary_file, external_summary_path)
    
    # XML 데이터 파싱 및 정보 추출
    extracted_info = parse_xml_data(xml_data)
    extracted_info['Version'] = 'Py'  # 폴더에서 찾은 경우 Version을 'Py'로 설정
    extracted_info['file_path'] = folder_path  # 폴더 경로로 file_path 설정
    return extracted_info

def default_extracted_info(file_path: str) -> dict:
    """
    기본 extracted_info 값을 반환
    """
    return {
        'Name': 'Unknown',
        'Author': 'Unknown',
        'Version': 'Py',
        'Level min': '',
        'Level max': '',
        'RequiredCoupons': {'number': 0, 'name': ''},
        'image_paths': [],
        'position_types': [],
        'image_data': None,
        'description': '',
        'language_code': 'Unknown',
        'file_path': file_path
    }

def parse_xml_data(xml_data: str) -> dict:
    extracted_info = {}
    try:
        # language_code를 xml_data에서 감지하여 설정
        language_code = detect_language(xml_data) or 'Unknown'
        
        root = ET.fromstring(xml_data)
        property_element = root.find('Property')
        if property_element is not None:
            extracted_info['Name'] = property_element.findtext('Name', default='Unknown')
            extracted_info['Author'] = property_element.findtext('Author', default='Unknown')
            level_element = property_element.find('Level')
            if level_element is not None:
                extracted_info['Level max'] = level_element.get('max', '')
                extracted_info['Level min'] = level_element.get('min', '')
            extracted_info['Version'] = 'Py'
            description_elem = property_element.find('Description')
            extracted_info['description'] = description_elem.text if description_elem is not None and description_elem.text else ''

            image_paths, position_types = [], []
            image_paths_elem = property_element.find('ImagePaths')
            if image_paths_elem is not None:
                for image_path_elem in image_paths_elem.findall('ImagePath'):
                    image_paths.append(image_path_elem.text)
                    position_types.append(image_path_elem.get('positiontype', ''))
            single_image_path_elem = property_element.find('ImagePath')
            if single_image_path_elem is not None:
                image_paths.append(single_image_path_elem.text)
                position_types.append(single_image_path_elem.get('positiontype', ''))
            extracted_info['image_paths'] = image_paths
            extracted_info['position_types'] = position_types

            required_coupons_elem = property_element.find('RequiredCoupons')
            if required_coupons_elem is not None:
                coupon_name = required_coupons_elem.text.strip() if required_coupons_elem.text else ''
                extracted_info['RequiredCoupons'] = {
                    'number': int(required_coupons_elem.attrib.get('number', 0)),
                    'name': coupon_name
                }
            else:
                extracted_info['RequiredCoupons'] = {'number': 0, 'name': ''}

        extracted_info['language_code'] = language_code

    except ET.ParseError as parse_error:
        logger.error(f"XML 파싱 실패: {parse_error}")
    
    return extracted_info

def find_files_with_content(folder_path):
    """주어진 폴더 경로에서 파일 정보를 스캔하고 반환"""
    files = []  # 파일 정보를 담을 리스트
    zip_files = []  # ZIP 파일을 따로 저장

    #  폴더 내 모든 파일 탐색 (ZIP 파일을 제외하고 먼저 처리)
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename).replace("\\", "/")  #  경로 슬래시 통일

            #  ZIP 파일은 나중에 처리하도록 리스트에 저장
            if filename.lower().endswith(".zip"):
                zip_files.append(file_path)
                continue  # ZIP 파일은 나중에 처리하도록 건너뛰기

            #  WSN 파일은 ZIP이지만, 바로 extract_info_from_scenario()로 전달
            if filename.lower().endswith(".wsn") or filename.lower().endswith(".wsm"):
                extracted_info = extract_info_from_scenario(file_path)  #  ZIP이지만 바로 처리
            elif filename.lower().endswith("summary.xml"):
                logger.debug(f"Processing Summary.xml file: {file_path}")
                with open(file_path, "rb") as xml_file:
                    xml_data = read_with_encoding(xml_file, file_path)
                    extracted_info = parse_xml_data(xml_data)
            else:
                continue  #  다른 파일들은 무시

            #  파일 수정 시간 가져오기 (변경 여부 확인용)
            modification_time = os.path.getmtime(file_path)

            if extracted_info:
                file_data = {
                    'file_path': extracted_info.get('file_path', file_path),
                    'title': extracted_info.get('Name', 'Unknown'),
                    'author': extracted_info.get('Author', 'Unknown'),
                    'version': extracted_info.get('Version', 'Py'),
                    'level_min': extracted_info.get('Level min', ''),
                    'level_max': extracted_info.get('Level max', ''),
                    'coupon_number': extracted_info.get('RequiredCoupons', {}).get('number', 0),
                    'coupon_name': extracted_info.get('RequiredCoupons', {}).get('name', ''),
                    'image_paths': extracted_info.get('image_paths', []),
                    'position_types': extracted_info.get('position_types', []),
                    'image_data': None,  # 기본적으로 None으로 설정
                    'description': extracted_info.get('description', ''),
                    'lang': extracted_info.get('language_code', 'Unknown'),
                    'modification_time': modification_time,
                    'limit_value': 0,  # 기본값 추가
                    'play_time': None,  # 기본값 추가
                    'mark': 'mark00',  # 기본값 추가
                    'tags': []  # 기본값 추가
                }
                
                files.append(file_data)

    #  ZIP 파일은 나중에 처리
    for zip_path in zip_files:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_contents = [decode_filename(name) for name in zip_ref.namelist()]
            logger.debug(f"Decoded ZIP Contents: {zip_contents}")

            for file_name in zip_contents:
                if file_name.lower().endswith(("summary.xml", "summary.wsm")):
                    logger.debug(f"Found Summary file in ZIP: {file_name}")
                    with zip_ref.open(file_name) as summary_file:
                        extracted_info = parse_summary_from_zip(summary_file, file_name, zip_path)

                    #  ZIP 내부 파일도 파일 목록에 추가
                    if extracted_info:
                        files.append({
                            'file_path': f"{zip_path}!{file_name}",
                            'title': extracted_info.get('Name', 'Unknown'),
                            'author': extracted_info.get('Author', 'Unknown'),
                            'version': extracted_info.get('Version', 'Py'),
                            'level_min': extracted_info.get('Level min', ''),
                            'level_max': extracted_info.get('Level max', ''),
                            'coupon_number': extracted_info.get('RequiredCoupons', {}).get('number', 0),
                            'coupon_name': extracted_info.get('RequiredCoupons', {}).get('name', ''),
                            'image_paths': extracted_info.get('image_paths', []),
                            'position_types': extracted_info.get('position_types', []),
                            'image_data': None,  # 기본적으로 None으로 설정
                            'description': extracted_info.get('description', ''),
                            'lang': extracted_info.get('language_code', 'Unknown'),
                            'modification_time': os.path.getmtime(zip_path),  # ZIP 파일의 수정 시간
                            'limit_value': 0,  # 기본값 추가
                            'play_time': None,  # 기본값 추가
                            'mark': 'mark00',  # 기본값 추가
                            'tags': []  # 기본값 추가
                        })

    logger.info(f"Total Number of Scanned Files: {len(files)}")
    return files

def parse_summary_from_zip(summary_file, file_name, zip_path=None):
    """ZIP 내부에서 Summary.xml 또는 Summary.wsm 내용을 읽어와서 파싱"""
    try:
        summary_file.seek(0)  #  ZIP 내부 파일 스트림 포인터 초기화
        raw_data = summary_file.read()

        if not raw_data:
            logger.error(f"Summary file {file_name} is empty.")
            return {}

        logger.debug(f"Read {len(raw_data)} bytes from {file_name}")

        #  XML 파일이면 XML 파싱
        if file_name.lower().endswith(".xml"):
            summary_file.seek(0)  #  포인터 재설정 후 다시 읽기
            xml_data = read_with_encoding(summary_file, file_name)
            extracted_info = parse_xml_data(xml_data)  #  기존 XML 파싱 함수 활용
        else:
            #  WSM/WSN 파일은 extract_info_from_scenario()로 넘김
            summary_file.seek(0)  #  포인터 초기화 후 WSM/WSN 처리
            extracted_info = extract_info_from_scenario(summary_file, file_name, zip_path, is_zip=True)

        return extracted_info

    except ET.ParseError as e:
        logger.error(f"Error parsing {file_name}: {e}")
        return {}

def load_image_data(file_path):
    """특정 WSM 파일의 image_data를 로드하여 반환합니다."""
    
    #  ZIP 내부 파일인지 확인
    if "!" in file_path:
        zip_path, inner_file = file_path.split("!", 1)
        
        if zipfile.is_zipfile(zip_path):
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                if inner_file.lower().endswith(".wsm"):
                    logger.debug(f"Extracting WSM from ZIP: {zip_path}!{inner_file}")
                    with zip_ref.open(inner_file) as wsm_file:
                        wsm_data = io.BytesIO(wsm_file.read())  #  BytesIO 변환 후 읽기
                        with CWFile(None, 'rb', f=wsm_data) as f:  #  BytesIO를 f 인자로 전달
                            reader = SummaryFileReader(f, inner_file)
                            extracted_info = reader.read_summary_data()
                            return extracted_info[9]  #  image_data 반환

        logger.error(f"{file_path}에서 WSM 파일을 찾을 수 없습니다.")
        return None

    #  일반 WSM 파일 처리
    elif file_path.endswith('.wsm'):
        with CWFile(file_path, 'rb') as f:
            reader = SummaryFileReader(f, file_path)
            extracted_info = reader.read_summary_data()
            return extracted_info[9]  #  image_data 반환

    #  WSM이 아닌 경우 오류 처리
    logger.error(f"{file_path}은 WSM 파일이 아닙니다. 이미지 데이터를 로드할 수 없습니다.")
    return None
