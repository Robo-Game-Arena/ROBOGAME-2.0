from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    robot_id = LaunchConfiguration("robot_id")
    joy_device_id = LaunchConfiguration("joy_device_id")

    robot_namespace = PythonExpression(["'robot_' + str(", robot_id, ")"])

    return LaunchDescription([
        DeclareLaunchArgument(
            "robot_id",
            default_value="1",
            description="Robot this controller drives"
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
            namespace=robot_namespace,
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
            namespace=robot_namespace,
            output="screen",
            parameters=[{
                "robot_id": ParameterValue(robot_id, value_type=int),
            }]
        ),
    ])
