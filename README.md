# Robogame ROS2

[![ROS2](https://img.shields.io/badge/ROS2-Jazzy-22314E)](https://docs.ros.org/en/jazzy/)
[![Python](https://img.shields.io/badge/python-3.10+-3776AB)](https://www.python.org/)
[![Build](https://img.shields.io/badge/build-ament__python-blue)](https://docs.ros.org/en/jazzy/How-To-Guides/Developing-a-ROS-2-Package.html)
[![Bluetooth](https://img.shields.io/badge/bluetooth-bleak-0082FC)](https://bleak.readthedocs.io/)

ROS2 workspace for the Robogame arena. It handles AprilTag perception,
autonomy, controller input, and the BLE bridge that relays commands to the
ESP32 robots.

## Nodes

| Node | Purpose |
| --- | --- |
| `microcontroller_node` | Finds robots over BLE and relays commands to them |
| `controller_input` | Turns PS4 controller input into velocity and arm commands |
| `autonomy_node` | Drives a robot to a goal point using odometry |
| `apriltag_node` | Publishes AprilTag detections from the arena camera |
| `gazebo_viz_node` | Draws detected tags as markers in Gazebo |

## Robot discovery

Robots are not configured by name. `microcontroller_node` scans for any
device advertising the Robogame BLE service, reads the robot number from the
advertised name (`Robogame-2` becomes robot 2), then connects and subscribes
to `/robot_2/cmd_vel` and `/robot_2/arm_command`. Robots that power on later
are picked up automatically.

## Build and run

```
colcon build --packages-select arena_perception
source install/setup.bash
ros2 launch arena_perception robot_control.launch.py
```

Use a second controller by launching again with a different robot and
joystick:

```
ros2 launch arena_perception robot_control.launch.py robot_id:=2 joy_device_id:=1
```

## Controller mapping

| Input | Action |
| --- | --- |
| Left stick | Drive forward and back |
| Right stick | Turn |
| Triangle, Cross | Shoulder up, shoulder down |
| Circle, Square | Elbow up, elbow down |
| R1, L1 | Gripper open, gripper close |

## Dependencies

`bleak` provides the BLE client. Install it alongside the ROS2 dependencies:

```
rosdep install --from-paths src --ignore-src -r -y
```
