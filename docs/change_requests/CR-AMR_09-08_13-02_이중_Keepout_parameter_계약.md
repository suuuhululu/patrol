# [AMR] 이중 Keepout parameter 계약 확정 요청

- 상태: 검토 중
- 최초 작성 시각: 2026-09-08 13:02 KST
- 요청자: AMR 개발 작업
- 요청 단위: AMR
- 대상 단위 및 로봇: AMR robot1·robot6, 관제
- 관련 TBD ID: TBD-IF-008, TBD-CTRL-002, TBD-INT-003
- 기준 문서·절: `interfaces.md` 7절, `amr.md` 4절, `control_server.md` 7절, `integration.md` IT-08·IT-09
- 결정 일자·근거: 2026-09-08 사용자가 빨간 Keepout 상시 적용, 노란 중앙통로 Keepout은 차량 움직임에 따라 관제가 적용한다고 확인했다.
- 코드 변경 승인 근거·범위: 2026-09-08 사용자가 다음 기능 구현 진행을 승인. AMR 로컬 Nav2 overlay·launch·시험·문서가 범위이며 관제 코드는 미승인.

## 변경 이유

기존 계약은 costmap마다 `keepout_filter.enabled` 하나만 규정했다. 그러나 빨간 기본 영역은 항상 차단하고 노란 중앙통로만 조건부로 켜려면 서로 다른 mask와 `enabled` parameter가 필요하다. 한 필터를 껐다 켜면 빨간 기본 영역까지 함께 해제되어 사용자 확인 동작을 만족하지 못한다.

AMR은 두 mask server와 두 costmap filter info server, global/local costmap의 두 KeepoutFilter를 구현했다. 관제가 어느 parameter만 변경해야 하는지 공유 계약을 확정해야 한다.

## 변경 전 → 변경 후

| 항목 | 변경 전 | 변경 후(AMR 제안) |
|---|---|---|
| 기본 빨간 영역 | 단일 `keepout_filter.enabled`에 함께 포함될 수 있음 | `base_keepout_filter.enabled=true`, 관제 변경 금지 |
| 노란 중앙통로 | 별도 parameter 미정 | `center_corridor_keepout_filter.enabled`, 초기 `false` |
| 적용 대상 | robot1·robot6 global/local costmap | 동일 네 노드의 중앙통로 parameter를 논리적 한 transaction으로 변경 |
| 입력 판단 | `patrol_allowed`는 주행 명령이 아님 | 관제가 `/vision/cctv/patrol_allowed=false` 수신 시 중앙통로 `true`, `true` 수신 시 `false` 요청 |
| 검증 | 이름·read-back 미정 | Q-07에 따라 snapshot→global/local 적용→두 값 read-back→실패 시 snapshot rollback |

정확한 제어 대상은 다음과 같다.

```text
/{robot}/global_costmap/global_costmap center_corridor_keepout_filter.enabled
/{robot}/local_costmap/local_costmap   center_corridor_keepout_filter.enabled
```

`{robot}`은 `robot1` 또는 `robot6`이다. 아래 두 parameter는 AMR 시작 시 항상 `true`이며 정상 관제 transaction의 변경 대상이 아니다.

```text
/{robot}/global_costmap/global_costmap base_keepout_filter.enabled
/{robot}/local_costmap/local_costmap   base_keepout_filter.enabled
```

## 요청 작업

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| AMR | 이중 mask/filter 서버, Nav2 overlay, namespace, 초기값과 실기 검증 | `patrol_amr` | AMR |
| 관제 | 중앙통로 두 parameter의 snapshot·Q-07 적용·read-back·rollback 구현 | Keepout transaction | 관제 |
| System monitor | 해당 없음. 정식 상태 토픽은 계속 TBD-IF-008이며 UI가 parameter를 직접 판단하지 않음 | - | - |
| 비전 | 변경 불필요. 기존 `/vision/cctv/patrol_allowed` 발행 유지 | - | - |

## 영향과 적용 순서

1. AMR이 robot1·robot6에 이중 filter 구성을 배포하고 두 filter server가 ACTIVE인지 확인한다.
2. 관제가 기존 단일 이름 대신 중앙통로 parameter 두 개만 transaction으로 변경한다.
3. `false→true→false` 입력에서 global/local read-back과 실제 costmap 변화를 확인한다.
4. global/local 한쪽 실패와 rollback 실패를 IT-08로 검증한다.

혼합 버전에서는 관제가 존재하지 않는 parameter를 변경하거나 빨간 영역을 함께 해제할 수 있으므로 실주행을 금지한다. 실패 시 일부 성공 값을 그대로 commit하지 않고 snapshot 복구 또는 UNKNOWN·안전 정지로 처리한다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| AMR / robot1 | 부분 반영 | 로컬 Nav2 overlay·launch | 실제 Nav2 parameter/read-back·주행 시험 |
| AMR / robot6 | 부분 반영 | 동일 robot_id 기반 구성 | robot6 실기 시험 |
| 관제 | 미반영 | 회신 미수신 | transaction·Q-07·rollback 구현 |
| System monitor | 변경 불필요 예정 | parameter API 소비자가 아님 | 영향 없음 확인 |
| 비전 | 변경 불필요 예정 | 기존 Bool 계약 유지 | 영향 없음 확인 |

## 완료 조건과 검증

- 관련 integration.md 시험 ID: IT-08, IT-09
- 추가 시험·기대 결과: 두 로봇에서 빨간 mask 상시 차단, 중앙통로 초기 OFF, `patrol_allowed=false` 후 중앙통로 ON, `true` 후 OFF, global/local 동일 read-back
- 실제 실행 결과와 증거: AMR 로컬 단위시험 `Ran 255 tests`/`OK`, 두 패키지 빌드 성공, 설치 launch `--show-args`에서 robot1·robot6 선택과 기본 파일 경로 확인.
- 미실행 또는 BLOCKED 항목: 관제 반영, robot1·robot6 TF·costmap·경로·실주행, 실패 주입과 rollback

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 | 사용자·AMR | 빨간 영역은 기본 Keepout, 노란 중앙통로는 차량 움직임에 따른 관제 제어 대상으로 구현 진행 | 사용자 제공 지도·좌표·설명 |
