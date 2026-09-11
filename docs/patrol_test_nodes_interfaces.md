# 순찰·이벤트·안전구역·로컬 비전 코드의 노드와 인터페이스

작성일: 2026-09-11 KST. **구현 대조 완료:** 아래 SHA-256의 현재 작업본과 로컬 ROS 2 Jazzy 라이브러리를 정적으로 확인했다.

**시험 상태:** 사용자가 네 파일 모두 단위 기능 테스트를 수행했다고 알렸다. 이번 정리는 그 사실을 사용자 보고로 기록하며, 시험 항목·로그·성공 건수나 실제 장비 통합시험 결과를 추가로 추정하지 않는다. 이번 작업에서는 코드·실행 설정을 변경하거나 로봇을 실행하지 않았다.

이 문서는 실제 구현 목록이다. 공용 통신 계약은 [interfaces.md](interfaces.md), 통합 절차는 [integration.md](integration.md)가 관리한다. 현재 코드와 공용 문서의 차이는 9절에 기록했다. 계약 변경이나 전환 완료를 뜻하지 않는다.

## 1. 파일과 실제 노드

기본 실행 기준 `{robot}=robot1`이다. 아래 이름은 ROS remap을 별도로 주지 않았을 때의 이름이다.

| 파일 | 클래스·생성 코드 | 실제 ROS 노드 이름 | 역할·수명 |
|---|---|---|---|
| [genius_patrol.py](../src/patrol_amr_safety/patrol_amr_safety/genius_patrol.py) | `rclpy.create_node(...)` | `/{robot}/follow_waypoints_server` | 외부 순찰 Action 서버. 프로세스 시작부터 종료까지 유지 |
| 같은 파일에서 생성 | `EventCheck(settings)`; 클래스 정의는 event_check.py | `/{robot}/event_check` | 정지 서비스와 재개 토픽 수신. 별도 executor 스레드에서 유지 |
| 같은 파일에서 생성 | `TurtleBot4Navigator(namespace=ns)` | `/{robot}/basic_navigator` | Nav2·도킹·위치 추정 통신. 순찰 Goal의 `execute()`에서 생성하고 종료 시 제거 |
| [event_check.py](../src/patrol_amr_safety/patrol_amr_safety/event_check.py) | `EventCheck(Node)` | 위의 `/{robot}/event_check` | 정지 요청·완료 Future·재개 조건 관리 |
| 같은 파일의 일반 클래스 | `VisionPatrolLink` | 별도 노드 없음 | 전달받은 비전 노드에 정지 client와 재개 publisher를 추가 |
| [move_to_safetyzone.py](../src/patrol_amr_safety/patrol_amr_safety/move_to_safetyzone.py) | `Evacuation` | 별도 노드 없음 | Navigator를 공유하고 odom·TF 구독, 작업 취소·정지 확인, 조건부 안전구역 이동 수행 |
| [vision_node_v2.py](../src/patrol_amr_safety/patrol_amr_safety/vision_node_v2.py) | `DetectingNode(Node)` | `/detecting_node_test` | AMR 로컬 카메라 YOLO 감지, 정지 요청, 사진 보고, 저장 성공 후 재개 |

따라서 **파일 4개가 각각 노드 1개인 구조가 아니다.** 순찰 실행 프로그램 하나와 비전 프로그램 하나를 함께 실행하면, Goal 대기 중에는 세 노드, 하나의 순찰 Goal 실행 중에는 Navigator를 포함한 네 노드가 구성된다. 카메라 드라이버·Nav2·AMCL·도킹 서버·System monitor 등 외부 노드는 이 수에 포함하지 않았다. `TransformListener`에도 기존 Navigator를 전달하므로 별도 TF listener 노드를 만들지 않는다.

`genius_patrol`이라는 ROS 노드 이름과 `move_to_safetyzone`이라는 ROS 노드 이름은 이 코드에서 생성하지 않는다. 비전 노드는 namespace를 명시하지 않지만 통신 주소와 보고의 `robot_id`는 파일 상수 `robot1`을 사용한다.

근거: genius_patrol.py 151–210행, event_check.py 19–31·130–145행, move_to_safetyzone.py 79–94행, vision_node_v2.py 63–120행. Navigator 이름은 저장소의 [TurtleBot4Navigator](../src/turtlebot4_navigation/turtlebot4_navigation/turtlebot4_navigator.py)와 설치된 `nav2_simple_commander/robot_navigator.py`의 상속·생성자를 대조했다.

## 2. 전체 연결

**구현 대조 완료:** 11절의 네 파일 작업본. 화살표는 인터페이스 방향이며, 노드 기동 순서를 뜻하지 않는다.

```mermaid
flowchart LR
    Caller[외부 순찰 Action client] -->|patrol_action: NavigateToPose| Server[follow_waypoints_server]
    Server -->|execute / run_patrol| Nav[basic_navigator]
    Server -->|생성 / 별도 executor| Event[event_check]
    Nav -->|navigate_to_pose / spin| Nav2[Nav2 Action 서버]
    Nav -->|dock / undock| Dock[도킹 Action 서버]
    Dock -->|dock_status| Nav
    Nav -->|initialpose / get_state| Loc[AMCL / bt_navigator]
    Loc -->|amcl_pose| Nav
    Odom[로봇 odom] -->|Odometry| Nav
    TF[로봇 tf / tf_static] -->|TFMessage| Nav
    Cam[로봇 OAK-D RGB] -->|CompressedImage| Vision[detecting_node_test]
    Odom -->|Odometry: pose| Vision
    Vision -->|patrol_stop: SetBool false| Event
    Event -. stop_requested / pause_and_wait .-> Nav
    Nav -. Evacuation.stop 완료 .-> Event
    Event -->|success / message| Vision
    Vision -->|ReportDetection 요청| Monitor[System monitor]
    Monitor -->|status / detail| Vision
    Vision -->|STORED 뒤 patrol_resume: Bool true| Event
```

`Evacuation`은 Navigator 내부에서 호출되는 Python 객체이고, `VisionPatrolLink`는 비전 노드에 붙는 Python 객체다. 점선은 ROS 통신이 아닌 프로세스 내부 함수·상태 공유다. 비전 노드는 PC 4 CCTV의 차량 상태 처리와 별개이며, 이 네 파일에는 `/vision/cctv/...` 통신이 없다.

## 3. 현재 실행 경로에서 사용하는 ROS 인터페이스

### 3.1 네 파일이 직접 연결하는 인터페이스

표의 이름은 기본값이다. `patrol_action`은 서버의 실제 namespace를 사용하고, 정지·재개·odom 기본 주소는 `arguments()`의 robot 설정에서 생성한다.

| 종류 | 이름 | 타입 | 제공·발행 → 호출·구독 | 실제 쓰임 |
|---|---|---|---|---|
| Action | `/{robot}/patrol_action` | `nav2_msgs/action/NavigateToPose` | `follow_waypoints_server` 서버 ← 외부 client | 고정 순찰 시작. Goal의 pose·behavior_tree는 읽지 않음 |
| Service | `/{robot}/patrol_stop` | `std_srvs/srv/SetBool` | `event_check` 서버 ← 비전의 `VisionPatrolLink` client | `data=false` 정지 요청. 실제 정지 확인 뒤 응답 |
| Topic | `/{robot}/patrol_resume` | `std_msgs/msg/Bool` | 비전의 `VisionPatrolLink` → `event_check.on_resume` | `true`: 기존 단계 재개 허용. `false`: 재개 보류 |
| Topic | `/{robot}/odom` | `nav_msgs/msg/Odometry` | 로봇 odom 발행자 → Navigator의 `Evacuation.on_odom` | timestamp와 3축 선속도·각속도로 정지 확인 |
| Topic | `/{robot}/tf` | `tf2_msgs/msg/TFMessage` | TF 발행자 → Navigator의 `TransformListener` | TF Buffer 갱신 |
| Topic | `/{robot}/tf_static` | `tf2_msgs/msg/TFMessage` | 정적 TF 발행자 → 같은 listener | 정적 변환 수신 |
| Topic | `/robot1/oakd/rgb/image_raw/compressed` | `sensor_msgs/msg/CompressedImage` | OAK-D 카메라 발행자 → `DetectingNode.image_callback` | 압축 이미지 decode·YOLO 추론 |
| Topic | `/robot1/odom` | `nav_msgs/msg/Odometry` | 로봇 odom 발행자 → `DetectingNode.odom_callback` | `pose.pose`를 저장하여 보고 위치·중복 판정에 사용 |
| Service | `/system_monitor/report_detection` | `patrol_interfaces/srv/ReportDetection` | System monitor 서버 ← `DetectingNode` client | 사건 정보와 JPEG 증거 사진 제출 |

기본 robot1에서는 두 odom 구독이 같은 토픽을 읽지만 목적과 QoS가 다르다. TF 구독은 현재 실행에서도 생성되며, `map → base_link` 위치 조회는 안전구역 이동 분기에서 사용한다.

### 3.2 Navigator 라이브러리를 통해 사용하는 인터페이스

아래 상대 이름은 Navigator namespace 아래에서 해석된다. 예를 들어 `navigate_to_pose`는 기본 `/robot1/navigate_to_pose`다.

| 종류 | 상대 이름 | 타입 | Navigator 기준 방향 | 호출 위치·소비값 |
|---|---|---|---|---|
| Action | `navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | client | `run_patrol → goToPose(step)`; 조건부 `Evacuation.navigate(pose)` |
| Action | `spin` | `nav2_msgs/action/Spin` | client | `startSpin → spin`; 기본 +2π rad, 제한 시간 20초 |
| Action | `dock` | `irobot_create_msgs/action/Dock` | client | 준비 시 필요하면 도킹, 순찰 종료 후 도킹 |
| Action | `undock` | `irobot_create_msgs/action/Undock` | client | 초기 도킹 상태 확인 뒤 출발 |
| Topic | `dock_status` | `irobot_create_msgs/msg/DockStatus` | 구독 | `getDockedStatus()`에서 사용하는 `is_docked` |
| Topic | `initialpose` | `geometry_msgs/msg/PoseWithCovarianceStamped` | 발행 | `setInitialPose`: map의 `(0,0)`, SOUTH=180°; covariance는 기본 0 |
| Topic | `initialpose` | 같은 타입 | 구독 | TurtleBot4Navigator가 기본 생성. 이번 경로에서는 대화식 경로 생성 기능을 호출하지 않음 |
| Topic | `amcl_pose` | `geometry_msgs/msg/PoseWithCovarianceStamped` | 구독 | `waitUntilNav2Active()`에서 초기 pose 수신 확인 |
| Service | `amcl/get_state` | `lifecycle_msgs/srv/GetState` | client | AMCL lifecycle 상태가 `active`가 될 때까지 확인 |
| Service | `bt_navigator/get_state` | `lifecycle_msgs/srv/GetState` | client | Nav2 navigator lifecycle 상태 `active` 확인 |

현재 순찰은 `FollowWaypoints` Action 호출이 아니라 **개별 `NavigateToPose`와 `Spin`의 반복**이다. 도킹은 `nav2_msgs/action/DockRobot`이 아니라 `irobot_create_msgs/action/Dock` 경로를 호출한다.

`goToPose()`·`spin()`의 반환 `True`는 Goal 수락을 뜻한다. 최종 성공은 `isTaskComplete()`와 `getResult() == TaskResult.SUCCEEDED`로 따로 확인한다. 정지 시에는 현재 Nav2 Goal의 `cancel_goal_async()`를 호출하고 결과 종료와 odom을 확인한다. 외부 순찰 Action 취소와 Nav2 내부 작업 취소는 서로 다른 인터페이스다.

### 3.3 라이브러리가 생성하지만 네 파일에서 호출하지 않는 client

설치된 Jazzy `BasicNavigator.__init__()`는 아래 client도 만든다. ROS 그래프에 나타날 수 있지만 이번 순찰 기능이 요청을 보낸다는 뜻은 아니다.

| 종류 | 상대 이름 → 타입 |
|---|---|
| Nav2 Action | `navigate_through_poses` → `NavigateThroughPoses`; `follow_waypoints` → `FollowWaypoints`; `follow_gps_waypoints` → `FollowGPSWaypoints`; `follow_path` → `FollowPath` |
| Nav2 Action | `compute_path_to_pose` → `ComputePathToPose`; `compute_path_through_poses` → `ComputePathThroughPoses`; `smooth_path` → `SmoothPath` |
| Nav2 Action | `backup` → `BackUp`; `drive_on_heading` → `DriveOnHeading`; `assisted_teleop` → `AssistedTeleop`; `dock_robot` → `DockRobot`; `undock_robot` → `UndockRobot` |
| Nav2 Service | `map_server/load_map` → `LoadMap` |
| Nav2 Service | `global_costmap/clear_entirely_global_costmap`、`local_costmap/clear_entirely_local_costmap` → `ClearEntireCostmap` |
| Nav2 Service | `local_costmap/clear_costmap_except_region` → `ClearCostmapExceptRegion`; `local_costmap/clear_costmap_around_robot` → `ClearCostmapAroundRobot`; `local_costmap/clear_costmap_around_pose` → `ClearCostmapAroundPose` |
| Nav2 Service | `global_costmap/get_costmap`、`local_costmap/get_costmap` → `GetCostmap` |

위 Action 타입의 패키지는 `nav2_msgs/action`, Service는 `nav2_msgs/srv`다. 설치 라이브러리 버전에 따라 생성 목록이 달라질 수 있다. `lifecycleStartup()`·`lifecycleShutdown()`은 호출하지 않으므로 그 함수 안에서 동적으로 만드는 `ManageLifecycleNodes` client는 현재 실행 목록에 넣지 않았다.

### 3.4 조건부 인터페이스: 기존 안전구역 대피 경로

| 활성 조건 | 이름·타입 | 입력과 처리 |
|---|---|---|
| `Evacuation(..., event_check=None)` | 기본 `/{robot}/safety_command`, `std_msgs/msg/UInt8` 구독 | `1`: active이며 PATROLLING이면 대피 요청. `2`: active이며 WAITING이면 재개 요청. 나머지는 무시 |

현재 `genius_patrol.main()`은 항상 EventCheck를 전달하므로 **이 UInt8 구독은 생성하지 않으며 `escape_and_wait()`도 호출하지 않는다.** `--command-topic`이나 `--safe`를 지정하는 것만으로 이 분기가 활성화되지 않는다. 현재 감지 연결은 안전구역 이동 없이 현재 위치에서 정지하고 재개한다.

조건부 대피 함수 자체는 `현재 작업 정지 → map에서 가장 가까운 안전구역 선택 → 이동 → 정지 확인 → 명령 2 대기 → 저장한 index 재실행`을 구현한다. 중단한 단계가 spin이면 직전 waypoint로 돌아간 뒤 spin을 다시 실행한다. 거리 기준은 map 평면의 직선거리이며 경로 길이·도달 가능성·Keepout을 별도로 평가하는 코드는 없다.

## 4. QoS와 ROS가 제공하는 부가 인터페이스

코드에 지정한 값과 설치된 Jazzy 기본값을 정리했다. 실제 연결 상대의 QoS 및 ROS remap 결과를 현장 그래프에서 조회한 결과는 아니다.

| 대상 | History / Depth | Reliability | Durability |
|---|---|---|---|
| 비전 camera·odom 구독 | KEEP_LAST / 1 | BEST_EFFORT | VOLATILE |
| Evacuation odom·Navigator dock_status 구독 | KEEP_LAST / 5 (`sensor_data`) | BEST_EFFORT | VOLATILE |
| patrol_resume 발행·구독 | KEEP_LAST / 2 | RELIABLE | VOLATILE |
| 조건부 safety_command 구독 | KEEP_LAST / 10 | RELIABLE | VOLATILE |
| TF 구독 | KEEP_LAST / 100 | RELIABLE | VOLATILE |
| TF static 구독 | KEEP_LAST / 100 | RELIABLE | TRANSIENT_LOCAL |
| initialpose 발행 | KEEP_LAST / 10 | RELIABLE | VOLATILE |
| Navigator initialpose 구독 | SYSTEM_DEFAULT | SYSTEM_DEFAULT | SYSTEM_DEFAULT |
| amcl_pose 구독 | KEEP_LAST / 1 | RELIABLE | TRANSIENT_LOCAL |
| 일반 Service 요청·응답 | KEEP_LAST / 10 (`services_default`) | RELIABLE | VOLATILE |
| Action Goal·Result·Cancel Service | KEEP_LAST / 10 (`services_default`) | RELIABLE | VOLATILE |
| Action Feedback | KEEP_LAST / 10 | RELIABLE | VOLATILE |
| Action Status | KEEP_LAST / 1 | RELIABLE | TRANSIENT_LOCAL |

Action 하나에는 내부적으로 `<action>/_action/send_goal`, `get_result`, `cancel_goal` Service와 `<action>/_action/feedback`, `status` Topic이 생긴다. 예를 들어 `patrol_action`의 Feedback wire 타입은 `nav2_msgs/action/NavigateToPose_FeedbackMessage`, Status는 `action_msgs/msg/GoalStatusArray`다. **외부 patrol_action에는 사용자 코드의 feedback 발행이 없다.** 성공 시 `goal.succeed()`, 실패 시 `goal.abort()`를 호출하며 양쪽 모두 새 `NavigateToPose.Result()`를 반환하고 실패 상세 필드를 채우지 않는다. 별도 cancel callback을 지정하지 않아 설치된 rclpy 기본 동작은 외부 Cancel 거절이다.

ROS 기본 `/rosout`, `/parameter_events`, 노드별 parameter Service(`describe_parameters`, `get_parameter_types`, `get_parameters`, `list_parameters`, `set_parameters`, `set_parameters_atomically`)는 기능 전용 목록에서 분리했다. 네 파일에는 사용자 정의 `declare_parameter()`가 없다. `use_sim_time` 같은 ROS 공통 파라미터와 그에 따른 `/clock` 구독은 실행 환경에 따른다.

QoS 근거: 설치된 `rclpy/action/server.py`, `rclpy/action/client.py`, `tf2_ros/transform_listener.py`, `rmw/qos_profiles.h`. 숫자 depth만 전달한 Topic은 기본 RELIABLE·VOLATILE이다.

## 5. 정지·보고·재개 때 오가는 값

### 5.1 순찰 Action과 내부 진행 상태

`patrol_action` Goal은 고정 경로 시작 신호다. 경로는 이동 9회와 360° spin 8회, 총 17단계이며 최종 `(0,0)` 이동 뒤 도킹한다. 경로 좌표는 [genius_patrol.py의 run_patrol](../src/patrol_amr_safety/patrol_amr_safety/genius_patrol.py) 95–114행에 고정되어 있다. 외부 Goal의 pose로 경로를 바꾸지 않는다.

`EventCheck._active`는 순찰 경로 루프에서만 True다. 준비 도킹·undock·초기 위치 설정·Nav2 대기·최종 도킹 중에는 정지 서비스가 `Patrol is not active`로 실패 응답한다. 저장한 `index`와 이벤트 이력은 메모리에 있으며 프로세스 재시작 후 복원하지 않는다.

### 5.2 정지 서비스와 재개 토픽

| 입력·출력 | 현재 코드 동작 |
|---|---|
| `SetBool.Request.data=false` | 정지 Future 생성. 진행 중인 정지에 대한 중복 요청은 같은 Future 공유 |
| `SetBool.Request.data=true` | `success=false`. 서비스로 재개하지 않음 |
| 정지 성공 응답 | `success=true`, `message='Stopped in place; patrol index=<index>'` |
| 정지 실패 응답 | `success=false`, `message`에 비활성·정지 실패 등 사유 |
| `Bool.data=true` | 최신 재개 허용값을 True로 기록. 정지 완료와 서비스 응답 콜백 처리가 확인되면 같은 index 재개 |
| `Bool.data=false` | 최신 허용값을 False로 바꾸어 재개 보류. 새로운 정지를 시작하지 않음 |

`EventCheck.on_stop()`은 Future를 await하고, 실제 Nav2 취소·정지 확인은 순찰 작업자가 `pause_and_wait() → Evacuation.stop()`으로 수행한다. `_responded`는 서비스 콜백의 응답 처리 표시이며 DDS 전송 완료나 상대 수신을 보증하는 별도 ACK는 아니다. 비전 client는 실제 서비스 응답 `success=true`를 받은 후에만 `stopped=True`로 바꾼다.

`stop()`은 취소 응답·Action 종료를 확인한 뒤 기존 odom을 버린다. Action 종료 이후 timestamp의 새 odom만 사용하고, 선속도·각속도 기준 이하가 odom 시각과 monotonic 시간 양쪽에서 `stop_hold` 이상 유지되어야 성공한다. 이 네 파일은 직접 `cmd_vel`을 발행하지 않는다.

### 5.3 ReportDetection 요청의 실제 대입값

필드 정의와 계약은 [ReportDetection.srv](../src/patrol_interfaces/srv/ReportDetection.srv) 및 [interfaces.md 8절](interfaces.md#8-reportdetection-service)을 참조한다. 다음은 새로운 스키마가 아니라 `submit_event()`가 현재 채우는 값이다.

| 필드 | 현재 생산하는 값 |
|---|---|
| `robot_id` | 파일 상수 `robot1` |
| `event_id` | `str(uuid.uuid4())`로 만든 소문자 UUID v4 |
| `detected_at` | 보고 요청을 만들 때의 ROS 현재 시각. 입력 이미지 header 시각을 복사하지 않음 |
| `position.x/y` | 최신 odom의 로봇 위치. 대상 물체 좌표나 ray 교차점을 보내는 것이 아님 |
| `position.z` | 별도 대입 없이 메시지 기본값 0 |
| `image` | 선택 bbox·클래스·confidence를 표시한 전체 프레임의 JPEG 바이트 |
| `event_type` | `fire → FIRE(1)`, `leak → LEAK(2)`, `obstacle → OBSTACLE(3)` |

`bbox`, confidence, yaw, theta, frame_id를 별도 필드로 보내지 않는다. bbox·confidence는 이미지 위에 표시하고 위치·theta는 로컬 중복 판단에도 사용한다.

응답은 `status`, `detail`을 읽는다. **STORED(0)일 때만** 로컬 중복 기록을 추가하고 `patrol_resume(true)`를 발행한다. DUPLICATE(1), REJECTED(2), 응답 예외에서는 재개를 발행하지 않는다.

### 5.4 한 사건의 정상 흐름

1. 비전이 허용 클래스 중 confidence가 가장 높은 bbox 한 개를 선택한다.
2. 알려진 사건으로 억제되지 않은 첫 유효 bbox에서 즉시 `patrol_stop(false)`를 요청한다.
3. 순찰 작업자가 현재 Action을 취소하고 새 odom으로 정지를 확인한다.
4. 비전이 정지 성공 응답을 받고, 후보 시작 후 1초 이상이며 미완료 보고가 없으면 `ReportDetection`을 요청한다.
5. System monitor의 STORED 응답 후 비전이 `patrol_resume(true)`를 발행한다.
6. 순찰 작업자가 같은 index를 다시 실행한다. 이동은 같은 목표를 재요청하고, spin은 현재 위치에서 360° 전체를 다시 실행한다.

1초는 **후보 시작 시점부터의 hold**이며 정지 성공 응답 이후 별도로 1초를 세는 구조가 아니다. 무검출 프레임에서 마지막 검출 후 0.30초를 넘으면 후보를 reset한다. 카메라 메시지가 아예 끊겼을 때 타이머가 동일 reset을 수행하는 구조는 아니다.

## 6. 파일 사이 Python 인터페이스와 소유권

| 호출·공유 | 입력 → 결과·역할 |
|---|---|
| `arguments()` → `genius_patrol.main()` | CLI → argparse Namespace. ROS parameter가 아님 |
| `execute(goal, ns, settings, event_check)` | Goal handle·설정 → Navigator/Evacuation 생성, 순찰 수행, 외부 Action 종료 |
| `run_patrol(navigator, evacuation)` | 공용 Navigator·helper → 성공 bool, 단계 index 관리 |
| `startSpin(..., evacuation=...)` | 회전량·제한 시간 → 회전 수락 및 완료 bool |
| `Evacuation.set_active(active)` → `EventCheck.set_active(active)` | 정지 요청 수락 가능 구간 전달 |
| `Evacuation.check_events()` ← `EventCheck.stop_requested` | 미완료 정지 Future를 읽고 `evacuate=True` |
| `EventCheck.pause_and_wait(evacuation, index)` | 현재 단계 저장 → 정지 확인·응답 처리·재개 대기 |
| `Evacuation.stop()` | 현재 Action·새 odom → 정상 반환 또는 RuntimeError |
| `VisionPatrolLink.request()` | 비전 이벤트 → 정지 서비스 비동기 전송; busy/미준비이면 False |
| `VisionPatrolLink._done(future)` | 정지 응답 → `stopped=True` 또는 실패 처리 |
| `DetectingNode.submit_event(frame)` | 증거 프레임·최신 위치 → ReportDetection 비동기 요청 |
| `on_submit_response(...) → VisionPatrolLink.resume()` | STORED → Bool True 발행, busy/stopped 해제 |

`EventCheck.history`는 최근 수신 이벤트 두 개 `(source, value, monotonic 수신시각)`만 보관한다. 제어는 history 전체가 아니라 최신 허용값·완료 Future·응답 표시로 판단한다. `Evacuation`의 PATROLLING=0, EVACUATING=1, WAITING=2는 내부 상태값이며 RobotStatus나 별도 상태 토픽으로 발행하지 않는다.

코드별 함수·분기·실패 순서도는 현재 SHA와 일치하는 [event_check 구현 대조](event_check.md)의 네 파일 절을 참조한다. 과거 [genius_patrol 상세 그림](genius_patrol.md)과 [대피 상세 그림](move_to_safetyzone_flowchart.md)은 기록된 SHA가 현재와 다르므로, 현재 정지 서비스 경로는 이 문서와 event_check.md를 먼저 확인한다.

## 7. 설정·수치·비ROS 자원

### 7.1 순찰 쪽 CLI

| 인자 | 기본값 | 적용 |
|---|---|---|
| `--robot-id` 또는 `--namespace` | `robot1`; 선택 `robot1`, `robot6` | 서버·event_check namespace, 기본 통신 주소 |
| `--stop-service` | `/{robot}/patrol_stop` | EventCheck 서비스 |
| `--resume-topic` | `/{robot}/patrol_resume` | EventCheck 구독 |
| `--odom-topic` | `/{robot}/odom` | Evacuation 정지 확인 |
| `--command-topic` | `/{robot}/safety_command` | EventCheck 미연결일 때만 UInt8 구독 |
| `--base-frame` | `base_link` | 조건부 안전구역 이동의 TF lookup |
| `--safe X Y YAW_DEG` | 코드의 SAFE_ZONES 6곳 | 반복 지정 가능. 조건부 대피 목표 |
| `--linear-epsilon` | 0.01 m/s | 3축 선속도 크기 상한 |
| `--angular-epsilon` | 0.02 rad/s | 3축 각속도 크기 상한 |
| `--stop-hold` | 0.5초 | 정지 유지 확인 |
| `--stop-timeout` | 10.0초 | 취소 응답·Action 종료·odom 확인이 공유하는 전체 기한 |
| `--data-max-age` | 1.0초 | odom 및 조건부 TF timestamp 허용 age |

수치와 좌표는 finite여야 하고 모든 제한값은 양수, stop-timeout은 stop-hold보다 커야 한다. 기본 안전구역은 SAFE_ZONES의 WP 1·2·4·5·6·7이며 WP 3은 제외한다. yaw 입력 단위는 degree다. 좌표의 단일 근거는 [move_to_safetyzone.py](../src/patrol_amr_safety/patrol_amr_safety/move_to_safetyzone.py) 27–41행이다.

### 7.2 비전 쪽 파일 상수

| 설정 | 현재값 |
|---|---|
| 로봇 | `ROBOT_ID="robot1"`; 사용자 정의 robot CLI·ROS parameter 없음 |
| 모델 | `Path(__file__).resolve().parents[3] / "detection_best" / "detection_best.pt"` |
| 추론 | confidence 0.70, image size 704, 클래스 fire·leak·obstacle |
| 보고 hold / 무검출 gap | 1.0초 / 0.30초 |
| JPEG | 품질 90, 1 MiB 초과 시 품질 50으로 한 번 재인코딩 |
| 중복 판단 | 수평 FOV 64°, 같은 자리 기준 0.5m, 방향 허용 15°, ray 최소 각도 차이 15°, 최대 교차 거리 5m |
| 중복 기록 | 최근 최대 500건, 메모리만 사용 |
| 진단 타이머 | 5초. 수신·감지·정지·보고 상태 로그용 |

외부 Python 자원은 `ultralytics.YOLO`, `cv2`, `numpy` 및 모델 파일이다. 현재 소스 경로에서 모델은 저장소 루트의 `detection_best/detection_best.pt`로 해석되며 파일 존재를 확인했다. 설치된 Python 모듈 위치가 달라지면 `parents[3]`의 결과도 달라질 수 있다.

OpenCV 창 `AMR Vision (test)`에 추론 결과를 표시하고 `q` 키로 종료한다. 이 네 파일은 증거 사진을 로컬 DB·파일에 저장하지 않으며, 저장은 ReportDetection 서버에 요청한다. 별도 HTTP·소켓 인터페이스는 없다.

### 7.3 Namespace 해석

순찰 쪽 `--robot-id robot6`은 EventCheck와 기본 odom 주소를 robot6으로 바꾼다. 비전의 robot1 상수에는 영향을 주지 않는다. 비전 노드에 `__ns`만 remap해도 절대 주소 `/robot1/...`와 보고 `robot_id`는 그대로다.

순찰 코드에서 `/tf:=tf`, `/tf_static:=tf_static` remap을 추가하므로 TF 토픽은 Navigator namespace 아래로 연결한다. TF 프레임 문자열 `map`, `base_link` 자체에는 namespace를 붙이지 않는다. 일반 CLI robot 설정과 ROS `__ns`를 서로 다르게 주면 실제 서버 namespace와 절대 서비스·odom 기본 주소가 달라질 수 있다.

## 8. 실행 진입점과 패키지 상태

| 진입점 | 현재 의미 |
|---|---|
| `genius_patrol.py:main` / console script `genius_patrol` | 순찰 서버와 EventCheck를 함께 시작 |
| `event_check.py:main` / console script `event_check` | `genius_patrol.main()`으로 위임. 독립 수신 전용 실행이 아님 |
| `vision_node_v2.py:main` / console script `vision_node_v2` | 별도 비전 노드 시작 |
| move_to_safetyzone.py 직접 실행 | helper 안내와 함께 종료. 독립 실행 entry point 없음 |

`genius_patrol`과 `event_check`는 같은 실행 흐름의 두 진입점이므로, 같은 로봇에 둘 다 실행하면 서버·event_check가 중복 생성될 수 있다. 보통 순찰 진입점 하나와 비전 진입점 하나의 구성을 읽으면 된다.

정적 패키지 확인 결과, [setup.py](../src/patrol_amr_safety/setup.py)에 등록된 `launch/amr_safety_status.launch.py` 및 일부 기존 console script 대상이 현재 소스 트리에 없다. 예를 들어 `3_1_c_follow_waypoints.py`는 삭제 상태이고 battery_monitor·command_gateway·local_safety_supervisor·status_reporter 모듈도 이 패키지의 현재 트리에 없다. 이것은 위 네 파일의 단위 기능 시험과 구분되는 패키징 상태다.

네 파일이 직접 import하는 `nav2_simple_commander`, `tf2_ros`, `ultralytics`는 [package.xml](../src/patrol_amr_safety/package.xml)·setup.py에 직접 의존성으로 선언되어 있지 않다. 환경에 이미 설치되었거나 전이 의존성으로 제공될 수 있으므로 import 실패를 단정하지 않는다. 이번에는 빌드·설치·실행을 재검증하지 않았다.

## 9. 공용 문서와 차이 및 현재 동작의 범위

| 확인 항목 | 코드에서 확인한 사실 | 연결 근거 |
|---|---|---|
| 외부 순찰 Action 타입 | 현재 `nav2_msgs/action/NavigateToPose`. 공용 v2 목록의 `patrol_interfaces/action/Patrol`과 이름은 같지만 타입이 달라 직접 호환되지 않음 | [interfaces.md](interfaces.md), [v2 전환 요청서](change_requests/CR-관제_09-10_15-26_patrol_interfaces_v2_전환.md) |
| 공용 순찰·감지 연결 | 이 네 파일은 PatrolCommand·DriveToken·DetectEvent를 소비하거나 제공하지 않음. 공용 Patrol Feedback·Result도 만들지 않음 | 같은 v2 전환 요청서 |
| 정지·재개 | 현재 SetBool·Bool 연결은 구현되어 있으나, 기존 요청서에는 상대 팀 합의·실기 통합 검증이 미완료로 기록되어 있음 | [정지 서비스·재개 토픽 요청서](change_requests/CR-AMR_09-11_08-00_정지서비스_재개토픽.md) |
| 보고 좌표 | 계약은 map 좌표. 비전은 odom pose를 변환 없이 대입하고 odom 미수신 시 기본 `(0,0,0)`을 보낼 수 있음 | [ReportDetection.srv](../src/patrol_interfaces/srv/ReportDetection.srv), vision_node_v2.py 140–159·404–418행 |
| 보고 재시도 | 응답 timeout·동일 event_id/내용 재전송 경로가 없음 | vision_node_v2.py 367–449행 |
| 보고를 보내지 못한 경우 | 인코딩 실패·용량 초과·서비스 미준비로 submit_event가 반환해도 호출부가 `reported=True`로 설정. 같은 후보에 대한 자동 보고 재시도를 보장하지 않음 | 같은 파일 248–254·382–402행 |
| 재개가 없는 경우 | 감지가 hold 전에 사라짐, 보고 실패·무응답, DUPLICATE·REJECTED에는 자동 재개하지 않음. reset도 재개를 발행하지 않음 | 같은 파일 219–221·283–294·430–449행 |
| 위치·카메라 진단 | 비전은 pose의 freshness·frame_id를 검증하지 않음. 5초 진단 로그는 센서 장애·복구 판단이 아님 | 같은 파일 126–144행 |
| 미확인 보정 | 실제 image_raw 기준 FOV와 bbox 방향 부호 확인 TODO가 코드에 남아 있음 | 같은 파일 53–54·168–170행 |

단위 기능 테스트 수행 보고만으로 위 타입 차이·좌표 차이·상대 팀 합의 상태가 해소되었다고 기록하지 않는다. 기존 AGENTS.md·architecture.md·amr.md 일부의 MissionCommand 설명과 interfaces.md의 v2 설명이 함께 남아 있으므로, 이 정리에서는 현재 코드를 어느 공용 계약으로도 임의 변경하지 않았다.

새 TBD ID나 계약 결정을 만들지 않았다. 공용 전환은 위 v2 요청서, 현재 정지·재개 연계는 위 AMR 요청서를 참조한다. 기능별 기존 TBD의 관리 위치는 [amr.md](amr.md#tbd)다.

## 10. 이번 정리의 검증 범위

- 네 파일의 노드 생성·pub/sub·Service·Action·CLI·상수·호출 경로를 정적으로 대조했다.
- Navigator·TF·QoS 기본값은 저장소의 TurtleBot4Navigator와 로컬 Jazzy 설치 소스에서 확인했다.
- ReportDetection 필드 사용과 현재 공용 인터페이스 문서·기존 요청서의 연결 차이를 확인했다.
- 새 문서의 상대 파일 링크와 코드 SHA-256 일치 여부를 검사했다.
- 코드 수정, 전체 패키지 빌드, 단위시험 재실행, ROS 그래프 조회, 카메라 추론, 로봇 주행·정지 및 장비 통합시험은 이번 작업에서 수행하지 않았다.

## 11. 대조한 코드 버전

2026-09-11 비전 정지·재개 연결 복구 후 비전 파일의 해시와 변경된 행 번호를 갱신했다. `DetectingNode.__init__`에서 `VisionPatrolLink`를 생성하는 회귀검사와 기존 동작 검사를 포함한 총 27개 검사 결과는 [event_check 검증](event_check.md#검증)에 기록했다. 10절의 미실행 항목은 최초 문서 정리 시점의 기록이다.

저장소 HEAD: `7b2ea41a662ba235916b48145a6c00b0af3efda5`에 미커밋 작업본을 포함한다. 사용자 변경은 그대로 유지했다.

| 파일 | 행 수 | SHA-256 |
|---|---:|---|
| genius_patrol.py | 233 | `5fae34a8ba2e9775b99d5076d7cec04889399a53dd11d1e8f4a6885fafef0970` |
| event_check.py | 208 | `71075b7bc793e0d4f52b270205180375c9a87967b47fc92280631bfc371da0bd` |
| move_to_safetyzone.py | 258 | `1934f394a2799540d16ab9f9982057ce847efdeb1a5dbebda63aebe20d6fad72` |
| vision_node_v2.py | 470 | `a9b8bd4e6726941bda0985f5ffc2ce2878cb5f7ad678765018356f504b3f5470` |
