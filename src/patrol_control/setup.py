"""Setuptools configuration for the patrol_control ROS 2 package."""

from setuptools import find_packages, setup


package_name = 'patrol_control'


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        (
            'share/ament_index/resource_index/packages',
            ['resource/' + package_name],
        ),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    extras_require={'test': ['pytest']},
    zip_safe=True,
    maintainer='Control Team',
    maintainer_email='control@example.com',
    description='Control-side command coordination for the patrol system',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'patrol_control_node = '
            'patrol_control.command_control_node:main',
        ],
    },
)
