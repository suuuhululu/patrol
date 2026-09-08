"""사용자 SQL 접근을 로그인 화면 처리와 분리한다."""
from ..database import get_db


def find_by_id(user_id):
    # [계정 조회] 비밀번호 해시를 화면에 전달하지 않는다.
    return get_db().execute(
        "SELECT id, username, role, is_active, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()


def find_for_login(username):
    # [인증 조회] 비밀번호 검증이 필요한 경우에만 해시를 읽는다.
    return get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def list_users():
    return get_db().execute(
        "SELECT id, username, role, is_active, created_at FROM users ORDER BY id"
    ).fetchall()


def has_active_admin():
    return get_db().execute(
        "SELECT 1 FROM users WHERE role = 'ADMIN' AND is_active = 1 LIMIT 1"
    ).fetchone() is not None


def insert_user(username, password_hash, role):
    # [계정 저장] 입력값과 SQL 구문을 분리하고 저장 실패 시 롤백한다.
    db = get_db()
    with db:
        cursor = db.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                            (username, password_hash, role))
    return cursor.lastrowid


def update_access(user_id, role, is_active):
    db = get_db()
    # [권한 변경 동시성] 마지막 활성 관리자가 동시에 제거되지 않도록 쓰기를 잠근다.
    with db:
        db.execute("BEGIN IMMEDIATE")
        user = find_by_id(user_id)
        if user is None:
            raise ValueError("사용자를 찾을 수 없습니다.")
        if user["role"] == "ADMIN" and user["is_active"] and (role != "ADMIN" or not is_active):
            count = db.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN' AND is_active = 1").fetchone()[0]
            if count <= 1:
                raise ValueError("활성 관리자 계정은 최소 한 개가 필요합니다.")
        db.execute("UPDATE users SET role = ?, is_active = ? WHERE id = ?", (role, int(is_active), user_id))
