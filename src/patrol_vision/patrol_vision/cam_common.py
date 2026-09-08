#!/usr/bin/env python3
"""gate_cam.py / center_cam.py 공통 유틸리티"""
import os
from datetime import datetime
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

# CCTV 이벤트 QoS: 신뢰성 있는 전달, 최근 20개까지 버퍼링(interfaces.md 9절)
# gate_event / center_event 둘 다 이 프로파일을 그대로 쓴다.
CCTV_EVENT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,   # 유실 없이 재전송 보장
    durability=DurabilityPolicy.VOLATILE,     # 늦게 붙는 구독자에게 과거 값 재전송 안 함
    history=HistoryPolicy.KEEP_LAST,          # 최근 depth개만 큐에 유지
    depth=20
)

# 대시보드용 CCTV 영상 스트림 QoS. 이벤트(위 CCTV_EVENT_QOS)와 달리 영상은
# "최신 프레임만 중요"하고 프레임 한두 개 유실돼도 다음 프레임이 금방 오므로
# BEST_EFFORT + depth=1을 쓴다(재전송 보장 안 함 → 대역폭·지연을 줄임).
IMAGE_STREAM_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,  # 유실 허용(재전송 안 함) - 영상은 최신 프레임이 더 중요
    durability=DurabilityPolicy.VOLATILE,       # 늦게 붙는 구독자에게 과거 프레임 재전송 안 함
    history=HistoryPolicy.KEEP_LAST,            # 최근 depth개만 큐에 유지
    depth=1,                                    # 항상 최신 프레임 1개만
)


def load_and_bump_restart_sequence(camera_id: str, state_dir: str) -> int:
    # 노드가 뜰 때마다 이 함수가 1번 호출되어, 로컬 파일에 저장된 숫자를 읽어서 +1 하고
    # 다시 저장한다. 이 값(restart_sequence)은 event_id가 재시작 전/후에 절대 안 겹치게
    # 하려고 존재하는 진단용 값일 뿐, patrol_allowed 판단에는 전혀 영향을 주지 않는다.
    path = os.path.join(state_dir, f'{camera_id}_restart_seq.txt')  # 카메라별 카운터 파일 경로
    seq = 1                                                          # 파일이 없거나 손상 시 기본값
    try:
        os.makedirs(state_dir, exist_ok=True)                        # 저장 폴더 없으면 생성
        if os.path.exists(path):
            with open(path, 'r') as f:
                seq = int(f.read().strip()) + 1                      # 기존 값 읽어서 +1
    except (OSError, ValueError):
        # 파일을 못 읽거나(OSError) 내용이 숫자가 아니면(ValueError) 그냥 1로 시작한다.
        # 진단용 카운터라 정확히 이어지지 않아도 노드 동작 자체엔 문제가 없기 때문에,
        # 여기서 예외를 던져서 노드를 죽이지 않고 조용히 폴백한다.
        seq = 1
    try:
        with open(path, 'w') as f:
            f.write(str(seq))                                        # 증가된 값 다시 저장
    except OSError:
        # 저장에 실패해도(디스크 문제 등) 이번 실행 자체는 계속 진행한다 - 이번에 구한
        # seq 값은 이미 리턴할 거라, 저장 실패는 "다음 재시작 때 카운터가 안 이어질 뿐"이지
        # 지금 당장 문제가 되는 건 아니다.
        pass
    return seq


def build_source_session_id(camera_id: str, restart_sequence: int, started_at: datetime = None) -> str:
    # camera_id + 시작 시각 + 재시작 순번을 합쳐서, "이번에 이 노드가 실행되는 동안"을
    # 대표하는 고유 문자열을 만든다. 노드가 켜져 있는 동안은 이 값이 바뀌지 않고,
    # 재시작하면 restart_sequence가 달라지므로 새 값이 나온다.
    # 예: gate_cam-20260907T170000-01 / center_cam-20260907T170000-01
    started_at = started_at or datetime.now()
    return f'{camera_id}-{started_at.strftime("%Y%m%dT%H%M%S")}-{restart_sequence:02d}'


def build_event_id(source_session_id: str, state: str, source_sequence: int) -> str:
    # 위에서 만든 세션id에 이번 이벤트의 state와 세션 내 순번을 붙여서 최종 event_id를
    # 만든다. 세션id가 재시작마다 달라지고 source_sequence가 세션 안에서 계속 증가하므로,
    # 이 event_id는 노드를 몇 번을 껐다 켜도 절대 겹치지 않는다(cam_master의 중복
    # 판정이 여기에 의존한다).
    # 예: cam-gate_cam-20260907T170000-01-entering-0001
    return f'cam-{source_session_id}-{state.lower()}-{source_sequence:04d}'