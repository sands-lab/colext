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


# ClientConfig: TypeAlias = Dict[str, str]
# JobConfig: TypeAlias = Dict[str, str]

@dataclass
class DeviceTypeRequest:
    """Class to represent a device type request"""
    device_type: str
    count: int

base_pod_config_by_type = {
    "Server":     { "image_name": "generic" },
    "Lattepanda": { "image_name": "generic" },
    "OrangePi": { "image_name": "generic" },
    "Jetson":     { "image_name": "jetson", "jetson_dev": True},
}

def get_base_pod_config_by_type(dev_type, config: Dict[str, str]):
    if "Jetson" in dev_type:
        base_pod_config = base_pod_config_by_type["Jetson"] 
    else:
        base_pod_config =  base_pod_config_by_type[dev_type]
    
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

    def prepare_server(self, job_id, config):
        server_pod_config = get_base_pod_config_by_type("Server", config)
        
        server_pod_config["job_id"] = job_id
        server_pod_config["n_clients"] = config["n_clients"]
        server_pod_config["image_args"] = config["code"]["server"]["args"]
        server_pod_config["server_entrypoint"] = config["code"]["server"]["entrypoint"]

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

    def prepare_clients(self, job_id, config):
        client_types_to_generate = config["client_types_to_generate"]
        curr_available_devices_by_type = self.get_available_devices_by_type(client_types_to_generate)
        client_image_args = config["code"]["client"]["args"]
        client_entrypoint = config["code"]["client"]["entrypoint"]
        
        clients_to_db = []
        pod_configs = []
        for client_i, client_type in enumerate(client_types_to_generate):
            (dev_id, dev_hostname) = self.get_device_hostname_by_type(curr_available_devices_by_type, client_type)
            pod_config = get_base_pod_config_by_type(client_type, config)
            pod_config["device_hostname"] = dev_hostname
            pod_config["pod_name"] = f"client-{client_i}"
            pod_config["job_id"] = job_id
            pod_config["client_id"] = client_i
            pod_config["client_entrypoint"] = client_entrypoint
            pod_config["image_args"] = client_image_args

            pod_configs.append(pod_config)
            clients_to_db.append((client_i, job_id, dev_id))
        
        log.debug(f"Generated {len(pod_configs)} pod configs")
        return pod_configs, clients_to_db
    
    def update_client_pod_dicts(self, client_pod_dicts, reg_clients):
        reg_clients_dict = {reg_client["client_number"]: reg_client["client_id"] for reg_client in reg_clients}
        for client_pod_dict in client_pod_dicts:
            client_i = client_pod_dict["client_id"]
            client_pod_dict["client_db_id"] = reg_clients_dict[client_i]

    def clear_prev_experiment(self) -> None:
        log.info("Clearing previous experiment")
        self.k_utils.delete_client_pods()
        self.k_utils.delete_fl_service()

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
        self.clear_prev_experiment()

        job_id = self.db_utils.create_job()
        
        server_pod_config = self.prepare_server(job_id, config)

        client_pod_config, clients_to_db = self.prepare_clients(job_id, config)
        registered_client_ids = self.db_utils.register_clients(job_id, clients_to_db)
        self.update_client_pod_dicts(client_pod_config, registered_client_ids)
        
        self.deploy_setup(server_pod_config, client_pod_config)

        return job_id
    
    def wait_for_job(self, job_id, config):
        """ Wait for all pods with label colext-job-id """
        # expected pods = n_clients + 1 server
        expected_pods = config["n_clients"] + 1 
        self.k_utils.wait_for_pods(f"colext-job-id={job_id}", expected_pods)

    def retrieve_metrics(self, job_id):
        """ Retrieve client metrics for job_id """
        with open(f"colext_hw_metrics_job_{job_id}.csv", "wb") as metric_writer:
            self.db_utils.get_metrics(job_id, metric_writer)
        