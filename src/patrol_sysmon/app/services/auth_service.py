"""계정 입력 검증과 비밀번호 해시 확인."""
import re
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from ..models import user as user_model

ROLE_LABELS = {"ADMIN": "관리자", "OPERATOR": "관제자", "VIEWER": "조회자"}
# [인증 실패] 없는 계정에도 해시 검증을 수행하고 실패 사유는 동일하게 안내한다.
_DUMMY_HASH = generate_password_hash("unused-password-for-login-timing")


def create_user(username, password, role):
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username):
        raise ValueError("아이디는 영문·숫자·밑줄·점·하이픈으로 3~32자 입력하세요.")
    if not 8 <= len(password) <= 128:
        raise ValueError("비밀번호는 8~128자로 입력하세요.")
    if role not in ROLE_LABELS:
        raise ValueError("올바른 권한을 선택하세요.")
    # [비밀번호 저장] 원문 대신 솔트를 포함한 해시를 저장한다.
    password_hash = generate_password_hash(password)
    try:
        return user_model.insert_user(username, password_hash, role)
    except sqlite3.IntegrityError as error:
        raise ValueError("이미 사용 중인 아이디입니다.") from error


def authenticate(username, password):
    if len(username) > 32 or len(password) > 128:
        return None
    user = user_model.find_for_login(username.strip())
    stored_hash = user["password_hash"] if user is not None else _DUMMY_HASH
    valid = check_password_hash(stored_hash, password)
    if user is not None and valid and user["is_active"]:
        return user
    return None


def update_access(user_id, role, is_active):
    if role not in ROLE_LABELS:
        raise ValueError("올바른 권한을 선택하세요.")
    user_model.update_access(user_id, role, is_active)
