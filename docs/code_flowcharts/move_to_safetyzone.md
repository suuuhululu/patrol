# move_to_safetyzone.py — 코드 기준 함수별 흐름

**구현 대조 완료: 2026-09-11 07:39:45 KST.** [move_to_safetyzone.py](../../src/patrol_amr_safety/patrol_amr_safety/move_to_safetyzone.py) 228행, SHA-256 `34637ffd14929c85b1f054e6970ea9ee93c93c2807f035d0b71aba5069883430`. 아래 L번호는 이 소스의 줄 번호다. 기존 Markdown 대신 Python과 설치 라이브러리 코드를 직접 대조했다. 호출자는 [genius_patrol](genius_patrol.md), 값 설명 그림은 [data_values](data_values.md)를 참조한다.

## 1. 입력·공유 변수

| 값 | 타입·초기값·용도 | 소스 |
|---|---|---|
| MOVE_TO_SAFE_ZONE / RESUME_PATROL | 정수 1 / 2; UInt8.data로 수신 | L23,93-113 |
| PATROLLING / EVACUATING / WAITING | 정수 0 / 1 / 2; 내부 상태이며 별도 상태 토픽 발행 없음 | L24-25 |
| active, evacuate, resume | bool; 모두 False. 호출자가 active를 바꾸고 명령 콜백이 플래그를 설정 | L77,95-100 |
| saved_index | 초기 None, 대피 때 현재 정수 index 저장; 영속 저장 없음 | L76,198 |
| odom | 초기 None, 콜백이 최신 Odometry 객체 대입; stop 중 캐시를 지움 | L78,115-116,170 |
| safe | args.safe 각 x,y,yaw를 PoseStamped로 바꾼 목록 | L85 |
| 기본 namespace | robot1; robot6 선택 가능. --robot-id와 --namespace는 같은 인자 | L46-47 |
| 기본 command / odom | /robot1/safety_command / /robot1/odom; namespace 또는 옵션으로 변경 | L56-58 |
| 기본 base_frame | base_link; TF frame 이름에 namespace를 자동 추가하지 않음 | L50,129 |
| command QoS / odom QoS | 깊이 10 / qos_profile_sensor_data | L81-84 |
| 초기 TF 구성 | Buffer(), TransformListener(self.tf,nav). 별도 navigator 생성 없음 | L75,79-80 |

기본 안전구역은 WP 1·2·4·5·6·7이며 순서대로 `(-0.206,-1.038,90.8)`, `(-1.147,0.500,175.4)`, `(-2.751,-2.422,182.4)`, `(-4.389,-1.122,94.3)`, `(-2.909,0.575,358.3)`, `(-1.374,-2.439,359.8)`이다(L27-34). x/y 단위는 m, yaw 입력 단위는 degree. 순찰의 방향 enum 값과 혼용하지 않는다.

기본값은 linear_epsilon=0.01 m/s, angular_epsilon=0.02 rad/s, stop_hold=0.5 s, stop_timeout=10.0 s, data_max_age=1.0 s다(L35-41). CLI가 이 값을 대체할 수 있다. --safe를 한 번 이상 지정하면 기본 안전구역 전체를 대체한다. 입력 순서·yaw를 보존하며 중복 제거·yaw 정규화는 하지 않는다.

## 2. M1 — arguments

```mermaid
flowchart TD
    A([arguments 진입<br/>L44]) --> P[ArgumentParser·옵션 등록<br/>L45-54]
    P --> PARSE[[remove_ros_args의 프로그램 이름 제외<br/>parser.parse_args → args<br/>L55]]
    PARSE --> C{command_topic is None?<br/>L56-57}
    C -->|True| CS[namespace로 기본 safety_command 생성<br/>L56]
    C -->|False| O{odom_topic is None?<br/>L58}
    CS --> O
    O -->|True| OS[namespace로 기본 odom 생성<br/>L58]
    O -->|False| S{args.safe is None?<br/>L59}
    OS --> S
    S -->|True| SS[args.safe=list SAFE_ZONES.values<br/>L59]
    S -->|False| V[values=모든 좌표·yaw<br/>limits=다섯 제한값<br/>L60-62]
    SS --> V
    V --> FIN{values+limits 모두 유한?<br/>L63}
    FIN -->|False| ERR[[parser.error: finite 오류<br/>L64]]
    FIN -->|True| LIMIT{모든 limits가 양수이고<br/>stop_timeout > stop_hold?<br/>L65}
    LIMIT -->|False| LE[[parser.error: limits 오류<br/>L66]]
    LIMIT -->|True| NAME{namespace와 topic·base_frame<br/>문자열이 모두 비어 있지 않은가?<br/>L67-68}
    NAME -->|False| NE[[parser.error: empty 오류<br/>L69]]
    NAME -->|True| RET([args 반환<br/>L70])
    ERR --> EXIT([SystemExit 2])
    LE --> EXIT
    NE --> EXIT
```

parse_args 자체의 구문·choices 오류는 뒤의 검증 이전에 종료한다. --help는 도움말 후 종료한다. 이 함수에는 configure callback 인자가 없다. topic/frame 문자열이 실제 ROS에서 유효한 이름인지 추가 검증하는 코드도 없다.

## 3. M2 — Evacuation.__init__

```mermaid
flowchart TD
    A([생성자 nav,args<br/>L74]) --> SAVE[self.nav=nav; self.args=args<br/>L75]
    SAVE --> INIT[state=PATROLLING 0; saved_index=None<br/>active=evacuate=resume=False; odom=None<br/>L76-78]
    INIT --> TF[[Buffer와 TransformListener 생성<br/>기존 nav에 연결<br/>L79-80]]
    TF --> CMD[[UInt8 command 구독<br/>on_command, 깊이 10<br/>L81-82]]
    CMD --> ODOM[[Odometry odom 구독<br/>on_odom, sensor_data QoS<br/>L83-84]]
    ODOM --> SAFE[[각 x,y,yaw를 nav.getPoseStamped로 변환<br/>self.safe 목록 생성<br/>L85]]
    SAFE --> LOG[/SAFETY_SUB: 실제 노드·topic 이름<br/>active=False,state=PATROLLING 로그<br/>L86-91/]
    LOG --> END([생성 완료; None 반환])
```

TurtleBot4Navigator의 getPoseStamped는 map 프레임, 생성 시각 stamp, `(x,y,0)`, quaternion `(0,0,sin(yaw×π/360),cos(yaw×π/360))`를 만든다. TransformListener의 TF callback은 Buffer를 갱신한다. 생성자가 on_command를 직접 호출하는 구조는 아니다. 실제 TF 토픽은 호출자의 remap 영향을 받고, 프레임 문자열은 별개다.

## 4. M3 — on_command

```mermaid
flowchart TD
    A([on_command msg<br/>L93]) --> INIT[accepted=False<br/>L94]
    INIT --> C1{active and state==0 and data==1?<br/>L95}
    C1 -->|True| E[evacuate=True; accepted=True<br/>reason=evacuation_flag_set<br/>L96-97]
    C1 -->|False| C2{active and state==2 and data==2?<br/>L98}
    C2 -->|True| R[resume=True; accepted=True<br/>reason=resume_flag_set<br/>L99-100]
    C2 -->|False| ACTIVE{not active?<br/>L101}
    ACTIVE -->|True| INACTIVE[reason=patrol_inactive<br/>L102]
    ACTIVE -->|False| D1{data==1?<br/>L103}
    D1 -->|True| P[reason=requires_PATROLLING<br/>L104]
    D1 -->|False| D2{data==2?<br/>L105}
    D2 -->|True| W[reason=requires_WAITING<br/>L106]
    D2 -->|False| U[reason=unsupported_command<br/>L108]
    E --> LOG[/data,active,state,decision,reason<br/>evacuate,resume 로그<br/>L109-113/]
    R --> LOG
    INACTIVE --> LOG
    P --> LOG
    W --> LOG
    U --> LOG
    LOG --> RET([None 반환])
```

decision은 accepted에 따라 ACCEPTED/IGNORED다. ACCEPTED는 플래그 설정을 의미하며 동작 완료가 아니다. 조건은 발행 시각이 아니라 콜백 실행 시점의 상태다. 중복 허용 명령은 같은 True를 다시 설정한다. 미수락 명령을 나중에 수행하도록 저장하지 않는다.

## 5. M4 — on_odom

```mermaid
flowchart TD
    A([on_odom msg<br/>L115]) --> IN[/Odometry 객체 입력/]
    IN --> SET[self.odom=msg<br/>L116]
    SET --> RET([None 반환])
```

복사·검증 없이 객체를 저장한다. pose·covariance·frame 문자열은 stop 판정에 사용하지 않는다.

## 6. M5 — tick

```mermaid
flowchart TD
    A([tick 진입<br/>L118]) --> Q{rclpy.ok?<br/>L119}
    Q -->|False| E([RuntimeError: ROS shutdown<br/>L120])
    Q -->|True| SPIN[[rclpy.spin_once nav,timeout_sec=0.1<br/>L121]]
    SPIN --> RET([None 반환])
```

tick 및 Nav2 API 내부 spin이 준비된 command·odom·TF callback을 처리할 수 있다. spin_once 한 번에 모든 callback이 처리된다는 뜻은 아니다. 0.1초는 호출의 timeout 인자이며 주기 타이머가 아니다.

## 7. M6 — fresh

```mermaid
flowchart TD
    A([fresh stamp<br/>L123]) --> AGE[age=현재 nav ROS 시각-Time.from_msg stamp<br/>nanoseconds / 1e9, 단위 s<br/>L124]
    AGE --> Q{0 ≤ age ≤ data_max_age?<br/>L125}
    Q -->|True| YES([True 반환])
    Q -->|False| NO([False 반환])
```

기본 허용 나이는 0..1.0초다. 미래 timestamp도 False다. 여기서는 monotonic이 아니라 navigator의 ROS 시계를 쓴다.

## 8. M7 — position

```mermaid
flowchart TD
    A([position 진입<br/>L127]) --> LOG[/SAFETY_TF 조회 로그<br/>L128/]
    LOG --> TF[[lookup_transform target=map<br/>source=args.base_frame, time=Time 0<br/>L129]]
    TF -->|정상| F[[fresh transform.header.stamp<br/>L130]]
    F --> Q{fresh True?<br/>L130}
    Q -->|False| STALE([RuntimeError: Current map position is stale<br/>L131])
    Q -->|True| P[p=transform.transform.translation<br/>L132]
    P --> FIN{p.x,p.y 모두 유한?<br/>L133}
    FIN -->|False| INVALID([RuntimeError: Invalid current position<br/>L134])
    FIN -->|True| RET([p.x,p.y 반환: map 좌표 m<br/>L135])
    TF -->|조회 예외| ERR([예외를 호출자로 전파])
```

최신 TF로 base 원점을 map에서 표현한 x,y다. z·quaternion·odom pose는 선택에 사용하지 않는다. timeout 인자를 주지 않아 설치된 TF API 기본 0초를 사용한다. TF 없음·연결 없음·외삽 오류에 재조회 루프는 없다.

## 9. M8 — wait_for_task

```mermaid
flowchart TD
    A([wait_for_task interruptible=True 기본값<br/>L138]) --> COMP[[nav.isTaskComplete → complete<br/>L140]]
    COMP --> EV{interruptible and evacuate?<br/>L141}
    EV -->|True| LOG[/대피 감지 SAFETY_STEP 로그<br/>L142/]
    LOG --> FALSE([False 반환<br/>L143])
    EV -->|False| CQ{complete?<br/>L144}
    CQ -->|True| RES[[nav.getResult<br/>L145]]
    RES --> RQ{TaskResult.SUCCEEDED인가?<br/>L145}
    RQ -->|True| TRUE([True 반환])
    RQ -->|False| NO([False 반환])
    CQ -->|False| OK{rclpy.ok?<br/>L146}
    OK -->|True| COMP
    OK -->|False| ERR([RuntimeError: ROS shutdown<br/>L147])
```

완료 여부를 얻은 뒤 대피를 먼저 검사한다. 이 함수는 대피 False 반환 시 직접 취소하지 않는다. 이어지는 escape_and_wait의 stop이 취소한다. interruptible=False이면 대피 플래그를 무시한다. 전체 이동 timeout은 없다. complete=True는 성공과 다르며 TaskResult를 별도로 검사한다.

## 10. M9 — navigate

```mermaid
flowchart TD
    A([navigate pose<br/>L149]) --> STAMP[pose.header.stamp=현재 ROS 시각<br/>입력 객체 직접 갱신<br/>L150]
    STAMP --> LOG[/SAFETY_NAV x,y 로그: 소수점 3자리<br/>L151-153/]
    LOG --> NAV[[nav.goToPose pose<br/>L154]]
    NAV --> Q{목표 수락?<br/>L154}
    Q -->|False| ERR([RuntimeError: Evacuation/return navigation failed<br/>L155])
    Q -->|True| AL[/goal accepted 로그<br/>L156/]
    AL --> WAIT[[wait_for_task interruptible=False<br/>L157]]
    WAIT --> WQ{반환 True?<br/>L157}
    WQ -->|False| FAIL([같은 RuntimeError<br/>L158])
    WQ -->|True| SUCCESS[/task succeeded 로그<br/>L159/]
    SUCCESS --> RET([None 반환])
```

좌표의 원래 정밀도는 유지하고 로그만 반올림해 표시한다. 이 함수 안에는 stop이 없다. Nav2 Goal은 pose와 기본 behavior_tree=''를 사용한다. 일반 순찰 goToPose와 달리 stamp를 갱신하며 spin 복귀 시 경로의 직전 Pose 객체도 갱신된다.

## 11. M10 — stop: 취소와 Action 종료

```mermaid
flowchart TD
    A([stop 진입<br/>L161]) --> CANCEL[[nav.cancelTask<br/>L162]]
    CANCEL --> DEAD[deadline=monotonic+stop_timeout<br/>L163]
    DEAD --> LOG[/cancelTask 반환 로그<br/>L164/]
    LOG --> COMP[[nav.isTaskComplete<br/>L165]]
    COMP --> Q{complete?<br/>L165}
    Q -->|False| TIME{monotonic ≥ deadline?<br/>L166}
    TIME -->|True| ERR([RuntimeError: Action termination timeout<br/>L167])
    TIME -->|False| TICK[[tick<br/>L168]]
    TICK --> COMP
    Q -->|True| RESET[self.odom=None<br/>settled=None; first_stamp=None<br/>L170-172]
    RESET --> READY[/Action 종료 확인 통과 로그<br/>L173-174/]
    READY --> NEXT([M11 odom 확인으로 진행<br/>같은 deadline 유지<br/>L175])
```

기본 10초는 cancelTask가 반환한 **뒤** 시작한다. cancelTask의 취소 응답 대기는 포함하지 않는다. 설치된 BasicNavigator.cancelTask는 응답 내용을 검사하지 않는다. Action 종료와 새 odom 확인은 하나의 deadline을 공유한다. 현재 Nav2 goal 취소이며 Dock/Undock 전용 goal handle을 취소하는 함수가 아니다.

## 12. M11 — stop: odom 정지와 두 시각 조건

```mermaid
flowchart TD
    A([M10에서 이어서 진행<br/>L175]) --> TIME{monotonic < deadline?<br/>L175}
    TIME -->|False| ERR([RuntimeError: Fresh odometry did not confirm a stop<br/>L193])
    TIME -->|True| TICK[[tick<br/>L176]]
    TICK --> READ[msg=self.odom; stopped=False<br/>L177-178]
    READ --> HAVE{msg is not None?<br/>L179}
    HAVE -->|False| SQ{stopped?<br/>L183}
    HAVE -->|True| F[[fresh msg.header.stamp<br/>L179]]
    F --> FQ{fresh True?<br/>L179}
    FQ -->|False| SQ
    FQ -->|True| V[v=twist.twist.linear; w=twist.twist.angular<br/>stopped=hypot vx,vy,vz ≤ linear_epsilon<br/>and hypot wx,wy,wz ≤ angular_epsilon<br/>L180-182]
    V --> SQ
    SQ -->|False| RESET[settled=first_stamp=None<br/>continue<br/>L184-185]
    RESET --> TIME
    SQ -->|True| STAMP[stamp=Time.from_msg header.stamp<br/>nanoseconds / 1e9<br/>L186]
    STAMP --> FIRST{settled is None?<br/>L187}
    FIRST -->|True| START[settled=monotonic; first_stamp=stamp<br/>L188]
    FIRST -->|False| HOLD{stamp-first_stamp ≥ stop_hold<br/>and monotonic-settled ≥ stop_hold?<br/>L189-190}
    START --> HOLD
    HOLD -->|False| TIME
    HOLD -->|True| OK[/정지 확인 로그<br/>L191/]
    OK --> RET([None 반환<br/>L192])
```

조건은 최신 odom, 3축 선속도 크기≤0.01 m/s, 3축 각속도 크기≤0.02 rad/s, odom stamp 진행과 monotonic 경과 **둘 다 ≥0.5초**다(기본값). 신선도·속도 조건 실패 시 유지 시작점을 지운다. 같은 stamp만 반복 확인하여서는 stamp 진행 조건을 만족하지 못한다. 샘플 수·각 연속 stamp의 단조 증가·누락 샘플 보간은 검사하지 않는다.

self.odom=None은 캐시 초기화이며, 이후 모든 메시지의 측정시각이 취소 이후라는 별도 검사는 없다. deadline은 tick 전에 검사하므로 tick 뒤 같은 반복에서 제한시간을 조금 넘겨 성공할 수 있다. 직접 cmd_vel=0은 발행하지 않는다.

## 13. M12 — escape_and_wait

```mermaid
flowchart TD
    A([escape_and_wait route,index<br/>L196]) --> SAVE[saved_index=index<br/>state=EVACUATING 1; evacuate=False<br/>L198-199]
    SAVE --> LOG[/Evacuating 저장 index 로그<br/>L200/]
    LOG --> STOP[[stop<br/>L201]]
    STOP --> POS[[position → x,y<br/>L202]]
    POS --> SELECT[target=min safe<br/>key=목표와 현재 x,y 제곱 직선거리<br/>L203-204]
    SELECT --> TARGET[/현재·안전구역 x,y 로그<br/>L205-207/]
    TARGET --> NAV[[navigate target<br/>L208]]
    NAV --> STOP2[[stop<br/>L209]]
    STOP2 --> WAIT[resume=False; state=WAITING 2<br/>대기 로그<br/>L212-214]
    WAIT --> Q{resume?<br/>L215}
    Q -->|False| TICK[[tick: 명령 2 처리 가능<br/>L216]]
    TICK --> Q
    Q -->|True| EV[state=EVACUATING 1<br/>L219]
    EV --> SPIN{route의 saved_index 값 == spin?<br/>L220}
    SPIN -->|True| BACK[[navigate route의 saved_index-1번째 Pose<br/>L221]]
    SPIN -->|False| PATROL[resume=False; state=PATROLLING 0<br/>재개 index 로그<br/>L222-224]
    BACK --> PATROL
    PATROL --> RET([None 반환: 호출자가 같은 index 재실행])
```

min 비용은 map의 m² 제곱 직선거리이며 yaw·실제 경로 길이·장애물은 사용하지 않는다. 동률이면 목록의 앞 항목을 고른다. 목표 이동 실패 시 다른 후보 재선택 없이 예외를 전파한다.

안전구역의 두 번째 stop 성공 뒤 WAITING에 들어간다. 대기는 시간제한·지속적인 odom 정지 재검사가 없다. 이동 중단점은 같은 목표를 재요청하고, spin 중단점은 직전 Pose로 복귀 후 2π 전체를 재실행한다. 복귀 navigate 뒤 별도 stop은 없다. saved_index와 active는 반환 시 초기화하지 않는다. 함수는 index·직전 항목 타입을 검증하지 않는다. 현재 경로에서는 모든 spin 앞에 Pose가 있다.

## 14. M13 — 모듈 직접 실행

```mermaid
flowchart TD
    A([모듈 진입<br/>L227]) --> Q{__name__ == __main__?<br/>L227}
    Q -->|False: import| IMPORT([정의만 로드하고 호출자가 사용])
    Q -->|True| EXIT([SystemExit 문자열 안내<br/>Run 3_1_c_follow_waypoints.py...<br/>L228])
```

직접 실행 안내와 docstring에는 이전 호출자 이름이 남아 있다. 실제 이번 대조 호출자는 genius_patrol.py다. 이 모듈에는 try/except가 없어 명시한 RuntimeError와 하위 ROS/TF/API 예외가 호출자로 전파된다. 호출자의 execute가 active=False·stop 재시도·abort·navigator 정리를 수행한다. 실기·ROS 통신 시험은 수행하지 않았다.
