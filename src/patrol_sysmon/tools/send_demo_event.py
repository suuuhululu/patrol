"""실제 토픽 연결 전 화재·누수·장애물 이벤트를 확인하는 수동 시연 도구."""

from datetime import datetime, timezone
import argparse
import json
import math
import os
import struct
import sys
import urllib.error
import urllib.request
from uuid import uuid4
import zlib


def _png_chunk(kind, data):
    checksum = zlib.crc32(kind + data) & 0xffffffff
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def build_demo_evidence(event_type="FIRE", width=320, height=180):
    """실제 카메라 사진과 혼동되지 않는 이벤트별 시연용 PNG를 만든다."""
    rows = bytearray()
    center_x, center_y = width * 0.5, height * 0.56
    for y in range(height):
        rows.append(0)
        for x in range(width):
            distance = math.hypot((x - center_x) / 1.15, y - center_y)
            if event_type == "LEAK" and distance < 43:
                color = (66, 170, 245) if distance > 22 else (170, 225, 255)
            elif event_type == "OBSTACLE" and abs(x - center_x) < 55 and abs(y - center_y) < 35:
                color = (242, 177, 66) if (x // 14 + y // 14) % 2 else (40, 44, 50)
            elif event_type == "FIRE" and distance < 22:
                color = (255, 236, 80)
            elif event_type == "FIRE" and distance < 43 and y > center_y - 38:
                color = (245, 82, 32)
            else:
                shade = 24 + int(18 * y / height)
                color = (shade, shade + 4, shade + 10)
            rows.extend(color)
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return signature + _png_chunk(b"IHDR", header) + _png_chunk(
        b"IDAT", zlib.compress(bytes(rows), 9)
    ) + _png_chunk(b"IEND", b"")


def multipart_body(metadata, image_bytes):
    boundary = f"----sysmon-{uuid4().hex}"
    marker = f"--{boundary}\r\n".encode("ascii")
    body = bytearray(marker)
    body.extend(b'Content-Disposition: form-data; name="metadata"\r\n')
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(json.dumps(metadata).encode("utf-8"))
    body.extend(b"\r\n")
    body.extend(marker)
    body.extend(b'Content-Disposition: form-data; name="image"; filename="demo-fire.png"\r\n')
    body.extend(b"Content-Type: image/png\r\n\r\n")
    body.extend(image_bytes)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode("ascii"))
    return bytes(body), boundary


def main():
    parser = argparse.ArgumentParser(description="Sysmon에 임시 이상 이벤트와 증거 이미지 한 장을 전송합니다.")
    parser.add_argument("--url", default="http://127.0.0.1:5000/api/events")
    parser.add_argument("--robot", choices=("AMR1", "AMR2"), default="AMR1")
    parser.add_argument("--type", choices=("FIRE", "LEAK", "OBSTACLE"), default="FIRE")
    args = parser.parse_args()
    token = os.environ.get("SYSMON_ROBOT_API_KEY")
    if not token:
        raise SystemExit("SYSMON_ROBOT_API_KEY 환경변수를 먼저 설정하세요.")
    try:
        token.encode("ascii")
    except UnicodeEncodeError as exc:
        raise SystemExit(
            "SYSMON_ROBOT_API_KEY는 영문·숫자·기호로 설정하세요. 서버와 같은 값을 사용합니다."
        ) from exc
    # [ReportDetection 필드] 서비스 요청과 같은 값을 보낸다. event_id는 소문자 UUID v4, 좌표계는 서버가 map으로 채운다.
    # 같은 로봇·같은 종류를 억제 시간(기본 60초) 안에 다시 보내면 저장하지 않고 duplicate로 응답한다.
    metadata = {
        "robot_id": args.robot,
        "event_id": str(uuid4()),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "x": 12.5,
        "y": 8.0,
        "event_type": args.type,
    }
    body, boundary = multipart_body(metadata, build_demo_evidence(args.type))
    request = urllib.request.Request(
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Robot-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        raise SystemExit(exc.code) from exc


if __name__ == "__main__":
    main()
