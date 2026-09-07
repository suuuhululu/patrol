"""실제 Nav2 연결 전 점유 지도 수신·표시를 확인하는 수동 시연 도구."""

from datetime import datetime, timezone
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def build_demo_grid(width, height):
    # [시연 지도] 외곽 벽과 주차 구획만 만들며 실제 주차장 지도가 아님을 전제로 한다.
    data = [0] * (width * height)

    def occupy(x, y, value=100):
        if 0 <= x < width and 0 <= y < height:
            data[y * width + x] = value

    for x in range(width):
        occupy(x, 0)
        occupy(x, height - 1)
    for y in range(height):
        occupy(0, y)
        occupy(width - 1, y)
    for x in range(7, width - 7, 8):
        for y in range(5, height - 5):
            if y % 13 not in {0, 1, 2, 3}:
                occupy(x, y)
    for y in (9, height - 10):
        for x in range(3, width - 3):
            if x % 8 != 0:
                occupy(x, y, 65)
    return data


def main():
    parser = argparse.ArgumentParser(description="Sysmon에 임시 Nav2 점유 지도를 한 건 전송합니다.")
    parser.add_argument("--url", default="http://127.0.0.1:5000/api/maps/current")
    args = parser.parse_args()
    token = os.environ.get("SYSMON_ROBOT_API_KEY")
    if not token:
        raise SystemExit("SYSMON_ROBOT_API_KEY 환경변수를 먼저 설정하세요.")
    try:
        token.encode("ascii")
    except UnicodeEncodeError as exc:
        # [HTTP 헤더 검증] 한글 토큰이 urllib 내부 오류로 이어지기 전에 사용법을 안내한다.
        raise SystemExit(
            "SYSMON_ROBOT_API_KEY는 영문·숫자·기호로 설정하세요. "
            "서버와 같은 값을 사용합니다."
        ) from exc
    # [화면 확인] 현재 대시보드의 세로형 지도 패널에서 전체 지도가 잘 보이는 비율을 사용한다.
    width, height = 48, 64
    now = datetime.now(timezone.utc)
    payload = {
        "message_id": f"demo-map-{now.strftime('%Y%m%d%H%M%S%f')}",
        "frame_id": "map", "resolution": 0.5,
        "width": width, "height": height,
        "origin": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        "data": build_demo_grid(width, height),
        "observed_at": now.isoformat(),
    }
    request = urllib.request.Request(
        args.url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "X-Robot-Token": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        raise SystemExit(exc.code) from exc


if __name__ == "__main__":
    main()
