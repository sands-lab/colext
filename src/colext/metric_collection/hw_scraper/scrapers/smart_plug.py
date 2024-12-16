import os
import asyncio
from tapo import ApiClient

class SmartPlug:
    """
    A plugin for collecting metrics from a smart plug device.
    """
    def __init__(self) -> None:
        """
        Initialize a SmartPlug

        The TAPO_USERNAME, TAPO_PASSWORD and SP_IP_ADDRESS environment variables
        must be set.
        """
        tapo_username = os.getenv("TAPO_USERNAME")
        tapo_password = os.getenv("TAPO_PASSWORD")
        ip_address = os.getenv("SP_IP_ADDRESS")

        if tapo_username is None or tapo_password is None or ip_address is None:
            raise ValueError(
                "SmartPlugPlugin requires the TAPO_USERNAME, TAPO_PASSWORD and SP_IP_ADDRESS "
                "env vars to be set"
            )

        self.client = ApiClient(tapo_username, tapo_password)
        self.asyncio_loop = asyncio.get_event_loop()
        self.device = self.asyncio_loop.run_until_complete(self.client.p110(ip_address))

    def get_power_consumption(self) -> int:
        """
        Retrieves the power consumption of the smart plug device in Milliwatts.
        """

        # Made call sync and we later run it concurrently using ThreadPoolExecutor
        energy_usage = self.asyncio_loop.run_until_complete(self.device.get_energy_usage())
        return energy_usage.current_power
