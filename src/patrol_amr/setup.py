from glob import glob
import os

from setuptools import find_packages, setup

package_name = "patrol_amr"

setup(
    name=package_name,
    version="0.4.0",
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
        (
            os.path.join("share", package_name, "config"),
            glob("config/*.yaml") + glob("config/*.pgm"),
        ),
        (
            os.path.join("share", package_name, "docs"),
            glob("docs/*.md"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Jonny",
    maintainer_email="jonnykoh2008@gmail.com",
    description="AMR mission, navigation, safety, and status integration",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "battery_monitor = patrol_amr.battery_monitor:main",
            "local_safety_supervisor = "
            "patrol_amr.local_safety_supervisor:main",
            "status_reporter = patrol_amr.status_reporter:main",
            "mission_supervisor = patrol_amr.mission_supervisor:main",
        ],
    },
)
