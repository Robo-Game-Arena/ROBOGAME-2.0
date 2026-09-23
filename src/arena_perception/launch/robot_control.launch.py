import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    launch_dir = os.path.join(
        get_package_share_directory("arena_perception"),
        "launch"
    )

    robot_id = LaunchConfiguration("robot_id")
    name_prefix = LaunchConfiguration("name_prefix")
    joy_device_id = LaunchConfiguration("joy_device_id")

    return LaunchDescription([
        DeclareLaunchArgument(
            "robot_id",
            default_value="1",
            description="Robot this controller drives"
        ),
        DeclareLaunchArgument(
            "name_prefix",
            default_value="Robogame",
            description="BLE name prefix every robot advertises"
        ),
        DeclareLaunchArgument(
            "joy_device_id",
            default_value="0",
            description="Index of the joystick device to read"
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, "bridge.launch.py")
            ),
            launch_arguments={
                "name_prefix": name_prefix,
            }.items()
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(launch_dir, "controller.launch.py")
            ),
            launch_arguments={
                "robot_id": robot_id,
                "joy_device_id": joy_device_id,
            }.items()
        ),
    ])
