# [관제] 비전 patrol_interfaces v1.0.0 통일

- 상태: v1.0 호환 반영·로컬 검증 완료 · 실제 카메라 시험 미실시
- 최초 작성 시각: 2026-09-08 21:04 KST
- 요청자: 관제 개발
- 요청 단위: 관제
- 대상 단위 및 로봇: 비전 / PC 4 CCTV·AMR Detection 입력
- 관련 TBD ID: TBD-IF-005·006·010
- 기준 문서·절: [interfaces.md](../interfaces.md), [vision.md](../vision.md)
- 결정 일자·근거: 2026-09-08 사용자 결정 — 현재 wire schema를 v1.0으로 고정하고 잔여 TBD는 차기 버전 이관
- 코드 변경 승인 근거·범위: 2026-09-08 사용자 승인 — 모든 팀을 공용 인터페이스 v1.0으로 일괄 통일

## 변경 이유

CameraState의 확정 enum·camera ID와 DetectionCandidate의 고정 wire 선언을 비전 생산부가 같은 설치 타입으로 사용하는지 확인하고, 의미 TBD와 wire 변경을 분리한다.

## 변경 전 → 변경 후

- 변경 전: CameraState 확정 내용을 일부 문서가 TBD로 표현하고 자동 호환 시험이 없었음.
- 변경 후: CameraState v1.0 계약과 2개 호환 시험, Detection wire 고정·의미 TBD 분리를 문서와 코드 주석에 반영.

## 요청·반영 범위

CameraState enum 0~4, `gate_cam`·`center_cam`, source session·sequence와 QoS를 v1.0으로 고정한다. DetectionCandidate는 v1.0 wire schema를 사용하되 미정 의미·중재는 차기 버전으로 이관한다. YOLO·ROI·카메라 설정은 변경하지 않는다.

## 검증·완료 조건

공용·비전 패키지 빌드, CameraState 호환 시험, 설치 인터페이스 manifest 일치를 완료 조건으로 한다. 실제 카메라와 PC 간 DDS 시험은 별도다.

## 2026-09-08 반영 결과

- `patrol_interfaces`, `patrol_vision` 로컬 빌드 성공.
- CameraState enum·camera ID·topic별 허용 상태·permit 매핑 시험 2개 통과.
- 설치 manifest: `5db7945d3495d954c195935e96a499535f052578d6755be622cd3a223b6816d6`.
- 전체 비전 lint는 기존 코드의 flake8 72건·pydocstyle 13건으로 실패했다. v1.0 호환 시험 실패는 아니며 이 요청서 범위 밖 코드 품질 항목으로 남긴다.
- PC 4 설치 결과 비교, 실제 카메라와 PC 간 DDS 시험은 **NOT_RUN**이다.

## 요청 작업과 영향

| 대상 단위 | 필요한 변경·검토 | 대상 경로 또는 기능 | 담당 |
|---|---|---|---|
| 비전 | PC 4에서 같은 commit·manifest 확인, CameraState 실제 발행 시험 | `patrol_vision` | 비전 |
| 관제 | CameraState 수신과 5초 timeout 판단 구현 | `src/patrol_control` | 관제 |
| System monitor | 같은 타입 수신 | 별도 요청서 | System monitor |
| AMR | DetectionCandidate 의미·중재는 차기 버전 합의 전 기존 범위 유지 | AMR Detection | AMR |

혼합 CameraState 타입은 허용하지 않는다. wire 스키마는 v1.0으로 고정하지만 Detection의 정식 토픽·의미를 이 요청서로 새로 확정하지 않는다.

## 단위별 반영 상태

| 단위·로봇 | 상태 | 반영 버전·근거 | 남은 작업 |
|---|---|---|---|
| 비전 | 로컬 호환 검증 완료 | 빌드·2개 시험·manifest PASS | PC 4 DDS·카메라 시험, 기존 lint 정리 |
| 관제 | 공용 타입만 반영 | 기준선·manifest PASS | 수신부 구현 |
| System monitor | 별도 요청서 | 25개 구독 검사 | 실제 PC 시험 |
| AMR / robot1·robot6 | wire만 고정 | 공용 manifest | Detection 의미 TBD |

## 검토·결정 이력

| 일자 | 검토자·단위 | 결정·의견 | 근거 |
|---|---|---|---|
| 2026-09-08 21:04 KST | 관제 | v1.0 일괄 통일 요청 작성 | 사용자 승인 |
| 2026-09-08 22:09 KST | 관제 | 로컬 호환 시험 완료, lint와 실장비 시험은 분리 | 실행 결과 |
