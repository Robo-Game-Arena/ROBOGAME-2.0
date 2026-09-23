import asyncio

from bleak import BleakClient


class BleRobotLink:

    def __init__(
        self,
        robot_id,
        device,
        characteristic_uuid,
        logger,
        radio_lock,
        retry_period=3.0
    ):
        self.robot_id = robot_id
        self.device = device
        self.characteristic_uuid = characteristic_uuid
        self.logger = logger
        self.radio_lock = radio_lock
        self.retry_period = retry_period

        self.client = None
        self.running = True

        self.pending_command = None
        self.command_ready = asyncio.Event()

    @property
    def address(self):
        return self.device.address

    def update_device(self, device):
        self.device = device

    def is_connected(self):
        return self.client is not None and self.client.is_connected

    def queue_command(self, command):
        self.pending_command = command
        self.command_ready.set()

    async def write_pending_commands(self):
        while self.running:
            await self.command_ready.wait()
            self.command_ready.clear()

            command = self.pending_command
            self.pending_command = None

            if command is None:
                continue

            await self.write_command(command)

    async def keep_connected(self):
        while self.running:
            if self.is_connected():
                await asyncio.sleep(1.0)
                continue

            await self.connect_once()

    async def connect_once(self):
        try:
            self.logger.info(
                f"Connecting to robot {self.robot_id} at {self.address}"
            )

            client = BleakClient(
                self.device,
                disconnected_callback=self.on_disconnected
            )

            async with self.radio_lock:
                await client.connect()

            self.client = client

            self.logger.info(f"Connected to robot {self.robot_id}")

        except Exception as error:
            self.logger.error(
                f"Robot {self.robot_id} connection failed: {error}"
            )
            self.client = None
            await asyncio.sleep(self.retry_period)

    def on_disconnected(self, client):
        self.logger.warning(f"Robot {self.robot_id} disconnected")
        self.client = None

    async def write_command(self, command):
        if not self.is_connected():
            return False

        try:
            await self.client.write_gatt_char(
                self.characteristic_uuid,
                command.encode("utf-8"),
                response=False
            )
            return True

        except Exception as error:
            self.logger.error(
                f"Robot {self.robot_id} rejected '{command}': {error}"
            )
            return False

    async def shutdown(self):
        self.running = False
        self.command_ready.set()

        if not self.is_connected():
            return

        await self.write_command("S")

        try:
            await self.client.disconnect()
        except Exception as error:
            self.logger.error(
                f"Robot {self.robot_id} disconnect failed: {error}"
            )
