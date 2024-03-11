import time
import kubernetes
from typing import Tuple
from colext.common.logger import log

FL_NAMESPACE = "default"
FL_SERVICE = "fl-server-svc"

class KubernetesUtils:
    def __init__(self) -> None:
        self.k8s_api, self.k8s_core_v1 = self.get_k8s_clients()

    def get_k8s_clients(self) -> Tuple[kubernetes.client.ApiClient, kubernetes.client.CoreV1Api]:
        MICROK8S_CONFIG_FILE = "/var/snap/microk8s/current/credentials/client.config"
        kubernetes.config.load_kube_config(config_file = MICROK8S_CONFIG_FILE)
        return kubernetes.client.ApiClient(), kubernetes.client.CoreV1Api()
    
    def create_from_yaml(self, yaml_file):
        kubernetes.utils.create_from_yaml(self.k8s_api, yaml_file)

    def create_from_dict(self, dict_obj):
        kubernetes.utils.create_from_dict(self.k8s_api, dict_obj)

    def delete_client_pods(self):
            pods = self.k8s_core_v1.list_namespaced_pod(FL_NAMESPACE).items
            pod_names_to_delete = [pod.metadata.name for pod in pods]
            for pod_name in pod_names_to_delete:
                log.info(f"Deleting pod {pod_name}")
                self.k8s_core_v1.delete_namespaced_pod(pod_name, FL_NAMESPACE)

            while pod_names_to_delete:
                pod_names_to_delete_copy = pod_names_to_delete.copy()
                for pod_name in pod_names_to_delete:
                    try:
                        self.k8s_core_v1.read_namespaced_pod_status(pod_name, FL_NAMESPACE)
                    except kubernetes.client.rest.ApiException as e:
                        if e.status == 404:
                            log.info(f"Pod {pod_name} was successfully deleted")
                            pod_names_to_delete_copy.remove(pod_name)
                        else:
                            log.error(f"Unexpected error while checking pod status for pod {pod_name}")
                
                pod_names_to_delete = pod_names_to_delete_copy
                time.sleep(4) 
            
            log.info(f"All pods deleted")

    def delete_fl_service(self):
        log.info(f"Deleting service {FL_SERVICE}")
        try: 
            self.k8s_core_v1.delete_namespaced_service(FL_SERVICE, FL_NAMESPACE)
        except kubernetes.client.rest.ApiException as e:
            if e.status == 404:
                log.info(f"Service {FL_SERVICE} did not exist")
                return
            else:
                log.error(f"Unexpected error while deleting {FL_SERVICE}")
        
        while True:
            try:
                self.k8s_core_v1.read_namespaced_service_status(FL_SERVICE, FL_NAMESPACE)
            except kubernetes.client.rest.ApiException as e:
                if e.status == 404:
                    log.info(f"FL server service ({FL_SERVICE}) was successfully deleted")
                    break
                else:
                    log.error(f"Unexpected error while checking status for service service {FL_SERVICE}")
            
            time.sleep(4) 

    def wait_for_pods(self, label_selectors, expected_pods):
        # Get current pods
        pods = self.k8s_core_v1.list_namespaced_pod(FL_NAMESPACE, label_selector=label_selectors).items
        pod_names_to_wait = [pod.metadata.name for pod in pods]

        log.info(f"Found {len(pod_names_to_wait)} running pods.")
        log.info(f"Waiting for pods to complete.")
        while pod_names_to_wait:
            pod_names_to_wait_copy = pod_names_to_wait.copy()
            for pod_name in pod_names_to_wait:
                try:
                    client_container_state = self.k8s_core_v1.read_namespaced_pod_status(pod_name, FL_NAMESPACE).status.container_statuses[0].state
                    
                    if client_container_state.terminated != None:
                        if client_container_state.terminated.reason == "Completed":
                            log.info(f"{pod_name} terminated successfully.")
                            pod_names_to_wait_copy.remove(pod_name)
                        else:
                            log.error(f"{pod_name} terminated with reason different than 'Completed'. Reason: {client_container_state.terminated.reason}")
                except kubernetes.client.rest.ApiException as e:
                    if e.status == 404:
                        log.error(f"{pod_name} pod was deleted while waiting for it. Removing it from the waiting list.")
                        pod_names_to_wait_copy.remove(pod_name)
                    else:
                        log.error(f"Unexpected error while checking pod status for pod {pod_name}. Error: {e}")
            
            pod_names_to_wait = pod_names_to_wait_copy
            time.sleep(4) 
        
        log.info(f"All pods completed successfully")