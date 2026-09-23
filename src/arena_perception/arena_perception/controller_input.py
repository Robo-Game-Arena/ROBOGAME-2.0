import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy
from std_msgs.msg import String

from arena_perception import robot_commands


class Ps4TeleopNode(Node):

    def __init__(self):
        super().__init__("ps4_teleop_node")

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

        self.twist_publisher = self.create_publisher(
            Twist, "/robot_1/cmd_vel", 10
        )
        self.arm_publisher = self.create_publisher(
            String, "/robot_1/arm_command", 10
        )

        self.subscription = self.create_subscription(
            Joy, "/joy", self.joy_callback, 10
        )

        self.arm_timer = self.create_timer(
            self.get_parameter("arm_repeat_period").value,
            self.publish_held_arm_commands
        )

        self.get_logger().info("PS4 teleop node started")

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
