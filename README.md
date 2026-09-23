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
| `list_joysticks` | Lists connected joysticks and their Bluetooth addresses |

## Robot discovery

Robots are not configured by name. `microcontroller_node` scans for any
device advertising the Robogame BLE service, reads the robot number from the
advertised name (`Robogame-2` becomes robot 2), then connects and subscribes
to `/robot_2/cmd_vel` and `/robot_2/arm_command`. Robots that power on later
are picked up automatically.

Scanning and connections share one radio, so scanning while robots are
connected can drop them and add latency. Discovery backs off as it finds
nothing new, and stops completely once `expected_robots` robots are
connected. Reconnecting never needs a scan, so a robot that drops is picked
straight back up.

Commands are not queued. Each robot has one writer that always sends the
most recent command, so a slow radio drops stale commands instead of
building a backlog that grows the delay between the stick and the robot.

Every board must be flashed from its own PlatformIO environment. Two boards
advertising the same name cannot be told apart, and the bridge will keep the
first one and warn about the second.

The characters the bridge writes over BLE are documented in
[PROTOCOL.md](https://github.com/Robo-Game-Arena/robogame-esp/blob/main/PROTOCOL.md)
in the firmware repository.

## Install

`install.sh` installs ROS2 Jazzy if it is missing, pulls the build tools and
Python dependencies, resolves package dependencies with rosdep, then builds
the workspace. It targets Ubuntu, and skips the apt steps on other systems.

```
./install.sh
```

## Build and run

```
colcon build --packages-select arena_perception
source install/setup.bash
ros2 launch arena_perception robot_control.launch.py
```

That starts the BLE bridge and two controllers, mapping robot 1 to joystick
0 and robot 2 to joystick 1. Use `robot_count` for a different number of
robots:

```
ros2 launch arena_perception robot_control.launch.py robot_count:=4
```

Robot `N` always uses joystick `N - 1`.

Each controller runs in its own `robot_<id>` namespace, so every joystick
publishes to its own `joy` topic instead of sharing one.

The bridge talks to every robot it finds, so start it once. The pieces can
also be launched separately:

```
ros2 launch arena_perception bridge.launch.py expected_robots:=2
ros2 launch arena_perception controller.launch.py robot_id:=1 joy_device_id:=0
```

## Checking the controllers

A DualShock 4 registers several input devices, so the second gamepad is not
always `js1`. List what is connected and which index to pass:

```
ros2 run arena_perception list_joysticks
```

Each teleop node logs every joystick it can see at startup, with Bluetooth
addresses, and warns if it receives no controller input or if no bridge is
listening for its robot.

`joy_node` selects the device itself, so `joy_device_id` is not guaranteed to
match `/dev/input/jsN`. To find which controller feeds which robot, start
both controllers, then watch one topic at a time and move the sticks:

```
ros2 topic echo /robot_1/joy
ros2 topic echo /robot_2/joy
```

Swap the two `joy_device_id` values if a controller drives the wrong robot.

Each teleop node logs every drive and arm command it publishes, whether or
not a robot is connected, so the controllers can be checked before any robot
is powered on.

## Joystick axes

A DualShock 4 reports axis 0 as the left stick X, axis 1 as the left stick
Y, axis 2 as L2, axis 3 as the right stick X, axis 4 as the right stick Y
and axis 5 as R2. Driving uses axis 1 and turning uses axis 3.

Triggers rest at full deflection rather than centred, so using one as a
drive or turn axis makes the robot move on its own. Each teleop node logs
the axes it is using at startup.

Joystick axes report up and left as negative, while a Twist uses positive
for forward and positive for a left turn, so both axes are negated before
they are published.

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
