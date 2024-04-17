import argparse
import logging
from colext.common.logger import log
from .experiment_manager import ExperimentManager

def get_args():
    parser = argparse.ArgumentParser(description='Retrieve metrics from CoLExt')

    parser.add_argument('-j', '--job_id', required=True, type=int, help="job id to retrieve metrics")

    args = parser.parse_args()

    return args

def retrieve_metrics():
    log.setLevel(logging.INFO)
    print("Retrieving metrics")

    args = get_args()

    e_manager = ExperimentManager({}, False)
    e_manager.retrieve_metrics(args.job_id)

if __name__ == "__main__":
    job_id = 146

    e_manager = ExperimentManager()
    e_manager.retrieve_metrics(job_id)
