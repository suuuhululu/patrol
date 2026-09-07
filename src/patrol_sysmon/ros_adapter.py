"""sysmon 웹 프로세스와 분리해 ROS 2 구독 adapter를 실행한다."""

import argparse
import json

from app import create_app
from app.ros_adapter import RosAdapterUnavailable, dependency_report, spin


def main():
    parser = argparse.ArgumentParser(description="sysmon ROS 2 adapter")
    parser.add_argument(
        "--check",
        action="store_true",
        help="토픽 구독을 시작하지 않고 ROS 의존성과 등록 토픽만 확인",
    )
    args = parser.parse_args()
    report = dependency_report()
    if args.check:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ready"] else 2
    try:
        spin(create_app())
    except RosAdapterUnavailable as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
