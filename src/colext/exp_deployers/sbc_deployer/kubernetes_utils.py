import time
import kubernetes
from typing import Tuple
from colext.common.logger import log
from enum import Enum

FL_NAMESPACE = "default"
FL_NETWORK_NAMESPACE = "default"
FL_SERVICE_PREFIX = "fl-server-svc"

class KubernetesUtils:
    def __init__(self) -> None:
        self.k8s_api, self.k8s_core_v1 = self.get_k8s_clients()

    def get_k8s_clients(self) -> Tuple[kubernetes.client.ApiClient, kubernetes.client.CoreV1Api]:
        MICROK8S_CONFIG_FILE = "/var/snap/microk8s/current/credentials/client.config"
        kubernetes.config.load_kube_config(config_file = MICROK8S_CONFIG_FILE)
        return kubernetes.client.ApiClient(), kubernetes.client.CoreV1Api()

    def get_nodes_info_by_type(self, dev_type: str) -> list:
        nodes = self.k8s_core_v1.list_node(label_selector=f"device-type={dev_type}").items
        return [
            (node.metadata.labels["device-id"], node.metadata.labels["kubernetes.io/hostname"])
            for node in nodes
            if not node.spec.unschedulable
            and node.status.conditions is not None
            and any(cond.type == "Ready" and cond.status == "True" for cond in node.status.conditions)
        ]

    def create_from_yaml(self, yaml_file):
        kubernetes.utils.create_from_yaml(self.k8s_api, yaml_file)

    def create_from_dict(self, dict_obj):
        kubernetes.utils.create_from_dict(self.k8s_api, dict_obj)
    
    def create_config_map(self, name, data_file):
        with open(data_file, 'r') as f:
            data = f.read()

        config_map = kubernetes.client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=kubernetes.client.V1ObjectMeta(name=name),
            data={f"tcconfig_rules.txt": data}
        )
        self.k8s_core_v1.create_namespaced_config_map(FL_NETWORK_NAMESPACE, config_map)

    def create_config_map_from_dict(self, name, folder_path):
        data = {}

        for file_name in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file_name)

            if os.path.isfile(file_path):
                with open(file_path, "r") as f:
                    data[file_name] = f.read()
        config_map = kubernetes.client.V1ConfigMap(
            api_version="v1",
            kind="ConfigMap",
            metadata=kubernetes.client.V1ObjectMeta(name=name),
            data={f"tcconfig_rules.txt": data}
        )
        self.k8s_core_v1.create_namespaced_config_map(FL_NETWORK_NAMESPACE, config_map)



    def delete_config_map(self,name):
        self.k8s_core_v1.delete_namespaced_config_map(name, FL_NETWORK_NAMESPACE)

    def delete_all_config_maps(self):
        configmaps = self.k8s_core_v1.list_namespaced_config_map(FL_NETWORK_NAMESPACE).items

        for configmap in configmaps:
            log.info(f"Deleteing configmap {configmap.metadata.name}")
            self.k8s_core_v1.delete_namespaced_config_map(configmap.metadata.name, FL_NETWORK_NAMESPACE)

    def delete_experiment_pods(self):
            pods = self.k8s_core_v1.list_namespaced_pod(FL_NAMESPACE).items
            pod_names_to_delete = [pod.metadata.name for pod in pods]
            for pod_name in pod_names_to_delete:
                log.info(f"Deleting pod {pod_name}")
                self.k8s_core_v1.delete_namespaced_pod(pod_name, FL_NAMESPACE)

            while pod_names_to_delete:
                for pod_name in pod_names_to_delete:
                    try:
                        self.k8s_core_v1.read_namespaced_pod_status(pod_name, FL_NAMESPACE)
                    except kubernetes.client.rest.ApiException as e:
                        if e.status == 404:
                            log.info(f"Pod {pod_name} was successfully deleted")
                            pod_names_to_delete.remove(pod_name)
                            continue
                        else:
                            log.error(f"Unexpected error while checking pod status for pod {pod_name}")
                            break

                time.sleep(4)

            log.info(f"All pods deleted")

    def delete_fl_service(self):
        services = self.k8s_core_v1.list_namespaced_service(FL_NAMESPACE).items
        services_to_delete = [service.metadata.name for service in services
                              if service.metadata.name.startswith(FL_SERVICE_PREFIX)]

        for service_name in services_to_delete:
                log.info(f"Deleting service {service_name}")
                self.k8s_core_v1.delete_namespaced_service(service_name, FL_NAMESPACE)

        while services_to_delete:
            for service_name in services_to_delete:
                try:
                    self.k8s_core_v1.read_namespaced_service_status(service_name, FL_NAMESPACE)
                except kubernetes.client.rest.ApiException as e:
                    if e.status == 404:
                        log.info(f"Service {service_name} was successfully deleted")
                        services_to_delete.remove(service_name)
                        break
                    else:
                        log.error(f"Unexpected error while checking service status for service {service_name}")

            time.sleep(4)

        log.info(f"All services deleted")


    class _PodCompletionStatus(Enum):
        COMPLETED = 1
        UNAVAILABLE = 2
        ERROR = 3

    def check_if_pod_completed(self, pod_name):
        try:
            container_statuses = self.k8s_core_v1.read_namespaced_pod_status(pod_name, FL_NAMESPACE).status.container_statuses
            if container_statuses is None:
                log.debug(f"Could not read container_status yet. Ignoring pod {pod_name}.")
                return self._PodCompletionStatus.UNAVAILABLE

            client_container_state = container_statuses[0].state
            if client_container_state.terminated is not None:
                if client_container_state.terminated.reason == "Completed":
                    log.info(f"{pod_name} terminated successfully.")
                    return self._PodCompletionStatus.COMPLETED
                else:
                    log.error(f"{pod_name} terminated with reason different than 'Completed'. Reason: {client_container_state.terminated.reason}")
                    return self._PodCompletionStatus.ERROR
            else:
                return self._PodCompletionStatus.UNAVAILABLE

        except kubernetes.client.rest.ApiException as e:
            if e.status == 404:
                log.error(f"{pod_name} pod was deleted while waiting for it. Removing it from the waiting list.")
            else:
                log.error(f"Unexpected error while checking pod status for pod {pod_name}. Error: {e}")
            return self._PodCompletionStatus.ERROR

    def wait_for_pods(self, label_selectors):
        pods = self.k8s_core_v1.list_namespaced_pod(FL_NAMESPACE, label_selector=label_selectors).items
        pod_names_to_wait = [pod.metadata.name for pod in pods]

        server_timeout = 10*60 # 10 min
        all_pods_completed = True
        server_end_time = None
        log.info(f"Found {len(pod_names_to_wait)} running pods.")
        log.info("Waiting for pods to complete.")
        while pod_names_to_wait:
            for pod_name in pod_names_to_wait:
                pod_status = self.check_if_pod_completed(pod_name)

                if pod_status == self._PodCompletionStatus.UNAVAILABLE:
                    continue

                pod_names_to_wait.remove(pod_name)
                if pod_name == "fl-server":
                    server_end_time = time.time()

                if pod_status == self._PodCompletionStatus.ERROR:
                    all_pods_completed = False

            if server_end_time and time.time() - server_end_time > server_timeout:
                log.info("Clients are still running but server has finished %s min ago. Setup might be stuck. Finishing job.", \
                         round(server_timeout/60, 2))
                all_pods_completed = False
                # break outer loop
                pod_names_to_wait.clear()
                continue

            time.sleep(4)

        if all_pods_completed:
            log.info("All pods completed successfully.")
        else:
            log.info("Not all pods finished successfully. An error occured during the job.")
