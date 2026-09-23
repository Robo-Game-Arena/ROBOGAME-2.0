import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def launch_directory():
    return os.path.join(
        get_package_share_directory("arena_perception"),
        "launch"
    )


def include_launch_file(name, launch_arguments):
    return IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(launch_directory(), name)
        ),
        launch_arguments=launch_arguments.items()
    )


def create_controllers(context, *args, **kwargs):
    robot_count = int(
        LaunchConfiguration("robot_count").perform(context)
    )

    controllers = []

    for robot_id in range(1, robot_count + 1):
        controllers.append(include_launch_file("controller.launch.py", {
            "robot_id": str(robot_id),
            "joy_device_id": str(robot_id - 1),
        }))

    return controllers


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            "robot_count",
            default_value="2",
            description="Number of robots and controllers to start"
        ),
        DeclareLaunchArgument(
            "name_prefix",
            default_value="Robogame",
            description="BLE name prefix every robot advertises"
        ),
        include_launch_file("bridge.launch.py", {
            "name_prefix": LaunchConfiguration("name_prefix"),
            "expected_robots": LaunchConfiguration("robot_count"),
        }),
        OpaqueFunction(function=create_controllers),
    ])
