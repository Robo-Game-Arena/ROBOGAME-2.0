import os
import re

from ament_index_python.packages import get_package_share_directory

import yaml

ADDRESS_PATTERN = re.compile(r"^[0-9A-F]{2}(:[0-9A-F]{2}){5}$")

HEADER = """\
# Which PS4 controller drives which robot.
#
# Robot N is the board flashed with `pio run -e robot_N`, which advertises
# itself as Robogame-N. Robot 0 is the instructor's. Each controller is
# listed by its Bluetooth address, so it always drives the same robot
# whatever order the controllers connect in. Keep the addresses in quotes.
#
# Update this file by pressing a button on each controller in turn:
#     ros2 run arena_perception assign_controllers 0 1 2 3 4 5 6
"""


def default_controllers_file():
    return os.path.join(
        get_package_share_directory("arena_perception"),
        "config",
        "controllers.yaml"
    )


def normalize_address(address):
    return address.strip().upper()


def load_controller_addresses(path):
    with open(path) as config_file:
        config = yaml.safe_load(config_file) or {}

    robots = config.get("robots") or {}
    addresses = {}

    for robot_id, address in robots.items():
        if not isinstance(robot_id, int) or robot_id < 0:
            raise ValueError(
                f"{path}: robot ids must be whole numbers from 0, "
                f"got {robot_id!r}"
            )

        if not isinstance(address, str):
            raise ValueError(
                f"{path}: put the address for robot {robot_id} in quotes"
            )

        address = normalize_address(address)

        if not ADDRESS_PATTERN.match(address):
            raise ValueError(
                f"{path}: {address!r} for robot {robot_id} is not a "
                "Bluetooth address like A0:5A:5E:EE:F8:FA"
            )

        if address in addresses.values():
            raise ValueError(
                f"{path}: controller {address} is listed for more than one "
                "robot"
            )

        addresses[robot_id] = address

    return addresses


def write_controller_addresses(path, addresses):
    lines = [HEADER, "robots:"]

    for robot_id in sorted(addresses):
        lines.append(f'  {robot_id}: "{addresses[robot_id]}"')

    with open(path, "w") as config_file:
        config_file.write("\n".join(lines) + "\n")
