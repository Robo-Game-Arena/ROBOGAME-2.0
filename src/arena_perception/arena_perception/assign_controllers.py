import argparse
import os
import select

from arena_perception.controller_config import (
    default_controllers_file,
    load_controller_addresses,
    write_controller_addresses,
)
from arena_perception.joystick_devices import (
    find_joystick_devices,
    JoystickDisconnected,
    JS_EVENT_BUTTON,
    open_joystick,
    read_joystick_events,
)


def open_controllers():
    controllers = {}

    for device in find_joystick_devices():
        if not device.address:
            print(f"Skipping {device.describe()}, it has no address")
            continue

        try:
            controllers[open_joystick(device)] = device
        except OSError as error:
            print(f"Cannot open {device.path}: {error.strerror}")

    return controllers


def wait_for_button_press(controllers):
    while controllers:
        readable, _, _ = select.select(list(controllers), [], [])

        for file_descriptor in readable:
            try:
                events = read_joystick_events(file_descriptor)
            except JoystickDisconnected:
                print(f"  {controllers[file_descriptor].address} disconnected")
                os.close(file_descriptor)
                del controllers[file_descriptor]
                continue

            for event_type, _, value in events:
                if event_type == JS_EVENT_BUTTON and value == 1:
                    return file_descriptor

    return None


def load_existing_addresses(path):
    if not os.path.exists(path):
        return {}

    try:
        return load_controller_addresses(path)
    except (OSError, ValueError) as error:
        print(f"Replacing the current assignments, they could not be read: "
              f"{error}")
        return {}


def main():
    parser = argparse.ArgumentParser(
        description="Choose which PS4 controller drives each robot by "
                    "pressing a button on each controller in turn. Robots "
                    "that are not named keep their current controller."
    )
    parser.add_argument(
        "robots",
        nargs="*",
        type=int,
        metavar="ROBOT",
        help="robot numbers, in the order their controllers will be pressed "
             "(default: 1, 2, 3, ... one per connected controller)"
    )
    parser.add_argument(
        "--file",
        default=os.path.realpath(default_controllers_file()),
        help="controller file to update (default: %(default)s)"
    )
    arguments = parser.parse_args()

    if any(robot_id < 0 for robot_id in arguments.robots):
        parser.error("robot numbers start at 0")

    if len(set(arguments.robots)) != len(arguments.robots):
        parser.error("each robot number can only be given once")

    controllers = open_controllers()

    if not controllers:
        print(
            "No controllers connected. Turn each one on with its PS button, "
            "then run this again."
        )
        return 1

    robot_ids = arguments.robots or list(range(1, len(controllers) + 1))

    print(f"Found {len(controllers)} controller(s).")
    print("Press any button on the controller for each robot in turn.")
    print("Ctrl+C stops without changing anything.")

    assigned = {}

    try:
        for robot_id in robot_ids:
            if not controllers:
                print(f"No controller left for robot {robot_id}")
                break

            print(f"Robot {robot_id}: press a button on its controller")

            file_descriptor = wait_for_button_press(controllers)

            if file_descriptor is None:
                break

            device = controllers.pop(file_descriptor)
            os.close(file_descriptor)

            assigned[robot_id] = device.address
            print(f"  robot {robot_id} -> {device.address}")

    except KeyboardInterrupt:
        print("\nStopped, nothing written")
        return 1

    if not assigned:
        print("No controllers assigned, nothing written")
        return 1

    # A controller drives one robot, so a controller that was moved to a new
    # robot is taken off its old one.
    existing = load_existing_addresses(arguments.file)
    addresses = {
        robot_id: address
        for robot_id, address in existing.items()
        if address not in assigned.values()
    }
    addresses.update(assigned)

    for robot_id in sorted(set(existing) - set(addresses)):
        print(f"Robot {robot_id} no longer has a controller")

    write_controller_addresses(arguments.file, addresses)

    print(f"Wrote {arguments.file}:")

    for robot_id in sorted(addresses):
        print(f"  robot {robot_id} -> {addresses[robot_id]}")

    print("Restart robot_control.launch.py to use the new assignments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
