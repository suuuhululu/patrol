"""여러 기능에서 사용하는 세션·CSRF·접근 권한 처리."""
from datetime import timedelta
from functools import wraps
from pathlib import Path
import os
import secrets
import tempfile

from flask import abort, current_app, g, redirect, request, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        # [로그인 검사] 주소를 직접 입력해도 미인증 사용자는 로그인 화면으로 보낸다.
        if g.user is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            # [권한 검사] 버튼 표시 여부와 별도로 서버에서 최신 DB 권한을 검사한다.
            if g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def device_token_is_authorized():
    """로봇·지도·이벤트 장치 API가 공유하는 헤더 토큰을 비교한다."""
    configured = current_app.config.get("ROBOT_API_KEY")
    supplied = request.headers.get("X-Robot-Token", "")
    try:
        return bool(configured and supplied and secrets.compare_digest(
            configured.encode("ascii"), supplied.encode("ascii")
        ))
    except (AttributeError, UnicodeEncodeError):
        # [잘못된 토큰 형식] 장치 입력이 서버 오류로 번지지 않도록 인증 실패로 처리한다.
        return False


def csrf_token():
    # [요청 검증] 브라우저 세션별 토큰을 변경 요청에 함께 제출한다.
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def init_app(app):
    if not app.config.get("SECRET_KEY"):
        # [서명 키 보관] 최초 실행 시 생성하여 재시작 후에도 세션을 검증한다.
        key_file = Path(app.config["DATABASE"]).parent / "session.key"
        # [동시 시작] 완성된 파일을 원자적으로 연결해 다른 프로세스가 빈 키를 읽지 않게 한다.
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=key_file.parent) as stream:
            if not key_file.exists():
                stream.write(secrets.token_hex(32))
                stream.flush()
                try:
                    os.link(stream.name, key_file)
                except FileExistsError:
                    pass
        app.config["SECRET_KEY"] = key_file.read_text(encoding="ascii").strip()
        if not app.config["SECRET_KEY"]:
            raise RuntimeError("세션 서명 키 파일이 비어 있습니다.")
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), SESSION_REFRESH_EACH_REQUEST=False)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def load_user_and_check_csrf():
        from .models.user import find_by_id
        # [사용자별 세션] 사용자 ID로 매 요청 DB 권한·활성 상태를 다시 확인한다.
        g.user = None
        user_id = session.get("user_id")
        if user_id is not None:
            user = find_by_id(user_id)
            if user is not None and user["is_active"]:
                g.user = user
            else:
                session.clear()
        # [장치 API 분리] 상태·지도·이벤트 입력은 브라우저 세션 대신 전용 토큰을 경로에서 검사한다.
        csrf_exempt = request.endpoint in current_app.config.get("CSRF_EXEMPT_ENDPOINTS", ())
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not csrf_exempt:
            expected = session.get("csrf_token", "")
            supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
            if not expected or not secrets.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8")):
                abort(400, description="요청 확인 정보가 만료되었습니다. 화면을 새로고침한 뒤 다시 시도하세요.")

    @app.after_request
    def disable_private_page_cache(response):
        # [로그아웃 후 화면] 사용자 정보가 포함된 페이지를 브라우저가 캐시하지 않도록 한다.
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response
