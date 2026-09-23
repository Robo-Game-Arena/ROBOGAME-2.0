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

    def has_found_every_robot(self):
        return (
            self.expected_robots > 0
            and len(self.links) >= self.expected_robots
        )

    async def discovery_loop(self):
        while self.running:
            if self.has_found_every_robot():
                self.logger.info(
                    f"All {self.expected_robots} robots found, "
                    "stopping discovery"
                )
                return

            found_new_robot = await self.scan_once()

            if found_new_robot:
                self.current_scan_period = self.scan_period
            else:
                self.current_scan_period = min(
                    self.current_scan_period * 2,
                    self.max_scan_period
                )

            await asyncio.sleep(self.current_scan_period)

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

        found_new_robot = False

        for device, advertisement in found.values():
            name = advertisement.local_name or device.name
            robot_id = parse_robot_id(name, self.name_prefix)

            if robot_id is None:
                self.logger.warning(
                    f"Ignoring BLE device with unexpected name: {name!r}"
                )
                continue

            if robot_id in self.links:
                known_link = self.links[robot_id]

                if known_link.address != device.address:
                    self.logger.warning(
                        f"Two boards are advertising as robot {robot_id}: "
                        f"{known_link.address} and {device.address}. "
                        "Flash each board from its own environment so that "
                        "every robot has a unique name."
                    )
                    continue

                known_link.update_device(device)
                continue

            self.add_robot(robot_id, device)
            found_new_robot = True

        return found_new_robot

    def add_robot(self, robot_id, device):
        self.logger.info(
            f"Discovered robot {robot_id} at {device.address}"
        )

        link = BleRobotLink(
            robot_id=robot_id,
            device=device,
            characteristic_uuid=self.characteristic_uuid,
            logger=self.logger,
            radio_lock=self.radio_lock
        )

        self.links[robot_id] = link
        self.link_tasks[robot_id] = [
            self.event_loop.create_task(link.keep_connected()),
            self.event_loop.create_task(link.write_pending_commands()),
        ]

        if self.on_robot_found is not None:
            self.on_robot_found(robot_id)

    def send(self, robot_id, command):
        link = self.links.get(robot_id)

        if link is None or not self.running:
            return

        self.event_loop.call_soon_threadsafe(link.queue_command, command)

    async def shutdown_all(self):
        self.running = False

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
