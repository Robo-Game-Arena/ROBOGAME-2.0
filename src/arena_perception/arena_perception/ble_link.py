import asyncio
import threading

from bleak import BleakClient, BleakScanner


class BleRobotLink:

    def __init__(
        self,
        device_name,
        characteristic_uuid,
        logger,
        scan_timeout=10.0,
        retry_period=3.0
    ):
        self.device_name = device_name
        self.characteristic_uuid = characteristic_uuid
        self.logger = logger
        self.scan_timeout = scan_timeout
        self.retry_period = retry_period

        self.client = None
        self.running = False

        self.event_loop = asyncio.new_event_loop()
        self.event_loop_thread = threading.Thread(
            target=self.run_event_loop,
            daemon=True
        )

    def start(self):
        self.running = True
        self.event_loop_thread.start()

        asyncio.run_coroutine_threadsafe(
            self.connection_manager(),
            self.event_loop
        )

    def run_event_loop(self):
        asyncio.set_event_loop(self.event_loop)
        self.event_loop.run_forever()

    def is_connected(self):
        return self.client is not None and self.client.is_connected

    async def connection_manager(self):
        while self.running:
            if self.is_connected():
                await asyncio.sleep(1.0)
                continue

            await self.connect_once()

    async def connect_once(self):
        try:
            self.logger.info(f"Scanning for {self.device_name}...")

            device = await BleakScanner.find_device_by_name(
                self.device_name,
                timeout=self.scan_timeout
            )

            if device is None:
                self.logger.warning(
                    f"{self.device_name} was not found, retrying"
                )
                await asyncio.sleep(self.retry_period)
                return

            self.logger.info(
                f"Found {self.device_name} at {device.address}"
            )

            client = BleakClient(
                device,
                disconnected_callback=self.on_disconnected
            )

            await client.connect()
            self.client = client

            self.logger.info(f"Connected to {self.device_name}")

        except Exception as error:
            self.logger.error(f"BLE connection failed: {error}")
            self.client = None
            await asyncio.sleep(self.retry_period)

    def on_disconnected(self, client):
        self.logger.warning(f"Disconnected from {self.device_name}")
        self.client = None

    def send(self, command):
        if not self.running:
            return

        asyncio.run_coroutine_threadsafe(
            self.write_command(command),
            self.event_loop
        )

    def send_and_wait(self, command, timeout=2.0):
        if not self.running:
            return

        future = asyncio.run_coroutine_threadsafe(
            self.write_command(command),
            self.event_loop
        )

        try:
            future.result(timeout=timeout)
        except Exception:
            pass

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
            self.logger.error(f"Failed to send '{command}': {error}")
            return False

    def stop(self):
        if not self.running:
            return

        if self.is_connected():
            self.send_and_wait("S")

            disconnect_future = asyncio.run_coroutine_threadsafe(
                self.client.disconnect(),
                self.event_loop
            )

            try:
                disconnect_future.result(timeout=3.0)
            except Exception:
                pass

        self.running = False
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.event_loop_thread.join(timeout=3.0)
