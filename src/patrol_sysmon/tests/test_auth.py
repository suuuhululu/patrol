"""3단계 검증: 임시 DB에서 실제 폼 요청·세션·권한·계정 보존을 확인한다."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from werkzeug.security import check_password_hash

from app import create_app
from app.database import get_db
from app.models import user as user_model
from app.services import auth_service


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.config = {
            "TESTING": True,
            "DATABASE": str(Path(self.folder.name) / "instance/db.sqlite3"),
            "EVIDENCE_DIR": str(Path(self.folder.name) / "instance/evidence"),
            "SECRET_KEY": "auth-tests-only-key",
        }
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.password = "Test-only-pass-123"
        with self.app.app_context():
            self.admin_id = auth_service.create_user("admin", self.password, "ADMIN")
            self.viewer_id = auth_service.create_user("viewer", self.password, "VIEWER")

    def token(self, client):
        client.get("/login")
        # [폼 검증] 로그인 후에는 기본 페이지의 로그아웃 폼에서 토큰을 생성한다.
        client.get("/")
        with client.session_transaction() as session:
            return session["csrf_token"]

    def post(self, client, url, **data):
        return client.post(url, data={"csrf_token": self.token(client), **data})

    def login(self, client, username="admin", password=None):
        return self.post(client, "/login", username=username, password=self.password if password is None else password)

    def test_authentication_gate_and_invalid_password(self):
        self.assertEqual(self.client.get("/").location, "/login")
        self.assertEqual(self.client.get("/admin/users").location, "/login")
        for username, password in [("admin", "wrong"), ("unknown", self.password), ("' OR 1=1 --", "anything")]:
            result = self.login(self.client, username, password)
            self.assertEqual(result.status_code, 401)
            with self.client.session_transaction() as session:
                self.assertNotIn("user_id", session)
        self.assertEqual(self.login(self.client).status_code, 302)
        page = self.client.get("/")
        self.assertIn("admin님", page.get_data(as_text=True))
        self.assertEqual(page.headers["Cache-Control"], "no-store")

    def test_password_is_hashed_and_duplicate_account_is_rejected(self):
        with self.app.app_context():
            row = user_model.find_for_login("admin")
            self.assertNotEqual(row["password_hash"], self.password)
            self.assertTrue(check_password_hash(row["password_hash"], self.password))
            with self.assertRaises(ValueError):
                auth_service.create_user("admin", "different-pass", "ADMIN")
            self.assertTrue(check_password_hash(user_model.find_for_login("admin")["password_hash"], self.password))

    def test_separate_clients_and_logout(self):
        viewer = self.app.test_client()
        self.login(self.client)
        self.login(viewer, "viewer")
        self.assertIn("admin님", self.client.get("/").get_data(as_text=True))
        self.assertIn("viewer님", viewer.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get("/logout").status_code, 405)
        self.assertEqual(self.post(self.client, "/logout").location, "/login")
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(viewer.get("/").status_code, 200)

    def test_csrf_protects_login_logout_and_account_changes(self):
        self.assertEqual(self.client.post("/login", data={"username": "admin", "password": self.password}).status_code, 400)
        self.login(self.client)
        self.assertEqual(self.client.post("/logout").status_code, 400)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.post("/admin/users", data={"csrf_token": "wrong"}).status_code, 400)
        self.assertEqual(self.client.post("/logout", data={"csrf_token": "잘못된토큰"}).status_code, 400)
        other = self.app.test_client()
        foreign_token = self.token(other)
        self.assertEqual(self.client.post("/logout", data={"csrf_token": foreign_token}).status_code, 400)

    def test_admin_creates_account_and_nonadmins_cannot_manage_users(self):
        self.login(self.client)
        response = self.post(self.client, "/admin/users", username="operator", password=self.password,
                             password_confirm=self.password, role="OPERATOR")
        self.assertEqual(response.status_code, 302)
        page = self.client.get("/admin/users").get_data(as_text=True)
        self.assertIn("operator", page)
        self.assertNotIn(self.password, page)
        self.assertNotIn("scrypt:", page)
        for username in ("viewer", "operator"):
            client = self.app.test_client()
            self.login(client, username)
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/admin/users").status_code, 403)
            self.assertEqual(self.post(client, "/admin/users", username="intruder", password=self.password,
                                       password_confirm=self.password, role="ADMIN").status_code, 403)
            self.assertEqual(self.post(client, f"/admin/users/{self.viewer_id}/access", role="ADMIN", is_active="1").status_code, 403)

    def test_invalid_creation_inputs_do_not_create_accounts(self):
        self.login(self.client)
        base = dict(username="newuser", password=self.password, password_confirm=self.password, role="VIEWER")
        for changes in ({"password_confirm": "mismatch"}, {"username": "<script>"},
                        {"role": "OWNER"}, {"password": "short", "password_confirm": "short"}):
            response = self.post(self.client, "/admin/users", **{**base, **changes})
            self.assertEqual(response.status_code, 400)
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0], 2)

    def test_role_changes_and_deactivation_apply_to_existing_session(self):
        viewer = self.app.test_client()
        self.login(self.client)
        self.login(viewer, "viewer")
        url = f"/admin/users/{self.viewer_id}/access"
        self.assertEqual(self.post(self.client, url, role="ADMIN", is_active="1").status_code, 302)
        self.assertEqual(viewer.get("/admin/users").status_code, 200)
        self.post(self.client, url, role="VIEWER", is_active="1")
        self.assertEqual(viewer.get("/admin/users").status_code, 403)
        self.post(self.client, url, role="VIEWER")
        self.assertEqual(viewer.get("/").location, "/login")
        self.assertEqual(self.login(viewer, "viewer").status_code, 401)

    def test_last_admin_cannot_be_disabled_or_demoted(self):
        self.login(self.client)
        url = f"/admin/users/{self.admin_id}/access"
        for data in ({"role": "VIEWER", "is_active": "1"}, {"role": "ADMIN"}):
            self.assertEqual(self.post(self.client, url, **data).status_code, 400)
        self.assertEqual(self.client.get("/admin/users").status_code, 200)
        with self.app.app_context():
            self.assertTrue(user_model.has_active_admin())

    def test_cli_creates_admin_without_overwriting_existing_account(self):
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["create-admin", "--username", "newadmin"],
                               input=f"{self.password}\n{self.password}\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertNotIn(self.password, result.output)
        result = runner.invoke(args=["create-admin", "--username", "newadmin"],
                               input="another-password\nanother-password\n")
        self.assertNotEqual(result.exit_code, 0)
        client = self.app.test_client()
        self.assertEqual(self.login(client, "newadmin").status_code, 302)

    def test_restart_preserves_accounts_and_signing_key(self):
        # [재시작] 운영과 동일하게 파일 키를 사용해 서버 재생성 후 기존 세션도 검증한다.
        config = {**self.config, "SECRET_KEY": None}
        app = create_app(config)
        client = app.test_client()
        self.login(client)
        cookie = client.get_cookie("session")
        restarted = create_app(config)
        self.assertEqual(app.secret_key, restarted.secret_key)
        self.assertEqual((Path(config["DATABASE"]).parent / "session.key").stat().st_mode & 0o777, 0o600)
        second = restarted.test_client()
        second.set_cookie("session", cookie.value)
        self.assertEqual(second.get("/").status_code, 200)
        fresh = restarted.test_client()
        self.assertEqual(self.login(fresh).status_code, 302)

    def test_simultaneous_admin_changes_leave_one_active_admin(self):
        with self.app.app_context():
            second_id = auth_service.create_user("admin2", self.password, "ADMIN")

        def demote(user_id):
            with self.app.app_context():
                try:
                    auth_service.update_access(user_id, "VIEWER", True)
                    return "changed"
                except ValueError:
                    return "blocked"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(demote, [self.admin_id, second_id]))
        self.assertCountEqual(outcomes, ["changed", "blocked"])
        with self.app.app_context():
            self.assertEqual(get_db().execute("SELECT COUNT(*) FROM users WHERE role='ADMIN' AND is_active=1").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
