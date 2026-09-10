-- [사용자] 원문 비밀번호 대신 해시를 저장한다. 계정 생성·로그인은 3단계에서 구현한다.
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- [로봇 기본 정보] robot_id로 AMR1·AMR2를 식별한다. 등록 데이터는 후속 단계에서 입력한다.
CREATE TABLE IF NOT EXISTS robots (
    robot_id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- [최신 상태] 로봇별 한 행을 유지한다. 좌표·임무 상태 값은 ROS 인터페이스 확정 전 내부 형식이다.
CREATE TABLE IF NOT EXISTS robot_latest_status (
    robot_id TEXT PRIMARY KEY NOT NULL REFERENCES robots(robot_id),
    message_id TEXT NOT NULL UNIQUE,
    battery REAL CHECK (battery BETWEEN 0 AND 100),
    x REAL,
    y REAL,
    frame_id TEXT,
    -- [위치 유효성] 로봇이 위치를 잃어도 배터리·임무는 계속 받는다.
    -- 무효일 때 좌표는 비우고 마지막으로 위치가 유효했던 시각만 남긴다.
    pose_valid INTEGER NOT NULL DEFAULT 1 CHECK (pose_valid IN (0, 1)),
    last_valid_pose_at TEXT,
    mission_status TEXT NOT NULL,
    -- [안전 상태] RobotStatus.safety_state(계약 4절). ESTOPPED만으로 실제 정지를 단정하지 않으므로
    -- motion_stopped와 원인 코드를 따로 보존한다.
    safety_state TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (safety_state IN ('UNKNOWN', 'NORMAL', 'STOPPING', 'STOPPED', 'ESTOPPED', 'ERROR')),
    motion_stopped INTEGER NOT NULL DEFAULT 0 CHECK (motion_stopped IN (0, 1)),
    safety_reason_code INTEGER NOT NULL DEFAULT 0,
    safety_reason TEXT NOT NULL DEFAULT '',
    connection_status TEXT NOT NULL CHECK (connection_status IN ('ONLINE', 'OFFLINE', 'UNKNOWN')),
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- [상태 이력] 최신 상태를 덮어써도 이전 수신 기록을 유지한다.
CREATE TABLE IF NOT EXISTS robot_status_history (
    id INTEGER PRIMARY KEY,
    robot_id TEXT NOT NULL REFERENCES robots(robot_id),
    message_id TEXT NOT NULL UNIQUE,
    battery REAL CHECK (battery BETWEEN 0 AND 100),
    x REAL,
    y REAL,
    frame_id TEXT,
    -- [위치 유효성] 로봇이 위치를 잃어도 배터리·임무는 계속 받는다.
    -- 무효일 때 좌표는 비우고 마지막으로 위치가 유효했던 시각만 남긴다.
    pose_valid INTEGER NOT NULL DEFAULT 1 CHECK (pose_valid IN (0, 1)),
    last_valid_pose_at TEXT,
    mission_status TEXT NOT NULL,
    -- [안전 상태] RobotStatus.safety_state(계약 4절). ESTOPPED만으로 실제 정지를 단정하지 않으므로
    -- motion_stopped와 원인 코드를 따로 보존한다.
    safety_state TEXT NOT NULL DEFAULT 'UNKNOWN'
        CHECK (safety_state IN ('UNKNOWN', 'NORMAL', 'STOPPING', 'STOPPED', 'ESTOPPED', 'ERROR')),
    motion_stopped INTEGER NOT NULL DEFAULT 0 CHECK (motion_stopped IN (0, 1)),
    safety_reason_code INTEGER NOT NULL DEFAULT 0,
    safety_reason TEXT NOT NULL DEFAULT '',
    connection_status TEXT NOT NULL CHECK (connection_status IN ('ONLINE', 'OFFLINE', 'UNKNOWN')),
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- [지도 이력] Nav2 OccupancyGrid를 웹 이미지로 변환하고 DB에는 파일 경로·좌표 메타데이터만 저장한다.
CREATE TABLE IF NOT EXISTS maps (
    id INTEGER PRIMARY KEY,
    message_id TEXT NOT NULL UNIQUE,
    frame_id TEXT NOT NULL,
    resolution REAL NOT NULL CHECK (resolution > 0),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    origin_x REAL NOT NULL,
    origin_y REAL NOT NULL,
    origin_yaw REAL NOT NULL,
    content_hash TEXT NOT NULL,
    image_path TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

-- [현재 지도] 지도 이력 중 대시보드에 사용할 한 건만 가리킨다.
CREATE TABLE IF NOT EXISTS map_latest (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    map_id INTEGER NOT NULL UNIQUE REFERENCES maps(id)
);

-- [17단계: 동적 costmap] 로봇·계층별 최신 격자만 유지해 고주기 토픽의 무제한 누적을 막는다.
CREATE TABLE IF NOT EXISTS costmap_latest (
    robot_id TEXT NOT NULL CHECK (robot_id IN ('AMR1', 'AMR2')),
    layer TEXT NOT NULL CHECK (layer IN ('global', 'local')),
    message_id TEXT NOT NULL,
    frame_id TEXT NOT NULL,
    resolution REAL NOT NULL CHECK (resolution > 0),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    origin_x REAL NOT NULL,
    origin_y REAL NOT NULL,
    origin_yaw REAL NOT NULL,
    content_hash TEXT NOT NULL,
    image_path TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    PRIMARY KEY (robot_id, layer)
);

-- [이벤트] ReportDetection 서비스로 받은 확정 사건. 사건 한 건 = 행 하나 + 증거 사진 파일 한 장.
-- 서비스가 주는 값(로봇·종류·시각·위치·사진)과 관제 처리 상태만 둔다. 위험도·메시지 번호 같은 옛 토픽 칸은 없다.
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY NOT NULL,
    robot_id TEXT NOT NULL REFERENCES robots(robot_id),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    x REAL,
    y REAL,
    frame_id TEXT,
    status TEXT NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW', 'REVIEWING', 'WORK_REQUESTED', 'RESOLVED')),
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- [재시도 판정] event_id + 내용 해시로 재시도(같음)와 잘못된 재사용(다름)을 가른다.
    content_hash TEXT,
    -- [증거 사진] 파일 경로만 저장한다. 바이너리는 넣지 않는다.
    image_path TEXT,
    captured_at TEXT
);

-- [관제 이력] 사용자 확인·메모·상태 변경을 기록한다. 상태 전이 규칙은 후속 서비스에서 검사한다.
CREATE TABLE IF NOT EXISTS event_changes (
    id INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events(event_id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    previous_status TEXT NOT NULL CHECK (previous_status IN ('NEW', 'REVIEWING', 'WORK_REQUESTED', 'RESOLVED')),
    new_status TEXT NOT NULL CHECK (new_status IN ('NEW', 'REVIEWING', 'WORK_REQUESTED', 'RESOLVED')),
    memo TEXT NOT NULL DEFAULT '',
    changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- [차량 입출차] 인식 모듈에서 받은 입차·출차 내역만 저장한다.
CREATE TABLE IF NOT EXISTS vehicle_access_logs (
    access_id TEXT PRIMARY KEY NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    camera_id TEXT NOT NULL CHECK (camera_id IN ('webcam1', 'webcam2')),
    direction TEXT NOT NULL CHECK (direction IN ('ENTRY', 'EXIT')),
    detected_at TEXT NOT NULL,
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- [19단계: CCTV 확정 상태] PC 4가 만든 CameraState를 원문 식별자와 함께 보존한다.
CREATE TABLE IF NOT EXISTS cctv_state_events (
    event_id TEXT PRIMARY KEY NOT NULL,
    camera_id TEXT NOT NULL CHECK (camera_id IN ('gate_cam', 'center_cam')),
    state TEXT NOT NULL CHECK (state IN ('ENTERING', 'PARKED', 'EXITING', 'EXITED')),
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

-- [19단계: 순찰 허용 최신값] 2 Hz 반복 수신은 한 행의 수신 시각만 갱신한다.
CREATE TABLE IF NOT EXISTS patrol_permit_latest (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    allowed INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    received_at TEXT NOT NULL
);

-- permit 값이 실제로 바뀐 시점만 남겨 반복 heartbeat의 무제한 누적을 막는다.
CREATE TABLE IF NOT EXISTS patrol_permit_history (
    id INTEGER PRIMARY KEY,
    allowed INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    received_at TEXT NOT NULL
);

-- [대시보드 표시 기준] DB 이력을 삭제하지 않고 사용자별 최근 목록 시작 시각만 저장한다.
CREATE TABLE IF NOT EXISTS dashboard_clear_state (
    user_id INTEGER PRIMARY KEY NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_cleared_at TEXT,
    vehicle_access_cleared_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- [외부 연동 예약] 기존 설계의 명령 이력 구조다. 시스템 모니터에서는 운영 요청을 생성하지 않는다.
CREATE TABLE IF NOT EXISTS commands (
    command_id TEXT PRIMARY KEY NOT NULL,
    robot_id TEXT NOT NULL REFERENCES robots(robot_id),
    event_id TEXT REFERENCES events(event_id),
    requested_by INTEGER REFERENCES users(id),
    command_type TEXT NOT NULL CHECK (command_type IN ('START_PATROL', 'PAUSE', 'RESUME', 'RETURN', 'EVACUATE')),
    status TEXT NOT NULL DEFAULT 'REQUESTED'
        CHECK (status IN ('REQUESTED', 'ACCEPTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED', 'REJECTED', 'TIMED_OUT')),
    result_message TEXT,
    requested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    accepted_at TEXT,
    started_at TEXT,
    finished_at TEXT
);

-- [순찰] 순찰 실행 단위와 각 관측점 방문 기록을 분리한다.
-- [20단계: 순찰 결과] PatrolReport 한 건이 순찰 실행 한 행이다.
-- 보고가 오지 않은 순찰은 저장하지 않고 화면에서 UNREPORTED로 계산한다. 관제는 결과를 대필하지 않는다.
CREATE TABLE IF NOT EXISTS patrol_runs (
    patrol_id TEXT PRIMARY KEY NOT NULL,
    report_id TEXT NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    robot_id TEXT NOT NULL REFERENCES robots(robot_id),
    mission_id TEXT NOT NULL DEFAULT '',
    command_id TEXT NOT NULL DEFAULT '',
    result TEXT NOT NULL CHECK (result IN ('SUCCEEDED', 'FAILED', 'CANCELED')),
    reason_code INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    ended_at TEXT,
    planned_visit_count INTEGER NOT NULL CHECK (planned_visit_count >= 0),
    completed_visit_count INTEGER NOT NULL CHECK (completed_visit_count >= 0),
    received_at TEXT NOT NULL
);

-- [20단계: 관측점 방문] PatrolVisit은 보고보다 먼저 올 수 있어 순찰 실행 행을 요구하지 않는다.
CREATE TABLE IF NOT EXISTS patrol_visits (
    visit_id TEXT PRIMARY KEY NOT NULL,
    message_id TEXT NOT NULL UNIQUE,
    robot_id TEXT NOT NULL REFERENCES robots(robot_id),
    patrol_id TEXT NOT NULL DEFAULT '',
    mission_id TEXT NOT NULL DEFAULT '',
    command_id TEXT NOT NULL DEFAULT '',
    waypoint_id TEXT NOT NULL,
    x REAL,
    y REAL,
    frame_id TEXT,
    result TEXT NOT NULL CHECK (result IN ('SUCCEEDED', 'SKIPPED', 'FAILED')),
    reason_code INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    arrived_at TEXT NOT NULL,
    completed_at TEXT,
    received_at TEXT NOT NULL
);

-- [20단계: Keepout] 로봇별 최신 적용 상태만 유지한다. 롤백 실패는 화면에서 경고로 구분한다.
CREATE TABLE IF NOT EXISTS keepout_latest (
    robot_id TEXT PRIMARY KEY NOT NULL REFERENCES robots(robot_id),
    message_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL CHECK (state IN ('UNKNOWN', 'DISABLED', 'APPLIED', 'ROLLED_BACK', 'ROLLBACK_FAILED')),
    global_enabled INTEGER NOT NULL CHECK (global_enabled IN (0, 1)),
    local_enabled INTEGER NOT NULL CHECK (local_enabled IN (0, 1)),
    reason_code INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

-- [20단계: E-stop 최신] Safety Arbiter가 대상(robot1·robot6·all)별로 보낸 마지막 상태다.
-- interfaces.md 3.1절(2026-09-08): 물리 E-stop·수동 reset은 구현 범위 밖이라 latched 계열 열이 없다.
CREATE TABLE IF NOT EXISTS estop_latest (
    target_robot_id TEXT PRIMARY KEY NOT NULL CHECK (target_robot_id IN ('robot1', 'robot6', 'all')),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    -- 대표 원인 하나(0~6). 전체 활성 원인 집합은 관제가 별도 계약(TBD-IF-011)으로 준다.
    reason INTEGER NOT NULL DEFAULT 0 CHECK (reason BETWEEN 0 AND 6),
    sequence INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

-- [20단계: E-stop 이력] 반복 수신은 최신 행만 갱신하고 활성·해제·대표 원인이 바뀐 시점만 남긴다.
CREATE TABLE IF NOT EXISTS estop_history (
    id INTEGER PRIMARY KEY,
    target_robot_id TEXT NOT NULL CHECK (target_robot_id IN ('robot1', 'robot6', 'all')),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    reason INTEGER NOT NULL DEFAULT 0 CHECK (reason BETWEEN 0 AND 6),
    sequence INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

-- [교대] 교대 전후 로봇과 요청·완료 시각을 보존한다.
CREATE TABLE IF NOT EXISTS handovers (
    handover_id TEXT PRIMARY KEY NOT NULL,
    from_robot_id TEXT NOT NULL REFERENCES robots(robot_id),
    to_robot_id TEXT NOT NULL REFERENCES robots(robot_id),
    reason TEXT,
    status TEXT NOT NULL CHECK (status IN ('REQUESTED', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
    requested_at TEXT NOT NULL,
    completed_at TEXT,
    CHECK (from_robot_id <> to_robot_id)
);

-- [조회 준비] 날짜별·로봇별 로그 검색에 필요한 인덱스를 만든다.
CREATE INDEX IF NOT EXISTS idx_events_occurred ON events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_robot_time ON events(robot_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_status_robot_time ON robot_status_history(robot_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_maps_observed ON maps(observed_at);
CREATE INDEX IF NOT EXISTS idx_costmap_observed ON costmap_latest(observed_at);
CREATE INDEX IF NOT EXISTS idx_event_changes_time ON event_changes(event_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_event_changes_changed_at ON event_changes(changed_at);
CREATE INDEX IF NOT EXISTS idx_commands_robot_time ON commands(robot_id, requested_at);
CREATE INDEX IF NOT EXISTS idx_patrol_robot_time ON patrol_runs(robot_id, started_at);
CREATE INDEX IF NOT EXISTS idx_visits_patrol ON patrol_visits(patrol_id, arrived_at);
CREATE INDEX IF NOT EXISTS idx_visits_robot_time ON patrol_visits(robot_id, arrived_at);
CREATE INDEX IF NOT EXISTS idx_estop_history_time ON estop_history(observed_at);
CREATE INDEX IF NOT EXISTS idx_handovers_time ON handovers(requested_at);
CREATE INDEX IF NOT EXISTS idx_handovers_from_time ON handovers(from_robot_id, requested_at);
CREATE INDEX IF NOT EXISTS idx_handovers_to_time ON handovers(to_robot_id, requested_at);
CREATE INDEX IF NOT EXISTS idx_vehicle_access_detected ON vehicle_access_logs(detected_at);
CREATE INDEX IF NOT EXISTS idx_vehicle_access_camera_time ON vehicle_access_logs(camera_id, detected_at);
CREATE INDEX IF NOT EXISTS idx_cctv_state_observed ON cctv_state_events(observed_at);
CREATE INDEX IF NOT EXISTS idx_cctv_state_camera_time ON cctv_state_events(camera_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_patrol_permit_time ON patrol_permit_history(received_at);
