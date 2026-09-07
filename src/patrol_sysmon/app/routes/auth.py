"""로그인·로그아웃·관리자 계정 관리와 초기 관리자 생성 명령."""
import click
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from flask.cli import with_appcontext
from ..models import user as user_model
from ..security import login_required, roles_required
from ..services import auth_service

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("dashboard.index"))
    error = None
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "")
        user = auth_service.authenticate(username, request.form.get("password", ""))
        if user is not None:
            # [로그인 성공] 이전 세션을 비우고 현재 사용자 ID와 8시간 만료 세션을 설정한다.
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(url_for("dashboard.index"))
        error = "아이디 또는 비밀번호를 확인하세요. 비활성 계정은 로그인할 수 없습니다."
    return render_template("auth/login.html", error=error, username=username,
                           setup_needed=not user_model.has_active_admin()), (401 if error else 200)


@auth_bp.post("/logout")
@login_required
def logout():
    # [로그아웃] POST와 CSRF 검증을 거쳐 현재 브라우저 세션만 제거한다.
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/admin/users", methods=["GET", "POST"])
@roles_required("ADMIN")
def users():
    error = None
    if request.method == "POST":
        try:
            password = request.form.get("password", "")
            if password != request.form.get("password_confirm", ""):
                raise ValueError("비밀번호 확인이 일치하지 않습니다.")
            auth_service.create_user(request.form.get("username", ""), password, request.form.get("role", ""))
        except ValueError as exc:
            error = str(exc)
        else:
            flash("사용자 계정을 생성했습니다.")
            return redirect(url_for("auth.users"))
    return render_template("auth/users.html", users=user_model.list_users(), error=error), (400 if error else 200)


@auth_bp.post("/admin/users/<int:user_id>/access")
@roles_required("ADMIN")
def user_access(user_id):
    try:
        auth_service.update_access(user_id, request.form.get("role", ""), request.form.get("is_active") == "1")
    except ValueError as exc:
        return render_template("auth/users.html", users=user_model.list_users(), error=str(exc)), 400
    flash("사용자 권한과 활성 상태를 변경했습니다.")
    return redirect(url_for("auth.users"))


@click.command("create-admin")
@click.option("--username", prompt="관리자 아이디")
@click.password_option(prompt="비밀번호", confirmation_prompt="비밀번호 확인")
@with_appcontext
def create_admin(username, password):
    # [초기 관리자] 서버 터미널에서 비밀번호를 입력한다. 기본 비밀번호는 만들지 않는다.
    try:
        auth_service.create_user(username, password, "ADMIN")
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"관리자 계정 '{username.strip()}' 생성 완료")


def init_app(app):
    app.register_blueprint(auth_bp)
    app.cli.add_command(create_admin)
    app.jinja_env.globals["role_labels"] = auth_service.ROLE_LABELS

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("error.html", title="접근 권한이 없습니다.",
                               message="이 기능은 관리자만 사용할 수 있습니다."), 403

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", title="요청을 처리할 수 없습니다.", message=error.description), 400
