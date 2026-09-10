# Detection 공용 인터페이스 v1.1 기준선

- 결정 일자: 2026-09-09
- 패키지: `patrol_interfaces 1.1.0`
- 등록 메시지: 16개
- manifest SHA-256: `ed46754623f43db928cb331a61ed4b918989e1bcb979e6cdc5348741837aa617`
- 상태: 공용 메시지 소스 반영·로컬 빌드·설치 타입 검증 PASS, 팀별 소비 코드 반영 및 통합시험 대기
- 관련 요청: [Detection v1.1 팀별 반영 요청](../change_requests/CR-관제_09-09_12-02_Detection_v1.1_팀별_반영.md)

## 결정

1. `DetectionCandidate`와 `DetectionEvent`의 event_type은 UNKNOWN=0, FIRE=1, LEAK=2, OBSTACLE=3으로 통일한다.
2. `DetectionEvent.risk_level`, 모든 `RISK_*` 상수, LIGHTING·FACILITY_DAMAGE는 제거한다. 네 팀은 event_type으로만 처리한다.
3. `DetectionResult`를 추가한다. 필드는 `header`, `robot_id`, `candidate_id`, `event_id`, `result`, `detail`이며 결과는 CONFIRMED=0, VERIFY_FAILED=1, INTERNAL_ERROR=2다.
4. CONFIRMED는 Event와 Evidence를 비전 로컬 재전송 큐에 등록한 상태다. 시스템 모니터 저장 완료를 의미하지 않으며 `IngestionAck`은 AMR 재개의 선행 조건이 아니다.
5. Candidate·Alignment·Result·Event·Evidence는 `/{robot}/detection/*` namespace로 통일한다. `IngestionAck`은 여러 수집 엔티티가 함께 쓰므로 `/{robot}/ingestion_ack`을 사용한다.
6. 비전팀이 detecting node를 개발하고 AMR PC에서 실행한다. AMR이 yaw 정렬과 정지 확인을 수행하며 관제는 AlignmentStatus·DetectionResult에 개입하지 않는다. 시스템 모니터가 IngestionAck을 발행한다.
7. 모든 로봇별 노드는 launch namespace와 상대 토픽을 사용하고 robot1·robot6 절대 경로를 코드에 하드코딩하지 않는다.

## v1.0과의 호환성

이 기준선은 `DetectionCandidate` 상수 값 변경, `DetectionEvent` 필드·상수 제거, `DetectionResult` 추가를 포함하므로 v1.0 wire schema와 호환되지 않는다. 일부 팀만 v1.1로 올린 혼합 구성을 허용하지 않는다. AMR·관제·시스템 모니터·비전은 같은 Git commit을 빌드하고 아래 검증 결과가 일치한 뒤 통합시험을 시작한다.

~~~text
package_version: 1.1.0
message_count: 16
message_manifest_sha256: ed46754623f43db928cb331a61ed4b918989e1bcb979e6cdc5348741837aa617
~~~

검증 명령은 `python3 scripts/verify_interface_v1.py`이며 설치 결과는 ROS 환경과 workspace overlay를 source한 뒤 `--installed`로 확인한다. 스크립트 파일명은 기존 자동화 호환을 위해 유지한다.

## 미완료

- AMR·비전·시스템 모니터·관제 소비 코드 반영
- 비전의 EvidenceChunk outbox·재전송과 System monitor ACK 종단시험
- 후보 중재·정렬 임계값, 증적 장기 재시도 횟수·간격·보존 한도
- IT-14·IT-15 실제 장비 통합시험
