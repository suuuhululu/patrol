"""실제 차량 인식 토픽 연결 전 입차·출차 내역을 보내는 수동 시연 도구."""

from datetime import datetime, timezone
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("1 이상이어야 합니다.")
    return parsed


def nonnegative_float(value):
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("0 이상이어야 합니다.")
    return parsed


def send_one(url, token, camera, direction):
    """한 건을 보내고 서버 응답을 그대로 돌려준다."""
    now = datetime.now(timezone.utc)
    unique = now.strftime("%Y%m%d%H%M%S%f")
    payload = {
        "access_id": f"demo-access-{unique}",
        "message_id": f"demo-access-message-{unique}",
        "camera_id": camera,
        "direction": direction,
        "detected_at": now.isoformat(),
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Robot-Token": token},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8")


def main():
    parser = argparse.ArgumentParser(description="Sysmon에 임시 차량 입출차 내역을 전송합니다.")
    parser.add_argument("--url", default="http://127.0.0.1:5000/api/vehicle-access")
    parser.add_argument("--camera", choices=("webcam1", "webcam2"), default="webcam1")
    parser.add_argument("--direction", choices=("ENTRY", "EXIT", "ALTERNATE"), default="ENTRY",
                        help="ALTERNATE는 입차·출차를 번갈아 보낸다.")
    # [시연 편의] 목록이 한눈에 차도록 여러 건을 간격을 두고 보낸다.
    parser.add_argument("--count", type=positive_int, default=1)
    parser.add_argument("--interval", type=nonnegative_float, default=1.0)
    args = parser.parse_args()
    token = os.environ.get("SYSMON_ROBOT_API_KEY")
    if not token:
        raise SystemExit("SYSMON_ROBOT_API_KEY 환경변수를 먼저 설정하세요.")
    try:
        token.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SystemExit("SYSMON_ROBOT_API_KEY는 ASCII 문자열이어야 합니다.") from exc

    for index in range(args.count):
        # [진입·진출 순서] ALTERNATE는 입차 다음 출차가 오도록 번갈아 보낸다.
        direction = (
            ("ENTRY" if index % 2 == 0 else "EXIT")
            if args.direction == "ALTERNATE" else args.direction
        )
        try:
            print(f"[{index + 1}/{args.count}] {direction} → " + send_one(
                args.url, token, args.camera, direction
            ))
        except urllib.error.HTTPError as exc:
            print(exc.read().decode("utf-8"), file=sys.stderr)
            raise SystemExit(exc.code) from exc
        if index + 1 < args.count and args.interval:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
