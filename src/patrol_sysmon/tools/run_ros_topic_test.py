"""15단계 가상 ROS publisher와 sysmon subscriber의 로컬 종단시험 CLI."""

from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from testkit.ros_topic_test import RosTopicTestConfig, run_local_ros_topic_test


def positive_float(value):
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("0보다 커야 합니다.")
    return parsed


def domain_id(value):
    parsed = int(value)
    if not 0 <= parsed <= 232 or parsed == 6:
        raise argparse.ArgumentTypeError("0~232 중 운영 도메인 6이 아닌 값이어야 합니다.")
    return parsed


def build_parser():
    parser = argparse.ArgumentParser(
        description="운영 ROS 도메인과 DB를 건드리지 않고 기본·costmap·CCTV·순찰·안전 토픽을 시험합니다."
    )
    parser.add_argument("--duration", type=positive_float, default=3.0)
    parser.add_argument("--domain-id", type=domain_id, default=77)
    parser.add_argument("--status-hz", type=positive_float, default=4.0)
    parser.add_argument("--map-hz", type=positive_float, default=1.0)
    parser.add_argument("--image-hz", type=positive_float, default=2.0)
    # [선택 토픽] 0이면 발행하지 않는다. 별도 프로세스 시험 CLI와 인자를 맞춘다.
    parser.add_argument("--costmap-hz", type=positive_float, default=0.0)
    parser.add_argument("--cctv-hz", type=positive_float, default=0.0)
    parser.add_argument("--patrol-hz", type=positive_float, default=0.0)
    parser.add_argument("--safety-hz", type=positive_float, default=0.0)
    parser.add_argument("--output", type=Path)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    report = run_local_ros_topic_test(RosTopicTestConfig(
        duration_seconds=args.duration,
        domain_id=args.domain_id,
        status_hz=args.status_hz,
        map_hz=args.map_hz,
        image_hz=args.image_hz,
        costmap_hz=args.costmap_hz,
        cctv_hz=args.cctv_hz,
        patrol_hz=args.patrol_hz,
        safety_hz=args.safety_hz,
    ))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["local_pass"] and report["temporary_storage_removed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
