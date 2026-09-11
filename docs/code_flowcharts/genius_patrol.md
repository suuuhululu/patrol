# genius_patrol.py — 코드 기준 전체·상세 흐름

**구현 대조 완료: 2026-09-11 07:39:45 KST.** [genius_patrol.py](../../src/patrol_amr_safety/patrol_amr_safety/genius_patrol.py) 206행, SHA-256 `12344529c2f84c9817348b721127efd435d3a014eaf867a1b0cd4fe3b181383a`. 기존 Markdown은 동작 근거로 사용하지 않았다. Python과 설치된 ROS 메시지 정의를 직접 대조했다. 현재 소스에는 Recheck 연결이 없다.

G:L번호는 이 파일, M:L번호는 [move_to_safetyzone.py](../../src/patrol_amr_safety/patrol_amr_safety/move_to_safetyzone.py)의 줄 번호다. T는 TurtleBot4Navigator, N은 BasicNavigator다. 파일 경로·해시는 [source_manifest.json](source_manifest.json), 좌표·설정 그림은 [data_values.md](data_values.md), 대피 상세는 [move_to_safetyzone.md](move_to_safetyzone.md)에 있다.

기호는 [ISO 5807:1985](https://www.iso.org/standard/11955.html)의 의미에 맞춘다. 둥근 양끝은 진입·반환, 직사각형은 처리, 마름모는 판단, 평행사변형은 입출력, 양쪽 이중선은 상세가 따로 있는 호출·구간이다. 실행 그림의 화살표는 제어 흐름이며 조건·예외 분기를 구별한다. 각 도형의 줄 번호는 해당 동작의 근거다.

## 0. 전체 실행 흐름

전체 그림은 main과 execute의 수명, 순찰·대피·재개를 연결한다. P1~P4와 M 상세에서 호출 상자를 확장한다. 실패 처리의 세부 생성·정리 예외는 P2를 따른다.

```mermaid
flowchart TD
    A([프로그램 시작<br/>G:L205-206]) --> SETUP[[인자·ROS·ActionServer 준비 / P1<br/>G:L173-188]]
    SETUP --> WAIT[[rclpy.spin: patrol_action 요청 대기<br/>G:L190-194]]
    WAIT -->|goal 실행 콜백| GOAL[/NavigateToPose goal 수신<br/>pose·behavior_tree 미사용<br/>G:L144-145,182-186/]
    GOAL --> EXEC[[execute / P2<br/>navigator와 Evacuation 생성<br/>G:L146-150]]
    EXEC -->|정상 생성| PRE[[도킹 확인·필요시 dock → undock<br/>초기 pose 0,0,SOUTH → Nav2 준비 / P3a<br/>G:L69-89]]
    PRE -->|준비 성공| ROUTE[[17단계 순찰 루프 / P3b<br/>이동 9회·spin 8회<br/>G:L92-132]]
    ROUTE -->|evacuate=True| ESC[[stop → 최근접 안전구역 → stop<br/>명령 2 대기 → 필요시 spin 위치 복귀<br/>G:L126-127 / M:L196-224]]
    ESC -->|정상 반환: 같은 index 재개| ROUTE
    ROUTE -->|index=17| DOCK[[active=False → 최종 dock·상태 확인<br/>G:L133-139]]
    DOCK -->|is_docked=True| SUCCESS[/goal.succeed·기본 Result<br/>G:L141,151-155/]
    EXEC -->|Exception| FAILURE[[P2 실패 정리<br/>Evacuation이 있으면 active=False·stop 시도<br/>G:L156-165]]
    PRE -->|False 또는 Exception| FAILURE
    ROUTE -->|False 또는 Exception| FAILURE
    ESC -->|Exception| FAILURE
    DOCK -->|False 또는 Exception| FAILURE
    FAILURE --> ABORT[/goal.abort·기본 Result<br/>G:L166-167/]
    SUCCESS --> CLEAN[[finally: navigator가 있으면 destroy_node<br/>G:L168-170]]
    ABORT --> CLEAN
    CLEAN -->|콜백 반환| WAIT
    WAIT -->|spin 반환·KeyboardInterrupt·예외| CLOSE[[서버·executor·노드 정리·필요시 shutdown<br/>G:L195-202]]
    CLOSE --> END([main 반환 또는 예외 전파<br/>G:L195-206])
```

콜백 `on_command()`는 플래그만 설정한다. `tick()`이나 navigator 내부 spin으로 콜백을 처리한 뒤 순찰 루프가 `evacuate`를 읽어 대피를 호출한다. 도표의 대피 재개 선은 직접 콜백 호출을 의미하지 않는다.

## 1. 실제 전달값

| 경계 | 값·의미 | 근거 |
|---|---|---|
| arguments → main | `settings`: argparse.Namespace; namespace 기본 robot1, 선택 robot1/robot6 | G:L174; M:L44-70 |
| main → execute | ServerGoalHandle `goal`, 실제 namespace에서 `/`를 제거한 `ns`, `settings` | G:L181,186 |
| 외부 Action → 서버 | 상대 `patrol_action`, nav2_msgs/action/NavigateToPose. 요청의 pose·behavior_tree를 읽지 않음 | G:L144-145,182-186 |
| execute → 순찰·대피 | 동일 TurtleBot4Navigator 인스턴스 공유 | G:L149-151; M:L75 |
| 순찰/대피 → Nav2 | `navigate_to_pose`, NavigateToPose.Goal.pose=PoseStamped, behavior_tree='' | G:L122; M:L154; N:L185-219 |
| 회전 → Nav2 | `spin`, Spin.Goal.target_yaw=2π rad, time_allowance.sec=20, nanosec=0 | G:L39,47; N:L269-289 |
| Nav2 → 호출자 | goToPose/spin의 True는 목표 수락. 별도로 isTaskComplete와 getResult로 완료·성공 판정 | G:L47-56,122-125 |
| 순찰 단계 반환 | `succeeded: bool`; 대피 감지·실패·취소 등은 False. 이후 evacuate를 먼저 검사 | G:L120-131; M:L138-147 |
| 순찰 → 대피 | `route=goal_pose`, `index=현재 0기반 단계`. 정상 복귀 후 index 유지 | G:L127-128 |
| 서버 → 외부 Action | 성공 succeed, 실패 abort. 양쪽 모두 NavigateToPose.Result() 기본 error_code=0, error_msg='' | G:L152-167; 설치된 NavigateToPose.action |

방향 상수는 NORTH=0°, WEST=90°, SOUTH=180°, EAST=270°다(T:L40-48). getPoseStamped는 map 프레임, 생성 당시 ROS stamp, 위치 `(x,y,0)`, quaternion `(0,0,sin(yaw×π/360),cos(yaw×π/360))`를 만든다(T:L74-94). 초기 pose는 `(0,0,SOUTH=180°)`다(G:L85). 순찰 Pose stamp는 goToPose 때 갱신하지 않으며, 대피 navigate는 전달 객체의 stamp를 갱신한다(M:L150). 초기 pose 발행도 생성 당시 stamp를 그대로 복사한다(N:L813-821).

TaskResult는 UNKNOWN=0, SUCCEEDED=1, CANCELED=2, FAILED=3. ROS action 상태 4/5/6을 각각 SUCCEEDED/CANCELED/FAILED로 바꾼다(N:L484-493). 결과 메시지의 error_code를 직접 검사하지 않는다. dock/undock 반환값은 None이며 순찰은 별도 DockStatus.is_docked 구독값을 검사한다(T:L159-264).

command/odom 기본 경로는 일반 인자의 namespace로 `/{namespace}/safety_command`, `/{namespace}/odom`을 만든다(M:L56-58). 실제 서버 namespace는 ROS `__ns` remap으로 달라질 수 있다. TF 토픽의 `/tf:=tf`, `/tf_static:=tf_static` remap과 프레임 문자열 `map`, `base_link`는 별개다(G:L176-181; M:L129).

외부 feedback 발행·외부 cancel callback·직접 cmd_vel 발행은 두 파일에 없다. 설치된 rclpy 기본 goal callback은 ACCEPT, cancel callback은 REJECT다. 내부 Nav2 취소와 외부 patrol_action 취소는 별개다.

## 2. P1 — main

```mermaid
flowchart TD
    A([main 진입<br/>G:L173]) --> ARGS[[arguments → settings<br/>G:L174 / M:L44-70]]
    ARGS -->|정상| INIT[[rclpy.init<br/>sys.argv + tf·tf_static remap<br/>G:L176-179]]
    ARGS -->|인자 오류| AX([argparse SystemExit<br/>ROS 초기화 전 종료<br/>M:L55,64,66,69])
    INIT --> NODE[[create_node follow_waypoints_server<br/>namespace=settings.namespace<br/>G:L180]]
    NODE --> NS[ns=node.get_namespace에서 앞뒤 / 제거<br/>G:L181]
    NS --> SERVER[ActionServer NavigateToPose, patrol_action<br/>callback: execute goal,ns,settings<br/>G:L182-187]
    SERVER --> EX[SingleThreadedExecutor 생성<br/>G:L188]
    EX --> SPIN[[try: 대기 로그 → rclpy.spin<br/>G:L190-194]]
    SPIN -->|정상 반환| FIN[finally 진입<br/>G:L197]
    SPIN -->|KeyboardInterrupt: pass| FIN
    SPIN -->|그 외 예외: 정리 후 전파| FIN
    FIN --> DEST[[server.destroy → executor.shutdown<br/>→ node.destroy_node<br/>G:L198-200]]
    DEST --> OK{rclpy.ok?<br/>G:L201}
    OK -->|True| SHUT[[rclpy.shutdown<br/>G:L202]]
    OK -->|False| RET([main 반환 또는 예외 전파<br/>G:L190-202])
    SHUT --> RET
```

G:L174-188은 try 바깥이므로 생성 실패가 해당 finally를 거치지는 않는다. 정리 함수가 예외를 내면 뒤 정리가 보장되지 않는다. Nav2/localization 프로세스를 자동 기동하는 코드는 없다.

## 3. P2 — execute

```mermaid
flowchart TD
    A([execute goal,ns,settings<br/>G:L144]) --> INIT[navigator=None; evacuation=None<br/>G:L146-147]
    INIT --> NAV[[try: TurtleBot4Navigator namespace=ns<br/>G:L148-149]]
    NAV -->|정상| EV[[Evacuation navigator,settings<br/>G:L150]]
    EV -->|정상| RUN[[run_patrol navigator,evacuation<br/>P3a·P3b / G:L151]]
    RUN -->|정상 반환| Q{반환 True?<br/>G:L151}
    Q -->|True| SUC[/goal.succeed<br/>G:L152/]
    Q -->|False| RAISE[RuntimeError: Patrol failed<br/>G:L154]
    NAV -->|Exception| ERR[except: navigator가 있으면 오류 로그<br/>G:L156-158]
    EV -->|Exception| ERR
    RUN -->|Exception| ERR
    SUC -->|Exception| ERR
    RAISE --> ERR
    ERR --> EQ{evacuation is not None?<br/>G:L160}
    EQ -->|True| OFF[evacuation.active=False<br/>G:L161]
    OFF --> STOP[[evacuation.stop<br/>G:L162-163 / M:L161-193]]
    STOP -->|정상| AB[/goal.abort<br/>G:L166/]
    STOP -->|Exception| LOG[/STOP NOT CONFIRMED 로그<br/>G:L164-165/]
    LOG --> AB
    EQ -->|False| AB
    SUC -->|정상| RES[기본 NavigateToPose.Result 반환 준비<br/>G:L155]
    AB --> ARES[기본 NavigateToPose.Result 반환 준비<br/>G:L167]
    RES --> FIN{finally: navigator is not None?<br/>G:L168-169}
    ARES --> FIN
    FIN -->|True| DEST[[navigator.destroy_node<br/>G:L170]]
    FIN -->|False| RET([Result 반환<br/>G:L155 또는 L167])
    DEST --> RET
```

BaseException(KeyboardInterrupt 등)은 except Exception이 잡지 않는다. finally는 try 탈출 시 실행된다. abort·로그·Result 생성·destroy 자체의 예외까지 별도로 복구하지 않는다. Evacuation 생성 중 실패하면 대입 전이므로 stop을 건너뛴다. stop까지 실패해도 로그 후 abort하므로 ABORTED를 실제 정지 확인과 동치로 볼 수 없다.

## 4. P3a — run_patrol 준비와 최종 도킹

```mermaid
flowchart TD
    A([run_patrol 진입<br/>G:L69]) --> STATUS[[getDockedStatus<br/>G:L71]]
    STATUS --> Q{도킹 상태 True?<br/>G:L71}
    Q -->|False| DOCK[[dock 후 getDockedStatus<br/>G:L72-74]]
    DOCK --> DQ{도킹 상태 True?<br/>G:L74}
    DQ -->|False| DF([오류 로그 후 False 반환<br/>G:L75-76])
    DQ -->|True| UNDOCK[[undock 후 getDockedStatus<br/>G:L79-80]]
    Q -->|True| UNDOCK
    UNDOCK --> UQ{도킹 상태 True?<br/>G:L80}
    UQ -->|True| UF([오류 로그 후 False 반환<br/>G:L81-82])
    UQ -->|False| POSE[[getPoseStamped 0,0,SOUTH<br/>setInitialPose initial_pose<br/>G:L85-86]]
    POSE --> READY[[waitUntilNav2Active<br/>AMCL active → amcl_pose → bt_navigator active<br/>G:L89 / N:L495-504]]
    READY --> ROUTE[17개 goal_pose 생성<br/>active=True; index=0<br/>G:L92-114]
    ROUTE --> LOOP[[P3b 순찰 루프<br/>G:L115-132]]
    LOOP -->|실패| LF([False 반환<br/>G:L124 또는 L131])
    LOOP -->|index=17| OFF[active=False<br/>G:L133]
    OFF --> FINAL[[dock 후 getDockedStatus<br/>G:L136-137]]
    FINAL --> FQ{도킹 상태 True?<br/>G:L137}
    FQ -->|False| FF([오류 로그 후 False 반환<br/>G:L138-139])
    FQ -->|True| OK([True 반환<br/>G:L141])
```

준비·최종 도킹 동안 active=False다. 모든 하위 예외는 execute로 전파된다. getDockedStatus는 최초 상태 수신까지 기다리며 이 파일은 준비 전체에 별도 timeout을 씌우지 않는다.

## 5. P3b — 순찰 루프·대피 후 동일 단계 재개

```mermaid
flowchart TD
    A([route·active·index 준비 후 진입<br/>G:L113-115]) --> Q{index가 len goal_pose=17 미만?<br/>G:L115}
    Q -->|False| DONE([P3a의 active=False로 진행<br/>G:L133])
    Q -->|True| TICK[[evacuation.tick<br/>G:L116 / M:L118-121]]
    TICK --> EV{evacuation.evacuate?<br/>G:L117}
    EV -->|False| STEP[step=goal_pose의 index번째 값<br/>G:L118]
    STEP --> SQ{step == spin?<br/>G:L119}
    SQ -->|True| SPIN[[startSpin navigator,evacuation<br/>→ succeeded / P4<br/>G:L120]]
    SQ -->|False| NAV[[navigator.goToPose step<br/>G:L122]]
    NAV --> AQ{목표 수락?<br/>G:L122}
    AQ -->|False| REJ([오류 로그 후 False 반환<br/>G:L123-124])
    AQ -->|True| WAIT[[evacuation.wait_for_task → succeeded<br/>G:L125 / M:L138-147]]
    SPIN --> EQ{evacuation.evacuate?<br/>G:L126}
    WAIT --> EQ
    EV -->|True: 단계 실행 건너뜀| EQ
    EQ -->|True| ESC[[escape_and_wait goal_pose,index<br/>G:L127 / M:L196-224]]
    ESC -->|정상 반환: continue, index 유지| Q
    EQ -->|False| SUCCESS{succeeded?<br/>G:L129}
    SUCCESS -->|False| FAIL([이동·spin 실패 로그 후 False 반환<br/>G:L130-131])
    SUCCESS -->|True| INC[index += 1<br/>G:L132]
    INC --> Q
```

대피가 True라 단계 실행을 건너뛰면 succeeded를 새로 대입하지 않는다. 하지만 escape 뒤 continue하므로 그 값을 읽지 않는다. 대피가 완료와 같은 확인 시점에 관측되면 대피 분기가 우선한다. 이동 goal 수락 실패는 즉시 False 반환하여 이후 대피 검사를 거치지 않는다. spin 수락 실패는 P4의 False 반환 후 대피 검사를 거친다.

## 6. P4 — startSpin

```mermaid
flowchart TD
    A([startSpin<br/>angle=2π rad; time_allowance=20 s<br/>evacuation=None 기본값<br/>G:L39]) --> SPIN[[navigator.spin spin_dist=angle<br/>time_allowance=time_allowance<br/>G:L47]]
    SPIN --> Q{목표 수락?<br/>G:L47}
    Q -->|False| LOG[/Spin request was rejected 로그<br/>G:L48/]
    LOG --> NO([False 반환<br/>G:L49])
    Q -->|True| EQ{evacuation is not None?<br/>G:L51}
    EQ -->|True: 현재 순찰 경로| WAIT[[evacuation.wait_for_task<br/>G:L52 / M:L138-147]]
    WAIT --> RET([bool 그대로 반환<br/>G:L52])
    EQ -->|False| COMP[[navigator.isTaskComplete<br/>G:L53]]
    COMP --> CQ{complete?<br/>G:L53}
    CQ -->|False: pass| COMP
    CQ -->|True| RES[[navigator.getResult<br/>G:L56]]
    RES --> RQ{result 값?<br/>G:L57-64}
    RQ -->|SUCCEEDED| OKLOG[/Spin succeeded 로그<br/>G:L58/]
    OKLOG --> YES([True 반환<br/>G:L59])
    RQ -->|CANCELED| CL[/Spin was canceled 로그<br/>G:L61/]
    RQ -->|FAILED| FL[/Spin failed 로그<br/>G:L63/]
    RQ -->|그 외| IL[/invalid return status 로그<br/>G:L65/]
    CL --> F([False 반환<br/>G:L66])
    FL --> F
    IL --> F
```

현재 순찰은 evacuation을 넘기므로 G:L56-66 결과별 로그 구간으로 진행하지 않는다. 20초는 Spin Goal 시간 허용값이며 Python 함수 전체의 벽시계 timeout이 아니다. 코드를 실행하지 않고 도형·호출값·소스 줄을 대조했다. 실기 시험은 수행하지 않았다.
