"""16~19단계: 가상 publisher와 adapter를 별도 프로세스로 실행해 수신 경계를 검증한다."""

from multiprocessing import get_context
from pathlib import Path
from queue import Empty
import os
import tempfile
import time

from app.ros_adapter import build_node, dependency_report
# [실행 방식] fork는 부모가 이미 만든 rclpy·DDS 스레드를 자식에서 되살리지 못해
# 같은 프로세스에서 다른 ROS 시험을 먼저 실행하면 adapter 자식이 준비되지 않는다.
# forkserver는 rclpy를 쓰지 않은 별도 서버 프로세스에서 자식을 만들어
# 시험 순서와 무관하게 같은 결과를 낸다.
START_METHOD = "forkserver"
# [준비 대기] forkserver 첫 기동은 서버 프로세스 생성 비용이 있다.
ADAPTER_READY_TIMEOUT_SECONDS = 30.0
# [수신 구간] 자식 시작이 늦어도 publisher가 끝날 때까지 adapter가 수신한다.
# 종료 신호는 spin 사이에서만 확인하므로, 조각을 잘게 나누면 수신량이 줄어든다.
ADAPTER_SPIN_SLICE_SECONDS = 1.0
ADAPTER_MAX_SPIN_SECONDS = 120.0

from .ros_topic_test import (
    RosTopicTestConfig,
    _create_viewer,
    _dashboard_report,
    _isolated_ros_environment,
    _spin_for,
    _storage_report,
    _temporary_app,
    run_virtual_publisher,
)


def _adapter_process(root_text, config, ready, stop, results):
    root = Path(root_text)
    node = None
    executor = None
    try:
        app = _temporary_app(root)
        with _isolated_ros_environment(
            config.domain_id, root / "ros_logs" / "adapter"
        ):
            import rclpy
            from rclpy.executors import SingleThreadedExecutor

            rclpy.init(args=None)
            executor = SingleThreadedExecutor()
            node = build_node(
                app, node_name=f"sysmon_ros_adapter_process_test_{os.getpid()}"
            )
            executor.add_node(node)
            ready.set()
            _spin_until_publisher_stops(executor, stop, config)
            results.put({
                "role": "adapter",
                "processed": dict(sorted(node.processing_counts.items())),
                "ack_publisher_matches": node.ack_publisher_matches(),
            })
    except Exception as exc:
        ready.set()
        results.put({
            "role": "adapter",
            "error": f"{type(exc).__name__}: {exc}",
        })
        raise
    finally:
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        try:
            import rclpy
            if rclpy.ok():
                rclpy.shutdown()
        except ImportError:
            pass


def _spin_until_publisher_stops(executor, stop, config):
    """publisher가 끝날 때까지 수신한다.

    고정 시간으로 spin하면 자식 프로세스 시작이 늦어진 만큼 수신 구간이 줄어
    ack 왕복 같은 늦은 메시지를 놓친다. 부모가 publisher 종료 후 stop을 설정한다.
    """
    deadline = time.monotonic() + min(
        ADAPTER_MAX_SPIN_SECONDS,
        config.duration_seconds + ADAPTER_READY_TIMEOUT_SECONDS,
    )
    while not stop.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        _spin_for(executor, min(ADAPTER_SPIN_SLICE_SECONDS, remaining))
    # [마지막 메시지] 종료 직전에 도착한 메시지까지 처리한다.
    _spin_for(executor, 0.5)


def _publisher_process(root_text, config, results):
    try:
        report = run_virtual_publisher(
            config, Path(root_text) / "ros_logs" / "publisher"
        )
        results.put({"role": "publisher", **report})
    except Exception as exc:
        results.put({
            "role": "publisher",
            "error": f"{type(exc).__name__}: {exc}",
        })
        raise


def _result_for(results, role):
    collected = {}
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and role not in collected:
        try:
            item = results.get(timeout=0.2)
        except Empty:
            continue
        collected[item["role"]] = item
    return collected.get(role)


def _stop_process(process):
    if process is None:
        return
    process.join(timeout=10.0)
    if process.is_alive():
        process.terminate()
        process.join(timeout=2.0)


def run_separate_process_ros_test(config=None):
    """별도 adapter·publisher 프로세스의 DDS 수신과 임시 저장 결과를 보고한다."""
    config = config or RosTopicTestConfig(domain_id=80)
    config.validate()
    dependencies = dependency_report()
    if not dependencies["ready"]:
        missing = [
            name for name, available in dependencies["dependencies"].items()
            if not available
        ]
        raise RuntimeError("ROS process 시험 의존성이 없습니다: " + ", ".join(missing))

    temporary = tempfile.TemporaryDirectory(prefix="sysmon-ros-stage16-")
    root = Path(temporary.name)
    report = None
    adapter_process = None
    publisher_process = None
    context = get_context(START_METHOD)
    results = context.Queue()
    ready = context.Event()
    stop = context.Event()
    try:
        adapter_process = context.Process(
            target=_adapter_process,
            args=(str(root), config, ready, stop, results),
            name="sysmon-stage16-adapter",
        )
        adapter_process.start()
        if not ready.wait(timeout=ADAPTER_READY_TIMEOUT_SECONDS):
            raise RuntimeError(
                f"adapter 프로세스가 {ADAPTER_READY_TIMEOUT_SECONDS:.0f}초 안에 준비되지 않았습니다."
            )
        if not adapter_process.is_alive():
            adapter_result = _result_for(results, "adapter")
            raise RuntimeError(f"adapter 프로세스 시작 실패: {adapter_result}")

        publisher_process = context.Process(
            target=_publisher_process,
            args=(str(root), config, results),
            name="sysmon-stage16-publisher",
        )
        publisher_process.start()
        _stop_process(publisher_process)
        # [수신 종료] publisher가 끝난 뒤 신호를 보내야 수신 구간이 짧아지지 않는다.
        stop.set()
        _stop_process(adapter_process)

        child_results = {}
        deadline = time.monotonic() + 3.0
        while len(child_results) < 2 and time.monotonic() < deadline:
            try:
                item = results.get(timeout=0.2)
            except Empty:
                continue
            child_results[item["role"]] = item
        adapter_result = child_results.get("adapter")
        publisher_result = child_results.get("publisher")

        app = _temporary_app(root)
        viewer_id = _create_viewer(app)
        storage = _storage_report(app)
        dashboard = _dashboard_report(app, viewer_id)
        child_errors = {
            role: result.get("error")
            for role, result in child_results.items()
            if result.get("error")
        }
        processed = adapter_result.get("processed", {}) if adapter_result else {}
        matched = (
            publisher_result.get("matched_subscriptions", {})
            if publisher_result else {}
        )
        # publisher가 종료되면 adapter 쪽 매칭 수는 0이 되므로 살아 있을 때
        # 가상 subscriber가 관측해 보고한 publisher 수를 사용한다.
        ack_matches = (
            publisher_result.get("ack_publisher_matches", {})
            if publisher_result else {}
        )
        received_acks = publisher_result.get("received_acks", {}) if publisher_result else {}
        processing_failures = sum(
            count for name, count in processed.items()
            if name.endswith("_failed") or name.endswith("_rejected")
        )
        process_pass = (
            adapter_process.exitcode == 0
            and publisher_process.exitcode == 0
            and not child_errors
            and len(matched) == (
                7 + (4 if config.costmap_hz > 0 else 0)
                + (4 if config.detection_hz > 0 else 0)
                + (3 if config.cctv_hz > 0 else 0)
                + (4 if config.patrol_hz > 0 else 0)
                + (3 if config.safety_hz > 0 else 0)
            )
            and all(count >= 1 for count in matched.values())
            and set(storage["robot_latest_ids"]) == {"AMR1", "AMR2"}
            and storage["robot_status_history"] >= 2
            and storage["maps"] >= 1
            and set(storage["camera_ids"]) == {"amr1", "amr2", "webcam1", "webcam2"}
            and storage["integrity_check"] == "ok"
            and storage["foreign_key_errors"] == 0
            and all(status == 200 for status in dashboard.values())
            and processing_failures == 0
            and (
                config.costmap_hz == 0
                or set(storage["costmap_sources"]) == {
                    "AMR1:global", "AMR1:local", "AMR2:global", "AMR2:local"
                }
            )
            and (
                config.detection_hz == 0
                or (
                    storage["detection_event_messages"] >= 2
                    and storage["stored_evidence"] >= 2
                    and storage["incomplete_evidence"] == 0
                    and storage["evidence_links"] >= 2
                    and storage["chunk_payloads_remaining"] == 0
                    and len(ack_matches) == 2
                    and all(count >= 1 for count in ack_matches.values())
                    and sum(received_acks.values()) >= 6
                )
            )
            and (
                config.patrol_hz == 0
                or (
                    storage["patrol_visits"] >= 2
                    and storage["patrol_reports"] >= 1
                )
            )
            and (
                config.safety_hz == 0
                or (
                    set(storage["keepout_states"]) and storage["estop_latest"] is not None
                    and storage["estop_changes"] >= 2
                )
            )
            and (
                config.cctv_hz == 0
                or (
                    storage["cctv_state_events"] >= 2
                    and set(storage["cctv_camera_ids"]) == {"gate_cam", "center_cam"}
                    and storage["patrol_permit_latest"] is not None
                    and storage["patrol_permit_history"] >= 2
                )
            )
        )
        report = {
            "stage": (
                20 if config.patrol_hz > 0 or config.safety_hz > 0
                else 19 if config.cctv_hz > 0
                else (18 if config.detection_hz > 0 else (17 if config.costmap_hz > 0 else 16))
            ),
            "test_kind": (
                "SEPARATE_PROCESS_VIRTUAL_DDS_WITH_PATROL_SAFETY"
                if config.patrol_hz > 0 or config.safety_hz > 0
                else "SEPARATE_PROCESS_VIRTUAL_DDS_WITH_CCTV" if config.cctv_hz > 0
                else "SEPARATE_PROCESS_VIRTUAL_DDS_WITH_DETECTION" if config.detection_hz > 0
                else ("SEPARATE_PROCESS_VIRTUAL_DDS_WITH_COSTMAP" if config.costmap_hz > 0 else "SEPARATE_PROCESS_VIRTUAL_DDS")
            ),
            "external_publishers": "NOT_RUN",
            "config": {
                "duration_seconds": config.duration_seconds,
                "domain_id": config.domain_id,
                "status_hz": config.status_hz,
                "map_hz": config.map_hz,
                "image_hz": config.image_hz,
                "costmap_hz": config.costmap_hz,
                "detection_hz": config.detection_hz,
                "cctv_hz": config.cctv_hz,
                "patrol_hz": config.patrol_hz,
                "safety_hz": config.safety_hz,
            },
            "process_exit_codes": {
                "adapter": adapter_process.exitcode,
                "publisher": publisher_process.exitcode,
            },
            "child_errors": child_errors,
            "published": publisher_result.get("published", {}) if publisher_result else {},
            "matched_subscriptions": matched,
            "ack_publisher_matches": ack_matches,
            "received_acks": received_acks,
            "processed": processed,
            "storage": storage,
            "dashboard_http": dashboard,
            "processing_failures": processing_failures,
            "process_pass": process_pass,
            "scope_note": "별도 로컬 프로세스·격리 도메인·임시 저장소 시험이며 PC 간 통합시험이 아님",
        }
    finally:
        stop.set()
        _stop_process(publisher_process)
        _stop_process(adapter_process)
        results.close()
        temporary.cleanup()
    report["temporary_storage_removed"] = not root.exists()
    return report
