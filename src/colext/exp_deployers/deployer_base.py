import sys
import time
import json
from collections import defaultdict
from abc import ABC, abstractmethod
from colext.common.vars import SMART_PLUG_HOST_MAP_FILE
from .db_utils import DBUtils


class DeployerBase(ABC):
    """
        Abstract class for deployers.
        Ideally, all invocations to DB should go through a common interface.
        See functions: register_client_in_db, get_available_devices_by_type
    """
    def __init__(self, config, test_env=False):
        self.config = config
        self.test_env = test_env
        self.launch_only = config['colext']['just_launcher'] == "True"
        self.smart_plug_host_map = get_smart_plug_host_map()

        if not self.launch_only:
            self.db_utils = DBUtils()
            self.check_project_in_db()

    def start(self):
        """ Start the deployment process """
        self.prepare_deployment()
        job_id = self.create_job_in_db()
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
    def wait_for_clients(self, job_id: int):
        """
            Wait for clients to finish
        """

    def check_project_in_db(self):
        if self.launch_only:
            return

        project_name = self.config['project']
        if not self.db_utils.project_exists(project_name):
            print(f"Could not find project named {project_name}. Please use a valid project name.")
            sys.exit(1)

    def create_job_in_db(self):
        if self.launch_only:
            return "14" # Fake placeholder data
        else:
            return self.db_utils.create_job(self.config)

    def register_client_in_db(self, client_id: int, dev_id: int, job_id: int) -> str:
        """ Register client in DB """
        if self.launch_only:
            return "2116" # Fake placeholder data

        return self.db_utils.register_client(client_id, dev_id, job_id)

    def finish_job_in_db(self, job_id):
        if self.launch_only:
            return
        self.db_utils.finish_job(job_id)


    def get_available_devices_by_type(self, client_types):
        clients = self.db_utils.get_current_available_clients(client_types)

        available_devices_by_type = defaultdict(list)
        for (dev_id, dev_hostname, dev_type) in clients:
            available_devices_by_type[dev_type].append((dev_id, dev_hostname))

        return available_devices_by_type

    def wait_for_job(self, job_id):
        """ Hand until job is finished and mark job as finished """
        # Give some buffer for experiment launch
        time.sleep(2)
        self.wait_for_clients(job_id)
        self.finish_job_in_db(job_id)

def get_smart_plug_host_map():
    try:
        with open(SMART_PLUG_HOST_MAP_FILE, encoding='utf-8') as f:
            ip_map = json.load(f)
    except FileNotFoundError:
        ip_map = {}
    except json.JSONDecodeError:
        print("Could not decode json. Try using a json validator tool.")
        raise

    return ip_map

