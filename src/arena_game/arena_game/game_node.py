"""ROS 2 node that runs the token game: rounds, secret roles, guesses, scores.

The rules are in game_rules.py and the round flow in game_flow.py; this
node only connects them to topics. Topics carry JSON in std_msgs/String.

Subscribes:
    /arena/zone_counts  the tokens in each base, from the vision node
    /arena/zone_events  tokens arriving in guess zones, from the vision node
    /game/command       commands such as {"cmd": "start"}, listed in
                        game_flow.py, from the scoreboard node or anyone
    /robot_N/joy        each robot's controller, from robot_control.launch.py
                        in arena_perception; pressing OPTIONS before the
                        first round joins Team N to the game
Publishes:
    /game/state         the whole game, ten times a second

Parameters: rounds (default 3), round_seconds (default 180), teams to
start with, such as "3,6" (default none), and join_button, the controller
button that joins (default 9, OPTIONS on a PS4 controller).
"""
import json
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Joy
from std_msgs.msg import String

from arena_game.game_flow import MAX_TEAM, GameFlow
from arena_game.game_rules import ROUND_SECONDS, ROUNDS


class GameNode(Node):

    def __init__(self):
        super().__init__('game_node')
        rounds = self.declare_parameter('rounds', ROUNDS).value
        round_seconds = self.declare_parameter(
            'round_seconds', ROUND_SECONDS).value
        teams = [int(team) for team in
                 str(self.declare_parameter('teams', '').value).split(',')
                 if team.strip()]
        self.join_button = self.declare_parameter('join_button', 9).value
        self.flow = GameFlow(rounds, round_seconds, teams,
                             log=self.get_logger().info)
        self.join_held = {}  # Robot to whether its join button is down

        self.state_pub = self.create_publisher(String, '/game/state', 10)
        self.create_subscription(
            String, '/arena/zone_counts', self.on_zone_counts, 10)
        self.create_subscription(
            String, '/arena/zone_events', self.on_zone_event, 10)
        self.create_subscription(
            String, '/game/command', self.on_command, 10)
        for robot in range(MAX_TEAM + 1):
            self.create_subscription(
                Joy, f'/robot_{robot}/joy',
                lambda msg, robot=robot: self.on_joy(robot, msg), 10)
        self.create_timer(0.1, self.step)
        self.get_logger().info(
            f'Game ready: {rounds} rounds of {round_seconds} s. Teams join '
            'by pressing OPTIONS on their controller')

    def on_joy(self, robot, msg):
        held = (self.join_button < len(msg.buttons)
                and msg.buttons[self.join_button] == 1)
        if held and not self.join_held.get(robot):
            self.flow.command({'cmd': 'join', 'team': robot}, time.time())
            self.publish_state()
        self.join_held[robot] = held

    def on_zone_counts(self, msg):
        bases = json.loads(msg.data)['base']
        self.flow.set_bases(
            {int(corner): counts for corner, counts in bases.items()})

    def on_zone_event(self, msg):
        event = json.loads(msg.data)
        self.flow.on_zone_change(event['zone'], event['corner'],
                                 event['color'], event['old'], event['new'])

    def on_command(self, msg):
        try:
            command = json.loads(msg.data)
        except json.JSONDecodeError:
            command = None
        if not isinstance(command, dict):
            self.get_logger().warning(f'Ignoring command {msg.data!r}: '
                                      'expected JSON like {"cmd": "start"}')
            return
        self.flow.command(command, time.time())
        self.publish_state()

    def step(self):
        self.flow.tick(time.time())
        self.publish_state()

    def publish_state(self):
        msg = String()
        msg.data = json.dumps(self.flow.state(time.time()))
        self.state_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = GameNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
