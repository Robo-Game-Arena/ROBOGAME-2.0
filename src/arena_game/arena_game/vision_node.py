"""ROS 2 node that watches the arena camera for tokens.

The work is done by TokenZones in token_zones.py; this node only publishes
what it finds. Topics carry JSON in std_msgs/String unless noted.

Zones are named by their corner, 1 to 4; the game node knows which team
plays from each corner.

Publishes:
    /arena/tokens           every token seen in the latest frame: color,
                            x_cm and y_cm, and its zone and corner if it is
                            in a base or guess zone
    /arena/zone_counts      the tokens counted in each base and guess zone,
                            by corner, after the half second hold
    /arena/zone_events      one message each time a zone's count changes
    /arena/view/compressed  the camera view with zones and tokens drawn on,
                            as a JPEG sensor_msgs/CompressedImage
Subscribes:
    /arena/command          {"cmd": "lock"} locks the arena again
    /game/state             to label each corner's zones with its team
"""
import json
import time

import cv2
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

from arena_game.arena_check import open_camera
from arena_game.scoreboard import KEYS_HINT
from arena_game.token_zones import TokenZones


class VisionNode(Node):

    def __init__(self):
        super().__init__('vision_node')
        device = self.declare_parameter('device', 0).value
        self.camera = open_camera(device, 1600, 1200)
        self.zones = TokenZones()
        # The scoreboard window shows this view, and takes these keys.
        self.zones.keys_hint = KEYS_HINT
        self.zones.listeners.append(self.on_zone_change)

        self.tokens_pub = self.create_publisher(String, '/arena/tokens', 10)
        self.counts_pub = self.create_publisher(
            String, '/arena/zone_counts', 10)
        self.events_pub = self.create_publisher(
            String, '/arena/zone_events', 10)
        self.view_pub = self.create_publisher(
            CompressedImage, '/arena/view/compressed', 1)
        self.create_subscription(
            String, '/arena/command', self.on_command, 10)
        self.create_subscription(
            String, '/game/state', self.on_game_state, 10)

        self.fps = 0.0
        self.last = time.time()
        self.create_timer(1 / 30, self.step)
        self.get_logger().info('Watching the arena camera')

    def publish_json(self, publisher, data):
        msg = String()
        msg.data = json.dumps(data)
        publisher.publish(msg)

    def on_command(self, msg):
        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError:
            command = None
        if isinstance(command, dict) and command.get('cmd') == 'lock':
            self.get_logger().info('Locking the arena again')
            self.zones.unlock()

    def on_game_state(self, msg):
        corners = json.loads(msg.data).get('corners', {})
        self.zones.names = {int(corner): f'T{team}'
                            for corner, team in corners.items()}

    def on_zone_change(self, zone, corner, color, old_count, new_count):
        self.publish_json(self.events_pub, {
            'zone': zone, 'corner': corner, 'color': color,
            'old': old_count, 'new': new_count})

    def step(self):
        ok, frame = self.camera.read()
        if not ok:
            self.get_logger().warning('No frame from the camera')
            return
        now = time.time()
        self.fps = 0.9 * self.fps + 0.1 / max(now - self.last, 1e-3)
        self.last = now

        placed = []
        if self.zones.homography is None:
            self.zones.lock(frame)
        else:
            placed = self.zones.update(frame, now)
            tokens = []
            for color, x, y, _ in placed:
                point = self.zones.to_arena([(x, y)])[0]
                zone = self.zones.zone_of(point)
                tokens.append({
                    'color': color,
                    'x_cm': round(float(point[0]), 1),
                    'y_cm': round(float(point[1]), 1),
                    'zone': zone[0] if zone else None,
                    'corner': zone[1] if zone else None,
                })
            self.publish_json(self.tokens_pub, tokens)
            self.publish_json(self.counts_pub, {
                'base': self.zones.counts('base'),
                'guess': self.zones.counts('guess')})

        view = self.zones.draw_view(frame, placed, self.fps)
        image = CompressedImage()
        image.header.stamp = self.get_clock().now().to_msg()
        image.format = 'jpeg'
        image.data = cv2.imencode('.jpg', view)[1].tobytes()
        self.view_pub.publish(image)

    def destroy_node(self):
        self.camera.release()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
