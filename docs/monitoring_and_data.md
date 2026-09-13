# 시스템 모니터 기능 설계

> 기준일: 2026-09-13 · 공용 계약: `patrol_interfaces 2.0.0`
>
> 담당: 시스템 모니터 팀 · 통합 실행 위치: PC 3

시스템 모니터는 관제와 별도 개발 단위다. 수신 결과와 이력을 저장·표시하지만
순찰·주행 권한·안전 판단을 생성하지 않는다.

## 1. 공용 인터페이스 범위

시스템 모니터가 서버로 제공하는 최종 공용 인터페이스는 다음 하나다.

| 이름 | 타입 | 역할 |
|---|---|---|
| `/system_monitor/report_detection` | `patrol_interfaces/srv/ReportDetection` | 확정 사건과 증거 사진 저장 |

Patrol Action의 상태와 결과를 화면에 표시할 수 있지만, 이를 위해 새로운 공용
상태 메시지를 추가하지 않는다. 구체적인 Action 상태 소비 방법은 시스템 모니터
구현 범위에서 정한다.

## 2. ReportDetection 처리

Request 검증:

- `robot_id`: `robot1` 또는 `robot6`
- `event_id`: 소문자 UUID v4
- `detected_at`: 서버 시각보다 5분 이상 미래가 아님
- `position`: `map` 좌표계, `z=0`
- `image`: JPEG 또는 PNG, 최대 1 MiB
- `event_type`: FIRE=1, LEAK=2, OBSTACLE=3

Response:

- `STORED`: 처음 저장 완료
- `DUPLICATE`: 같은 사건 또는 억제 기간 안의 동일 종류 사건
- `REJECTED`: 필드나 내용이 계약과 다름

같은 `event_id`와 같은 내용의 재시도는 중복 저장하지 않는다. 같은 `event_id`에
다른 내용이 들어오면 거절한다. 저장 성공 전에는 `STORED`를 반환하지 않는다.

## 3. 책임 경계

- bbox 정렬, 감지 판단과 사건 확정은 AMR 감지 측 책임이다.
- 관제는 Patrol Feedback의 감지 상태를 사용해 운영 판단을 수행한다.
- 시스템 모니터는 `ReportDetection` 요청을 검증·저장하고 결과를 반환한다.
- 시스템 모니터는 Patrol Goal, PatrolCommand, DriveToken, EStop을 발행하지 않는다.
- Dashboard는 읽기 전용이다.

`DetectionEvidence`는 공용 타입으로 존재하지만 전용 토픽은 확정하지 않았다.
기본 감지 저장 경로에서는 `ReportDetection.image`를 사용한다.

## 4. 논리 데이터 모델

아래는 내부 저장 모델의 최소 요구사항이며 공용 ROS 계약이 아니다.

| 항목 | 필수 내용 |
|---|---|
| detection_events | robot_id, event_id, detected_at, position, event_type |
| detection_images | event_id, 원본 이미지, 저장 형식·크기 |
| ingestion_results | event_id, status, detail, 서버 수신 시각 |
| patrol_runs | Action 식별자와 최종 outcome·reason |

DB 엔진, 컬럼 타입, 인덱스, 보존 기간과 백업 정책은 시스템 모니터 팀 내부 설계로
관리한다. 내부 DB 구조를 다른 개발 단위의 직접 접근 계약으로 사용하지 않는다.

## 5. Dashboard

기본 화면은 다음 정보를 읽기 전용으로 표시한다.

- robot1·robot6 Patrol 진행 상태와 최근 pose
- waypoint 도착 상태
- permit과 관제가 제공한 운영 상태
- Patrol Result
- 감지 사건, 위치, 종류와 증거 사진
- 저장 성공·중복·거절 상태

화면이 자체 timeout이나 안전 상태를 계산해 관제 판단을 대체하지 않는다.

## 6. 검증

- 정상 사건 저장과 이미지 복원
- 같은 요청 재전송의 `DUPLICATE`
- 같은 event_id의 다른 내용 `REJECTED`
- 잘못된 robot, event type, 미래 시각, 이미지 형식·크기 거절
- DB 실패 시 성공 응답 금지
- Dashboard에서 제어 인터페이스 발행 불가
- 실제 AMR 감지 측과 Service 종단시험

상세 통합 순서는 [integration.md](integration.md)의 IT-04를 따른다.

## TBD

| ID | 미정 사항 | 영향 단위 |
|---|---|---|
| TBD-MON-001 | DB 엔진·인덱스·보존·백업 | 시스템 모니터 |
| TBD-MON-002 | 장기 저장 실패 시 재시도와 운영 알림 | 시스템 모니터·관제 |
| TBD-MON-003 | Dashboard 상세 화면과 조회 범위 | 시스템 모니터 |
