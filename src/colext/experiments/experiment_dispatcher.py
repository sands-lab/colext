from python_on_whales import docker
import argparse
import yaml
from pathlib import Path
import os
import sys 
import logging
from .experiment_manager import ExperimentManager
from colext.common.logger import log
from colext.common.vars import REGISTY

def get_args():
    parser = argparse.ArgumentParser(description='Run an experiment on the FL Testbed')
    
    parser.add_argument('-c', '--config_file', type=str, default="./colext_config.yaml", help="Path to CoLExT config file")
    parser.add_argument('-t', '--test_local', default=False, action='store_true', help="Test deployment locally")
    parser.add_argument('-w', '--wait_for_experiment', default=True, action='store_true', help="Wait for experiment to finish.")
    
    args = parser.parse_args()

    return args

def read_config(config_file):
    print(f"Trying to read CoLExT configuration file from '{config_file}'")

    try:
        with open(config_file, "r") as stream:
            config_dict = yaml.safe_load(stream)
    except OSError as os_err:
        print(f"Could not read config file: {os_err}")
        sys.exit(1)
    except yaml.YAMLError as yaml_err:
        print(f"Error parsing configuration file: {yaml_err}")
        sys.exit(1)

    # TODO Support specifying device type + count
    config_dict["client_types_to_generate"] = []
    n_clients = 0
    for dev in config_dict["devices"]:
        config_dict["client_types_to_generate"].extend([dev["device_type"]]*dev["count"])
        n_clients += dev["count"]

    config_dict["n_clients"] = n_clients

    print(f"CoLExT configuration read successfully")

    return config_dict

def containerize_app(config_dict, testing_locally):
    project_name = config_dict["project"]
    user_code_path = Path(config_dict["code"]["path"])
    file_dir = Path(__file__).parent.resolve()
    hcl_file_dir = os.path.join(file_dir, "Dockerfiles", "pip_w_install")

    target = "default"
    context = user_code_path
    if testing_locally:
        target = "testing"
        # Testing assumes code from /colext/user_code_example
        # We need to set context to /colext so we can copy the package
        context = os.path.dirname(user_code_path)
        assert os.path.isdir(os.path.join(context, "src", "colext")), \
               f"Testing package. Expected to find src/colext dir in '{context}'"

    docker.buildx.bake( targets=[target], 
                        files=os.path.join(hcl_file_dir, "docker-bake.hcl"),
                        variables={
                            "REGISTY": REGISTY,
                            "PROJECT_NAME": project_name,
                            "CONTEXT": context,
                            "BAKE_FILE_DIR": hcl_file_dir
                        },
                        push=True)
    
DASHBOARD_URL = "http://localhost:3000/d/c9b9dcd9-9304-47d7-8dd2-92b8529725c8/fl-dashboard?orgId=1"
def launch_experiment():
    log.setLevel(logging.INFO)
    print(f"Starting experiment manager")

    args = get_args()
    config_dict = read_config(args.config_file)
    
    containerize_app(config_dict, args.test_local)

    e_manager = ExperimentManager()
    job_id = e_manager.launch_experiment(config_dict)

    print(f"Launched experiment with {job_id=}")
    print(f"Job logs and metrics are available on the Grafana dashboard:\n{DASHBOARD_URL}&var-jobid={job_id}")
    print(f"You may need to create an SSH tunnel to see the dashboard:")
    print(f"ssh -L 3000:localhost:3000 -N flserver")
    print(f"\nExperiment running...")

    if args.wait_for_experiment:
        e_manager.wait_for_job(job_id, config_dict)
        print(f"Experiment complete.")
    else: 
        print(f"Command will exit but experiment is still running. ")

    # if args.collect_metrics:
    #     print(f"Collecting metrics to...")
        
