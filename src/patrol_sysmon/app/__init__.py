from flask import Flask
from pathlib import Path
import os


def create_app(test_config=None):
    # [1단계: 앱 생성] day5/0_app.py의 Flask 생성 코드를 함수로 분리한다.
    app = Flask(__name__)

    # [2단계: 저장 경로] 실행 위치와 무관하게 프로젝트의 instance 폴더를 사용한다.
    app.config.from_mapping(
        DATABASE=str(Path(app.instance_path) / "sysmon.sqlite3"),
        EVIDENCE_DIR=str(Path(app.instance_path) / "evidence"),
        VIDEO_DIR=None,
        MAP_DIR=None,
        COSTMAP_DIR=None,
        SECRET_KEY=os.environ.get("SYSMON_SECRET_KEY"),
        ROBOT_API_KEY=os.environ.get("SYSMON_ROBOT_API_KEY"),
        ROBOT_OFFLINE_AFTER_SECONDS=15,
        MAP_FRAME_ID="map",
        # [지도 크기] 실제 Nav2 지도는 100m×100m·5cm면 400만 셀이다. 받아서 표시하되
        # 화면용 PNG는 아래 최대 변 길이로 솎아 저장한다.
        MAP_MAX_CELLS=16_000_000,
        MAP_MAX_IMAGE_SIDE=2000,
        EVENT_IMAGE_MAX_BYTES=5 * 1024 * 1024,
        # [증적 상태] 사건은 왔는데 증적 조립이 끝나지 않은 시간으로 지연·누락을 구분한다.
        # 저장값은 INCOMPLETE 그대로 두고 경과 시간으로 화면 표시만 나눈다.
        EVIDENCE_DELAYED_AFTER_SECONDS=30,
        EVIDENCE_MISSING_AFTER_SECONDS=300,
        VIDEO_FRAME_MAX_BYTES=2 * 1024 * 1024,
        CAMERA_OFFLINE_AFTER_SECONDS=5,
        # [계약 2.5절] 표시용 영상은 최대 5 Hz까지만 처리한다. 초과분은 버린다.
        CAMERA_MAX_HZ=5.0,
        # [20단계] E-stop은 상태 유지 토픽이라 끊겨도 마지막 값을 남기고 경과만 표시한다.
        ESTOP_STALE_AFTER_SECONDS=10,
        PATROL_PERMIT_STALE_SECONDS=1.5,
        CSRF_EXEMPT_ENDPOINTS=(
            "robots.receive_status", "maps.receive_map", "events.receive_event",
            "cameras.receive_frame", "vehicle_access.receive_access",
        ),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    )
    if test_config is not None:
        app.config.update(test_config)
    robot_api_key = app.config.get("ROBOT_API_KEY")
    if robot_api_key and (not isinstance(robot_api_key, str) or not robot_api_key.isascii()):
        # [장치 토큰 검증] HTTP 헤더에서 안전하게 전달되지 않는 한글 토큰은 시작 시 차단한다.
        raise RuntimeError(
            "SYSMON_ROBOT_API_KEY는 영문·숫자·기호로 구성된 ASCII 문자열이어야 합니다."
        )
    if not app.config.get("MAP_DIR"):
        # [6단계: 지도 경로] 테스트 DB를 쓰면 지도 파일도 같은 임시 폴더에 저장한다.
        app.config["MAP_DIR"] = str(Path(app.config["DATABASE"]).parent / "maps")
    if not app.config.get("VIDEO_DIR"):
        # [9단계: 영상 경로] 최신 프레임만 보관하며 테스트 DB와 같은 임시 영역을 사용한다.
        app.config["VIDEO_DIR"] = str(Path(app.config["DATABASE"]).parent / "live_frames")
    if not app.config.get("COSTMAP_DIR"):
        # [17단계: costmap 경로] 고주기 동적 격자는 정적 지도 파일과 분리한다.
        app.config["COSTMAP_DIR"] = str(Path(app.config["DATABASE"]).parent / "costmaps")
    # [DB 초기화] 폴더·연결·필수 테이블을 준비한 후 페이지 경로를 등록한다.
    from . import database
    database.init_app(app)

    # [3단계: 인증 준비] 세션·CSRF·권한 검사와 로그인·계정 관리 경로를 등록한다.
    from . import security
    from .routes import auth
    security.init_app(app)
    auth.init_app(app)

    # [5단계: 상태 API] 장치 입력과 로그인 사용자의 상태 조회 경로를 등록한다.
    from .routes.robots import robots_bp
    app.register_blueprint(robots_bp)

    # [6단계: 지도 API] Nav2 점유 지도 수신·웹 이미지·표시 데이터 경로를 등록한다.
    from .routes.maps import maps_bp
    app.register_blueprint(maps_bp)

    # [17단계: costmap API] ROS로 저장한 네 동적 격자의 로그인 조회 경로를 등록한다.
    from .routes.costmaps import costmaps_bp
    app.register_blueprint(costmaps_bp)

    # [7단계: 이벤트 API] 화재 메타데이터와 증거 이미지 한 장을 함께 수신한다.
    from .routes.events import events_bp
    app.register_blueprint(events_bp)

    # [11단계: 차량 입출차] 고정 웹캠 인식 결과와 증거 이미지 조회 경로를 등록한다.
    from .routes.vehicle_access import vehicle_access_bp
    app.register_blueprint(vehicle_access_bp)

    # [9단계: 영상 API] 네 카메라의 최신 프레임 수신·로그인 조회 경로를 등록한다.
    from .routes.cameras import cameras_bp
    app.register_blueprint(cameras_bp)

    # [19단계: CCTV 상태] ROS로 저장한 CameraState·permit의 로그인 조회 경로를 등록한다.
    from .routes.cctv import cctv_bp
    app.register_blueprint(cctv_bp)

    # [20단계: 순찰·안전] 방문·보고와 Keepout·E-stop 관측 결과 조회 경로를 등록한다.
    from .routes.patrol import patrol_bp
    app.register_blueprint(patrol_bp)

    # [10단계: 통합 이력] DB의 사건·상태·순찰·교대 검색 페이지와 API를 등록한다.
    from .routes.history import history_bp
    app.register_blueprint(history_bp)

    # [기능 연결] 페이지 경로를 등록하고 실행 파일과 화면 처리를 분리한다.
    from .routes.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp)
    return app
