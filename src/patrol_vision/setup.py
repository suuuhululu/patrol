from setuptools import find_packages, setup

package_name = "patrol_vision"

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
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="hv-06",
    maintainer_email="acbal0012@gmail.com",
    description="CCTV vision nodes for the patrol project",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "gate_cam = patrol_vision.gate_cam:main",
            "center_cam = patrol_vision.center_cam:main",
            "cam_master = patrol_vision.cam_master:main",
        ],
    },
)
