DRIVE_FORWARD = "F"
DRIVE_BACKWARD = "B"
TURN_LEFT = "L"
TURN_RIGHT = "R"
STOP = "S"

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
