from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    name_prefix = LaunchConfiguration("name_prefix")

    return LaunchDescription([
        DeclareLaunchArgument(
            "name_prefix",
            default_value="Robogame",
            description="BLE name prefix every robot advertises"
        ),
        Node(
            package="arena_perception",
            executable="microcontroller_node",
            name="microcontroller_node",
            output="screen",
            parameters=[{
                "name_prefix": name_prefix,
            }]
        ),
    ])
