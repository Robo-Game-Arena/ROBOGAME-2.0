import glob
import os
import struct

SYSFS_INPUT_PATH = "/sys/class/input"

# Each read from /dev/input/jsN returns whole js_event structs from
# linux/joystick.h: a timestamp, a value, a type and an axis or button index.
JS_EVENT_FORMAT = "IhBB"
JS_EVENT_SIZE = struct.calcsize(JS_EVENT_FORMAT)
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80


class JoystickDisconnected(Exception):
    pass


def read_attribute(device_directory, attribute_name):
    try:
        path = os.path.join(device_directory, attribute_name)

        with open(path) as attribute_file:
            return attribute_file.read().strip()

    except OSError:
        return ""


class JoystickDevice:

    def __init__(self, index, path, name, address, physical_port):
        self.index = index
        self.path = path
        self.name = name
        self.address = address
        self.physical_port = physical_port

    @property
    def is_bluetooth(self):
        return bool(self.address)

    def describe(self):
        name = self.name or "unknown device"
        address = self.address if self.address else "wired, no address"

        return f"{self.path} name='{name}' address={address}"


def find_joystick_devices():
    devices = []

    for path in glob.glob("/dev/input/js*"):
        basename = os.path.basename(path)

        if not basename[2:].isdigit():
            continue

        device_directory = os.path.join(SYSFS_INPUT_PATH, basename, "device")

        devices.append(JoystickDevice(
            index=int(basename[2:]),
            path=path,
            name=read_attribute(device_directory, "name"),
            address=read_attribute(device_directory, "uniq").upper(),
            physical_port=read_attribute(device_directory, "phys")
        ))

    devices.sort(key=lambda device: device.index)

    return devices


def find_joystick_device(index):
    for device in find_joystick_devices():
        if device.index == index:
            return device

    return None


def find_joystick_device_by_address(address):
    for device in find_joystick_devices():
        if device.address == address:
            return device

    return None


def open_joystick(device):
    return os.open(device.path, os.O_RDONLY | os.O_NONBLOCK)


def read_joystick_events(file_descriptor, max_events=64):
    try:
        data = os.read(file_descriptor, JS_EVENT_SIZE * max_events)
    except BlockingIOError:
        return []
    except OSError as error:
        raise JoystickDisconnected(error.strerror) from error

    if not data:
        raise JoystickDisconnected("device closed")

    events = []

    for offset in range(0, len(data) - JS_EVENT_SIZE + 1, JS_EVENT_SIZE):
        _, value, event_type, number = struct.unpack_from(
            JS_EVENT_FORMAT,
            data,
            offset
        )
        events.append((event_type, number, value))

    return events


def main():
    devices = find_joystick_devices()

    if not devices:
        print("No joystick devices found under /dev/input")
        return

    print(f"Found {len(devices)} joystick device(s)")

    for device in devices:
        print(f"  joy_device_id:={device.index}  {device.describe()}")


if __name__ == "__main__":
    main()
