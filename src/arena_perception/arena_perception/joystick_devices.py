import glob
import os

SYSFS_INPUT_PATH = "/sys/class/input"


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
