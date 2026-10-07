import struct

DRIVE_FORWARD = "F"
DRIVE_BACKWARD = "B"
TURN_LEFT = "L"
TURN_RIGHT = "R"
STOP = "S"
SPEED = "V"

SHOULDER_UP = "+"
SHOULDER_DOWN = "-"
ELBOW_UP = "X"
ELBOW_DOWN = "H"
GRIPPER_OPEN = "o"
GRIPPER_CLOSE = "c"

DRIVE_COMMANDS = frozenset({
    DRIVE_FORWARD,
    DRIVE_BACKWARD,
    TURN_LEFT,
    TURN_RIGHT,
    STOP,
})

ARM_COMMANDS = frozenset({
    SHOULDER_UP,
    SHOULDER_DOWN,
    ELBOW_UP,
    ELBOW_DOWN,
    GRIPPER_OPEN,
    GRIPPER_CLOSE,
})


def twist_to_drive_command(linear_x, angular_z, linear_threshold,
                           angular_threshold):
    if linear_x > linear_threshold:
        return DRIVE_FORWARD

    if linear_x < -linear_threshold:
        return DRIVE_BACKWARD

    if angular_z > angular_threshold:
        return TURN_LEFT

    if angular_z < -angular_threshold:
        return TURN_RIGHT

    return STOP


def clamp_percent(value):
    return max(-100, min(100, int(round(value))))


def speed_command(forward_percent, turn_percent):
    # V followed by the forward speed and the turn as signed bytes, each a
    # percentage from -100 to 100. A positive turn turns left.
    return struct.pack(
        "<cbb",
        SPEED.encode("ascii"),
        clamp_percent(forward_percent),
        clamp_percent(turn_percent)
    )


def twist_to_speed_command(linear_x, angular_z, full_linear_speed,
                           full_angular_speed):
    return speed_command(
        100.0 * linear_x / full_linear_speed,
        100.0 * angular_z / full_angular_speed
    )


def describe_drive_command(command):
    if len(command) == 3 and command[:1] == SPEED.encode("ascii"):
        _, forward, turn = struct.unpack("<cbb", command)
        return f"speed {forward}% forward, {turn}% turn"

    return command.decode("ascii")
