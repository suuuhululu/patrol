"""13단계: 임시 sysmon 환경에서 동시 입력·조회와 SQLite 경합을 측정한다."""

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import json
import math
import resource
import secrets
import sqlite3
import tempfile
import threading
import time

from app import create_app
from app.database import get_db
from app.services import auth_service
from app.services.map_service import occupancy_to_png


@dataclass(frozen=True)
class LoadTestConfig:
    """확정되지 않은 현장 부하를 실행 인자로 바꿀 수 있게 한 시험 설정."""

    duration_seconds: float = 3.0
    readers: int = 2
    read_hz_per_reader: float = 2.0
    status_hz: float = 4.0
    map_hz: float = 0.2
    camera_hz: float = 8.0
    event_hz: float = 0.2
    vehicle_hz: float = 0.2
    seed_history: int = 100
    lock_seconds: float = 0.0

    def validate(self):
        numeric_rates = {
            "duration_seconds": self.duration_seconds,
            "read_hz_per_reader": self.read_hz_per_reader,
            "status_hz": self.status_hz,
            "map_hz": self.map_hz,
            "camera_hz": self.camera_hz,
            "event_hz": self.event_hz,
            "vehicle_hz": self.vehicle_hz,
            "lock_seconds": self.lock_seconds,
        }
        if (
            isinstance(self.duration_seconds, bool)
            or not math.isfinite(self.duration_seconds)
            or self.duration_seconds <= 0
        ):
            raise ValueError("duration_seconds는 0보다 큰 유한한 숫자여야 합니다.")
        for name, value in numeric_rates.items():
            if name == "duration_seconds":
                continue
            if isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name}은 0 이상의 유한한 숫자여야 합니다.")
        if (
            isinstance(self.readers, bool)
            or not isinstance(self.readers, int)
            or self.readers < 0
        ):
            raise ValueError("readers는 0 이상의 정수여야 합니다.")
        if (
            isinstance(self.seed_history, bool)
            or not isinstance(self.seed_history, int)
            or self.seed_history < 0
        ):
            raise ValueError("seed_history는 0 이상의 정수여야 합니다.")


class Metrics:
    """여러 worker의 요청 결과를 한곳에 모으는 thread-safe 수집기."""

    def __init__(self):
        self._lock = threading.Lock()
        self._latencies = defaultdict(list)
        self._statuses = defaultdict(Counter)
        self._exceptions = defaultdict(Counter)

    def record_response(self, operation, elapsed_seconds, status_code):
        with self._lock:
            self._latencies[operation].append(elapsed_seconds * 1000.0)
            self._statuses[operation][str(status_code)] += 1

    def record_exception(self, operation, elapsed_seconds, exc):
        with self._lock:
            self._latencies[operation].append(elapsed_seconds * 1000.0)
            self._exceptions[operation][type(exc).__name__] += 1

    @staticmethod
    def _percentile(values, percentile):
        if not values:
            return None
        ordered = sorted(values)
        position = (len(ordered) - 1) * percentile
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    def report(self):
        operations = sorted(
            set(self._latencies) | set(self._statuses) | set(self._exceptions)
        )
        result = {}
        for operation in operations:
            samples = self._latencies[operation]
            result[operation] = {
                "requests": len(samples),
                "status_codes": dict(sorted(self._statuses[operation].items())),
                "exceptions": dict(sorted(self._exceptions[operation].items())),
                "latency_ms": {
                    "p50": _rounded(self._percentile(samples, 0.50)),
                    "p95": _rounded(self._percentile(samples, 0.95)),
                    "p99": _rounded(self._percentile(samples, 0.99)),
                    "max": _rounded(max(samples) if samples else None),
                },
            }
        return result


def _rounded(value):
    return round(value, 3) if value is not None else None


def _utc_now():
    return datetime.now(timezone.utc)


def _utc_text(value):
    return value.astimezone(timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _test_app(root):
    instance = root / "instance"
    return create_app({
        "TESTING": True,
        "DATABASE": str(instance / "sysmon.sqlite3"),
        "EVIDENCE_DIR": str(instance / "evidence"),
        "MAP_DIR": str(instance / "maps"),
        "VIDEO_DIR": str(instance / "live_frames"),
        "SECRET_KEY": secrets.token_urlsafe(32),
        "ROBOT_API_KEY": secrets.token_urlsafe(32),
        "ROBOT_OFFLINE_AFTER_SECONDS": 15,
        "MAP_MAX_CELLS": 1_000_000,
        "EVENT_IMAGE_MAX_BYTES": 5 * 1024 * 1024,
        "VIDEO_FRAME_MAX_BYTES": 2 * 1024 * 1024,
        "CAMERA_OFFLINE_AFTER_SECONDS": 5,
    })


def _seed_history(app, count):
    if count == 0:
        return
    start = _utc_now() - timedelta(seconds=count + 10)
    with app.app_context():
        db = get_db()
        db.executemany(
            "INSERT OR IGNORE INTO robots(robot_id, name) VALUES (?, ?)",
            (("AMR1", "로봇 1"), ("AMR2", "로봇 2")),
        )
        rows = []
        for index in range(count):
            robot_id = "AMR1" if index % 2 == 0 else "AMR2"
            observed = _utc_text(start + timedelta(seconds=index))
            rows.append((
                robot_id,
                f"load-seed-status-{index}",
                80.0 - index % 30,
                float(index % 40),
                float(index % 20),
                "map",
                "PATROLLING",
                "ONLINE",
                observed,
                observed,
            ))
        db.executemany(
            """
            INSERT INTO robot_status_history
                (robot_id, message_id, battery, x, y, frame_id,
                 mission_status, connection_status, observed_at, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        db.commit()


def _create_viewer(app):
    with app.app_context():
        return auth_service.create_user(
            f"load-viewer-{secrets.token_hex(6)}",
            secrets.token_urlsafe(24),
            "VIEWER",
        )


def _device_headers(app):
    return {"X-Robot-Token": app.config["ROBOT_API_KEY"]}


def _measure(metrics, operation, request_fn):
    started = time.perf_counter()
    try:
        response = request_fn()
    except Exception as exc:
        metrics.record_exception(operation, time.perf_counter() - started, exc)
        return
    try:
        metrics.record_response(
            operation, time.perf_counter() - started, response.status_code
        )
    finally:
        response.close()


def _run_at_rate(stop_at, rate_hz, operation):
    if rate_hz <= 0:
        return
    interval = 1.0 / rate_hz
    sequence = 0
    next_run = time.perf_counter()
    while time.perf_counter() < stop_at:
        operation(sequence)
        sequence += 1
        next_run += interval
        delay = min(next_run, stop_at) - time.perf_counter()
        if delay > 0:
            time.sleep(delay)


def _status_worker(app, stop_at, rate_hz, metrics):
    client = app.test_client()
    headers = _device_headers(app)

    def send(sequence):
        robot_id = "AMR1" if sequence % 2 == 0 else "AMR2"
        now = _utc_now()
        payload = {
            "message_id": f"load-status-{sequence}-{time.time_ns()}",
            "robot_id": robot_id,
            "battery": 80.0 - sequence % 20,
            "x": float(sequence % 30),
            "y": float(sequence % 15),
            "frame_id": "map",
            "mission_status": "PATROLLING",
            "connection_status": "ONLINE",
            "observed_at": _utc_text(now),
        }
        _measure(
            metrics, "write_robot_status",
            lambda: client.post("/api/robots/status", json=payload, headers=headers),
        )

    _run_at_rate(stop_at, rate_hz, send)


def _map_worker(app, stop_at, rate_hz, metrics):
    client = app.test_client()
    headers = _device_headers(app)
    width, height = 16, 16
    data = [0] * (width * height)

    def send(sequence):
        now = _utc_now()
        payload = {
            "message_id": f"load-map-{sequence}-{time.time_ns()}",
            "frame_id": "map",
            "resolution": 0.5,
            "width": width,
            "height": height,
            "origin": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            "data": data,
            "observed_at": _utc_text(now),
        }
        _measure(
            metrics, "write_map",
            lambda: client.post("/api/maps/current", json=payload, headers=headers),
        )

    _run_at_rate(stop_at, rate_hz, send)


def _camera_worker(app, stop_at, rate_hz, metrics, png):
    client = app.test_client()
    headers = _device_headers(app)
    cameras = ("amr1", "amr2", "webcam1", "webcam2")

    def send(sequence):
        camera_id = cameras[sequence % len(cameras)]
        now = _utc_now()
        frame_headers = {
            **headers,
            "X-Frame-Id": f"load-{camera_id}-{sequence}-{time.time_ns()}",
            "X-Captured-At": _utc_text(now),
        }
        _measure(
            metrics, "write_camera_frame",
            lambda: client.post(
                f"/api/cameras/{camera_id}/frame",
                data=png,
                headers=frame_headers,
                content_type="image/png",
            ),
        )

    _run_at_rate(stop_at, rate_hz, send)


def _event_worker(app, stop_at, rate_hz, metrics, png):
    client = app.test_client()
    headers = _device_headers(app)
    event_types = ("FIRE", "LEAK", "OBSTACLE")

    def send(sequence):
        unique = f"{sequence}-{time.time_ns()}"
        now = _utc_now()
        metadata = {
            "event_id": f"load-event-{unique}",
            "message_id": f"load-event-message-{unique}",
            "robot_id": "AMR1" if sequence % 2 == 0 else "AMR2",
            "event_type": event_types[sequence % len(event_types)],
            "occurred_at": _utc_text(now),
            "captured_at": _utc_text(now),
            "x": float(sequence % 30),
            "y": float(sequence % 15),
            "frame_id": "map",
            "risk_level": "MEDIUM",
        }
        _measure(
            metrics, "write_event",
            lambda: client.post(
                "/api/events",
                data={
                    "metadata": json.dumps(metadata),
                    "image": (BytesIO(png), f"load-{unique}.png"),
                },
                headers=headers,
                content_type="multipart/form-data",
            ),
        )

    _run_at_rate(stop_at, rate_hz, send)


def _vehicle_worker(app, stop_at, rate_hz, metrics):
    client = app.test_client()
    headers = _device_headers(app)

    def send(sequence):
        unique = f"{sequence}-{time.time_ns()}"
        payload = {
            "access_id": f"load-access-{unique}",
            "message_id": f"load-access-message-{unique}",
            "camera_id": "webcam1" if sequence % 2 == 0 else "webcam2",
            "direction": "ENTRY" if sequence % 2 == 0 else "EXIT",
            "detected_at": _utc_text(_utc_now()),
        }
        _measure(
            metrics, "write_vehicle_access",
            lambda: client.post("/api/vehicle-access", json=payload, headers=headers),
        )

    _run_at_rate(stop_at, rate_hz, send)


def _reader_worker(app, viewer_id, stop_at, rate_hz, metrics, reader_index):
    client = app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = viewer_id
    paths = (
        "/",
        "/api/robots/status",
        "/api/maps/current",
        "/api/cameras",
        "/api/events",
        "/api/vehicle-access",
        "/api/history",
    )

    def read(sequence):
        path = paths[(sequence + reader_index) % len(paths)]
        operation = "read_" + (
            "dashboard"
            if path == "/"
            else path.strip("/").replace("/", "_").replace("-", "_")
        )
        _measure(metrics, operation, lambda: client.get(path))

    _run_at_rate(stop_at, rate_hz, read)


def _lock_worker(database_path, stop_at, lock_seconds, lock_state):
    if lock_seconds <= 0:
        return
    delay = max(0.0, min(0.1, (stop_at - time.perf_counter()) / 4))
    if delay:
        time.sleep(delay)
    connection = sqlite3.connect(database_path, timeout=1.0)
    try:
        connection.execute("BEGIN IMMEDIATE")
        lock_state["acquired"] = True
        time.sleep(lock_seconds)
        connection.rollback()
        lock_state["released"] = True
    finally:
        connection.close()


def _post_lock_probe(app, metrics):
    """장기 lock이 해제된 뒤 같은 쓰기 경로가 정상 복구됐는지 확인한다."""
    client = app.test_client()
    now = _utc_now()
    payload = {
        "message_id": f"load-post-lock-{time.time_ns()}",
        "robot_id": "AMR1",
        "battery": 79.0,
        "x": 1.0,
        "y": 1.0,
        "frame_id": "map",
        "mission_status": "PATROLLING",
        "connection_status": "ONLINE",
        "observed_at": _utc_text(now),
    }
    _measure(
        metrics,
        "post_lock_robot_status",
        lambda: client.post(
            "/api/robots/status",
            json=payload,
            headers=_device_headers(app),
        ),
    )


def _folder_usage(path):
    files = 0
    size = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                files += 1
                size += item.stat().st_size
    return {"files": files, "bytes": size}


def _storage_report(app):
    database_path = Path(app.config["DATABASE"])
    connection = sqlite3.connect(database_path)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = len(connection.execute("PRAGMA foreign_key_check").fetchall())
        table_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "users",
                "robot_status_history",
                "maps",
                "events",
                "event_evidence",
                "vehicle_access_logs",
            )
        }
    finally:
        connection.close()
    instance = database_path.parent
    temporary_files = [
        str(path.relative_to(instance))
        for path in instance.rglob("*.tmp")
        if path.is_file()
    ]
    return {
        "integrity_check": integrity,
        "foreign_key_errors": foreign_key_errors,
        "table_counts": table_counts,
        "database_bytes": database_path.stat().st_size,
        "wal_bytes": Path(str(database_path) + "-wal").stat().st_size
        if Path(str(database_path) + "-wal").exists() else 0,
        "evidence": _folder_usage(Path(app.config["EVIDENCE_DIR"])),
        "maps": _folder_usage(Path(app.config["MAP_DIR"])),
        "live_frames": _folder_usage(Path(app.config["VIDEO_DIR"])),
        "temporary_files": temporary_files,
    }


def run_load_test(config=None):
    """임시 환경에서 부하를 실행하고 합격 판정이 아닌 측정 보고서를 반환한다."""
    config = config or LoadTestConfig()
    config.validate()
    temporary = tempfile.TemporaryDirectory(prefix="sysmon-load-")
    root = Path(temporary.name)
    report = None
    try:
        app = _test_app(root)
        _seed_history(app, config.seed_history)
        viewer_id = _create_viewer(app)
        png = occupancy_to_png([0, 100, -1, 0], 2, 2)
        metrics = Metrics()
        lock_state = {"requested_seconds": config.lock_seconds, "acquired": False, "released": False}
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        stop_at = wall_start + config.duration_seconds
        workers = []
        worker_specs = (
            (_status_worker, (app, stop_at, config.status_hz, metrics)),
            (_map_worker, (app, stop_at, config.map_hz, metrics)),
            (_camera_worker, (app, stop_at, config.camera_hz, metrics, png)),
            (_event_worker, (app, stop_at, config.event_hz, metrics, png)),
            (_vehicle_worker, (app, stop_at, config.vehicle_hz, metrics)),
        )
        for worker, arguments in worker_specs:
            rate = arguments[2]
            if rate > 0:
                workers.append((worker, arguments))
        for reader_index in range(config.readers):
            workers.append((
                _reader_worker,
                (
                    app,
                    viewer_id,
                    stop_at,
                    config.read_hz_per_reader,
                    metrics,
                    reader_index,
                ),
            ))
        if config.lock_seconds > 0:
            workers.append((
                _lock_worker,
                (
                    app.config["DATABASE"],
                    stop_at,
                    config.lock_seconds,
                    lock_state,
                ),
            ))
        with ThreadPoolExecutor(max_workers=max(1, len(workers))) as pool:
            futures = [pool.submit(worker, *arguments) for worker, arguments in workers]
            for future in futures:
                future.result()
        if config.lock_seconds > 0:
            _post_lock_probe(app, metrics)
        wall_seconds = time.perf_counter() - wall_start
        cpu_seconds = time.process_time() - cpu_start
        storage = _storage_report(app)
        operation_report = metrics.report()
        unexpected_exceptions = sum(
            sum(operation["exceptions"].values()) for operation in operation_report.values()
        )
        unexpected_http_errors = 0
        for operation_name, operation in operation_report.items():
            for status_code, count in operation["status_codes"].items():
                code = int(status_code)
                expected_lock_timeout = (
                    config.lock_seconds > 0
                    and code == 503
                    and operation_name.startswith("write_")
                )
                if code >= 400 and not expected_lock_timeout:
                    unexpected_http_errors += count
        integrity_ok = (
            storage["integrity_check"] == "ok"
            and storage["foreign_key_errors"] == 0
            and not storage["temporary_files"]
        )
        report = {
            "stage": 13,
            "measurement_status": "MEASURED",
            "pass_threshold_status": "TBD-MON-001·003",
            "started_at": _utc_text(
                _utc_now() - timedelta(seconds=wall_seconds)
            ),
            "config": asdict(config),
            "runtime": {
                "wall_seconds": _rounded(wall_seconds),
                "cpu_seconds": _rounded(cpu_seconds),
                "cpu_to_wall_ratio": _rounded(cpu_seconds / wall_seconds)
                if wall_seconds else None,
                "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
            "operations": operation_report,
            "storage": storage,
            "lock_scenario": lock_state,
            "integrity_ok": integrity_ok,
            "unexpected_exceptions": unexpected_exceptions,
            "unexpected_http_errors": unexpected_http_errors,
            "scope_note": "임시 Flask client·SQLite 측정이며 실제 ROS·PC 간 네트워크 시험이 아님",
        }
    finally:
        temporary.cleanup()
    report["temporary_storage_removed"] = not root.exists()
    return report
