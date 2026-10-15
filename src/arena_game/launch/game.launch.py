"""Start the token game: the vision, game and scoreboard nodes.

    ros2 launch arena_game game.launch.py
    ros2 launch arena_game game.launch.py teams:=3,6 rounds:=1 round_seconds:=60

Teams join by pressing OPTIONS on their controller, with the robots'
controllers running (robot_control.launch.py in arena_perception), or are
listed in teams. Closing the scoreboard window stops all three nodes.
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, Shutdown
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    teams = LaunchConfiguration("teams")
    join_button = LaunchConfiguration("join_button")
    rounds = LaunchConfiguration("rounds")
    round_seconds = LaunchConfiguration("round_seconds")

    return LaunchDescription([
        DeclareLaunchArgument(
            "join_button",
            default_value="9",
            description="Controller button that joins a team, 9 being "
                        "OPTIONS on a PS4 controller"
        ),
        DeclareLaunchArgument(
            "teams",
            default_value="",
            description="Teams to start with, numbered like their robots, "
                        "such as 3,6; others join from their controllers"
        ),
        DeclareLaunchArgument(
            "rounds",
            default_value="3",
            description="Rounds in a game"
        ),
        DeclareLaunchArgument(
            "round_seconds",
            default_value="180",
            description="Length of each round in seconds"
        ),
        Node(
            package="arena_game",
            executable="vision_node",
            name="vision_node",
            output="screen"
        ),
        Node(
            package="arena_game",
            executable="game_node",
            name="game_node",
            output="screen",
            parameters=[{
                "teams": ParameterValue(teams, value_type=str),
                "join_button": ParameterValue(join_button, value_type=int),
                "rounds": ParameterValue(rounds, value_type=int),
                "round_seconds": ParameterValue(round_seconds, value_type=int),
            }]
        ),
        Node(
            package="arena_game",
            executable="scoreboard_node",
            name="scoreboard_node",
            output="screen",
            on_exit=Shutdown()
        ),
    ])
