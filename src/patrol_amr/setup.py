from glob import glob
import os

from setuptools import find_packages, setup

package_name = "patrol_amr"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        (
            "share/" + package_name,
            ["package.xml"],
        ),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Jonny",
    maintainer_email="jonnykoh2008@gmail.com",
    description="AMR safety and status nodes for the patrol project",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "battery_monitor = patrol_amr.battery_monitor:main",
            "local_safety_supervisor = "
            "patrol_amr.local_safety_supervisor:main",
            "status_reporter = patrol_amr.status_reporter:main",
        ],
    },
)
