"""ROS adapter가 공통으로 쓰는 예외."""


class RosAdapterUnavailable(RuntimeError):
    """ROS 런타임이나 공용 메시지 패키지가 준비되지 않았을 때 사용한다."""


class RosMessageMappingError(ValueError):
    """수신한 ROS 메시지를 현재 sysmon 내부 입력으로 안전하게 바꿀 수 없을 때 사용한다."""
