import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from std_msgs.msg import String

from arena_perception.ble_link import BleRobotLink
from arena_perception import robot_commands


class MicrocontrollerNode(Node):

    def __init__(self):
        super().__init__("microcontroller_node")

        self.declare_parameter("device_name", "XIAO-C3-Robot")
        self.declare_parameter(
            "characteristic_uuid",
            "beb5483e-36e1-4688-b7f5-ea07361b26a8"
        )
        self.declare_parameter("linear_threshold", 0.1)
        self.declare_parameter("angular_threshold", 0.1)
        self.declare_parameter("keepalive_period", 0.25)

        self.linear_threshold = self.get_parameter("linear_threshold").value
        self.angular_threshold = self.get_parameter("angular_threshold").value

        self.drive_command = robot_commands.STOP

        self.link = BleRobotLink(
            device_name=self.get_parameter("device_name").value,
            characteristic_uuid=self.get_parameter(
                "characteristic_uuid"
            ).value,
            logger=self.get_logger()
        )
        self.link.start()

        self.cmd_vel_subscription = self.create_subscription(
            Twist,
            "/robot_1/cmd_vel",
            self.cmd_vel_callback,
            10
        )

        self.arm_subscription = self.create_subscription(
            String,
            "/robot_1/arm_command",
            self.arm_callback,
            10
        )

        self.keepalive_timer = self.create_timer(
            self.get_parameter("keepalive_period").value,
            self.send_keepalive
        )

        self.get_logger().info("Microcontroller bridge started")

    def cmd_vel_callback(self, message: Twist):
        command = robot_commands.twist_to_drive_command(
            message.linear.x,
            message.angular.z,
            self.linear_threshold,
            self.angular_threshold
        )

        if command == self.drive_command:
            return

        self.drive_command = command
        self.get_logger().info(f"Drive command: {command}")
        self.link.send(command)

    def arm_callback(self, message: String):
        command = message.data.strip()

        if command not in robot_commands.ARM_COMMANDS:
            self.get_logger().warning(
                f"Ignoring unknown arm command: {message.data!r}"
            )
            return

        self.get_logger().info(f"Arm command: {command}")
        self.link.send(command)

    def send_keepalive(self):
        if self.drive_command == robot_commands.STOP:
            return

        self.link.send(self.drive_command)

    def destroy_node(self):
        self.drive_command = robot_commands.STOP
        self.link.stop()
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
