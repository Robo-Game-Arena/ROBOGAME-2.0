import os

from ament_index_python.packages import get_package_share_directory

from arena_perception.controller_config import (
    default_controllers_file,
    load_controller_addresses,
)

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
)
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


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


def create_robots(context, *args, **kwargs):
    controllers_file = LaunchConfiguration("controllers_file").perform(context)
    addresses = load_controller_addresses(controllers_file)

    actions = [
        LogInfo(msg=(
            f"{len(addresses)} controller(s) assigned in {controllers_file}"
        )),
        include_launch_file("bridge.launch.py", {
            "name_prefix": LaunchConfiguration("name_prefix"),
            "expected_robots": str(len(addresses)),
            "drive_mode": LaunchConfiguration("drive_mode"),
        }),
    ]

    for robot_id, address in sorted(addresses.items()):
        namespace = f"robot_{robot_id}"

        actions.append(Node(
            package="arena_perception",
            executable="gamepad_node",
            name="gamepad_node",
            namespace=namespace,
            output="screen",
            parameters=[{
                "controller_address": ParameterValue(address, value_type=str),
            }]
        ))
        actions.append(Node(
            package="arena_perception",
            executable="controller_input",
            name="ps4_teleop_node",
            namespace=namespace,
            output="screen",
            parameters=[{"robot_id": robot_id}]
        ))

    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            "controllers_file",
            default_value=default_controllers_file(),
            description="File saying which controller drives which robot"
        ),
        DeclareLaunchArgument(
            "name_prefix",
            default_value="Robogame",
            description="BLE name prefix every robot advertises"
        ),
        DeclareLaunchArgument(
            "drive_mode",
            default_value="speed",
            description="speed for smooth driving, or letters for the old "
                        "full speed, one direction at a time commands"
        ),
        OpaqueFunction(function=create_robots),
    ])
