from setuptools import setup

package_name = "patrol_amr_safety"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages",
         ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch",
         ["launch/amr_safety_status.launch.py"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="조정묵",
    maintainer_email="kj270477@gmail.com",
    description="AMR local safety, status and command-identity nodes",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "genius_patrol = patrol_amr_safety.genius_patrol:main",
            "battery_monitor = patrol_amr_safety.battery_monitor:main",
            "command_gateway = patrol_amr_safety.command_gateway:main",
            "local_safety_supervisor = "
            "patrol_amr_safety.local_safety_supervisor:main",
            "status_reporter = patrol_amr_safety.status_reporter:main",
            "3_1_c_follow_waypoints = patrol_amr_safety.3_1_c_follow_waypoints:main"
        ],
    },
)
