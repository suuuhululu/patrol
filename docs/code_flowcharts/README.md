# 코드 기준 플로우차트 산출물

두 Python 파일을 직접 읽어 작성한 전체 실행 흐름과 함수별 상세 흐름이다. 기존 설계·설명 Markdown은 코드 동작의 근거로 사용하지 않았다. `.md`는 이번에 작성한 도표의 편집 원본이다.

- [전체·상세 이미지 보기](exports/index.html)
- [편집 가능한 draw.io 파일](exports/patrol_code_flowcharts.drawio)
- [genius_patrol.py: 전체 실행 + 상세 5개](genius_patrol.md)
- [move_to_safetyzone.py: 함수별 상세](move_to_safetyzone.md)
- [현재 순찰 코드가 호출하는 Recheck 상세](recheck_event_dependency.md)
- [PNG·draw.io에 포함한 좌표·입출력값 설명](data_values.md)
- [코드 경로·SHA-256·확인 시각](source_manifest.json)

전체 흐름은 draw.io의 첫 페이지다. 이후 페이지는 순찰·대피·Recheck 상세이며, 각 페이지의 PNG/SVG는 이미지 보기에서 열 수 있다. draw.io에는 도형·문구·연결선이 개별 객체로 저장되어 편집할 수 있다.

`G:L…`, `M:L…`, `R:L…`는 각각 genius_patrol.py, move_to_safetyzone.py, recheck_event.py의 근거 줄 번호다. `genius_patrol.py`·`move_to_safetyzone.py`는 2026-09-11 07:26:04 KST, 작성 중 갱신된 `recheck_event.py`는 07:33:59 KST 소스로 대조했다. 로컬 의존 라이브러리와 메시지 정의의 해시도 기록했다.

코드는 변경하지 않았다. 검증은 코드와 도형의 정적 대조 및 산출물의 파싱·렌더링이며, ROS 통신·카메라·도킹·주행·물리적 정지 시험은 수행하지 않았다. 코드를 수정한 경우 줄 번호·흐름·전달값과 모든 내보내기 파일을 함께 갱신해야 한다.
