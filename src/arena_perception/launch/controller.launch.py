from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    robot_id = LaunchConfiguration("robot_id")
    joy_device_id = LaunchConfiguration("joy_device_id")
    linear_axis = LaunchConfiguration("linear_axis")
    angular_axis = LaunchConfiguration("angular_axis")

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
        DeclareLaunchArgument(
            "linear_axis",
            default_value="4",
            description="Joystick axis that drives forward and back"
        ),
        DeclareLaunchArgument(
            "angular_axis",
            default_value="0",
            description="Joystick axis that turns"
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
                "joy_device_id": ParameterValue(
                    joy_device_id,
                    value_type=int
                ),
                "linear_axis": ParameterValue(
                    linear_axis,
                    value_type=int
                ),
                "angular_axis": ParameterValue(
                    angular_axis,
                    value_type=int
                ),
            }]
        ),
    ])
