import rclpy
from rclpy.node import Node

from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy
from std_msgs.msg import String

from arena_perception import robot_commands


class Ps4TeleopNode(Node):

    def __init__(self):
        super().__init__("ps4_teleop_node")

        self.declare_parameter("robot_id", 1)
        self.declare_parameter("linear_axis", 1)
        self.declare_parameter("steering_axis", 0)
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
        self.declare_parameter("input_timeout", 0.5)

        self.robot_id = self.get_parameter("robot_id").value
        self.linear_axis = self.get_parameter("linear_axis").value
        self.steering_axis = self.get_parameter("steering_axis").value
        self.angular_axis = self.get_parameter("angular_axis").value
        self.max_linear_speed = self.get_parameter("max_linear_speed").value
        self.max_angular_speed = self.get_parameter("max_angular_speed").value
        self.deadzone = self.get_parameter("deadzone").value
        self.input_timeout = self.get_parameter("input_timeout").value

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
        self.last_joy_time = None
        self.stopped_for_lost_input = False

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

        self.no_input_timer = self.create_timer(
            5.0,
            self.warn_when_no_input
        )

        self.input_watchdog_timer = self.create_timer(
            0.1,
            self.stop_when_input_lost
        )

        self.get_logger().info(
            f"PS4 teleop node started for robot {self.robot_id}, driving "
            f"with axis {self.linear_axis}, steering with axis "
            f"{self.steering_axis} and spinning with axis {self.angular_axis}"
        )

    def warn_when_no_input(self):
        self.no_input_timer.cancel()

        if self.last_joy_time is not None:
            return

        self.get_logger().warning(
            f"No controller input on {self.subscription.topic_name} yet. "
            "Is the controller for this robot turned on?"
        )

    def stop_when_input_lost(self):
        if self.last_joy_time is None or self.stopped_for_lost_input:
            return

        elapsed = self.get_clock().now() - self.last_joy_time

        if elapsed.nanoseconds < self.input_timeout * 1e9:
            return

        # A controller that dies while a stick is held would otherwise leave
        # the robot driving, because the bridge holds the last command.
        self.stopped_for_lost_input = True
        self.button_states = []
        self.publish_twist([])

        self.get_logger().warning(
            f"Lost controller input for robot {self.robot_id}, stopping it"
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
        self.last_joy_time = self.get_clock().now()
        self.stopped_for_lost_input = False

        self.publish_twist(message.axes)
        self.publish_pressed_arm_commands(message.buttons)

        self.button_states = list(message.buttons)

    def publish_twist(self, axes):
        # joy reports up and left as positive, the same way a Twist counts
        # forward and a left turn, so the sticks are used as they are. The
        # left stick steers while driving and the right stick spins in place,
        # and using both adds them together.
        stick_forward = self.read_axis(axes, self.linear_axis)
        stick_left = self.read_axis(axes, self.steering_axis) \
            + self.read_axis(axes, self.angular_axis)
        stick_left = max(-1.0, min(1.0, stick_left))

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

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
