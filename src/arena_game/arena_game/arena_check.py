#!/usr/bin/env python3
"""Live check of the arena camera, its AprilTags and the arena calibration.

The left half of the window shows the camera with every tag25h9 AprilTag
outlined, and the arena drawn through the outer corners of the four corner
tags. The right half warps the arena to a top-down view with a 10 cm grid,
with tag 3 at (0, 0), tag 2 at (L, 0), tag 1 at (L, L) and tag 0 at (0, L).
That is apriltag_node's frame, though apriltag_node still expects tag 4 at
(0, L), where tag 0 replaced it. If the calibration holds, the grid sits
square on the board, and tags placed symmetrically read symmetric positions.

    ros2 run arena_game arena_check

Keys: space locks the arena outline and then shows how far the corner tags
have moved since, s saves a snapshot, q quits.

It needs no ROS, and runs on OpenCV 4.6 (the NUC) as well as 4.7 and newer.
"""
import argparse
from collections import Counter
import os
import sys
import time

import cv2
import numpy as np

VIEW_HEIGHT = 800  # Height of each half of the window, in screen pixels
MARGIN_CM = 5  # Floor shown around the arena in the top-down view
GRID_CM = 10
DRIFT_WARNING_PX = 3  # Corner movement that means the camera or arena moved

WHITE = (255, 255, 255)
GREEN = (0, 220, 0)
YELLOW = (0, 220, 255)
BLUE = (255, 160, 0)
RED = (0, 0, 255)


def make_detector():
    """Return a function that finds tag25h9 tags in a grayscale image."""
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_25h9)
    # On the NUC, subpixel refinement takes about 10 ms a frame, against
    # about 55 ms for the AprilTag refinement apriltag_node uses.
    if hasattr(cv2.aruco, 'ArucoDetector'):  # OpenCV 4.7 and newer
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        detector = cv2.aruco.ArucoDetector(dictionary, params)
        return lambda gray: detector.detectMarkers(gray)[:2]
    params = cv2.aruco.DetectorParameters_create()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    return lambda gray: cv2.aruco.detectMarkers(
        gray, dictionary, parameters=params)[:2]


def open_camera(device, width, height):
    """Open the arena camera at full frame rate."""
    backend = cv2.CAP_V4L2 if sys.platform.startswith('linux') else cv2.CAP_ANY
    camera = cv2.VideoCapture(device, backend)
    # Uncompressed video manages only 5 fps at 1600x1200, so ask for MJPG,
    # and ask for it before the size.
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    camera.set(cv2.CAP_PROP_FPS, 30)
    if not camera.isOpened():
        sys.exit(f'Could not open camera {device}. '
                 'Close any other program using it, then try again.')
    return camera


def largest_tags(tags, wanted_ids):
    """Return the four points of the largest tag seen for each wanted ID.

    The corner tags are printed larger than any other tag, so if a corner
    ID also turns up on a smaller tag, the corner is still the one taken.
    """
    found = {}
    for tag_id, points in tags:
        if tag_id not in wanted_ids:
            continue
        if tag_id not in found or (
                cv2.contourArea(points) > cv2.contourArea(found[tag_id])):
            found[tag_id] = points
    return found


def stray_corners(corner_tags, ratio=0.65):
    """Return the IDs of corner tags that look too small to be corners.

    The corner tags are all printed the same size, and perspective changes
    their size in the image by about a quarter at most. One much smaller
    than the others is a spare copy of that ID elsewhere in view, such as
    on the desk, taken while the real corner tag was hidden.
    """
    areas = {i: cv2.contourArea(p) for i, p in corner_tags.items()}
    return [i for i, area in areas.items()
            if area < ratio * np.median(
                [other for j, other in areas.items() if j != i])]


def label(image, text, origin, color=WHITE, scale=0.6):
    """Draw text with a dark outline, so it reads on the white board."""
    origin = (int(origin[0]), int(origin[1]))
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale,
                (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, scale,
                color, 2, cv2.LINE_AA)


class ArenaCheck:
    """Draws the camera and top-down views, and holds the arena lock."""

    def __init__(self, corner_ids, arena_cm):
        self.corner_ids = corner_ids
        self.arena_cm = arena_cm
        self.detect = make_detector()
        self.homography = None  # Camera pixels to arena centimetres
        self.seen = {}  # Corner tag ID to that tag's four points
        self.locked = None  # Corner tag ID to arena corner, once locked

        # Arena centimetres to top-down view pixels, leaving a margin.
        self.scale = VIEW_HEIGHT / (arena_cm + 2 * MARGIN_CM)
        offset = self.scale * MARGIN_CM
        self.to_view = np.array([[self.scale, 0, offset],
                                 [0, self.scale, offset],
                                 [0, 0, 1]])

    def find_corners(self, tags):
        """Return the four points of each corner tag in view.

        The corner tags are placed with their first point in the corner of
        the arena.
        """
        return largest_tags(tags, self.corner_ids)

    def is_corner(self, tag_id, points):
        return self.seen.get(tag_id) is points

    def to_arena(self, points):
        """Map camera pixels to arena centimetres."""
        return cv2.perspectiveTransform(
            points.reshape(-1, 1, 2).astype(np.float32),
            self.homography).reshape(-1, 2)

    def view_point(self, arena_point):
        """Map arena centimetres to a pixel in the top-down view."""
        x, y = (np.asarray(arena_point) + MARGIN_CM) * self.scale
        return int(round(x)), int(round(y))

    def toggle_lock(self):
        """Lock the outline to the corners in view, or unlock it."""
        if self.locked is not None:
            self.locked = None
            return 'Arena unlocked'
        if len(self.seen) < 4:
            return 'Cannot lock: not all four corner tags are in view'
        self.locked = {i: self.seen[i][0].copy() for i in self.corner_ids}
        corners = ', '.join(
            f'tag {i} ({p[0]:.0f}, {p[1]:.0f})'
            for i, p in self.locked.items())
        return f'Arena locked with corners at {corners} px'

    def process(self, frame, fps=0.0):
        """Detect the tags in one frame and return the window image."""
        corners, ids = self.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        tags = []
        if ids is not None:
            tags = [(int(i), c[0]) for c, i in zip(corners, ids.flatten())]
        self.seen = self.find_corners(tags)

        if (self.locked is None and len(self.seen) == 4
                and not stray_corners(self.seen)):
            camera_corners = np.float32(
                [self.seen[i][0] for i in self.corner_ids])
            length = self.arena_cm
            arena_corners = np.float32(
                [[0, 0], [length, 0], [length, length], [0, length]])
            self.homography = cv2.getPerspectiveTransform(
                camera_corners, arena_corners)

        return cv2.hconcat([
            self.draw_camera(frame, tags, fps),
            self.draw_top_down(frame, tags),
        ])

    def draw_camera(self, frame, tags, fps):
        s = VIEW_HEIGHT / frame.shape[0]
        view = cv2.resize(frame, None, fx=s, fy=s,
                          interpolation=cv2.INTER_AREA)
        counts = Counter(tag_id for tag_id, _ in tags)

        for tag_id, points in tags:
            text = str(tag_id)
            if self.is_corner(tag_id, points):
                color = BLUE
            else:
                color = RED if counts[tag_id] > 1 else GREEN
                if self.homography is not None:
                    x, y = self.to_arena(points).mean(axis=0)
                    text += f' ({x:.0f}, {y:.0f})'
            cv2.polylines(view, [np.int32(points * s)], True, color, 2)
            label(view, text, (points[:, 0].max() * s + 6,
                               points[:, 1].mean() * s + 6), YELLOW)

        if self.locked is not None:
            outline = [self.locked[i] for i in self.corner_ids]
            cv2.polylines(view, [np.int32(np.array(outline) * s)], True,
                          BLUE, 3)
        elif len(self.seen) == 4:
            outline = [self.seen[i][0] for i in self.corner_ids]
            cv2.polylines(view, [np.int32(np.array(outline) * s)], True,
                          YELLOW, 2)

        lines = [(f'{fps:4.1f} fps   {len(tags)} tags', WHITE)]
        missing = [i for i in self.corner_ids if i not in self.seen]
        if missing:
            lines.append((f'Corner tags not seen: {missing}', RED))
        if self.locked is not None:
            drift = max((np.linalg.norm(self.seen[i][0] - self.locked[i])
                         for i in self.seen), default=0.0)
            color = RED if drift > DRIFT_WARNING_PX else BLUE
            lines.append((f'LOCKED, corners moved {drift:.1f} px', color))
        duplicates = sorted(i for i, n in counts.items() if n > 1)
        if duplicates:
            lines.append((f'Tag IDs seen twice: {duplicates}', RED))
        lines.append(('space lock   s save   q quit', WHITE))
        for row, (text, color) in enumerate(lines):
            label(view, text, (10, 30 + 28 * row), color, 0.7)
        return view

    def draw_top_down(self, frame, tags):
        if self.homography is None:
            view = np.zeros((VIEW_HEIGHT, VIEW_HEIGHT, 3), np.uint8)
            label(view, 'Waiting to see all four corner tags', (20, 40),
                  YELLOW)
            return view

        view = cv2.warpPerspective(frame, self.to_view @ self.homography,
                                   (VIEW_HEIGHT, VIEW_HEIGHT))
        length = self.arena_cm
        for cm in range(0, int(length) + 1, GRID_CM):
            cv2.line(view, self.view_point((cm, 0)),
                     self.view_point((cm, length)), GREEN, 1)
            cv2.line(view, self.view_point((0, cm)),
                     self.view_point((length, cm)), GREEN, 1)
            x, y = self.view_point((cm, 0))
            label(view, str(cm), (x - 8, y - 8), GREEN, 0.4)
            x, y = self.view_point((0, cm))
            label(view, str(cm), (x - 30, y + 4), GREEN, 0.4)
        cv2.rectangle(view, self.view_point((0, 0)),
                      self.view_point((length, length)), BLUE, 2)
        label(view, f'cm, tag {self.corner_ids[0]} at (0, 0)',
              (8, VIEW_HEIGHT - 10), WHITE, 0.45)

        for tag_id, points in tags:
            if self.is_corner(tag_id, points):
                continue
            arena = self.to_arena(points)
            center = arena.mean(axis=0)
            # An arrow through the middle of the tag's top edge shows
            # which way the tag, and later a robot, is facing.
            front = (arena[0] + arena[1]) / 2
            cv2.arrowedLine(view, self.view_point(center),
                            self.view_point(center + 3 * (front - center)),
                            RED, 2, tipLength=0.3)
            x, y = self.view_point(center)
            label(view, f'{tag_id} ({center[0]:.0f}, {center[1]:.0f})',
                  (x + 14, y - 14), YELLOW)
        return view


def main():
    parser = argparse.ArgumentParser(
        description='Live check of the arena camera and its calibration.')
    parser.add_argument('--device', type=int, default=0,
                        help='camera index (default 0, /dev/video0)')
    parser.add_argument('--width', type=int, default=1600)
    parser.add_argument('--height', type=int, default=1200)
    parser.add_argument('--arena-cm', type=float, default=112.0,
                        help='distance between the outer corners of '
                             'neighbouring corner tags (default 112)')
    parser.add_argument('--corners', default='3,2,1,0',
                        help='corner tag IDs at (0, 0), (L, 0), (L, L) and '
                             '(0, L) (default 3,2,1,0)')
    args = parser.parse_args()

    check = ArenaCheck([int(i) for i in args.corners.split(',')],
                       args.arena_cm)
    camera = open_camera(args.device, args.width, args.height)
    print('Camera opened at {}x{}'.format(
        int(camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))))
    print('Keys: space locks or unlocks the arena, s saves a snapshot, '
          'q quits')

    window = 'Arena check'
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

            shown = check.process(frame, fps)
            cv2.imshow(window, shown)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                break
            if key == ord(' '):
                print(check.toggle_lock())
            elif key == ord('s'):
                path = os.path.abspath(
                    time.strftime('arena_check_%Y%m%d_%H%M%S.jpg'))
                cv2.imwrite(path, shown)
                print('Saved', path)
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        camera.release()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
