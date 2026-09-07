# parking_interfaces

AMR 순찰 시스템의 공용 ROS 2 메시지 패키지다. 메시지 필드·상수의 원본은 [공용 인터페이스 계약 v1.0](../docs/interfaces.md)이며 이 패키지에서 독자적으로 계약을 변경하지 않는다.

## PC 3 빌드

ROS 빌드 전에 Python 가상환경을 비활성화한다. 이 PC의 기본 로그인 환경에서는 가상환경의 `python3`가 rosidl 생성기를 가로챌 수 있으므로 아래처럼 시스템 Python을 명시한다.

```bash
cd /home/hun/rokey_ws
source /opt/ros/jazzy/setup.bash
env -u VIRTUAL_ENV \
  PATH=/opt/ros/jazzy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  /usr/bin/colcon build \
  --base-paths /home/hun/finalpjtdb/finalproject/parking_interfaces \
  --packages-select parking_interfaces --symlink-install \
  --cmake-clean-cache \
  --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3 -DPYTHON_EXECUTABLE=/usr/bin/python3
source /home/hun/rokey_ws/install/setup.bash
```

확인 명령:

```bash
ros2 pkg prefix parking_interfaces
ros2 interface package parking_interfaces
cd /home/hun/finalpjtdb/finalproject/sysmon
.venv/bin/python ros_adapter.py --check
```

현재 PC 3 로컬 빌드와 14개 메시지 import는 검증했다. PC 1·2·4 반영과 실제 publisher/subscriber 통합시험은 아직 수행하지 않았다.
