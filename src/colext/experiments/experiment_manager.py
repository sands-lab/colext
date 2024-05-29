import time
from dataclasses import dataclass
from colext.experiments.db_utils import DBUtils
from colext.experiments.sbc_deployer import SBCDeploymentHandler

# ClientConfig: TypeAlias = Dict[str, str]
@dataclass
class DeviceTypeRequest:
    """Class to represent a device type request"""
    device_type: str
    count: int

class ExperimentManager():
    def __init__(self, config, test_env):
        self.db_utils = DBUtils()
        self.config = config
        self.d_handler = SBCDeploymentHandler(config, test_env)

    def validate_feasibility(self):
        return self.d_handler.validate_feasibility()

    def launch_experiment(self):
        d_handler = self.d_handler
        # Validate that deployment is feasible
        d_handler.validate_feasibility()
        d_handler.clear_prev_experiment()

        job_id = self.db_utils.create_job()
        d_handler.prepare_deployment(job_id)
        d_handler.deploy_setup()

        return job_id

    def wait_for_job(self, job_id):
        # Give some buffer for experiment launch
        time.sleep(1)
        self.d_handler.wait_for_job(job_id)
        self.db_utils.finish_job(job_id)

    def retrieve_metrics(self, job_id):
        """ Retrieve client metrics for job_id """
        # Make sure job id exists
        if not self.db_utils.check_if_job_exists(job_id):
            raise JobNotFoundException

        with open(f"colext_{job_id}_hw_metrics.csv", "wb") as metric_writer:
            self.db_utils.get_hw_metrics(job_id, metric_writer)

        with open(f"colext_{job_id}_round_timestamps.csv", "wb") as metric_writer:
            self.db_utils.get_round_timestamps(job_id, metric_writer)

        with open(f"colext_{job_id}_client_round_timings.csv", "wb") as metric_writer:
            self.db_utils.get_client_round_timings(job_id, metric_writer)

        with open(f"colext_{job_id}_client_info.csv", "wb") as metric_writer:
            self.db_utils.get_client_info(job_id, metric_writer)

class JobNotFoundException(ValueError):
    """Could not find the job in db"""
