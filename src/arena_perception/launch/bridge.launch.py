from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    name_prefix = LaunchConfiguration("name_prefix")
    expected_robots = LaunchConfiguration("expected_robots")

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
            }]
        ),
    ])
