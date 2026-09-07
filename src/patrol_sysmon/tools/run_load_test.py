"""13단계 sysmon 부하·동시접속·SQLite 경합 측정 CLI."""

from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from testkit.load_test import LoadTestConfig, run_load_test


def nonnegative_int(value):
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("0 이상이어야 합니다.")
    return parsed


def nonnegative_float(value):
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("0 이상이어야 합니다.")
    return parsed


def positive_float(value):
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("0보다 커야 합니다.")
    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description="실제 운영 DB를 건드리지 않고 sysmon 부하를 측정합니다."
    )
    parser.add_argument("--duration", type=positive_float, default=3.0)
    parser.add_argument("--readers", type=nonnegative_int, default=2)
    parser.add_argument("--read-hz", type=nonnegative_float, default=2.0)
    parser.add_argument("--status-hz", type=nonnegative_float, default=4.0)
    parser.add_argument("--map-hz", type=nonnegative_float, default=0.2)
    parser.add_argument("--camera-hz", type=nonnegative_float, default=8.0)
    parser.add_argument("--event-hz", type=nonnegative_float, default=0.2)
    parser.add_argument("--vehicle-hz", type=nonnegative_float, default=0.2)
    parser.add_argument("--seed-history", type=nonnegative_int, default=100)
    parser.add_argument(
        "--lock-seconds",
        type=nonnegative_float,
        default=0.0,
        help="LT-13-06용 write lock 유지 시간. 0이면 lock을 주입하지 않음",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSON 결과 저장 경로. 생략하면 표준 출력에만 표시",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    report = run_load_test(LoadTestConfig(
        duration_seconds=args.duration,
        readers=args.readers,
        read_hz_per_reader=args.read_hz,
        status_hz=args.status_hz,
        map_hz=args.map_hz,
        camera_hz=args.camera_hz,
        event_hz=args.event_hz,
        vehicle_hz=args.vehicle_hz,
        seed_history=args.seed_history,
        lock_seconds=args.lock_seconds,
    ))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if (
        report["integrity_ok"]
        and report["unexpected_exceptions"] == 0
        and report["unexpected_http_errors"] == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
