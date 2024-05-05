from pathlib import Path
import os
import copy
import yaml
import sys
from python_on_whales import docker
from jinja2 import Environment, FileSystemLoader
# from typing import TypeAlias
from typing import Dict

from colext.common.logger import log
from colext.experiments.db_utils import DBUtils
from colext.experiments.kubernetes_utils import KubernetesUtils
from colext.common.vars import REGISTY, STD_DATASETS_PATH, PYTORCH_DATASETS_PATH

# JobConfig: TypeAlias = Dict[str, str]

class SBCDeploymentHandler:
    def __init__(self, config, test_env) -> None:
        self.config = config
        self.test_env = test_env

        self.k_utils = KubernetesUtils()
        self.db_utils = DBUtils()

        # Get k8s templates
        dirname = os.path.dirname(__file__)
        config_path = os.path.join(dirname, 'microk8s/templates')
        jinja_env = Environment(loader=FileSystemLoader(config_path))
        self.client_template = jinja_env.get_template("client_pod.yaml.jinja")
        self.server_template = jinja_env.get_template("server.yaml.jinja")
        # Configs will be populated once we know the job_id
        self.server_pod_config = {}
        self.client_pod_configs = [{}]
        # Get server service
        self.server_service_path = os.path.join(dirname, 'microk8s/server_service.yaml')

        # Get Docker bake file dir
        parent_dir = Path(__file__).parent.resolve()
        self.hcl_file_dir = os.path.join(parent_dir, "Dockerfiles", "pip_w_install")

    def validate_feasibility(self):
        self.containerize_app(self.config, self. test_env)

    def prepare_deployment(self, job_id):
        self.server_pod_config = self.prepare_server_for_launch(job_id, self.config)
        self.client_pod_configs = self.prepare_clients_for_launch(job_id, self.config)

    def containerize_app(self, config_dict, test_env):
        project_name = config_dict["project"]
        user_code_path = Path(config_dict["code"]["path"])

        target = "default"
        context = user_code_path
        if test_env:
            target = "testing"
            # Testing assumes code from /colext/user_code_example
            # We need to set context to /colext so we can copy the package
            context = os.path.dirname(user_code_path)
            assert os.path.isdir(os.path.join(context, "src", "colext")), \
                f"Testing package. Expected to find src/colext dir in '{context}'"

        docker.buildx.bake( targets=[target],
                            files=os.path.join(self.hcl_file_dir, "docker-bake.hcl"),
                            variables={
                                "REGISTY": REGISTY,
                                "PROJECT_NAME": project_name,
                                "CONTEXT": context,
                                "BAKE_FILE_DIR": self.hcl_file_dir
                            },
                            push=True)

    def prepare_server_for_launch(self, job_id, config):
        server_pod_config = self.get_base_pod_config("Server", config)

        server_pod_config["job_id"] = job_id
        server_pod_config["n_clients"] = config["n_clients"]
        server_pod_config["entrypoint"] = config["code"]["server"]["entrypoint"]
        server_pod_config["entrypoint_args"] = config["code"]["server"]["args"]

        return server_pod_config

    FL_SERVER_ADDRESS = "fl-server-svc:80"
    def prepare_clients_for_launch(self, job_id, config):
        client_types_to_generate = config["client_types_to_generate"]
        curr_available_devices_by_type = self.get_available_devices_by_type(client_types_to_generate)

        pod_configs = []
        for client_i, client_type in enumerate(client_types_to_generate):
            pod_config = self.get_base_pod_config(client_type, config)
            (dev_id, dev_hostname) = self.get_device_hostname_by_type(curr_available_devices_by_type, client_type)

            pod_config["job_id"] = job_id
            pod_config["client_id"] = client_i
            pod_config["pod_name"] = f"client-{client_i}"
            pod_config["entrypoint"] = config["code"]["client"]["entrypoint"]
            pod_config["entrypoint_args"] = config["code"]["client"]["args"]
            pod_config["client_db_id"] = self.db_utils.register_client(client_i, dev_id, job_id)
            pod_config["dev_type"] = client_type
            pod_config["device_hostname"] = dev_hostname
            pod_config["server_address"] = self.FL_SERVER_ADDRESS
            pod_config["monitoring_live_metrics"] = config["monitoring"]["live_metrics"]
            pod_config["monitoring_push_interval"] = config["monitoring"]["push_interval"]
            pod_config["monitoring_scrape_interval"] = config["monitoring"]["scrapping_interval"]

            pod_configs.append(pod_config)

        log.debug(f"Generated {len(pod_configs)} pod configs")
        return pod_configs

    BASE_POD_CONFIG_BY_TYPE = {
        "GenericCPU": { "image_name": "generic-cpu" },
        "GenericGPU": { "image_name": "generic-gpu" }, # only supports amd64
        "Jetson":      { "image_name": "jetson", "jetson_dev": True},
        "JetsonNano": { "image_name": "jetson-nano", "jetson_dev": True},
    }

    def get_base_pod_config(self, dev_type, config: Dict[str, str]):
        pod_type = "GenericCPU"
        if "JetsonNano" == dev_type:
            pod_type = "JetsonNano"
        elif "Jetson" in dev_type:
            pod_type = "Jetson"
        elif "Server" in dev_type:
            pod_type = "GenericGPU"
        base_pod_config = self.BASE_POD_CONFIG_BY_TYPE[pod_type]
        pod_config = copy.deepcopy(base_pod_config)

        project_name = config["project"]
        pod_config["image"] =  f"{REGISTY}/{project_name}/{pod_config['image_name']}:latest"
        pod_config["std_datasets_path"] = STD_DATASETS_PATH
        pod_config["pytorch_datasets_path"] = PYTORCH_DATASETS_PATH

        return pod_config

    def clear_prev_experiment(self) -> None:
        log.info("Clearing previous experiment")
        self.k_utils.delete_fl_service()
        self.k_utils.delete_experiment_pods()

    def deploy_setup(self) -> None:
        """ Launch experiment in kubernetes cluster
            Prepares and deployes client pods and fl service
        """
        log.info(f"Deploying FL server and service")
        server_pod_dict = yaml.safe_load(self.server_template.render(self.server_pod_config))
        self.k_utils.create_from_dict(server_pod_dict)
        self.k_utils.create_from_yaml(self.server_service_path)

        log.debug(f"Deploying Client pods")
        for pod_config in self.client_pod_configs:
            # log.debug(f"Deploying Client pod = {pod_config}")
            client_pod_dict = yaml.safe_load(self.client_template.render(pod_config))
            self.k_utils.create_from_dict(client_pod_dict)

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
            sys.exit(1)

        return (dev_id, dev_hostname)

    def wait_for_job(self, job_id):
        """ Wait for all pods with label colext-job-id """
        self.k_utils.wait_for_pods(f"colext-job-id={job_id}")