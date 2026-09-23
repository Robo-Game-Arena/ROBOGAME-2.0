import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy
from std_msgs.msg import String

from arena_perception import robot_commands
from arena_perception.joystick_devices import find_joystick_devices


class Ps4TeleopNode(Node):

    def __init__(self):
        super().__init__("ps4_teleop_node")

        self.declare_parameter("robot_id", 1)
        self.declare_parameter("joy_device_id", 0)
        self.declare_parameter("linear_axis", 1)
        self.declare_parameter("angular_axis", 3)
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

        self.robot_id = self.get_parameter("robot_id").value
        self.joy_device_id = self.get_parameter("joy_device_id").value
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
        self.last_drive_command = None
        self.joy_message_count = 0

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

        self.diagnostics_timer = self.create_timer(
            5.0,
            self.warn_when_no_joy_messages
        )

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
            self.get_logger().info(
                f"  joystick {device.index}: {device.describe()}"
            )

        self.get_logger().info(
            f"Robot {self.robot_id} is configured for joy_device_id "
            f"{self.joy_device_id}, driving with axis {self.linear_axis} and "
            f"turning with axis {self.angular_axis}"
        )

    def warn_when_no_joy_messages(self):
        if self.joy_message_count > 0:
            return

        self.get_logger().warning(
            f"No messages received on {self.subscription.topic_name}. "
            f"joy_node may be reading a device other than joy_device_id "
            f"{self.joy_device_id}, or this controller is not connected."
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
        self.joy_message_count += 1

        self.publish_twist(message.axes)
        self.publish_pressed_arm_commands(message.buttons)

        self.button_states = list(message.buttons)

    def publish_twist(self, axes):
        stick_forward = -self.read_axis(axes, self.linear_axis)
        stick_left = -self.read_axis(axes, self.angular_axis)

        twist = Twist()
        twist.linear.x = stick_forward * self.max_linear_speed
        twist.angular.z = stick_left * self.max_angular_speed

        self.twist_publisher.publish(twist)
        self.log_drive_command(twist)

    def log_drive_command(self, twist):
        command = robot_commands.twist_to_drive_command(
            twist.linear.x,
            twist.angular.z,
            0.1,
            0.1
        )

        if command == self.last_drive_command:
            return

        self.last_drive_command = command

        self.get_logger().info(
            f"Robot {self.robot_id} drive {command} "
            f"linear={twist.linear.x:.2f} angular={twist.angular.z:.2f}"
        )

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

        self.get_logger().info(f"Robot {self.robot_id} arm {command}")


def main(args=None):
    rclpy.init(args=args)
    node = Ps4TeleopNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
