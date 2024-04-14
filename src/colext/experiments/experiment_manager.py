from dataclasses import dataclass
import os
import copy
import yaml
from .kubernetes_utils import KubernetesUtils
from .db_utils import DBUtils
from jinja2 import Environment, FileSystemLoader
# from typing import TypeAlias
from typing import Dict
from colext.common.vars import REGISTY, STD_DATASETS_PATH, PYTORCH_DATASETS_PATH

from colext.common.logger import log

FL_DEFAULT_SERVER_ADDRESS = "fl-server-svc:80"
# ClientConfig: TypeAlias = Dict[str, str]
# JobConfig: TypeAlias = Dict[str, str]

@dataclass
class DeviceTypeRequest:
    """Class to represent a device type request"""
    device_type: str
    count: int

base_pod_config_by_type = {
    "Generic_CPU": { "image_name": "generic-cpu" },
    "Generic_GPU": { "image_name": "generic-gpu" }, # only supports amd64
    "Jetson":     { "image_name": "jetson", "jetson_dev": True},
}

def get_base_pod_config_by_type(dev_type, config: Dict[str, str]):
    if "Jetson" in dev_type:
        base_pod_config = base_pod_config_by_type["Jetson"]
    elif "Server" in dev_type:
        base_pod_config =  base_pod_config_by_type["Generic_GPU"]
    else:
        base_pod_config =  base_pod_config_by_type["Generic_CPU"]

    pod_config = copy.deepcopy(base_pod_config)
    project_name = config["project"]
    pod_config["image"] =  f"{REGISTY}/{project_name}/{pod_config['image_name']}:latest"
    pod_config["std_datasets_path"] = STD_DATASETS_PATH
    pod_config["pytorch_datasets_path"] = PYTORCH_DATASETS_PATH
    return pod_config

class ExperimentManager():
    def __init__(self) -> None:
        self.k_utils = KubernetesUtils()
        self.db_utils = DBUtils()

        # Get templates
        dirname = os.path.dirname(__file__)
        config_path = os.path.join(dirname, 'microk8s/templates')
        jinja_env = Environment(loader=FileSystemLoader(config_path))
        self.client_template = jinja_env.get_template("client_pod.yaml.jinja")
        self.server_template = jinja_env.get_template("server.yaml.jinja")

        # Get server service
        self.server_service_path = os.path.join(dirname, 'microk8s/server_service.yaml')

    def prepare_server_for_launch(self, job_id, config):
        server_pod_config = get_base_pod_config_by_type("Server", config)

        server_pod_config["job_id"] = job_id
        server_pod_config["n_clients"] = config["n_clients"]
        server_pod_config["entrypoint"] = config["code"]["server"]["entrypoint"]
        server_pod_config["entrypoint_args"] = config["code"]["server"]["args"]

        return server_pod_config

    def get_available_devices_by_type(self, client_types):
        clients = self.db_utils.get_current_available_clients(client_types)
        available_devices_by_type = {}
        for (dev_id, dev_hostname, dev_type) in clients:
            if dev_type not in available_devices_by_type:
                available_devices_by_type[dev_type] = [(dev_id, dev_hostname)]
            else:
                available_devices_by_type[dev_type].append((dev_id, dev_hostname))

        return available_devices_by_type

    def get_device_hostname_by_type(self, curr_available_devices_by_type, device_type):
        try:
            (dev_id, dev_hostname) = curr_available_devices_by_type[device_type].pop()
        except IndexError:
            log.error(f"Not enough {device_type}s available for the request.")
            exit(1)

        return (dev_id, dev_hostname)

    def prepare_clients_for_launch(self, job_id, config):
        client_types_to_generate = config["client_types_to_generate"]
        curr_available_devices_by_type = self.get_available_devices_by_type(client_types_to_generate)

        pod_configs = []
        for client_i, client_type in enumerate(client_types_to_generate):
            pod_config = get_base_pod_config_by_type(client_type, config)
            (dev_id, dev_hostname) = self.get_device_hostname_by_type(curr_available_devices_by_type, client_type)

            pod_config["job_id"] = job_id
            pod_config["client_id"] = client_i
            pod_config["pod_name"] = f"client-{client_i}"
            pod_config["entrypoint"] = config["code"]["client"]["entrypoint"]
            pod_config["entrypoint_args"] = config["code"]["client"]["args"]
            pod_config["client_db_id"] = self.db_utils.register_client(client_i, dev_id, job_id)
            pod_config["dev_type"] = client_type
            pod_config["device_hostname"] = dev_hostname
            pod_config["server_address"] = FL_DEFAULT_SERVER_ADDRESS
            pod_config["monitoring_live_metrics"] = config["monitoring"]["live_metrics"]
            pod_config["monitoring_push_interval"] = config["monitoring"]["push_interval"]
            pod_config["monitoring_scrape_interval"] = config["monitoring"]["scrapping_interval"]

            pod_configs.append(pod_config)

        log.debug(f"Generated {len(pod_configs)} pod configs")
        return pod_configs


    def clear_prev_experiment(self) -> None:
        log.info("Clearing previous experiment")
        self.k_utils.delete_fl_service()
        self.k_utils.delete_experiment_pods()

    def deploy_setup(self, server_pod_config, client_pod_configs) -> None:
        log.info(f"Deploying FL server and service")
        server_pod_dict = yaml.safe_load(self.server_template.render(server_pod_config))
        self.k_utils.create_from_dict(server_pod_dict)
        self.k_utils.create_from_yaml(self.server_service_path)

        log.debug(f"Deploying Client pods")
        for pod_config in client_pod_configs:
            (f"Deploying Client pod = {pod_config}")
            client_pod_dict = yaml.safe_load(self.client_template.render(pod_config))
            self.k_utils.create_from_dict(client_pod_dict)

    def launch_experiment(self, config):
        """
            Launch experiment in kubernetes cluster
            Prepares and deployes client pods and fl service
        """
        self.clear_prev_experiment()

        job_id = self.db_utils.create_job()

        server_pod_config = self.prepare_server_for_launch(job_id, config)
        client_pod_config = self.prepare_clients_for_launch(job_id, config)

        self.deploy_setup(server_pod_config, client_pod_config)

        return job_id

    def wait_for_job(self, job_id, config):
        """ Wait for all pods with label colext-job-id """
        self.k_utils.wait_for_pods(f"colext-job-id={job_id}")
        self.db_utils.finish_job(job_id)

    def retrieve_metrics(self, job_id):
        """ Retrieve client metrics for job_id """
        with open(f"colext_{job_id}_hw_metrics.csv", "wb") as metric_writer:
            self.db_utils.get_hw_metrics(job_id, metric_writer)

        with open(f"colext_{job_id}_round_timestamps.csv", "wb") as metric_writer:
            self.db_utils.get_round_timestamps(job_id, metric_writer)

        with open(f"colext_{job_id}_client_round_timings.csv", "wb") as metric_writer:
            self.db_utils.get_client_round_timings(job_id, metric_writer)

        with open(f"colext_{job_id}_client_info.csv", "wb") as metric_writer:
            self.db_utils.get_client_info(job_id, metric_writer)

