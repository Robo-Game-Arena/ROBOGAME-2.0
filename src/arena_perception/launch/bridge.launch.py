from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    name_prefix = LaunchConfiguration("name_prefix")
    expected_robots = LaunchConfiguration("expected_robots")
    drive_mode = LaunchConfiguration("drive_mode")

    return LaunchDescription([
        DeclareLaunchArgument(
            "name_prefix",
            default_value="Robogame",
            description="BLE name prefix every robot advertises"
        ),
        DeclareLaunchArgument(
            "expected_robots",
            default_value="0",
            description="Stop scanning once this many robots are found"
        ),
        DeclareLaunchArgument(
            "drive_mode",
            default_value="speed",
            description="speed for smooth driving, or letters for the old "
                        "full speed, one direction at a time commands"
        ),
        Node(
            package="arena_perception",
            executable="microcontroller_node",
            name="microcontroller_node",
            output="screen",
            parameters=[{
                "name_prefix": name_prefix,
                "expected_robots": ParameterValue(
                    expected_robots,
                    value_type=int
                ),
                "drive_mode": drive_mode,
            }]
        ),
    ])
