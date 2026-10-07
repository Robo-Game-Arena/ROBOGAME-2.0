from functools import partial
from queue import Empty, Queue

import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from std_msgs.msg import String

from arena_perception.ble_fleet import BleRobotFleet
from arena_perception import robot_commands


class MicrocontrollerNode(Node):

    def __init__(self):
        super().__init__("microcontroller_node")

        self.declare_parameter("name_prefix", "Robogame")
        self.declare_parameter(
            "service_uuid",
            "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
        )
        self.declare_parameter(
            "characteristic_uuid",
            "beb5483e-36e1-4688-b7f5-ea07361b26a8"
        )
        self.declare_parameter("drive_mode", "speed")
        self.declare_parameter("full_linear_speed", 0.5)
        self.declare_parameter("full_angular_speed", 1.5)
        self.declare_parameter("linear_threshold", 0.1)
        self.declare_parameter("angular_threshold", 0.1)
        self.declare_parameter("keepalive_period", 0.25)
        self.declare_parameter("scan_period", 5.0)
        self.declare_parameter("max_scan_period", 60.0)
        self.declare_parameter("expected_robots", 0)

        self.drive_mode = self.get_parameter("drive_mode").value

        if self.drive_mode not in ("speed", "letters"):
            raise ValueError(
                f"drive_mode must be 'speed' or 'letters', "
                f"got {self.drive_mode!r}"
            )

        self.full_linear_speed = self.get_parameter("full_linear_speed").value
        self.full_angular_speed = self.get_parameter(
            "full_angular_speed"
        ).value
        self.linear_threshold = self.get_parameter("linear_threshold").value
        self.angular_threshold = self.get_parameter("angular_threshold").value

        self.drive_commands = {}
        self.drive_directions = {}
        self.robot_subscriptions = {}
        self.discovered_robots = Queue()

        self.fleet = BleRobotFleet(
            service_uuid=self.get_parameter("service_uuid").value,
            characteristic_uuid=self.get_parameter(
                "characteristic_uuid"
            ).value,
            name_prefix=self.get_parameter("name_prefix").value,
            logger=self.get_logger(),
            on_robot_found=self.discovered_robots.put,
            scan_period=self.get_parameter("scan_period").value,
            max_scan_period=self.get_parameter("max_scan_period").value,
            expected_robots=self.get_parameter("expected_robots").value
        )
        self.fleet.start()

        self.discovery_timer = self.create_timer(
            0.5,
            self.subscribe_to_discovered_robots
        )

        self.keepalive_timer = self.create_timer(
            self.get_parameter("keepalive_period").value,
            self.send_keepalive
        )

        self.get_logger().info(
            f"Microcontroller bridge started, sending {self.drive_mode} "
            "drive commands"
        )

    def subscribe_to_discovered_robots(self):
        while True:
            try:
                robot_id = self.discovered_robots.get_nowait()
            except Empty:
                return

            self.add_robot_subscriptions(robot_id)

    def add_robot_subscriptions(self, robot_id):
        if robot_id in self.robot_subscriptions:
            return

        namespace = f"/robot_{robot_id}"
        self.drive_commands[robot_id] = robot_commands.STOP.encode("ascii")

        self.robot_subscriptions[robot_id] = [
            self.create_subscription(
                Twist,
                f"{namespace}/cmd_vel",
                partial(self.cmd_vel_callback, robot_id),
                10
            ),
            self.create_subscription(
                String,
                f"{namespace}/arm_command",
                partial(self.arm_callback, robot_id),
                10
            ),
        ]

        self.get_logger().info(
            f"Relaying {namespace}/cmd_vel and {namespace}/arm_command"
        )

    def cmd_vel_callback(self, robot_id, message: Twist):
        direction = robot_commands.twist_to_drive_command(
            message.linear.x,
            message.angular.z,
            self.linear_threshold,
            self.angular_threshold
        )

        if self.drive_mode == "speed":
            command = robot_commands.twist_to_speed_command(
                message.linear.x,
                message.angular.z,
                self.full_linear_speed,
                self.full_angular_speed
            )
        else:
            command = direction.encode("ascii")

        if command == self.drive_commands.get(robot_id):
            return

        self.drive_commands[robot_id] = command
        self.log_drive_change(robot_id, direction, command)
        self.fleet.send_drive_command(robot_id, command)

    def log_drive_change(self, robot_id, direction, command):
        # Speed commands change many times a second while a stick moves, so
        # only a change of direction is logged.
        if direction == self.drive_directions.get(robot_id):
            return

        self.drive_directions[robot_id] = direction
        self.get_logger().info(
            f"Robot {robot_id} drive command: "
            f"{robot_commands.describe_drive_command(command)}"
        )

    def arm_callback(self, robot_id, message: String):
        command = message.data.strip()

        if command not in robot_commands.ARM_COMMANDS:
            self.get_logger().warning(
                f"Ignoring unknown arm command: {message.data!r}"
            )
            return

        self.get_logger().info(f"Robot {robot_id} arm command: {command}")
        self.fleet.send_arm_command(robot_id, command.encode("ascii"))

    def send_keepalive(self):
        for robot_id, command in self.drive_commands.items():
            self.fleet.send_drive_command(robot_id, command)

    def destroy_node(self):
        for robot_id in self.drive_commands:
            self.drive_commands[robot_id] = robot_commands.STOP.encode(
                "ascii"
            )

        self.fleet.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = MicrocontrollerNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
