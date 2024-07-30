import time
from dataclasses import dataclass
from collections import defaultdict
from abc import ABC, abstractmethod
from .db_utils import DBUtils

# ClientConfig: TypeAlias = Dict[str, str]
@dataclass
class DeviceTypeRequest:
    """Class to represent a device type request"""
    device_type: str
    count: int

class DeployerBase(ABC):
    """
        Abstract class for deployers.
        Ideally, all invocations to DB should go through a common interface.
        See functions: register_client_in_db, get_available_devices_by_type
    """
    def __init__(self, config, test_env=False):
        self.db_utils = DBUtils()
        self.config = config
        self.test_env = test_env

    def start(self):
        """ Start the deployment process """
        self.prepare_deployment()
        job_id = self.db_utils.create_job(self.config)
        self.deploy_setup(job_id)

        return job_id

    @abstractmethod
    def prepare_deployment(self):
        """
            Make necessary preparations before deployment
            SBC: containerize the app and push it to the container registry
            Android: creating the apk and push it to the devices
        """

    @abstractmethod
    def deploy_setup(self, job_id: int):
        """
            Initiate the actual deployment process.
            SBC: launch kubernetes pods
            Android: start app
        """

    @abstractmethod
    def wait_for_devices(self, job_id: int):
        """
            Wait for devices to finish
        """

    def register_client_in_db(self, client_id: int, dev_id: int, job_id: int) -> str:
        """ Register client in DB """
        return self.db_utils.register_client(client_id, dev_id, job_id)

    def get_available_devices_by_type(self, client_types):
        clients = self.db_utils.get_current_available_clients(client_types)

        available_devices_by_type = defaultdict(list)
        for (dev_id, dev_hostname, dev_type) in clients:
            available_devices_by_type[dev_type].append((dev_id, dev_hostname))

        return available_devices_by_type

    def wait_for_job(self, job_id):
        """ Hand until job is finished and mark job as finished """
        # Give some buffer for experiment launch
        time.sleep(1)
        self.wait_for_devices(job_id)
        self.db_utils.finish_job(job_id)
