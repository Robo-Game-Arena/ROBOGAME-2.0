from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    device_name = LaunchConfiguration("device_name")
    joy_device_id = LaunchConfiguration("joy_device_id")

    return LaunchDescription([
        DeclareLaunchArgument(
            "device_name",
            default_value="XIAO-C3-Robot",
            description="BLE advertised name of the ESP32 robot"
        ),
        DeclareLaunchArgument(
            "joy_device_id",
            default_value="0",
            description="Index of the joystick device to read"
        ),
        Node(
            package="joy",
            executable="joy_node",
            name="joy_node",
            output="screen",
            parameters=[{
                "device_id": ParameterValue(
                    joy_device_id,
                    value_type=int
                ),
                "deadzone": 0.05,
                "autorepeat_rate": 20.0,
            }]
        ),
        Node(
            package="arena_perception",
            executable="controller_input",
            name="ps4_teleop_node",
            output="screen"
        ),
        Node(
            package="arena_perception",
            executable="microcontroller_node",
            name="microcontroller_node",
            output="screen",
            parameters=[{
                "device_name": device_name,
            }]
        ),
    ])
