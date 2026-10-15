#!/usr/bin/env python3
"""The whole game in one program without ROS, as a backup to the ROS 2 nodes.

It runs the same pieces as the vision, game and scoreboard nodes, in one
loop: token_zones.py watches the camera, game_flow.py runs the rounds, and
scoreboard.py draws the panel and reads the keys listed there.

    ros2 run arena_game standalone

or, without building the workspace:

    cd ~/ROBOGAME-2.0/src/arena_game && python3 -m arena_game.standalone
"""
import argparse
import os
import time

import cv2

from arena_game.arena_check import label, open_camera
from arena_game.game_flow import GameFlow
from arena_game.game_rules import ROUND_SECONDS, ROUNDS
from arena_game.scoreboard import KEYS_HINT, draw_panel, key_command
from arena_game.token_zones import RED, TokenZones


def main():
    parser = argparse.ArgumentParser(
        description='Run the token game in one program, without ROS.')
    parser.add_argument('--teams', default='',
                        help='teams playing, numbered like their robots, '
                             'such as 3,6; more can be added on the panel')
    parser.add_argument('--rounds', type=int, default=ROUNDS)
    parser.add_argument('--round-seconds', type=int, default=ROUND_SECONDS)
    parser.add_argument('--device', type=int, default=0,
                        help='camera index (default 0, /dev/video0)')
    args = parser.parse_args()

    camera = open_camera(args.device, 1600, 1200)
    zones = TokenZones()
    zones.keys_hint = KEYS_HINT
    teams = [int(team) for team in args.teams.split(',') if team.strip()]
    flow = GameFlow(args.rounds, args.round_seconds, teams, log=zones.log)
    zones.listeners.append(flow.on_zone_change)
    window = 'Robogame'
    cv2.namedWindow(window)
    fps = 0.0
    last = time.time()
    quit_until = 0.0
    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print('Lost the camera')
                break
            now = time.time()
            fps = 0.9 * fps + 0.1 / max(now - last, 1e-3)
            last = now

            placed = []
            if zones.homography is None:
                zones.lock(frame)
            else:
                placed = zones.update(frame, now)
            flow.set_bases(zones.counts('base'))
            flow.tick(now)
            state = flow.state(now)
            zones.names = {int(corner): f'T{team}'
                           for corner, team in state['corners'].items()}
            shown = cv2.hconcat([zones.draw_view(frame, placed, fps),
                                 draw_panel(state)])
            if now < quit_until:
                label(shown, 'Press q again to quit', (10, 40), RED, 0.9)
            cv2.imshow(window, shown)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                # One stray q mid-game should not throw the scores away.
                if now < quit_until:
                    break
                quit_until = now + 3
            elif key == ord('l'):
                zones.unlock()
            elif key == ord('s'):
                path = os.path.abspath(
                    time.strftime('robogame_%Y%m%d_%H%M%S.jpg'))
                cv2.imwrite(path, shown)
                print('Saved', path)
            elif key != 255:
                command = key_command(key, state['phase'])
                if command:
                    flow.command(command, now)
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
