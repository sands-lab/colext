import shutil
import subprocess
import os
from pathlib import Path
import time

from colext.common.logger import log
from colext.exp_deployers.deployer_base import DeployerBase

class LocalDeployer(DeployerBase):
    """Deployer for SBC devices"""
    def __init__(self, config, test_env=False) -> None:
        # Creates db_utils and saves init parameters in self
        super().__init__(config, test_env)

        # Will be assigned to inside deploy_setup
        self.server_proc = None
        self.log_file_handles = []
        self.client_procs = []

    def prepare_deployment(self):
        log.debug("Nothing to do for prepare_deployment")

    def deploy_setup(self, job_id: int):
        server_launch_cmd, server_env = self.prepare_server(job_id)
        client_launch_cmd, cli_env = self.prepare_clients(job_id)

        # Prepare logs
        logs_dir = Path("logs")
        # Clear previous logs
        shutil.rmtree(logs_dir, ignore_errors=True)
        os.makedirs(logs_dir, exist_ok=True)

        self.log_file_handles = []

        log.info("Deploying server")
        server_log_path = logs_dir.joinpath("server.out")
        server_log_handle = open(server_log_path, 'w', encoding='UTF-8')
        self.log_file_handles.append(server_log_handle)

        log.info(f"{server_launch_cmd=}")
        self.server_proc = subprocess.Popen(server_launch_cmd, shell=True, env=server_env,
                                        stdout=server_log_handle, stderr=server_log_handle)
        log.info("Waiting 3 sec for server startup")
        time.sleep(3)
        log.info("Deploying clients")
        log.info(f"{client_launch_cmd=}")
        for c_id in range(self.config["n_clients"]):
            if c_id == 0:
                time.sleep(3) # weird flower bug

            client_log_path = logs_dir.joinpath(f"client_{c_id}.out")
            client_log_handle = open(client_log_path, 'w', encoding='UTF-8')
            self.log_file_handles.append(client_log_handle)

            c_proc = subprocess.Popen(client_launch_cmd, shell=True, env=cli_env[c_id],
                                        stdout=client_log_handle, stderr=client_log_handle)
            self.client_procs.append(c_proc)

    def prepare_server(self, job_id: int):
        current_env = os.environ.copy()
        env_vars = {
            "COLEXT_ENV": "1",
            "COLEXT_JOB_ID": str(job_id),
            "COLEXT_DEVICE_TYPE": "FLServer",
            "COLEXT_LOG_LEVEL": "DEBUG",

            "COLEXT_N_CLIENTS": str(self.config["n_clients"]),

            "COLEXT_DATA_HOME_FOLDER": "/colext/datasets",
            "COLEXT_PYTORCH_DATASETS": "/colext/pytorch_datasets",

            "PGHOSTADDR": "127.0.0.1",
            "PGDATABASE": "colext_db",
            "PGUSER": "colext_user",
        }

        server_code = self.config["code"]["server"]
        # server_command = [sys.executable, server_code["entrypoint"], server_code["args"]]
        server_command = [server_code['command']]

        return server_command, {**current_env, **env_vars}


    def prepare_clients(self, job_id: int):
        current_env = os.environ.copy()
        base_env_vars = {
            "COLEXT_ENV": "1",
            "COLEXT_JOB_ID": str(job_id),
            "COLEXT_DEVICE_TYPE": "FLServer", # clients run on the server
            "COLEXT_LOG_LEVEL": "DEBUG",

            "COLEXT_SERVER_ADDRESS": "0.0.0.0:8080",
            "COLEXT_N_CLIENTS": str(self.config["n_clients"]),

            # "COLEXT_DATA_HOME_FOLDER": "/colext/datasets",
            # "COLEXT_PYTORCH_DATASETS": "/colext/pytorch_datasets",

            "COLEXT_MONITORING_LIVE_METRICS": str(self.config["monitoring"]["live_metrics"]),
            "COLEXT_MONITORING_PUSH_INTERVAL": str(self.config["monitoring"]["push_interval"]),
            "COLEXT_MONITORING_SCRAPE_INTERVAL": str(self.config["monitoring"]["scraping_interval"]),
            "COLEXT_MONITORING_MEASURE_SELF": str(self.config["monitoring"]["measure_self"]),

            "PGHOSTADDR": "127.0.0.1",
            "PGDATABASE": "colext_db",
            "PGUSER": "colext_user",
        }

        client_envs = []
        for client_id in range(self.config["n_clients"]):
            local_dev_id = 40 # Corresponds to the local device
            per_client = {
                "COLEXT_CLIENT_ID": str(client_id),
                "COLEXT_CLIENT_DB_ID": self.register_client_in_db(client_id, local_dev_id, job_id),
            }
            client_envs.append({**current_env, **base_env_vars, **per_client})

        client_code = self.config["code"]["client"]
        # client_command = [f"python3 {client_code['entrypoint']} {client_code['args']}"]
        client_command = [client_code['command']]

        return client_command, client_envs

    def wait_for_devices(self, job_id: int) -> None:
        # Wait for bg processes
        log.info("Waiting for server proc to finish")
        exit_code = self.server_proc.wait()
        if exit_code != 0:
            log.error(f"Server process exited with error different than 0. Error = {exit_code}")
        else:
            log.info("Server finished successfully")

        log.info("Waiting for server proc to finish")
        exit_codes = [c_proc.wait() for c_proc in self.client_procs]
        for i, exit_code in enumerate(exit_codes):
            if exit_code != 0:
                log.error(f"Client {i} exited with error different than 0. Error = {exit_code}")
            else:
                log.info(f"Client {i} finished successfully")

        # Close file handles
        for f in self.log_file_handles:
            f.close()


