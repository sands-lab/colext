import sys
import argparse
import logging
from colext.common.logger import log
from .experiment_manager import ExperimentManager, JobNotFoundException

def get_args():
    parser = argparse.ArgumentParser(description='Retrieve metrics from CoLExt')

    parser.add_argument('-j', '--job_id', required=True, type=int, help="job id to retrieve metrics")

    args = parser.parse_args()

    return args

def retrieve_metrics():
    log.setLevel(logging.INFO)
    args = get_args()

    print("Retrieving metrics")
    job_id = args.job_id
    e_manager = ExperimentManager({}, False)
    try:
        e_manager.retrieve_metrics(job_id)
    except JobNotFoundException:
        print(f"Could not find job with id {job_id}")
        sys.exit(1)
