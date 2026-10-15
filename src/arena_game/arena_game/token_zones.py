#!/usr/bin/env python3
"""Find the colored tokens on the arena, and the base or guess zone each is in.

Each team owns a corner. The black quarter circle in that corner is the
team's base, and the small tag in the same quadrant marks its guess zone, as
in the old game: Team 1's guess zone is tag 4, Team 2's tag 5, Team 3's tag 6
and Team 4's tag 7. The arena locks as soon as all four corner tags are in
view, and from then on red, green, blue and yellow tokens are found by color
in every frame.

A token counts as arrived in a zone once it has stayed there for half a
second, and as gone once it has been missing for two seconds, so a robot
driving over a base does not register as tokens leaving it. Every change is
listed in the window and printed here.

Run on its own, it shows the tokens without any game:

    ros2 run arena_game token_zones

Keys: space locks the arena again after the camera or arena has moved,
s saves a snapshot, q quits.
"""
import argparse
from collections import defaultdict, deque
import os
import time

import cv2
import numpy as np

from arena_game.arena_check import (
    label, largest_tags, make_detector, open_camera, stray_corners)

ARENA_CM = 112.0
CORNER_IDS = (3, 2, 1, 0)  # Corner tags at (0, 0), (L, 0), (L, L), (0, L)

# Each base corner in arena centimetres, numbered 1 to 4. As in the old game,
# corner 1 has tag 0, corner 2 tag 1, corner 3 tag 2 and corner 4 tag 3. In
# this file a "team" is a corner's number; the game gives each corner to a
# team numbered like its robot.
BASE_CORNERS = {
    1: (0.0, ARENA_CM),
    2: (ARENA_CM, ARENA_CM),
    3: (ARENA_CM, 0.0),
    4: (0.0, 0.0),
}
GUESS_TAG_TEAMS = {4: 1, 5: 2, 6: 3, 7: 4}  # Guess zone tag ID to its team
# Where the guess zone tags were on 2026-10-15, for any not in view at lock.
GUESS_DEFAULTS = {1: (32, 80), 2: (80, 80), 3: (80, 32), 4: (32, 31)}

BASE_RADIUS_CM = 22  # The black quarter circles are 20.5 cm, plus half a token
# About the guess zone tag itself, a 7.4 cm square, so a token only counts as
# a guess when it is put on the tag, not when it is pushed past nearby.
GUESS_RADIUS_CM = 5
EDGE_CM = 3  # Also look for tokens this far outside the corner tags

ARRIVE_S = 0.5
LEAVE_S = 2.0
LOCK_S = 1.0  # How long all four corner tags must stay in view to lock

# Hue, saturation and value ranges for each token color, from the old game's
# token_calibration.json with these changes:
# - Yellow's saturation floor is 30, not 60. The camera exposes the white
#   board brightly, which washes the yellow tokens out.
# - Blue's saturation and value floors are 60 and 80, not 15 and 12, which
#   let the dark parts of the tags through.
# - Red's low hues stop at 10, not 20, and yellow's start at 21, not 16, to
#   leave out the gold tape at the corner tags (hue 13 to 20). A token
#   touching the tape otherwise merges with it and is no longer round.
# - Every value floor is 80, not 30. The tokens read 200 or more, and the
#   camera's color noise on the black bases made phantom tokens there.
TOKEN_HSV = {
    'Red': [((0, 30, 80), (10, 255, 255)), ((160, 30, 80), (179, 255, 255))],
    'Green': [((38, 30, 80), (92, 255, 255))],
    'Blue': [((85, 60, 80), (143, 255, 255))],
    'Yellow': [((21, 30, 80), (38, 255, 255))],
}
# Token shape limits, in camera pixels at 1600x1200, where a token's radius
# is about 11 px. A token is a filled, nearly round blob.
MIN_AREA = 150
MIN_RADIUS = 6
MAX_RADIUS = 25
MIN_CIRCULARITY = 0.65
MIN_FILL = 0.55
KERNEL = np.ones((5, 5), np.uint8)

VIEW_HEIGHT = 800
PANEL_WIDTH = 600
MAX_EVENTS = 12

WHITE = (255, 255, 255)
GRAY = (150, 150, 150)
RED = (0, 0, 255)
CYAN = (255, 255, 0)
MAGENTA = (255, 0, 255)
TOKEN_BGR = {
    'Red': (60, 60, 255),
    'Green': (80, 220, 80),
    'Blue': (255, 140, 40),
    'Yellow': (0, 230, 255),
}


def find_tokens(frame, mask, roi):
    """Return (color, x, y, radius) in camera pixels for each token found."""
    x0, y0, x1, y1 = roi
    hsv = cv2.cvtColor(cv2.GaussianBlur(frame[y0:y1, x0:x1], (5, 5), 0),
                       cv2.COLOR_BGR2HSV)
    found = []
    for color, ranges in TOKEN_HSV.items():
        in_range = np.zeros(hsv.shape[:2], np.uint8)
        for low, high in ranges:
            in_range |= cv2.inRange(hsv, low, high)
        in_range &= mask
        in_range = cv2.morphologyEx(in_range, cv2.MORPH_OPEN, KERNEL)
        in_range = cv2.morphologyEx(in_range, cv2.MORPH_CLOSE, KERNEL,
                                    iterations=2)
        # Closing can bridge a token to tape beside it; open again to cut
        # such thin bridges.
        in_range = cv2.morphologyEx(in_range, cv2.MORPH_OPEN, KERNEL)
        contours, _ = cv2.findContours(in_range, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if area < MIN_AREA or perimeter == 0:
                continue
            (x, y), radius = cv2.minEnclosingCircle(contour)
            if not MIN_RADIUS <= radius <= MAX_RADIUS:
                continue
            if 4 * np.pi * area / perimeter ** 2 < MIN_CIRCULARITY:
                continue
            if area / (np.pi * radius ** 2) < MIN_FILL:
                continue
            found.append((area, color, x + x0, y + y0, radius))

    # A blob can match two overlapping ranges, or one range twice; keep
    # only the largest match at each spot.
    tokens = []
    for _, color, x, y, radius in sorted(found, reverse=True):
        if all(np.hypot(x - tx, y - ty) > max(radius, tr)
               for _, tx, ty, tr in tokens):
            tokens.append((color, x, y, radius))
    return tokens


class TokenZones:
    """Locks the arena, then counts the tokens in each base and guess zone."""

    def __init__(self):
        self.detect_tags = make_detector()
        self.homography = None  # Camera pixels to arena centimetres
        self.inverse = None
        self.guess_centers = {}
        self.missing = list(CORNER_IDS)
        self.stray = []  # Corner IDs only seen on a tag too small for one
        self.corners_since = None  # When all four corners came into view
        self.confirmed = defaultdict(int)  # (zone, team, color) to a count
        self.pending = {}  # (zone, team, color) to (count, seen since)
        self.events = deque(maxlen=MAX_EVENTS)
        self.started = time.time()
        # Called as listener(zone, team, color, old_count, new_count).
        self.listeners = []
        self.keys_hint = 'space re-lock   s save   q quit'
        # Corner to the name its zones are labelled with. None labels every
        # corner by its number; otherwise corners left out are greyed.
        self.names = None

    def to_arena(self, points):
        return cv2.perspectiveTransform(
            np.float32(points).reshape(-1, 1, 2), self.homography
        ).reshape(-1, 2)

    def to_camera(self, points):
        return cv2.perspectiveTransform(
            np.float32(points).reshape(-1, 1, 2), self.inverse
        ).reshape(-1, 2)

    def unlock(self):
        self.homography = None
        self.corners_since = None

    def lock(self, frame):
        """Lock the arena once all four corner tags have stayed in view.

        Waiting a moment keeps it from locking onto a corner tag that is
        still being put down.
        """
        corners, ids = self.detect_tags(
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        tags = []
        if ids is not None:
            tags = [(int(i), c[0]) for c, i in zip(corners, ids.flatten())]
        corner_tags = largest_tags(tags, CORNER_IDS)
        self.missing = [i for i in CORNER_IDS if i not in corner_tags]
        self.stray = [] if self.missing else stray_corners(corner_tags)
        if self.missing or self.stray:
            self.corners_since = None
            return
        if self.corners_since is None:
            self.corners_since = time.time()
        if time.time() - self.corners_since < LOCK_S:
            return

        length = ARENA_CM
        self.homography = cv2.getPerspectiveTransform(
            np.float32([corner_tags[i][0] for i in CORNER_IDS]),
            np.float32([[0, 0], [length, 0], [length, length], [0, length]]))
        self.inverse = np.linalg.inv(self.homography)

        # A guess zone tag counts only on the arena, and if its ID is seen
        # twice, as when the old corner tag 4 lies about, the smaller one.
        self.guess_centers = {
            team: np.float32(center)
            for team, center in GUESS_DEFAULTS.items()}
        sizes = {}
        for tag_id, points in tags:
            team = GUESS_TAG_TEAMS.get(tag_id)
            center = self.to_arena(points).mean(axis=0)
            size = cv2.contourArea(points)
            on_arena = all(0 <= v <= length for v in center)
            if team is None or not on_arena or size > sizes.get(team, size):
                continue
            sizes[team] = size
            self.guess_centers[team] = center
        from_tags = list(sizes)

        # Only look for tokens on the arena, to skip things around it.
        edge = EDGE_CM
        outline = self.to_camera([[-edge, -edge], [length + edge, -edge],
                                  [length + edge, length + edge],
                                  [-edge, length + edge]])
        x, y, w, h = cv2.boundingRect(np.int32(outline))
        x0, y0 = max(x, 0), max(y, 0)
        x1 = min(x + w, frame.shape[1])
        y1 = min(y + h, frame.shape[0])
        self.roi = (x0, y0, x1, y1)
        self.mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillPoly(self.mask, [np.int32(outline - (x0, y0))], 255)

        defaults = sorted(set(GUESS_DEFAULTS) - set(from_tags))
        note = f', default spot for teams {defaults}' if defaults else ''
        self.log(f'Arena locked, guess zones from tags{note}')

    def zone_of(self, point):
        """Return ('base' or 'guess', team) for a point in centimetres."""
        for team, corner in BASE_CORNERS.items():
            if np.hypot(*(point - corner)) <= BASE_RADIUS_CM:
                return 'base', team
        for team, center in self.guess_centers.items():
            if np.hypot(*(point - center)) <= GUESS_RADIUS_CM:
                return 'guess', team
        return None

    def update(self, frame, now):
        """Find the tokens in one frame, and update the zone counts."""
        placed = []
        seen = defaultdict(int)
        for color, x, y, radius in find_tokens(frame, self.mask, self.roi):
            zone = self.zone_of(self.to_arena([(x, y)])[0])
            placed.append((color, x, y, radius))
            if zone is not None:
                seen[zone + (color,)] += 1
        for key in set(self.confirmed) | set(seen):
            self.settle(key, seen.get(key, 0), now)
        return placed

    def settle(self, key, count, now):
        """Take a zone's new count once it has held long enough."""
        current = self.confirmed[key]
        if count == current:
            self.pending.pop(key, None)
            return
        pending, since = self.pending.get(key, (None, now))
        if pending != count:
            self.pending[key] = (count, now)
            return
        if now - since < (ARRIVE_S if count > current else LEAVE_S):
            return
        self.confirmed[key] = count
        del self.pending[key]

        zone, team, color = key
        if zone == 'base':
            change = count - current
            self.log(f'Team {team} base: {change:+d} {color}, now {count}')
        elif count > current:
            self.log(f'Team {team} guess zone: {color} token arrived')
        else:
            self.log(f'Team {team} guess zone: {color} token left')
        for listener in self.listeners:
            listener(zone, team, color, current, count)

    def log(self, text):
        elapsed = int(time.time() - self.started)
        line = f'{elapsed // 60:02d}:{elapsed % 60:02d}  {text}'
        self.events.appendleft(line)
        print(line, flush=True)

    def counts(self, zone):
        """Return {team: {color: count}} for 'base' or 'guess' zones."""
        return {team: {color: self.confirmed.get((zone, team, color), 0)
                       for color in TOKEN_BGR}
                for team in BASE_CORNERS}

    def draw(self, frame, placed, fps):
        """Return the camera view beside the token counts in each zone."""
        return cv2.hconcat([self.draw_view(frame, placed, fps),
                            self.draw_panel()])

    def draw_view(self, frame, placed, fps):
        """Return the camera view with the zones and tokens drawn on."""
        s = VIEW_HEIGHT / frame.shape[0]
        view = cv2.resize(frame, None, fx=s, fy=s,
                          interpolation=cv2.INTER_AREA)

        names = self.names
        if names is None:
            names = {team: f'T{team}' for team in BASE_CORNERS}
        if self.homography is not None:
            for team, (cx, cy) in BASE_CORNERS.items():
                # Unit steps from this corner into the arena.
                sx = 1 if cx == 0 else -1
                sy = 1 if cy == 0 else -1
                arc = [(cx + sx * BASE_RADIUS_CM * np.cos(a),
                        cy + sy * BASE_RADIUS_CM * np.sin(a))
                       for a in np.linspace(0, np.pi / 2, 20)]
                outline = self.to_camera([(cx, cy)] + arc) * s
                cv2.polylines(view, [np.int32(outline)], True,
                              CYAN if team in names else GRAY, 2)
                # Label the base just outside its corner, clear of the
                # guess zone labels.
                x, y = self.to_camera([(cx - sx * 6, cy - sy * 6)])[0] * s
                if team in names:
                    label(view, f'{names[team]} base', (x - 35, y + 5), CYAN)
            for team, center in self.guess_centers.items():
                circle = [center + GUESS_RADIUS_CM * np.float32(
                    [np.cos(a), np.sin(a)])
                    for a in np.linspace(0, 2 * np.pi, 36, endpoint=False)]
                outline = self.to_camera(circle) * s
                cv2.polylines(view, [np.int32(outline)], True,
                              MAGENTA if team in names else GRAY, 2)
                if team in names:
                    label(view, f'{names[team]} guess',
                          (outline[:, 0].mean() - 40,
                           outline[:, 1].min() - 8), MAGENTA)

        for color, x, y, radius in placed:
            center = (int(x * s), int(y * s))
            ring = int(radius * s) + 5
            cv2.circle(view, center, ring, (0, 0, 0), 4)
            cv2.circle(view, center, ring, TOKEN_BGR[color], 2)

        if self.homography is None and self.missing:
            status = (f'Looking for corner tags, missing {self.missing}', RED)
        elif self.homography is None and self.stray:
            ids = ', '.join(str(i) for i in self.stray)
            status = (f'Tag {ids} too small for a corner: spare copy in view?',
                      RED)
        elif self.homography is None:
            status = ('All corner tags found, locking', CYAN)
        else:
            status = (f'Arena locked   {len(placed)} tokens', CYAN)
        lines = [(f'{fps:4.1f} fps', WHITE), status, (self.keys_hint, WHITE)]
        for row, (text, color) in enumerate(lines):
            label(view, text, (10, VIEW_HEIGHT - 76 + 28 * row), color, 0.7)
        return view

    def draw_panel(self):
        panel = np.full((VIEW_HEIGHT, PANEL_WIDTH, 3), 30, np.uint8)
        label(panel, 'Tokens in zones', (20, 40), WHITE, 0.9)
        y = 95
        for team in BASE_CORNERS:
            label(panel, f'Team {team}', (20, y), WHITE, 0.75)
            label(panel, 'base', (130, y), GRAY)
            for column, color in enumerate(TOKEN_BGR):
                count = self.confirmed.get(('base', team, color), 0)
                label(panel, f'{color[0]} {count}', (190 + 62 * column, y),
                      TOKEN_BGR[color] if count else GRAY, 0.75)
            guesses = [color for color in TOKEN_BGR
                       for _ in range(self.confirmed.get(
                           ('guess', team, color), 0))]
            label(panel, 'guess  ' + (', '.join(guesses) or '-'),
                  (130, y + 32), MAGENTA if guesses else GRAY)
            y += 80
        label(panel, 'Changes', (20, y + 10), WHITE, 0.75)
        for row, line in enumerate(self.events):
            label(panel, line, (20, y + 45 + 26 * row), WHITE, 0.55)
        return panel


def main():
    parser = argparse.ArgumentParser(
        description='Track the tokens in the arena bases and guess zones.')
    parser.add_argument('--device', type=int, default=0,
                        help='camera index (default 0, /dev/video0)')
    args = parser.parse_args()

    camera = open_camera(args.device, 1600, 1200)
    zones = TokenZones()
    window = 'Token zones'
    cv2.namedWindow(window)
    fps = 0.0
    last = time.time()
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
            shown = zones.draw(frame, placed, fps)
            cv2.imshow(window, shown)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            if key == ord(' '):
                zones.unlock()
            elif key == ord('s'):
                path = os.path.abspath(
                    time.strftime('token_zones_%Y%m%d_%H%M%S.jpg'))
                cv2.imwrite(path, shown)
                print('Saved', path)
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
