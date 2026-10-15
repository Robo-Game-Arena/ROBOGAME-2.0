"""ROS 2 node that shows the scoreboard window and takes the instructor's keys.

It draws the camera view from the vision node beside a panel drawn from the
game node's state, and turns key presses into commands; the keys are listed
in scoreboard.py. It keeps no game state of its own, so it can be closed and
started again in the middle of a game.

Subscribes:
    /game/state             JSON in std_msgs/String, from the game node
    /arena/view/compressed  sensor_msgs/CompressedImage, from the vision node
Publishes:
    /game/command           commands for the game node
    /arena/command          {"cmd": "lock"} when l is pressed
"""
import json
import os
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from arena_game.arena_check import label
from arena_game.scoreboard import draw_panel, key_command
from arena_game.token_zones import GRAY, RED, VIEW_HEIGHT

VIEW_WIDTH = round(VIEW_HEIGHT * 4 / 3)  # The 1600x1200 camera view, scaled


class ScoreboardNode(Node):

    def __init__(self):
        super().__init__('scoreboard_node')
        self.state = None
        self.view = None
        self.create_subscription(String, '/game/state', self.on_state, 10)
        self.create_subscription(
            CompressedImage, '/arena/view/compressed', self.on_view, 1)
        self.game_pub = self.create_publisher(String, '/game/command', 10)
        self.arena_pub = self.create_publisher(String, '/arena/command', 10)

        self.window = 'Robogame'
        cv2.namedWindow(self.window)
        self.quit_until = 0.0
        self.done = False
        self.create_timer(1 / 20, self.step)

    def on_state(self, msg):
        self.state = json.loads(msg.data)

    def on_view(self, msg):
        view = cv2.imdecode(np.frombuffer(bytes(msg.data), np.uint8),
                            cv2.IMREAD_COLOR)
        if view is not None:
            self.view = view

    def send(self, publisher, command):
        msg = String()
        msg.data = json.dumps(command)
        publisher.publish(msg)

    def step(self):
        view = self.view
        if view is None:
            view = np.zeros((VIEW_HEIGHT, VIEW_WIDTH, 3), np.uint8)
            label(view, 'Waiting for the camera view from the vision node',
                  (20, 40), GRAY, 0.8)
        shown = cv2.hconcat([view, draw_panel(self.state)])
        now = time.time()
        if now < self.quit_until:
            label(shown, 'Press q again to quit', (10, 40), RED, 0.9)
        cv2.imshow(self.window, shown)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            # One stray q mid-game should not close the scoreboard.
            self.done = now < self.quit_until
            self.quit_until = now + 3
        elif key == ord('l'):
            self.send(self.arena_pub, {'cmd': 'lock'})
        elif key == ord('s'):
            path = os.path.abspath(
                time.strftime('robogame_%Y%m%d_%H%M%S.jpg'))
            cv2.imwrite(path, shown)
            self.get_logger().info(f'Saved {path}')
        elif key != 255 and self.state is not None:
            command = key_command(key, self.state['phase'])
            if command:
                self.send(self.game_pub, command)
        if cv2.getWindowProperty(self.window, cv2.WND_PROP_VISIBLE) < 1:
            self.done = True


def main(args=None):
    rclpy.init(args=args)
    node = ScoreboardNode()
    try:
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.05)
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
