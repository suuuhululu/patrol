"""실제 영상 토픽 연결 전 네 카메라의 움직이는 시연 프레임을 반복 전송한다."""

from datetime import datetime, timezone
import argparse
import math
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib


CAMERAS = ("amr1", "amr2", "webcam1", "webcam2")
PALETTES = {
    "amr1": ((12, 30, 48), (52, 146, 220)),
    "amr2": ((11, 42, 42), (52, 190, 151)),
    "webcam1": ((42, 28, 16), (224, 145, 61)),
    "webcam2": ((38, 20, 42), (177, 99, 210)),
}


def _png_chunk(kind, data):
    checksum = zlib.crc32(kind + data) & 0xffffffff
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def build_demo_frame(camera_id, tick, width=320, height=180):
    """실제 카메라 사진과 혼동되지 않는 움직이는 격자형 PNG를 만든다."""
    dark, accent = PALETTES[camera_id]
    scan_x = (tick * 13) % width
    pulse_x = width * (0.5 + 0.34 * math.sin(tick / 4))
    pulse_y = height * (0.5 + 0.22 * math.cos(tick / 5))
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            grid = x % 40 < 2 or y % 30 < 2
            scan = abs(x - scan_x) < 3
            pulse = math.hypot(x - pulse_x, y - pulse_y) < 16
            if pulse:
                color = (235, 244, 250)
            elif scan:
                color = accent
            elif grid:
                color = tuple(min(255, value + 24) for value in dark)
            else:
                shade = int(10 * y / height)
                color = tuple(min(255, value + shade) for value in dark)
            rows.extend(color)
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return signature + _png_chunk(b"IHDR", header) + _png_chunk(
        b"IDAT", zlib.compress(bytes(rows), 6)
    ) + _png_chunk(b"IEND", b"")


def send_frame(base_url, token, camera_id, tick):
    now = datetime.now(timezone.utc)
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/{camera_id}/frame",
        data=build_demo_frame(camera_id, tick),
        method="POST",
        headers={
            "Content-Type": "image/png",
            "X-Robot-Token": token,
            "X-Frame-Id": f"demo-{camera_id}-{now.strftime('%Y%m%d%H%M%S%f')}",
            "X-Captured-At": now.isoformat(),
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


def main():
    parser = argparse.ArgumentParser(description="Sysmon 네 영상 영역에 움직이는 임시 프레임을 전송합니다.")
    parser.add_argument("--url", default="http://127.0.0.1:5000/api/cameras")
    parser.add_argument("--camera", choices=("all",) + CAMERAS, default="all")
    parser.add_argument("--fps", type=float, default=2.0, help="카메라별 초당 프레임 수(0.2~5)")
    parser.add_argument("--duration", type=float, default=30.0, help="전송 시간(초), 0이면 Ctrl+C까지 계속")
    args = parser.parse_args()
    if not 0.2 <= args.fps <= 5:
        raise SystemExit("--fps는 0.2에서 5 사이여야 합니다.")
    if args.duration < 0:
        raise SystemExit("--duration은 0 이상이어야 합니다.")
    token = os.environ.get("SYSMON_ROBOT_API_KEY")
    if not token:
        raise SystemExit("SYSMON_ROBOT_API_KEY 환경변수를 먼저 설정하세요.")
    try:
        token.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SystemExit(
            "SYSMON_ROBOT_API_KEY는 영문·숫자·기호로 설정하세요. 서버와 같은 값을 사용합니다."
        ) from exc
    selected = CAMERAS if args.camera == "all" else (args.camera,)
    started = time.monotonic()
    tick = 0
    print(f"시연 영상 전송 시작: {', '.join(selected)} · {args.fps:g} FPS · Ctrl+C로 종료")
    try:
        while args.duration == 0 or time.monotonic() - started < args.duration:
            cycle_started = time.monotonic()
            for camera_id in selected:
                try:
                    send_frame(args.url, token, camera_id, tick)
                except urllib.error.HTTPError as exc:
                    print(exc.read().decode("utf-8"), file=sys.stderr)
                    raise SystemExit(exc.code) from exc
                except urllib.error.URLError as exc:
                    raise SystemExit(f"서버에 연결할 수 없습니다: {exc.reason}") from exc
            tick += 1
            remaining = (1 / args.fps) - (time.monotonic() - cycle_started)
            if remaining > 0:
                time.sleep(remaining)
    except KeyboardInterrupt:
        pass
    print(f"전송 종료: 카메라 {len(selected)}개 · 주기 {tick}회")


if __name__ == "__main__":
    main()
