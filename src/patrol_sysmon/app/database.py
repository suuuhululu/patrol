"""SQLite 연결과 초기화: day5의 DB 예제를 기능별 모듈로 분리한다."""

import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    # [요청별 DB 연결] 사용자 요청 간 연결을 공유하지 않고 현재 앱 문맥에서 재사용한다.
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"], timeout=5.0)
        try:
            connection.row_factory = sqlite3.Row
            # [참조 무결성] SQLite 외래 키 검사는 새 연결마다 활성화해야 한다.
            connection.execute("PRAGMA foreign_keys = ON")
        except sqlite3.Error:
            connection.close()
            raise
        g.db = connection
    return g.db


def close_db(error=None):
    # [연결 정리] 요청 종료 시 연결을 닫는다. 저장은 서비스에서 명시적으로 커밋한다.
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db():
    # [폴더 준비] DB와 이미지 파일은 소스 코드와 분리해서 보관한다.
    Path(current_app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    Path(current_app.config["EVIDENCE_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(current_app.config["MAP_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(current_app.config["COSTMAP_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(current_app.config["VIDEO_DIR"]).mkdir(parents=True, exist_ok=True)
    connection = get_db()
    # [동시 접근 준비] 읽기와 쓰기의 경합을 줄인다. 쓰기는 여전히 한 번에 하나씩 처리된다.
    connection.execute("PRAGMA journal_mode = WAL")
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    # [순서] 낡은 순찰 표가 남아 있으면 새 인덱스 생성이 실패하므로 스키마 실행 전에 정리한다.
    _drop_legacy_patrol_tables(connection)
    _migrate_estop_contract(connection)
    try:
        # [테이블 생성] 없을 때만 생성하며 초기화 전체를 하나의 트랜잭션으로 처리한다.
        connection.executescript("BEGIN IMMEDIATE;\n" + schema + "\nCOMMIT;")
    except sqlite3.Error:
        connection.rollback()
        raise
    _migrate_vehicle_access(connection)
    _migrate_detection_storage(connection)
    _migrate_pose_validity(connection)
    _migrate_safety_state(connection)
    _migrate_events_report(connection)


ESTOP_COLUMNS = {
    "estop_latest": {
        "target_robot_id", "active", "reason", "sequence", "observed_at", "received_at",
    },
    "estop_history": {
        "id", "target_robot_id", "active", "reason", "sequence", "observed_at", "received_at",
    },
}


def _migrate_estop_contract(connection):
    """EStopState 기준 E-stop 표를 계약 EStop(대상별·reason enum) 구조로 바꾼다.

    옛 열(estop_id·manual_reset_required·source_id)은 새 계약에 대응 값이 없어 옮기지
    않는다. 기록이 있으면 지우지 않고 `_legacy` 이름으로 남겨 필요할 때 확인하게 한다.
    """
    present = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    stale = [
        name for name, columns in ESTOP_COLUMNS.items()
        if name in present
        and {row[1] for row in connection.execute(f"PRAGMA table_info({name})")} != columns
    ]
    if not stale:
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        for name in stale:
            rows = connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            connection.execute(f"DROP TABLE IF EXISTS {name}_legacy")
            if rows:
                connection.execute(f"ALTER TABLE {name} RENAME TO {name}_legacy")
            else:
                connection.execute(f"DROP TABLE {name}")
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise


def _migrate_safety_state(connection):
    """기존 상태 이력을 보존하며 RobotStatus 안전 상태 열만 추가한다."""
    additions = (
        ("safety_state", "TEXT NOT NULL DEFAULT 'UNKNOWN' CHECK (safety_state IN "
                         "('UNKNOWN', 'NORMAL', 'STOPPING', 'STOPPED', 'ESTOPPED', 'ERROR'))"),
        ("motion_stopped", "INTEGER NOT NULL DEFAULT 0 CHECK (motion_stopped IN (0, 1))"),
        ("safety_reason_code", "INTEGER NOT NULL DEFAULT 0"),
        ("safety_reason", "TEXT NOT NULL DEFAULT ''"),
    )
    try:
        connection.execute("BEGIN IMMEDIATE")
        for name in ("robot_latest_status", "robot_status_history"):
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({name})")}
            for column, definition in additions:
                if column not in columns:
                    # 기존 행은 안전 상태를 받은 적이 없으므로 UNKNOWN 기본값이 맞다.
                    connection.execute(f"ALTER TABLE {name} ADD COLUMN {column} {definition}")
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise


def _migrate_events_report(connection):
    """ReportDetection용으로 events의 위험도를 NULL 허용으로 바꾸고 내용 해시 열을 더한다.

    SQLite는 CHECK 제약을 바꿀 수 없어 위험도가 NOT NULL인 기존 DB는 표를 다시 만들어 옮긴다.
    다른 표가 events를 참조하므로 외래 키 검사를 잠시 끄고 수행한다. 기존 행은 모두 보존한다.
    """
    info = {row[1]: row for row in connection.execute("PRAGMA table_info(events)")}
    risk_not_null = bool(info["risk_level"][3]) if "risk_level" in info else False
    if not risk_not_null and "content_hash" in info:
        return
    if not risk_not_null:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ALTER TABLE events ADD COLUMN content_hash TEXT")
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise
        return
    columns = [
        "event_id", "message_id", "robot_id", "event_type", "occurred_at", "x", "y", "frame_id",
        "confidence", "location_valid", "evidence_id", "risk_level", "status", "received_at",
    ]
    present = [name for name in columns if name in info]
    column_list = ", ".join(present)
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE events_report_new (
                event_id TEXT PRIMARY KEY NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                robot_id TEXT NOT NULL REFERENCES robots(robot_id),
                event_type TEXT NOT NULL DEFAULT 'UNKNOWN',
                occurred_at TEXT NOT NULL,
                x REAL,
                y REAL,
                frame_id TEXT,
                confidence REAL CHECK (confidence IS NULL OR (confidence BETWEEN 0 AND 1)),
                location_valid INTEGER NOT NULL DEFAULT 1 CHECK (location_valid IN (0, 1)),
                evidence_id TEXT,
                risk_level TEXT CHECK (risk_level IS NULL OR risk_level IN ('HIGH', 'MEDIUM', 'LOW')),
                status TEXT NOT NULL DEFAULT 'NEW'
                    CHECK (status IN ('NEW', 'REVIEWING', 'WORK_REQUESTED', 'RESOLVED')),
                received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                content_hash TEXT
            )
            """
        )
        connection.execute(
            f"INSERT INTO events_report_new ({column_list}) SELECT {column_list} FROM events"
        )
        connection.execute("DROP TABLE events")
        connection.execute("ALTER TABLE events_report_new RENAME TO events")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_robot_time ON events(robot_id, occurred_at)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_evidence_id ON events(evidence_id)")
        problems = connection.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise sqlite3.IntegrityError(f"events 재구성 후 외래 키 불일치 {len(problems)}건")
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _drop_legacy_patrol_tables(connection):
    """예약 구조로 만들어 둔 순찰 표를 지워 20단계 계약 구조로 다시 만들게 한다."""
    expected = {
        "patrol_runs": {
            "patrol_id", "report_id", "message_id", "robot_id", "mission_id", "command_id",
            "result", "reason_code", "reason", "started_at", "ended_at",
            "planned_visit_count", "completed_visit_count", "received_at",
        },
        "patrol_visits": {
            "visit_id", "message_id", "robot_id", "patrol_id", "mission_id", "command_id",
            "waypoint_id", "x", "y", "frame_id", "result", "reason_code", "reason",
            "arrived_at", "completed_at", "received_at",
        },
    }
    present = {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    stale = [
        name for name, columns in expected.items()
        if name in present
        and {row[1] for row in connection.execute(f"PRAGMA table_info({name})")} != columns
    ]
    if not stale:
        return
    # [보존 판단] 예약 구조에는 실제 기록이 없어야 한다. 값이 있으면 지우지 않고 시작을 중단한다.
    for name in stale:
        rows = connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        if rows:
            raise sqlite3.IntegrityError(
                f"{name}에 기존 기록 {rows}건이 있어 20단계 구조로 자동 변환하지 않습니다."
            )
    try:
        # 방문이 실행을 참조하지 않으므로 순서와 무관하게 지운다. 생성은 schema.sql이 담당한다.
        connection.executescript(
            "BEGIN IMMEDIATE;\n"
            "DROP TABLE IF EXISTS patrol_visits;\n"
            "DROP TABLE IF EXISTS patrol_runs;\n"
            "COMMIT;"
        )
    except sqlite3.Error:
        connection.rollback()
        raise


def _migrate_vehicle_access(connection):
    """초기 이미지형 입출차 테이블을 토픽 내역 전용 구조로 한 번 변환한다."""
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(vehicle_access_logs)")
    }
    expected = {
        "access_id", "message_id", "camera_id", "direction", "detected_at", "received_at",
    }
    if columns == expected:
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "ALTER TABLE vehicle_access_logs RENAME TO vehicle_access_logs_legacy"
        )
        connection.execute(
            """
            CREATE TABLE vehicle_access_logs (
                access_id TEXT PRIMARY KEY NOT NULL,
                message_id TEXT NOT NULL UNIQUE,
                camera_id TEXT NOT NULL CHECK (camera_id IN ('webcam1', 'webcam2')),
                direction TEXT NOT NULL CHECK (direction IN ('ENTRY', 'EXIT')),
                detected_at TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        # [기존 기록 보존] 제거 대상 부가 필드를 버리고 입차·출차 핵심 내역은 유지한다.
        connection.execute(
            """
            INSERT INTO vehicle_access_logs
                (access_id, message_id, camera_id, direction, detected_at, received_at)
            SELECT access_id, message_id, camera_id, direction, detected_at, received_at
              FROM vehicle_access_logs_legacy
            """
        )
        connection.execute("DROP TABLE vehicle_access_logs_legacy")
        connection.execute(
            "CREATE INDEX idx_vehicle_access_detected ON vehicle_access_logs(detected_at)"
        )
        connection.execute(
            "CREATE INDEX idx_vehicle_access_camera_time ON vehicle_access_logs(camera_id, detected_at)"
        )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise


def _migrate_pose_validity(connection):
    """기존 상태 이력을 보존하며 위치 유효성 열만 추가한다."""
    tables = ("robot_latest_status", "robot_status_history")
    missing = {
        name: {row[1] for row in connection.execute(f"PRAGMA table_info({name})")}
        for name in tables
    }
    if all(
        {"pose_valid", "last_valid_pose_at"} <= columns
        for columns in missing.values()
    ):
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        for name, columns in missing.items():
            if "pose_valid" not in columns:
                # 기존 행은 좌표가 유효한 상태로만 저장돼 있어 기본값 1이 맞다.
                connection.execute(
                    f"ALTER TABLE {name} ADD COLUMN pose_valid INTEGER NOT NULL DEFAULT 1 "
                    "CHECK (pose_valid IN (0, 1))"
                )
            if "last_valid_pose_at" not in columns:
                connection.execute(f"ALTER TABLE {name} ADD COLUMN last_valid_pose_at TEXT")
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise


def _migrate_detection_storage(connection):
    """기존 이벤트 이력을 보존하며 ROS Detection 연결에 필요한 열만 추가한다."""
    event_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(events)")
    }
    evidence_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(event_evidence)")
    }
    try:
        connection.execute("BEGIN IMMEDIATE")
        if "confidence" not in event_columns:
            connection.execute(
                "ALTER TABLE events ADD COLUMN confidence REAL "
                "CHECK (confidence IS NULL OR (confidence BETWEEN 0 AND 1))"
            )
        if "location_valid" not in event_columns:
            connection.execute(
                "ALTER TABLE events ADD COLUMN location_valid INTEGER NOT NULL DEFAULT 1 "
                "CHECK (location_valid IN (0, 1))"
            )
        if "evidence_id" not in event_columns:
            connection.execute("ALTER TABLE events ADD COLUMN evidence_id TEXT")
        if "evidence_id" not in evidence_columns:
            connection.execute("ALTER TABLE event_evidence ADD COLUMN evidence_id TEXT")
        # [증적 식별자] NULL인 기존 HTTP 증적은 유지하고 ROS UUID만 전역 중복을 막는다.
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_evidence_id "
            "ON events(evidence_id) WHERE evidence_id IS NOT NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_event_evidence_evidence_id "
            "ON event_evidence(evidence_id) WHERE evidence_id IS NOT NULL"
        )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        try:
            init_db()
        except (OSError, sqlite3.Error):
            # [초기화 실패] DB 없이 서버가 정상 동작하는 것처럼 시작하지 않도록 중단한다.
            app.logger.exception("SQLite 초기화 실패: 저장 경로와 접근 권한을 확인하세요.")
            raise
