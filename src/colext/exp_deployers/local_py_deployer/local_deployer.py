import shutil
import subprocess
import os
from pathlib import Path
import time

from colext.common.logger import log
from colext.exp_deployers.deployer_base import DeployerBase
from colext.common.vars import STD_DATASETS_PATH, PYTORCH_DATASETS_PATH


class LocalDeployer(DeployerBase):
    """Local deployer for experimentation"""
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
        server_launch_cmd, server_env   = self.prepare_server(job_id)
        client_launch_cmds, client_envs = self.prepare_clients(job_id)
        code_path = self.config["code"]["path"]

        # Prepare logs
        logs_dir = Path("logs")
        # Clear previous logs
        shutil.rmtree(logs_dir, ignore_errors=True)
        os.makedirs(logs_dir, exist_ok=True)

        self.log_file_handles = []

        log.info("Deploying server")
        server_log_path = logs_dir.joinpath("server.log")
        server_log_handle = open(server_log_path, 'w', encoding='UTF-8')
        self.log_file_handles.append(server_log_handle)

        log.debug(f"{server_launch_cmd=}")
        self.server_proc = subprocess.Popen(server_launch_cmd,
                                            shell=True, env=server_env, cwd=code_path,
                                            stdout=server_log_handle, stderr=server_log_handle)
        log.info("Waiting 3 sec for server startup")
        time.sleep(3)
        log.info("Deploying clients")
        log.debug(f"{client_launch_cmds=}")
        for c_id in range(self.config["n_clients"]):
            if c_id == 0:
                time.sleep(3) # weird flower bug

            client_log_path = logs_dir.joinpath(f"client_{c_id}.log")
            client_log_handle = open(client_log_path, 'w', encoding='UTF-8')
            self.log_file_handles.append(client_log_handle)

            c_proc = subprocess.Popen(client_launch_cmds[c_id],
                                      shell=True, env=client_envs[c_id], cwd=code_path,
                                      stdout=client_log_handle, stderr=client_log_handle)
            self.client_procs.append(c_proc)

    def get_base_env_vars(self, job_id):
        base_env_vars = {
            "COLEXT_ENV": str(self.config["colext"]["monitor_job"]),
            "COLEXT_JOB_ID": str(job_id),
            "COLEXT_DEVICE_TYPE": "FLServer", # both clients and server run on the server
            "COLEXT_LOG_LEVEL": os.getenv("COLEXT_LOG_LEVEL", self.config["colext"]["log_level"]),

            "COLEXT_SERVER_ADDRESS": "0.0.0.0:8080",
            "COLEXT_N_CLIENTS": str(self.config["n_clients"]),

            "COLEXT_DATASETS": os.getenv("COLEXT_DATASETS", STD_DATASETS_PATH),
            "COLEXT_PYTORCH_DATASETS": os.getenv("PYTORCH_DATASETS_PATH", PYTORCH_DATASETS_PATH),

            "COLEXT_MONITORING_LIVE_METRICS": str(self.config["monitoring"]["live_metrics"]),
            "COLEXT_MONITORING_PUSH_INTERVAL": str(self.config["monitoring"]["push_interval"]),
            "COLEXT_MONITORING_SCRAPE_INTERVAL": str(self.config["monitoring"]["scraping_interval"]),
            "COLEXT_MONITORING_MEASURE_SELF": str(self.config["monitoring"]["measure_self"]),

            "PGHOSTADDR": "127.0.0.1",
            "PGDATABASE": "colext_db",
            "PGUSER": "colext_user",
        }

        return base_env_vars

    def prepare_server(self, job_id: int):
        env_vars = self.get_base_env_vars(job_id)
        current_env = os.environ.copy()

        server_code = self.config["code"]["server"]
        # server_command = [sys.executable, server_code["entrypoint"], server_code["args"]]
        server_command = [server_code['command']]

        return server_command, {**current_env, **env_vars}

    def prepare_clients(self, job_id: int):
        base_env_vars = self.get_base_env_vars(job_id)

        client_envs = []
        client_commands = []
        client_base_cmd = self.config["code"]["client"]['command']

        def prepare_client(client_id):
            local_dev_id = 40 # Corresponds to the local device
            client_env = {
                "COLEXT_CLIENT_ID": str(client_id),
                "COLEXT_CLIENT_DB_ID": self.register_client_in_db(client_id, local_dev_id, job_id),
            }
            client_additional_args = client.get("add_args", "")
            client_cmd = [f'{client_base_cmd} {client_additional_args}']
            return client_cmd, client_env

        client_id = 0
        current_env = os.environ.copy()
        for client in self.config["clients"]:
            for _ in range(client["count"]):
                client_cmd, client_env = prepare_client(client_id)
                client_commands.append(client_cmd)
                client_envs.append({**current_env, **base_env_vars, **client_env})
                client_id += 1

        return client_commands, client_envs

    def wait_for_clients(self, job_id: int) -> None:
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
