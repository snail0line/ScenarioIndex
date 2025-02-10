import sqlite3
import json
from typing import Optional, List, Dict
from PyQt5.QtGui import QPixmap
import re
import os
import shutil
import traceback
from loguru import logger
from utils_and_ui import get_mark_pixmap
from file_scanner import find_files_with_content
from languages import language_settings

class DatabaseManager:    
    def __init__(self, db_name: str = "file_data.db") -> None:
        self.db_name = db_name
        self.connection = sqlite3.connect(self.db_name)
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()

        # 관련 관리 클래스 초기화
        self.limit_manager = LimitManager(self)
        self.mark_manager = MarkManager(self)
        self.tag_manager = TagManager(self)
        self.time_manager = TimeManager(self)
        self.comp_manager = CompManager(self)

    def initialize_database(self) -> None:
        """데이터베이스 초기화: 테이블 생성 및 기본 데이터 설정"""
        try:
            # 테이블 생성
            self._create_tables()
            # 기본 태그 초기화
            self.tag_manager.initialize_default_tags()
        except sqlite3.Error as db_error:
            logger.error(f"Database error during initialization: {db_error}")
        except Exception as e:
            logger.error(f"Unexpected error during database initialization: {e}")
    
    def _create_tables(self) -> None:
        """테이블 생성"""
        try:
            # file_data 테이블 생성
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS file_data (
                    file_path TEXT PRIMARY KEY,
                    title TEXT,
                    author TEXT,
                    version TEXT,
                    level_min INTEGER,
                    level_max INTEGER,
                    coupon_number INTEGER,
                    coupon_name TEXT,
                    image_paths TEXT,
                    position_types TEXT,
                    image_data BLOB,
                    description TEXT,
                    lang TEXT,
                    modification_time REAL,
                    limit_value INTEGER DEFAULT 0,
                    play_time TEXT,
                    mark TEXT DEFAULT 'mark00',
                    file_tags TEXT,
                    is_completed INTEGER DEFAULT 0
                )
            """)

            # tags_list 테이블 생성
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS tags_list (
                    tag TEXT PRIMARY KEY,
                    KR_translation TEXT,
                    JP_translation TEXT
                )
            """)
            self.connection.commit()
        except sqlite3.Error as db_error:
            logger.error(f"Database error during table creation: {db_error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during table creation: {e}")
            raise
    
    def fetch_file_data_count(self, folder_path: Optional[str] = None) -> int:
        """파일 데이터의 총 개수를 반환합니다. 폴더 경로를 선택적으로 필터링할 수 있습니다."""
        query = "SELECT COUNT(*) FROM file_data"
        params = ()
        if folder_path:
            normalized_folder_path = folder_path.replace("\\", "/") + "/%"  # 슬래시로 통일하는 경우
            query += " WHERE file_path LIKE ?"
            params = (normalized_folder_path,)
        self.cursor.execute(query, params)
        return self.cursor.fetchone()[0]
    
    def update_files_for_folder(self, folder_path):
        try:
            # ✅ 기존 데이터베이스에서 해당 폴더의 파일 경로 가져오기
            existing_files = self.cursor.execute(
                "SELECT file_path FROM file_data WHERE file_path LIKE ?", 
                (folder_path.replace("\\", "/") + "/%",)
            ).fetchall()
            existing_file_paths = {row["file_path"] for row in existing_files}

            # ✅ 폴더에서 파일 목록을 새로 스캔
            new_files = find_files_with_content(folder_path)
            logger.info("find_files_with_content 실행 완료")
            new_file_paths = {file_data["file_path"] for file_data in new_files}

            # ✅ DB에만 존재하고 폴더에는 없는 파일을 '삭제됨'으로 처리
            files_to_mark_as_deleted = existing_file_paths - new_file_paths
            for file_path in files_to_mark_as_deleted:
                # ✅ 기존에 이미 "Deleted: " 상태인지 확인
                self.cursor.execute("SELECT file_path FROM file_data WHERE file_path = ?", (f"Deleted: {file_path}",))
                if self.cursor.fetchone():
                    logger.warning(f"File already marked as deleted: {file_path}")
                    continue

                logger.info(f"Marking file as deleted: {file_path}")
                self.cursor.execute(
                    "UPDATE file_data SET file_path = ? WHERE file_path = ?",
                    (f"Deleted: {file_path}", file_path)
                )

            # ✅ 새 파일을 데이터베이스에 삽입 또는 갱신
            for file_data in new_files:
                file_path = file_data["file_path"]
                
                # ✅ 기존에 "Deleted: file_path"로 저장된 데이터가 있는지 확인
                self.cursor.execute("SELECT file_path FROM file_data WHERE file_path = ?", (f"Deleted: {file_path}",))
                deleted_entry = self.cursor.fetchone()

                if deleted_entry:
                    # ✅ 기존에 삭제된 파일이 있으면 INSERT 하지 않고 UPDATE로 복구
                    logger.info(f"Restoring deleted file: {file_path}")
                    self.cursor.execute("""
                        UPDATE file_data
                        SET file_path = ?, title = ?, author = ?, version = ?, level_min = ?, level_max = ?, 
                            coupon_number = ?, coupon_name = ?, image_paths = ?, position_types = ?, 
                            image_data = ?, description = ?, lang = ?, modification_time = ?, 
                            limit_value = ?, play_time = ?, mark = ?, file_tags = ?, is_completed = ?
                        WHERE file_path = ?
                    """, (
                        file_path, file_data["title"], file_data["author"], file_data["version"], file_data["level_min"],
                        file_data["level_max"], file_data["coupon_number"], file_data["coupon_name"],
                        json.dumps(file_data["image_paths"]), json.dumps(file_data["position_types"]),
                        None, file_data["description"], file_data["lang"], file_data["modification_time"], 
                        file_data.get("limit_value", 0), file_data.get("play_time", ""), file_data.get("mark", "mark00"),
                        json.dumps(file_data.get("file_tags", [])), 0, f"Deleted: {file_path}"
                    ))
                else:
                    # ✅ 기존에 없으면 INSERT 수행
                    self.cursor.execute("SELECT 1 FROM file_data WHERE file_path = ?", (file_path,))
                    exists = self.cursor.fetchone()

                    if not exists:
                        self.cursor.execute("""
                            INSERT INTO file_data (file_path, title, author, version, level_min, level_max, 
                                                coupon_number, coupon_name, image_paths, position_types, 
                                                image_data, description, lang, modification_time, 
                                                limit_value, play_time, mark, file_tags, is_completed)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            file_path, file_data["title"], file_data["author"], file_data["version"], file_data["level_min"],
                            file_data["level_max"], file_data["coupon_number"], file_data["coupon_name"],
                            json.dumps(file_data["image_paths"]), json.dumps(file_data["position_types"]),
                            None, file_data["description"], file_data["lang"], file_data["modification_time"], 
                            file_data.get("limit_value", 0), file_data.get("play_time", ""), file_data.get("mark", "mark00"),
                            json.dumps(file_data.get("file_tags", [])), 0
                        ))

            # ✅ 변경 사항 커밋
            self.connection.commit()
        
        except sqlite3.DatabaseError as db_error:
            self.connection.rollback()
            tb = traceback.format_exc()
            logger.error(f"Database error in update_files_for_folder ({folder_path}): {repr(db_error)}\nTraceback:\n{tb}")
        except FileNotFoundError as fnf_error:
            tb = traceback.format_exc()
            logger.error(f"FileNotFoundError in update_files_for_folder ({folder_path}): {repr(fnf_error)}\nTraceback:\n{tb}")
        except Exception as e:
            self.connection.rollback()
            tb = traceback.format_exc()
            logger.error(f"Unexpected error in update_files_for_folder ({folder_path}): {repr(e)}\nTraceback:\n{tb}")

    def update_completed_status(self, file_path: str, is_completed: int):
            self.cursor.execute(
                "UPDATE file_data SET is_completed = ? WHERE file_path = ?", 
                (is_completed, file_path)
            )
            self.connection.commit()

    def fetch_file_data(self, folder_path: str, page_size: int, start_index: int) -> List[Dict]:
        """지정된 폴더와 페이지의 파일 데이터를 가져옵니다."""
        normalized_folder_path = folder_path.replace("\\", "/") + "/%"
        
        # 쿼리 실행 및 디버깅 출력
        query = "SELECT * FROM file_data WHERE file_path LIKE ? LIMIT ? OFFSET ?"
        self.cursor.execute(query, (normalized_folder_path, page_size, start_index))
        
        rows = self.cursor.fetchall()

        result = []
        for row in rows:
            row_data = dict(row)
            try:
                row_data['file_tags'] = json.loads(row_data['file_tags']) if row_data['file_tags'] else []
            except (json.JSONDecodeError, TypeError):
                row_data['file_tags'] = []
            result.append(row_data)
        
        return result

    def fetch_sorted_file_data(self, folder_path, sort_field, page_size, start_index):
        """주어진 필드로 정렬된 파일 데이터를 가져옵니다."""

        # 필드와 쿼리 매핑
        valid_sort_fields = {
            "title": "title",
            "author": "author",
            "modification_time": "modification_time",
            "level_min": "level_min"
        }
        sort_column = valid_sort_fields.get(sort_field)
        if not sort_column:
            logger.warning(f"Invalid sort field: {sort_field}. Defaulting to 'modification_time'.")
            sort_column = "modification_time"

        # ✅ 특정 필드에 대해 정렬 방향 조정
        # - 'modification_time'은 최신순(DESC), 나머지는 오름차순(ASC)
        if sort_field in ["modification_time"]:
            sort_desc = True   # 최신 수정 시간순 (내림차순)
        elif sort_field in ["title", "author", "level_min"]:
            sort_desc = False  # 제목, 저자, 최소 레벨은 오름차순

        # 매개변수 유효성 검사
        if page_size is None or page_size <= 0:
            page_size = 30  # 기본 페이지 크기
        if start_index is None or start_index < 0:
            start_index = 0  # 기본 시작 인덱스

        # SQL 쿼리 작성
        query = f"""
        SELECT * FROM file_data
        WHERE file_path LIKE ?
        ORDER BY COALESCE({sort_column}, '') {"COLLATE NOCASE" if sort_field != "modification_time" else ""} {"DESC" if sort_desc else "ASC"}
        LIMIT ? OFFSET ?
        """

        # 디버깅 로그 추가
        logger.info(f"With parameters: {folder_path}%, {page_size}, {start_index}")

        # 쿼리를 실행하고 결과 반환
        try:
            self.cursor.execute(query, (f"{folder_path}%", page_size, start_index))
            rows = self.cursor.fetchall()
            logger.info(f"Rows fetched: {len(rows)}")

            # 결과를 딕셔너리 리스트로 변환
            result = []
            for row in rows:
                row_data = dict(row)
                try:
                    row_data['file_tags'] = json.loads(row_data['file_tags']) if row_data['file_tags'] else []
                except (json.JSONDecodeError, TypeError):
                    row_data['file_tags'] = []
                result.append(row_data)

            return result
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise

    def update_field(self, file_path, field, value):
        """파일의 특정 필드를 업데이트"""
        query = f"UPDATE file_data SET {field} = ? WHERE file_path = ?"
        try:
            self.cursor.execute(query, (value, file_path))
            self.connection.commit()
        except Exception as e:
            logger.error(f"Failed to update {field} for {file_path}: {e}")

    def update_level(self, file_path, level_min, level_max):
        """파일의 level_min과 level_max를 동시에 업데이트"""
        query = "UPDATE file_data SET level_min = ?, level_max = ? WHERE file_path = ?"
        try:
            self.cursor.execute(query, (level_min, level_max, file_path))
            self.connection.commit()
        except Exception as e:
            logger.error(f"Failed to update level for {file_path}: {e}")

    def fetch_all_files_for_folder(self, folder_path: str) -> List[Dict]:
        """데이터베이스에서 특정 폴더 경로의 모든 파일 정보를 가져옵니다."""
        normalized_folder_path = folder_path.replace("\\", "/") + "/%"
        self.cursor.execute("SELECT * FROM file_data WHERE file_path LIKE ?", (normalized_folder_path,))
        return [dict(row) for row in self.cursor.fetchall()]

    def close(self) -> None:
        self.connection.close()

class LimitManager:   
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    
    def update_limit(self, file_path: str, limit_value: int) -> None:
        self.db.cursor.execute("UPDATE file_data SET limit_value = ? WHERE file_path = ?", (limit_value, file_path))
        self.db.connection.commit()

    
    def reset_limits(self) -> None:
        self.db.cursor.execute("UPDATE file_data SET limit_value = 0")
        self.db.connection.commit()    

class CompManager:  
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    
    def update_comp(self, file_path: str, is_completed: int) -> None:
        self.db.cursor.execute("UPDATE file_data SET is_completed = ? WHERE file_path = ?", (is_completed, file_path))
        self.db.connection.commit()

    
    def reset_comps(self) -> None:
        self.db.cursor.execute("UPDATE file_data SET is_completed = 0")
        self.db.connection.commit()  

class TimeManager:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    
    def update_play_time(self, file_path: str, play_time: str) -> None:
        """특정 파일의 play_time을 업데이트합니다."""
        self.db.cursor.execute("UPDATE file_data SET play_time = ? WHERE file_path = ?", (play_time, file_path))
        self.db.connection.commit()

    
    def reset_play_times(self) -> None:
        """모든 파일의 play_time을 NULL로 초기화합니다."""
        self.db.cursor.execute("UPDATE file_data SET play_time = NULL")
        self.db.connection.commit()

    
    def fetch_play_time(self, file_path: str) -> Optional[str]:
        """특정 파일의 play_time을 가져옵니다."""
        self.db.cursor.execute("SELECT play_time FROM file_data WHERE file_path = ?", (file_path,))
        result = self.db.cursor.fetchone()       
        return result["play_time"] if result else None

    
    def fetch_all_play_times(self) -> List[str]:
        """모든 파일의 play_time 목록을 반환합니다."""
        self.db.cursor.execute("SELECT DISTINCT play_time FROM file_data")  # 중복 없는 모든 play_time 선택            
        return [row["play_time"] for row in self.db.cursor.fetchall()]

class MarkManager:
    def __init__(self, db_manager):
        self.db = db_manager
        self.base_path = os.path.abspath(".")
        self.assets_path = os.path.join(self.base_path, "assets")  # 사용자 마크 경로

    def get_mark_image(self, mark: str) -> QPixmap:
        """
        파일에 할당된 마크 이미지를 반환.
        - 사용자 정의 이미지가 존재하면 assets 폴더에서 로드
        - 없으면 기본 마크 이미지를 바이너리 데이터에서 로드
        """
        user_image_path = os.path.join(self.assets_path, f"{mark}.png")

        if os.path.exists(user_image_path):  # 사용자 이미지가 존재하면 로드
            return QPixmap(user_image_path)

        else:  # 기본 마크 이미지를 바이너리 데이터에서 로드
            pixmap = get_mark_pixmap(int(mark[4:]))  # "markXX"에서 숫자 추출하여 전달
            if pixmap is None:
                logger.error(f"[ERROR] Failed to load default image for {mark}")
            return pixmap

    
    def set_mark_image(self, mark: str, new_image_path: str) -> None:
        """
        사용자가 마크 이미지를 변경하면 assets 폴더에 저장.
        """
        target_path = os.path.join(self.assets_path, f"{mark}.png")

        # assets 폴더에 새 이미지를 복사하여 덮어쓰기
        os.makedirs(self.assets_path, exist_ok=True)  # 폴더가 없으면 생성
        shutil.copyfile(new_image_path, target_path)
        logger.debug(f"[INFO] New user image saved to {target_path}")

    
    def update_mark(self, file_path: str, mark: str) -> None:
        self.db.cursor.execute("UPDATE file_data SET mark = ? WHERE file_path = ?", (mark, file_path))
        self.db.connection.commit()

    
    def reset_marks(self) -> None:
        """모든 마크를 'mark00'으로 초기화합니다."""
        self.db.cursor.execute("UPDATE file_data SET mark = 'mark00'")
        self.db.connection.commit()

    def fetch_mark(self, file_path: str) -> Optional[str]:
        self.db.cursor.execute("SELECT mark FROM file_data WHERE file_path = ?", (file_path,))
        result = self.db.cursor.fetchone()
        return result["mark"] if result else None

    
    def fetch_all_marks(self) -> List[str]:
        """모든 마크를 반환합니다."""
        self.db.cursor.execute("SELECT DISTINCT mark FROM file_data")  # 중복 없는 모든 마크를 선택
        return [row["mark"] for row in self.db.cursor.fetchall()]

class TagManager:  
    def __init__(self, db_manager):
        self.db = db_manager
        self.default_tags = ["battle", "dungeon", "explorer", "novel", "shop", "town", "item", "skill", "short", "long"]

    
    def set_language(self, language_code):
        """언어 변경 시 호출하여 번역을 업데이트"""
        language_settings.set_language(language_code)  # LanguageSettings에서 언어 설정
        self._notify_update() 

    
    def initialize_default_tags(self):
        """기본 태그를 데이터베이스에 추가합니다."""
        try:
            original_language = language_settings.current_locale
            language_settings.set_language("kr")  # KR 태그 로드
            kr_translations = language_settings.translations.get("tags", {})
            language_settings.set_language("jp")  # JP 태그 로드
            jp_translations = language_settings.translations.get("tags", {})
            language_settings.set_language(original_language)  # 원래 언어로 복원

            self.db.cursor.execute("SELECT tag FROM tags_list")
            existing_tags = {row["tag"] for row in self.db.cursor.fetchall()}

            for tag in self.default_tags:
                if tag not in existing_tags:
                    self.db.cursor.execute(
                        "INSERT INTO tags_list (tag, KR_translation, JP_translation) VALUES (?, ?, ?)",
                        (tag, kr_translations.get(tag, ""), jp_translations.get(tag, ""))
                    )

            self.db.connection.commit()

        except Exception as e:
            self.db.connection.rollback()
            logger.error(f"Error initializing default tags: {e}")

    
    def _tag_exists(self, tag):
        """태그 존재 여부 확인"""
        self.db.cursor.execute("SELECT 1 FROM tags_list WHERE tag = ? COLLATE NOCASE", (tag,))
        return self.db.cursor.fetchone() is not None
    
    
    def fetch_tag_keys_with_translations(self):
        """태그 키와 현재 언어 번역을 가져옵니다."""
        try:
            current_language = language_settings.current_locale.upper()  # 현재 언어 코드 가져오기
            translation_column = f"{current_language}_translation"
            self.db.cursor.execute(
                f"SELECT tag, {translation_column} AS translation FROM tags_list"
            )
            result = [(row['tag'], row['translation']) for row in self.db.cursor.fetchall()]
            return result
        except Exception as e:
            logger.error(f"Error fetching tag keys with translations: {e}")
            return []

    def get_tag_translation(self, tag_key):
        """태그 키에 대한 현재 언어의 번역을 반환"""
        language_code = language_settings.current_locale  # 현재 언어 코드 가져오기
        translation_column = f"{language_code}_translation"  # 해당 언어의 번역 컬럼 선택

        self.db.cursor.execute(
            f"SELECT {translation_column} FROM tags_list WHERE tag = ?",
            (tag_key,)
        )
        result = self.db.cursor.fetchone()
        return result[translation_column] if result else tag_key

    
    def get_translations_for_tags(self, tag_keys):
        """여러 태그 키에 대한 번역을 한 번에 가져옴"""
        if not tag_keys:
            return []
            
        language_code = language_settings.current_locale  # 현재 언어 코드 가져오기
        translation_column = f"{language_code}_translation"  # 해당 언어의 번역 컬럼 선택

        placeholders = ','.join('?' * len(tag_keys))
        self.db.cursor.execute(
            f"SELECT tag, {translation_column} FROM tags_list WHERE tag IN ({placeholders})",
            tuple(tag_keys)
        )
        translations = {row['tag']: row[translation_column] 
                    for row in self.db.cursor.fetchall()}
        return [translations.get(key, key) for key in tag_keys]

    def get_tag_display_name(self, tag_key):
        return self.get_tag_translation(tag_key)

    
    def add_custom_tag(self, tag_key, translation_text):
        """사용자 정의 태그 추가"""
        if not tag_key or not translation_text:
            return

        # 태그 키에 허용되지 않는 문자 검사
        if not re.match("^[a-zA-Z0-9_-]+$", tag_key):
            logger.warning("Tag key can only contain letters, numbers, underscore, and hyphen")
            return

        if tag_key not in self.default_tags and not self._tag_exists(tag_key):
            try:
                current_language = language_settings.current_locale.upper()  # 현재 언어 가져오기

                if current_language == "kr":
                    self.db.cursor.execute(
                        "INSERT INTO tags_list (tag, KR_translation, JP_translation) VALUES (?, ?, NULL)",
                        (tag_key, translation_text)
                    )
                elif current_language == "jp":
                    self.db.cursor.execute(
                        "INSERT INTO tags_list (tag, KR_translation, JP_translation) VALUES (?, NULL, ?)",
                        (tag_key, translation_text)
                    )
                else:
                    logger.warning(f"Unsupported language: {current_language}. Skipping tag insertion.")
                    return

                self.db.connection.commit()
                self._notify_update()
            except Exception as e:
                self.db.connection.rollback()
                logger.error(f"Error adding custom tag: {e}")

    
    def update_custom_tag(self, old_tag: str, new_tag_key: str, translation_text: str) -> None:
        """사용자 정의 태그를 수정합니다."""
        try:
            current_language = language_settings.current_locale.upper()
            if old_tag == new_tag_key:  # 태그 키가 같은 경우
                translation_column = f"{current_language}_translation"
                self.db.cursor.execute(
                    f"UPDATE tags_list SET {translation_column} = ? WHERE tag = ?",
                    (translation_text, old_tag)
                )
                self.db.connection.commit()
                self._notify_update()
                return

            if self._tag_exists(old_tag):
                if new_tag_key != old_tag and self._tag_exists(new_tag_key):
                    logger.warning(f"Warning: Tag {new_tag_key} already exists")
                    return

                translation_column = f"{current_language}_translation"
                self.db.cursor.execute(
                    f"UPDATE tags_list SET tag = ?, {translation_column} = ? WHERE tag = ?",
                    (new_tag_key, translation_text, old_tag)
                )
                # 파일 태그 업데이트는 같은 트랜잭션 내에서 수행
                self.update_file_tags_after_changes(old_tag, new_tag_key)

                self.db.connection.commit()
                self._notify_update()
        except Exception as e:
            self.db.connection.rollback()
            logger.error(f"Error updating tag: {e}")

    
    def delete_custom_tag(self, tag):
        """사용자 정의 태그를 삭제합니다."""
        try:
            if tag not in self.default_tags and self._tag_exists(tag):
                self.db.cursor.execute("DELETE FROM tags_list WHERE tag = ?", (tag,))
                self.update_file_tags_after_changes(tag)
                self.db.connection.commit()
                self._notify_update()
        except Exception as e:
            self.db.connection.rollback()
            logger.error(f"Error deleting custom tag: {e}")

    
    def fetch_tags_for_file(self, file_path):
        """파일의 태그 목록을 가져옵니다."""
        try:
            self.db.cursor.execute("SELECT file_tags FROM file_data WHERE file_path = ?", (file_path,))
            result = self.db.cursor.fetchone()
            if result and result["file_tags"]:
                file_tags = result["file_tags"]
                if isinstance(file_tags, str):
                    try:
                        tags = json.loads(file_tags)
                        if isinstance(tags, list):
                            return tags
                        logger.error(f"Invalid tag format for {file_path}: {tags}")
                    except json.JSONDecodeError:
                        logger.error(f"JSON decoding error for tags in {file_path}: {file_tags}")
            return []
        except Exception as e:
            logger.error(f"Error fetching tags for file {file_path}: {e}")
            return []

    
    def update_tags_for_file(self, file_path, tags):
        """파일의 태그 목록을 업데이트"""
        try:
            # 태그 목록 유효성 검사 추가
            if not isinstance(tags, list):
                logger.error(f"Invalid tags format: {tags}")
                return
                
            # 각 태그가 실제 존재하는 태그키인지 확인
            valid_tags = []
            for tag in tags:
                if self._tag_exists(tag):
                    valid_tags.append(tag)
                else:
                    logger.warning(f"Skipping invalid tag: {tag}")
                    
            tags_json = json.dumps(valid_tags, ensure_ascii=False)
            
            self.db.cursor.execute(
                "UPDATE file_data SET file_tags = ? WHERE file_path = ?",
                (tags_json, file_path)
            )
            self.db.connection.commit()
        except Exception as e:
            logger.error(f"Error updating tags for file {file_path}: {e}")
            self.db.connection.rollback()

    
    def update_file_tags_after_changes(self, old_tag, new_tag=None):
        """태그 변경/삭제 시 모든 파일의 태그 업데이트"""
        try:
            self.db.cursor.execute("SELECT file_path, file_tags FROM file_data WHERE file_tags IS NOT NULL")
            for file in self.db.cursor.fetchall():
                try:
                    current_tags = json.loads(file['file_tags']) if file['file_tags'] else []
                    if old_tag in current_tags:
                        if new_tag:
                            current_tags[current_tags.index(old_tag)] = new_tag
                        else:
                            current_tags.remove(old_tag)
                        self.update_tags_for_file(file['file_path'], current_tags)
                except json.JSONDecodeError as e:
                    logger.error(f"Error updating tags for file {file['file_path']}: {e}")
            self.db.connection.commit()  
        except Exception as e:
            self.db.connection.rollback()

    
    def reset_file_tags(self):
        """모든 파일별 태그를 삭제합니다."""
        try:
            self.db.cursor.execute("UPDATE file_data SET file_tags = '[]'")
            self.db.connection.commit()
            self._notify_update()
        except Exception as e:
            self.db.connection.rollback()
            logger.error(f"Error resetting file tags: {e}")

    
    def delete_all_custom_tags(self):
        """모든 사용자 정의 태그 삭제"""
        try:
            # 먼저 삭제될 태그 목록 가져오기
            self.db.cursor.execute("SELECT tag FROM tags_list WHERE tag NOT IN ({})".format(
                ", ".join(["?"] * len(self.default_tags))
            ), tuple(self.default_tags))
            tags_to_delete = [row['tag'] for row in self.db.cursor.fetchall()]
            
            if not tags_to_delete:  # 삭제할 태그가 없으면 종료
                return
                
            # 태그 삭제
            placeholders = ", ".join(["?"] * len(self.default_tags))
            self.db.cursor.execute(
                f"DELETE FROM tags_list WHERE tag NOT IN ({placeholders})", 
                tuple(self.default_tags)
            )
            
            # 각 태그에 대해 파일 태그 업데이트
            for tag in tags_to_delete:
                self.update_file_tags_after_changes(tag)
                
            self.db.connection.commit()
            self._notify_update()
        except Exception as e:
            self.db.connection.rollback()
            logger.error(f"Error deleting all custom tags: {e}")

    
    def set_update_callback(self, callback):
        """UI 업데이트 콜백 설정"""
        self._update_callback = callback

    
    def _notify_update(self):
        """태그 변경 시 UI 업데이트"""
        if not hasattr(self, '_update_callback'):
            return

        try:
            self._update_callback()
        except Exception as e:
            logger.error(f"Error in UI update callback: {e}", exc_info=True)