"""상대 publisher 대신 기본·costmap·CCTV·순찰·안전 토픽을 발행하는 시험 CLI. 사건은 서비스로 받으므로 발행하지 않는다."""

from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from testkit.ros_topic_test import RosTopicTestConfig, run_virtual_publisher
from tools.run_ros_topic_test import domain_id, positive_float


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="운영 도메인 6과 분리해 기본·costmap·CCTV·순찰·안전 토픽을 발행합니다."
    )
    parser.add_argument("--duration", type=positive_float, default=3.0)
    parser.add_argument("--domain-id", type=domain_id, default=80)
    parser.add_argument("--status-hz", type=positive_float, default=4.0)
    parser.add_argument("--map-hz", type=positive_float, default=1.0)
    parser.add_argument("--image-hz", type=positive_float, default=2.0)
    parser.add_argument("--costmap-hz", type=positive_float, default=0.0)
    parser.add_argument("--cctv-hz", type=positive_float, default=0.0)
    parser.add_argument("--patrol-hz", type=positive_float, default=0.0)
    parser.add_argument("--safety-hz", type=positive_float, default=0.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = run_virtual_publisher(RosTopicTestConfig(
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
