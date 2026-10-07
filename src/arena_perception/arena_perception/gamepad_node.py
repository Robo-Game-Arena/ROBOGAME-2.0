import os

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Joy

from arena_perception.controller_config import normalize_address
from arena_perception.joystick_devices import (
    find_joystick_device_by_address,
    JoystickDisconnected,
    JS_EVENT_AXIS,
    JS_EVENT_BUTTON,
    JS_EVENT_INIT,
    open_joystick,
    read_joystick_events,
)

AXIS_LIMIT = 32767.0


def convert_axis(raw_value, deadzone):
    # Same scaling as joy_node: the deadzone is cut out, the rest of the
    # range is stretched back to 1.0, and the sign is flipped so that up and
    # left are positive.
    value = max(float(raw_value), -AXIS_LIMIT)
    unscaled_deadzone = AXIS_LIMIT * deadzone

    if value > unscaled_deadzone:
        value -= unscaled_deadzone
    elif value < -unscaled_deadzone:
        value += unscaled_deadzone
    else:
        return 0.0

    return -value / (1.0 - deadzone) / AXIS_LIMIT


class GamepadNode(Node):

    def __init__(self):
        super().__init__("gamepad_node")

        self.declare_parameter("controller_address", "")
        self.declare_parameter("deadzone", 0.05)
        self.declare_parameter("autorepeat_rate", 20.0)
        self.declare_parameter("poll_rate", 50.0)

        self.address = normalize_address(
            self.get_parameter("controller_address").value
        )
        self.deadzone = self.get_parameter("deadzone").value

        if not self.address:
            raise ValueError(
                "Set controller_address to the Bluetooth address of the "
                "controller to read. List connected controllers with: "
                "ros2 run arena_perception list_joysticks"
            )

        autorepeat_rate = self.get_parameter("autorepeat_rate").value
        self.repeat_nanoseconds = (
            int(1e9 / autorepeat_rate) if autorepeat_rate > 0 else None
        )

        self.file_descriptor = None
        self.axes = []
        self.buttons = []
        self.last_publish_time = None
        self.last_problem = None

        self.publisher = self.create_publisher(Joy, "joy", 10)

        self.poll_timer = self.create_timer(
            1.0 / self.get_parameter("poll_rate").value,
            self.poll
        )
        self.connect_timer = self.create_timer(1.0, self.open_controller)

        self.get_logger().info(
            f"Reading PS4 controller {self.address} on "
            f"{self.publisher.topic_name}"
        )

        self.open_controller()

    def report_problem(self, message):
        if message == self.last_problem:
            return

        self.last_problem = message
        self.get_logger().warning(message)

    def open_controller(self):
        if self.file_descriptor is not None:
            return

        device = find_joystick_device_by_address(self.address)

        if device is None:
            self.report_problem(
                f"Controller {self.address} is not connected. "
                "Press its PS button to connect it."
            )
            return

        try:
            self.file_descriptor = open_joystick(device)
        except OSError as error:
            self.report_problem(
                f"Cannot open {device.path} for controller {self.address}: "
                f"{error.strerror}"
            )
            return

        self.axes = []
        self.buttons = []
        self.last_problem = None

        self.get_logger().info(
            f"Controller {self.address} connected as {device.path}"
        )

    def close_controller(self, reason):
        try:
            os.close(self.file_descriptor)
        except OSError:
            pass

        self.file_descriptor = None

        self.get_logger().warning(
            f"Controller {self.address} disconnected ({reason})"
        )

    def poll(self):
        if self.file_descriptor is None:
            return

        try:
            events = read_joystick_events(self.file_descriptor)
        except JoystickDisconnected as error:
            self.close_controller(error)
            return

        for event_type, number, value in events:
            self.apply_event(event_type & ~JS_EVENT_INIT, number, value)

        now = self.get_clock().now()

        if events or self.is_repeat_due(now):
            self.publish_state(now)

    def apply_event(self, event_type, number, value):
        if event_type == JS_EVENT_AXIS:
            if number >= len(self.axes):
                self.axes.extend([0.0] * (number + 1 - len(self.axes)))

            self.axes[number] = convert_axis(value, self.deadzone)

        elif event_type == JS_EVENT_BUTTON:
            if number >= len(self.buttons):
                self.buttons.extend([0] * (number + 1 - len(self.buttons)))

            self.buttons[number] = 1 if value else 0

    def is_repeat_due(self, now):
        if self.repeat_nanoseconds is None:
            return False

        if self.last_publish_time is None:
            return True

        elapsed = (now - self.last_publish_time).nanoseconds
        return elapsed >= self.repeat_nanoseconds

    def publish_state(self, now):
        message = Joy()
        message.header.stamp = now.to_msg()
        message.header.frame_id = "joy"
        message.axes = list(self.axes)
        message.buttons = list(self.buttons)

        self.publisher.publish(message)
        self.last_publish_time = now

    def destroy_node(self):
        if self.file_descriptor is not None:
            os.close(self.file_descriptor)
            self.file_descriptor = None

        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GamepadNode()

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
