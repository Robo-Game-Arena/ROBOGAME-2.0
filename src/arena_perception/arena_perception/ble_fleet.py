import asyncio
import threading

from bleak import BleakScanner

from arena_perception.ble_link import BleRobotLink


def parse_robot_id(name, name_prefix):
    if not name:
        return None

    prefix = name_prefix + "-"

    if not name.startswith(prefix):
        return None

    suffix = name[len(prefix):]

    if not suffix.isdigit():
        return None

    return int(suffix)


class BleRobotFleet:

    def __init__(
        self,
        service_uuid,
        characteristic_uuid,
        name_prefix,
        logger,
        on_robot_found=None,
        scan_timeout=3.0,
        scan_period=5.0,
        max_scan_period=60.0,
        expected_robots=0
    ):
        self.service_uuid = service_uuid
        self.characteristic_uuid = characteristic_uuid
        self.name_prefix = name_prefix
        self.logger = logger
        self.on_robot_found = on_robot_found
        self.scan_timeout = scan_timeout
        self.scan_period = scan_period
        self.max_scan_period = max_scan_period
        self.current_scan_period = scan_period
        self.expected_robots = expected_robots

        self.links = {}
        self.link_tasks = {}
        self.running = False
        self.radio_lock = asyncio.Lock()
        self.scan_requested = asyncio.Event()

        self.event_loop = asyncio.new_event_loop()
        self.event_loop_thread = threading.Thread(
            target=self.run_event_loop,
            daemon=True
        )

    def start(self):
        self.running = True
        self.event_loop_thread.start()

        asyncio.run_coroutine_threadsafe(
            self.discovery_loop(),
            self.event_loop
        )

    def run_event_loop(self):
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.run_forever()

    def known_robot_ids(self):
        return sorted(self.links)

    def is_connected(self, robot_id):
        link = self.links.get(robot_id)
        return link is not None and link.is_connected()

    def needs_discovery(self):
        if self.expected_robots <= 0:
            return True

        if len(self.links) < self.expected_robots:
            return True

        return not all(link.is_connected() for link in self.links.values())

    def request_scan(self, robot_id):
        self.current_scan_period = self.scan_period
        self.scan_requested.set()

    async def wait_for_scan_request(self, timeout=None):
        try:
            await asyncio.wait_for(self.scan_requested.wait(), timeout)
        except asyncio.TimeoutError:
            pass

        self.scan_requested.clear()

    async def discovery_loop(self):
        while self.running:
            if not self.needs_discovery():
                self.logger.info(
                    f"All {self.expected_robots} robots connected, "
                    "pausing discovery until one drops"
                )
                await self.wait_for_scan_request()
                continue

            found_robot = await self.scan_once()

            if found_robot:
                self.current_scan_period = self.scan_period
            else:
                self.current_scan_period = min(
                    self.current_scan_period * 2,
                    self.max_scan_period
                )

            await self.wait_for_scan_request(self.current_scan_period)

    async def scan_once(self):
        try:
            async with self.radio_lock:
                found = await BleakScanner.discover(
                    timeout=self.scan_timeout,
                    service_uuids=[self.service_uuid],
                    return_adv=True
                )

        except Exception as error:
            self.logger.error(f"BLE scan failed: {error}")
            return False

        found_robot = False

        for device, advertisement in found.values():
            name = advertisement.local_name or device.name
            robot_id = parse_robot_id(name, self.name_prefix)

            if robot_id is None:
                self.logger.warning(
                    f"Ignoring BLE device with unexpected name: {name!r}"
                )
                continue

            link = self.links.get(robot_id)

            if link is None:
                self.add_robot(robot_id, device)
                found_robot = True
                continue

            if link.address != device.address:
                self.logger.warning(
                    f"Two boards are advertising as robot {robot_id}: "
                    f"{link.address} and {device.address}. "
                    "Flash each board from its own environment so that "
                    "every robot has a unique name."
                )
                continue

            if not link.is_connected():
                self.logger.info(f"Robot {robot_id} is advertising again")
                found_robot = True

            link.update_device(device)

        return found_robot

    def add_robot(self, robot_id, device):
        self.logger.info(
            f"Discovered robot {robot_id} at {device.address}"
        )

        link = BleRobotLink(
            robot_id=robot_id,
            device=device,
            characteristic_uuid=self.characteristic_uuid,
            logger=self.logger,
            radio_lock=self.radio_lock,
            on_connect_failed=self.request_scan
        )

        self.links[robot_id] = link
        self.link_tasks[robot_id] = [
            self.event_loop.create_task(link.keep_connected()),
            self.event_loop.create_task(link.write_pending_commands()),
        ]

        if self.on_robot_found is not None:
            self.on_robot_found(robot_id)

    def running_link(self, robot_id):
        if not self.running:
            return None

        return self.links.get(robot_id)

    def send_drive_command(self, robot_id, command):
        link = self.running_link(robot_id)

        if link is not None:
            self.event_loop.call_soon_threadsafe(
                link.queue_drive_command,
                command
            )

    def send_arm_command(self, robot_id, command):
        link = self.running_link(robot_id)

        if link is not None:
            self.event_loop.call_soon_threadsafe(
                link.queue_arm_command,
                command
            )

    async def shutdown_all(self):
        self.running = False
        self.scan_requested.set()

        for tasks in self.link_tasks.values():
            for task in tasks:
                task.cancel()

        for link in self.links.values():
            await link.shutdown()

    def stop(self):
        if not self.running:
            return

        shutdown_future = asyncio.run_coroutine_threadsafe(
            self.shutdown_all(),
            self.event_loop
        )

        try:
            shutdown_future.result(timeout=5.0)
        except Exception:
            pass

        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.event_loop_thread.join(timeout=3.0)
