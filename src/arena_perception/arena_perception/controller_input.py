import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy
from std_msgs.msg import String

from arena_perception import robot_commands
from arena_perception.joystick_devices import (
    find_joystick_device,
    find_joystick_devices,
)


class Ps4TeleopNode(Node):

    def __init__(self):
        super().__init__("ps4_teleop_node")

        self.declare_parameter("robot_id", 1)
        self.declare_parameter("joy_device_id", 0)
        self.declare_parameter("linear_axis", 4)
        self.declare_parameter("angular_axis", 0)
        self.declare_parameter("max_linear_speed", 0.5)
        self.declare_parameter("max_angular_speed", 1.5)
        self.declare_parameter("deadzone", 0.05)

        self.declare_parameter("shoulder_up_button", 2)
        self.declare_parameter("shoulder_down_button", 0)
        self.declare_parameter("elbow_up_button", 1)
        self.declare_parameter("elbow_down_button", 3)
        self.declare_parameter("gripper_open_button", 5)
        self.declare_parameter("gripper_close_button", 4)
        self.declare_parameter("arm_repeat_period", 0.15)

        self.linear_axis = self.get_parameter("linear_axis").value
        self.angular_axis = self.get_parameter("angular_axis").value
        self.max_linear_speed = self.get_parameter("max_linear_speed").value
        self.max_angular_speed = self.get_parameter("max_angular_speed").value
        self.deadzone = self.get_parameter("deadzone").value

        self.held_arm_buttons = {
            self.get_parameter("shoulder_up_button").value:
                robot_commands.SHOULDER_UP,
            self.get_parameter("shoulder_down_button").value:
                robot_commands.SHOULDER_DOWN,
            self.get_parameter("elbow_up_button").value:
                robot_commands.ELBOW_UP,
            self.get_parameter("elbow_down_button").value:
                robot_commands.ELBOW_DOWN,
        }

        self.pressed_arm_buttons = {
            self.get_parameter("gripper_open_button").value:
                robot_commands.GRIPPER_OPEN,
            self.get_parameter("gripper_close_button").value:
                robot_commands.GRIPPER_CLOSE,
        }

        self.button_states = []

        self.robot_id = self.get_parameter("robot_id").value
        namespace = f"/robot_{self.robot_id}"

        self.twist_publisher = self.create_publisher(
            Twist, f"{namespace}/cmd_vel", 10
        )
        self.arm_publisher = self.create_publisher(
            String, f"{namespace}/arm_command", 10
        )

        self.subscription = self.create_subscription(
            Joy, "joy", self.joy_callback, 10
        )

        self.arm_timer = self.create_timer(
            self.get_parameter("arm_repeat_period").value,
            self.publish_held_arm_commands
        )

        self.bridge_check_timer = self.create_timer(
            5.0,
            self.warn_when_no_bridge_is_listening
        )

        self.joy_device_id = self.get_parameter("joy_device_id").value

        self.get_logger().info(
            f"PS4 teleop node started for robot {self.robot_id}"
        )

        self.log_joystick_devices()

    def log_joystick_devices(self):
        devices = find_joystick_devices()

        if not devices:
            self.get_logger().warning(
                "No joystick devices found under /dev/input"
            )
            return

        self.get_logger().info(f"{len(devices)} joystick device(s) connected")

        for device in devices:
            self.get_logger().info(f"  joystick {device.index}: "
                                   f"{device.describe()}")

        bound_device = find_joystick_device(self.joy_device_id)

        if bound_device is None:
            self.get_logger().warning(
                f"Joystick {self.joy_device_id} is not connected, so robot "
                f"{self.robot_id} has no controller"
            )
            return

        self.get_logger().info(
            f"Robot {self.robot_id} is driven by joystick "
            f"{bound_device.index}: {bound_device.describe()}"
        )

    def warn_when_no_bridge_is_listening(self):
        if self.twist_publisher.get_subscription_count() > 0:
            return

        self.get_logger().warning(
            f"Nothing is subscribed to /robot_{self.robot_id}/cmd_vel. "
            f"The bridge has not discovered robot {self.robot_id} yet, so "
            "this controller is not driving anything."
        )

    def apply_deadzone(self, value):
        return value if abs(value) > self.deadzone else 0.0

    def read_axis(self, axes, index):
        if index < 0 or index >= len(axes):
            return 0.0

        return self.apply_deadzone(axes[index])

    def is_button_down(self, index):
        return 0 <= index < len(self.button_states) \
            and self.button_states[index] == 1

    def joy_callback(self, message: Joy):
        self.publish_twist(message.axes)
        self.publish_pressed_arm_commands(message.buttons)

        self.button_states = list(message.buttons)

    def publish_twist(self, axes):
        twist = Twist()
        twist.linear.x = (
            self.read_axis(axes, self.linear_axis) * self.max_linear_speed
        )
        twist.angular.z = (
            self.read_axis(axes, self.angular_axis) * self.max_angular_speed
        )

        self.twist_publisher.publish(twist)

    def publish_pressed_arm_commands(self, buttons):
        for index, command in self.pressed_arm_buttons.items():
            if index < 0 or index >= len(buttons):
                continue

            if buttons[index] == 1 and not self.is_button_down(index):
                self.publish_arm_command(command)

    def publish_held_arm_commands(self):
        for index, command in self.held_arm_buttons.items():
            if self.is_button_down(index):
                self.publish_arm_command(command)

    def publish_arm_command(self, command):
        message = String()
        message.data = command
        self.arm_publisher.publish(message)


def main(args=None):
    rclpy.init(args=args)
    node = Ps4TeleopNode()

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
