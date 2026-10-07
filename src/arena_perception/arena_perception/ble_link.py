import asyncio

from bleak import BleakClient

# A write without response carries at most 20 bytes on a default BLE link,
# so arm commands waiting to be sent are capped well below that.
MAX_PENDING_ARM_COMMANDS = 8


class BleRobotLink:

    def __init__(
        self,
        robot_id,
        device,
        characteristic_uuid,
        logger,
        radio_lock,
        on_connect_failed=None,
        min_write_interval=0.05
    ):
        self.robot_id = robot_id
        self.device = device
        self.characteristic_uuid = characteristic_uuid
        self.logger = logger
        self.radio_lock = radio_lock
        self.on_connect_failed = on_connect_failed
        self.min_write_interval = min_write_interval

        self.client = None
        self.running = True

        # BlueZ forgets a device shortly after it stops advertising, so a
        # handle from an old scan cannot be reconnected. This is set whenever
        # a scan sees the robot advertising, and cleared when connecting
        # fails, so the link waits for a fresh handle instead of retrying a
        # stale one forever.
        self.device_seen = asyncio.Event()
        self.device_seen.set()

        # Only the newest drive command matters, so a new one replaces any
        # that has not been sent yet. Arm commands each move a joint one
        # step, so they are kept and sent in order.
        self.pending_drive_command = None
        self.pending_arm_commands = bytearray()
        self.command_ready = asyncio.Event()

    @property
    def address(self):
        return self.device.address

    def update_device(self, device):
        self.device = device
        self.device_seen.set()

    def is_connected(self):
        return self.client is not None and self.client.is_connected

    def queue_drive_command(self, command):
        self.pending_drive_command = command
        self.command_ready.set()

    def queue_arm_command(self, command):
        if len(self.pending_arm_commands) >= MAX_PENDING_ARM_COMMANDS:
            return

        self.pending_arm_commands += command
        self.command_ready.set()

    async def write_pending_commands(self):
        while self.running:
            await self.command_ready.wait()
            self.command_ready.clear()

            # The robot runs every command in a write in order, so the drive
            # command and any arm commands go out together.
            payload = (self.pending_drive_command or b"") \
                + bytes(self.pending_arm_commands)

            self.pending_drive_command = None
            self.pending_arm_commands.clear()

            if not payload:
                continue

            await self.write_command(payload)

            # Commands that arrive meanwhile are merged into the next write,
            # so a fast stick cannot queue writes faster than the radio sends
            # them.
            await asyncio.sleep(self.min_write_interval)

    async def keep_connected(self):
        while self.running:
            if self.is_connected():
                await asyncio.sleep(1.0)
                continue

            await self.device_seen.wait()

            if await self.connect_once():
                continue

            self.device_seen.clear()

            if self.on_connect_failed is not None:
                self.on_connect_failed(self.robot_id)

    async def connect_once(self):
        async with self.radio_lock:
            self.logger.info(
                f"Connecting to robot {self.robot_id} at {self.address}"
            )

            client = BleakClient(
                self.device,
                disconnected_callback=self.on_disconnected
            )

            try:
                await client.connect()
            except Exception as error:
                self.logger.error(
                    f"Robot {self.robot_id} connection failed, waiting for "
                    f"it to advertise again: "
                    f"{str(error) or type(error).__name__}"
                )
                return False

        self.client = client

        self.logger.info(f"Connected to robot {self.robot_id}")
        return True

    def on_disconnected(self, client):
        self.logger.warning(f"Robot {self.robot_id} disconnected")
        self.client = None

    async def write_command(self, command):
        if not self.is_connected():
            return False

        try:
            await self.client.write_gatt_char(
                self.characteristic_uuid,
                command,
                response=False
            )
            return True

        except Exception as error:
            self.logger.error(
                f"Robot {self.robot_id} rejected {command!r}: {error}"
            )
            return False

    async def shutdown(self):
        self.running = False
        self.command_ready.set()

        if not self.is_connected():
            return

        await self.write_command(b"S")

        try:
            await self.client.disconnect()
        except Exception as error:
            self.logger.error(
                f"Robot {self.robot_id} disconnect failed: {error}"
            )
