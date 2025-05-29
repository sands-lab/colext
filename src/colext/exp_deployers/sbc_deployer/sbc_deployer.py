import os
import json
from importlib.metadata import distribution
import sys
from pathlib import Path
from typing import Dict
from collections import defaultdict
import yaml
from python_on_whales import docker
from jinja2 import Environment, FileSystemLoader

from colext.common.logger import log
from colext.common.vars import REGISTY, STD_DATASETS_PATH, PYTORCH_DATASETS_PATH, SMART_PLUGS_HOST_SP_IP_MAP
from colext.exp_deployers.deployer_base import DeployerBase
from .kubernetes_utils import KubernetesUtils

# from typing import TypeAlias
# JobConfig: TypeAlias = Dict[str, str]

class SBCDeployer(DeployerBase):
    """Deployer for SBC devices"""
    def __init__(self, config, test_env=False) -> None:
        # Creates db_utils and saves init parameters in self
        super().__init__(config, test_env)
        self.k_utils = KubernetesUtils()

        # Get k8s templates
        dirname = os.path.dirname(__file__)
        config_path = os.path.join(dirname, 'microk8s/templates')
        jinja_env = Environment(loader=FileSystemLoader(config_path))
        self.client_template = jinja_env.get_template("client_pod.yaml.jinja")
        self.server_template = jinja_env.get_template("server.yaml.jinja")
        self.server_service_path = os.path.join(dirname, 'microk8s/server_service.yaml')

        # Get Docker bake file dir
        parent_dir = Path(__file__).parent.resolve()
        self.hcl_file_dir = os.path.join(parent_dir, "Dockerfiles", "pip")

    def prepare_deployment(self):
        self.containerize_app(self.config, self. test_env)

    def containerize_app(self, config_dict, test_env):
        project_name = config_dict["project"]
        user_code_path = Path(config_dict["code"]["path"])

        extra_vars = {}
        context = user_code_path
        inheritance_target = "prod-base"
        py38 = str(config_dict["code"]["python_version"] == "3.8")

        # Get CoLExT commit and pass it to the dockerfile to ensure we use the same version
        direct_url_info = json.loads(distribution("colext").read_text("direct_url.json"))
        colext_commit = direct_url_info["vcs_info"]["commit_id"] if "vcs_info" in direct_url_info else "main"
        log.info(f"Using colext commit: {colext_commit}")

        if test_env:
            inheritance_target = "test-base"
            # Testing assumes code from /colext/examples/<folder>
            # We need to go up two levels to set the context to /colext so we can copy the package
            context = user_code_path.parents[1]
            test_rel_dir = user_code_path.parts[-2:]
            extra_vars["TEST_REL_DIR"] = Path(*test_rel_dir)
            assert os.path.isdir(os.path.join(context, "src", "colext")), \
                f"Testing package. Expected to find src/colext dir in '{context}'"

        # Construct targets based on requested device types + Server, which is always there
        server_image = self.get_image_for_dev_type("Server")
        targets = [server_image]
        for dev_type in config_dict["req_dev_types"]:
            dev_image = self.get_image_for_dev_type(dev_type)
            if dev_image not in targets:
                targets.append(dev_image)

        log.info(f"Building containers for {targets=}")
        docker.buildx.bake( targets=targets,
                            files=os.path.join(self.hcl_file_dir, "docker-bake.hcl"),
                            variables={
                                "REGISTY": REGISTY,
                                "PROJECT_NAME": project_name,
                                "CONTEXT": context,
                                "INHERITANCE_TARGET": inheritance_target,
                                "PY38": py38,
                                "COLEXT_COMMIT_HASH": colext_commit,
                                "BAKE_FILE_DIR": self.hcl_file_dir,
                                ** extra_vars
                            },
                            push=True)

    def clear_prev_experiment(self) -> None:
        log.info("Clearing previous experiment")
        self.k_utils.delete_fl_service()
        self.k_utils.delete_experiment_pods()

    def prepare_server_for_launch(self, job_id):
        config = self.config
        server_pod_config = self.get_base_pod_config("Server")

        server_pod_config["job_id"] = job_id
        server_pod_config["n_clients"] = config["n_clients"]
        server_pod_config["command"] = config["code"]["server"]["command"]

        return server_pod_config

    FL_SERVER_ADDRESS = "fl-server-svc:80"
    def prepare_clients_for_launch(self, job_id: int) -> list:
        client_types_to_generate = self.config["req_dev_types"]
        available_devices_by_type = self.get_available_devices_by_type(client_types_to_generate)

        def prepare_client(client_prototype, client_id):
            dev_type = client_prototype["dev_type"]
            pod_config = self.get_base_pod_config(dev_type)
            dev_id, dev_hostname = self.get_device_hostname_by_type(available_devices_by_type, dev_type)
            client_additional_args = client_prototype.get("add_args", "")

            pod_config["job_id"] = job_id
            pod_config["n_clients"] = self.config["n_clients"]
            pod_config["client_id"] = client_id
            pod_config["pod_name"] = f"client-{client_id}"
            pod_config["command"] = f'{self.config["code"]["client"]["command"]} {client_additional_args}'
            pod_config["client_db_id"] = self.register_client_in_db(client_id, dev_id, job_id)
            pod_config["dev_type"] = dev_type
            pod_config["device_hostname"] = dev_hostname
            pod_config["server_address"] = self.FL_SERVER_ADDRESS
            pod_config["monitoring_live_metrics"] = self.config["monitoring"]["live_metrics"]
            pod_config["monitoring_push_interval"] = self.config["monitoring"]["push_interval"]
            pod_config["monitoring_scrape_interval"] = self.config["monitoring"]["scraping_interval"]
            pod_config["monitoring_measure_self"] = self.config["monitoring"]["measure_self"]

            # Add IP of smartplug in case it exists
            pod_config["SP_IP_ADDRESS"] = SMART_PLUGS_HOST_SP_IP_MAP.get(dev_hostname, None)

            return pod_config

        pod_configs = []
        client_id = 0
        for client_prototype in self.config["clients"]:
            for _ in range(client_prototype["count"]):
                pod_configs.append(prepare_client(client_prototype, client_id))
                client_id += 1

        log.debug(f"Generated {len(pod_configs)} pod configs")
        return pod_configs

    IMAGE_BY_DEV_TYPE = {
        "JetsonNano":       "jetson-nano",
        "JetsonAGXOrin":    "jetson",
        "JetsonOrinNano":   "jetson",
        "JetsonXavierNX":   "jetson",
        "Server":           "generic-gpu",     # only supports amd64
        "LattePandaDelta3": "generic-cpu-x86",
        "OrangePi5B":       "generic-cpu-arm",
    }

    def get_image_for_dev_type(self, dev_type: str):
        return self.IMAGE_BY_DEV_TYPE[dev_type]

    def get_base_pod_config(self, dev_type):
        config = self.config
        pod_config = {}
        project_name = config["project"]

        pod_image_name = self.get_image_for_dev_type(dev_type)
        pod_config["image"] =  f"{REGISTY}/{project_name}/{pod_image_name}:latest"
        pod_config["colext_env"] = config["colext"]["monitor_job"]
        pod_config["log_level"] = config["colext"]["log_level"]
        pod_config["std_datasets_path"] = STD_DATASETS_PATH
        pod_config["pytorch_datasets_path"] = PYTORCH_DATASETS_PATH

        return pod_config

    def deploy_setup(self, job_id: int) -> None:
        """
            Launch experiment in kubernetes cluster
            Prepares and deployes client pods and fl service
        """

        self.clear_prev_experiment()

        log.info(f"Deploying FL server and service")
        server_pod_config = self.prepare_server_for_launch(job_id)
        server_pod_dict = yaml.safe_load(self.server_template.render(server_pod_config))
        self.k_utils.create_from_dict(server_pod_dict)
        self.k_utils.create_from_yaml(self.server_service_path)

        log.debug(f"Deploying Client pods")
        client_pod_configs = self.prepare_clients_for_launch(job_id)
        for pod_config in client_pod_configs:
            # log.debug(f"Deploying Client pod = {pod_config}")
            client_pod_dict = yaml.safe_load(self.client_template.render(pod_config))
            self.k_utils.create_from_dict(client_pod_dict)

        log.info(f"Experiment deployed. It can be canceled with 'mk delete pods --all'")

    def get_available_devices_by_type(self, dev_types):
        available_devices_by_type = defaultdict(list)
        for dev_type in dev_types:
            for (dev_id, dev_hostname) in self.k_utils.get_nodes_info_by_type(dev_type):
                available_devices_by_type[dev_type].append((dev_id, dev_hostname))

        return available_devices_by_type

    def get_device_hostname_by_type(self, available_devices_by_type, dev_type):
        try:
            dev_id, dev_hostname = available_devices_by_type[dev_type].pop()
        except IndexError:
            log.error(f"Not enough {dev_type}s available for the request.")
            sys.exit(1)

        return dev_id, dev_hostname

    def wait_for_clients(self, job_id):
        """ Wait for all pods with label colext-job-id """
        print("Note that pods can take up to 10 minutes to start.")
        self.k_utils.wait_for_pods(f"colext-job-id={job_id}")
