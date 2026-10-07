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
| `gamepad_node` | Reads one PS4 controller, chosen by Bluetooth address, and publishes `joy` |
| `controller_input` | Turns PS4 controller input into velocity and arm commands |
| `autonomy_node` | Drives a robot to a goal point using odometry |
| `apriltag_node` | Publishes AprilTag detections from the arena camera |
| `gazebo_viz_node` | Draws detected tags as markers in Gazebo |
| `list_joysticks` | Lists connected joysticks and their Bluetooth addresses |
| `assign_controllers` | Records which controller drives which robot |

## Robot discovery

Robots are not configured by name. `microcontroller_node` scans for any
device advertising the Robogame BLE service, reads the robot number from the
advertised name (`Robogame-2` becomes robot 2), then connects and subscribes
to `/robot_2/cmd_vel` and `/robot_2/arm_command`. Robots that power on later
are picked up automatically.

Scanning and connections share one radio, so scanning while robots are
connected can drop them and add latency. Discovery backs off as it finds
nothing new, and pauses once `expected_robots` robots are connected.

A robot that drops is reconnected straight away if it is still advertising.
If that fails, for example because the robot was power cycled, BlueZ has
forgotten the old device and a new scan is needed. The link then waits for
discovery to see the robot advertising again, and discovery resumes at its
fastest rate until it does.

Drive commands are not queued. Each robot has one writer that always sends
the most recent drive command, so a slow radio drops stale commands instead
of building a backlog that grows the delay between the stick and the robot.
Arm commands each move a joint one step, so they are kept and sent in order
alongside the drive command. Each robot gets at most 20 writes a second.

By default the bridge sends proportional speeds: `cmd_vel` becomes a forward
speed and a turn, each as a percentage, and the robot mixes them into left
and right wheel speeds. `linear.x` of `full_linear_speed` (0.5) and
`angular.z` of `full_angular_speed` (1.5) are full power. Launching with
`drive_mode:=letters` sends the older single letters instead, which drive
at full speed in one direction at a time.

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
colcon build --symlink-install --packages-select arena_perception
source install/setup.bash
ros2 launch arena_perception robot_control.launch.py
```

That starts the BLE bridge, and for every robot listed in
`src/arena_perception/config/controllers.yaml` a `gamepad_node` and a teleop
node in that robot's `robot_<id>` namespace. Each controller is chosen by its
Bluetooth address, so it drives the same robot whatever order the
controllers connect in, and a controller that drops is picked back up when
it reconnects.

If the smooth driving misbehaves, fall back to the older full speed
commands without reflashing any robot:

```
ros2 launch arena_perception robot_control.launch.py drive_mode:=letters
```

The bridge talks to every robot it finds, so start it once. The pieces can
also be launched separately. `controller.launch.py` uses the standard
`joy_node`, which picks a controller by index rather than address. That is
fine with a single controller, for example when testing one robot on a
laptop:

```
ros2 launch arena_perception bridge.launch.py expected_robots:=1
ros2 launch arena_perception controller.launch.py robot_id:=1 joy_device_id:=0
```

## Assigning controllers to robots

Robot `N` is the board flashed with `pio run -e robot_N`. Robot 0 is the
instructor's, and each team gets its own number from 1. Label every
controller and board with its number.

1. Pair every controller with this computer once. Hold Share and PS until
   the light bar flashes quickly, then pick "Wireless Controller" in the
   Ubuntu Bluetooth settings. A paired controller reconnects whenever its PS
   button is pressed.
2. Turn every controller on, then run:

   ```
   ros2 run arena_perception assign_controllers 0 1 2 3 4 5 6
   ```

   Press a button on each controller in the order the numbers are listed,
   here the instructor's first and then teams 1 to 6. Without numbers the
   tool counts from 1. Robots that are not listed keep their controller, so
   `assign_controllers 4` swaps in a new controller for team 4 only. The tool
   updates `config/controllers.yaml`, which can also be edited by hand.
3. Restart `robot_control.launch.py`.

A controller plugged in with a USB cable keeps the same address, so cables
are a fallback if one Bluetooth radio struggles with every controller and
robot at once.

## Checking the controllers

List the connected controllers with their Bluetooth addresses:

```
ros2 run arena_perception list_joysticks
```

Each `gamepad_node` logs when its controller connects or drops. Each teleop
node warns if no controller input arrives, and stops its robot if input stops
for `input_timeout` seconds (0.5 by default), so a controller that dies while
a stick is held does not leave the robot driving.

To check which controller feeds which robot, watch one topic at a time and
move the sticks:

```
ros2 topic echo /robot_1/joy
ros2 topic echo /robot_2/joy
```

With `controller.launch.py`, `joy_node` selects the device itself, so
`joy_device_id` is not guaranteed to match `/dev/input/jsN`.

Each teleop node logs every drive and arm command it publishes, whether or
not a robot is connected, so the controllers can be checked before any robot
is powered on.

## Joystick axes

A DualShock 4 reports axis 0 as the left stick X, axis 1 as the left stick
Y, axis 2 as L2, axis 3 as the right stick X, axis 4 as the right stick Y
and axis 5 as R2. Driving uses axis 1, steering uses axis 0 and spinning in
place uses axis 3.

Triggers rest at full deflection rather than centred, so using one as a
drive or turn axis makes the robot move on its own. Each teleop node logs
the axes it is using at startup.

`joy_node` and `gamepad_node` both report up and left as positive, which is
also how a Twist counts forward and a left turn, so the sticks are used
without changing sign. If a robot drives backwards, fix it on the robot with
the direction setting in the firmware, not here, so that `cmd_vel` means the
same thing for every robot and for autonomy.

## Controller mapping

| Input | Action |
| --- | --- |
| Left stick | Drive forward and back, and steer while driving |
| Right stick | Spin in place |
| Triangle, Cross | Shoulder up, shoulder down |
| Circle, Square | Elbow up, elbow down |
| R1, L1 | Gripper open, gripper close |

## Dependencies

`bleak` provides the BLE client. Install it alongside the ROS2 dependencies:

```
rosdep install --from-paths src --ignore-src -r -y
```
