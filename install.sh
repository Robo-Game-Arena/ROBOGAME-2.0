#!/usr/bin/env bash
set -euo pipefail

ROS_DISTRO_NAME="jazzy"
WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROS_SETUP="/opt/ros/${ROS_DISTRO_NAME}/setup.bash"

log() {
    echo ""
    echo ">> $1"
}

fail() {
    echo "error: $1" >&2
    exit 1
}

require_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        SUDO=""
        return
    fi

    command -v sudo >/dev/null 2>&1 || fail "sudo is required but not installed"
    SUDO="sudo"
}

require_ubuntu() {
    [ -f /etc/os-release ] || fail "cannot detect the operating system"

    . /etc/os-release

    if [ "${ID}" != "ubuntu" ]; then
        fail "this script installs ROS2 ${ROS_DISTRO_NAME} on Ubuntu. Detected ${PRETTY_NAME}. Install ROS2 manually, then run this script again."
    fi
}

install_ros() {
    if [ -f "${ROS_SETUP}" ]; then
        log "ROS2 ${ROS_DISTRO_NAME} is already installed"
        return
    fi

    require_ubuntu

    log "Installing ROS2 ${ROS_DISTRO_NAME}"

    $SUDO apt-get update
    $SUDO apt-get install -y software-properties-common curl
    $SUDO add-apt-repository -y universe

    $SUDO curl -sSL \
        https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME}") main" \
        | $SUDO tee /etc/apt/sources.list.d/ros2.list >/dev/null

    $SUDO apt-get update
    $SUDO apt-get install -y "ros-${ROS_DISTRO_NAME}-ros-base"

    [ -f "${ROS_SETUP}" ] || fail "ROS2 ${ROS_DISTRO_NAME} installation did not complete"
}

install_tools() {
    if ! command -v apt-get >/dev/null 2>&1; then
        log "Skipping apt packages, this system does not use apt"
        echo "Make sure colcon, rosdep, bleak, opencv, numpy and the joy package are installed"
        return
    fi

    log "Installing build tools and runtime dependencies"

    $SUDO apt-get update

    $SUDO apt-get install -y \
        python3-colcon-common-extensions \
        python3-rosdep \
        python3-bleak \
        python3-opencv \
        python3-numpy \
        "ros-${ROS_DISTRO_NAME}-joy"
}

install_bleak_fallback() {
    if python3 -c "import bleak" >/dev/null 2>&1; then
        return
    fi

    log "Installing bleak with pip"

    pip3 install --user --break-system-packages bleak \
        || fail "could not install bleak. Install it manually, then run this script again."
}

resolve_dependencies() {
    log "Resolving package dependencies with rosdep"

    if [ ! -d /etc/ros/rosdep/sources.list.d ]; then
        $SUDO rosdep init
    fi

    rosdep update

    set +u
    . "${ROS_SETUP}"
    set -u

    rosdep install \
        --from-paths "${WORKSPACE_DIR}/src" \
        --ignore-src \
        --rosdistro "${ROS_DISTRO_NAME}" \
        -r -y
}

build_workspace() {
    log "Building the workspace"

    cd "${WORKSPACE_DIR}"

    set +u
    . "${ROS_SETUP}"
    set -u

    colcon build --symlink-install
}

print_next_steps() {
    log "Done"

    echo ""
    echo "Source the workspace in every new shell:"
    echo "    source ${ROS_SETUP}"
    echo "    source ${WORKSPACE_DIR}/install/setup.bash"
    echo ""
    echo "Then start the bridge and a controller:"
    echo "    ros2 launch arena_perception robot_control.launch.py"
    echo ""
}

require_sudo
install_ros
install_tools
install_bleak_fallback
resolve_dependencies
build_workspace
print_next_steps
