from python_on_whales import docker
import argparse
import yaml
from pathlib import Path
import os
import sys 
import logging
from .experiment_manager import ExperimentManager
from fltb.common.logger import log
from fltb.common.vars import REGISTY

def get_args():
    parser = argparse.ArgumentParser(description='Run an experiment on the FL Testbed')
    
    parser.add_argument('-c', '--config_file', type=str, default="./fltb_config.yaml", help="Path to FLTB config file")
    parser.add_argument('-t', '--test_local', default=False, action='store_true', help="Test deployment locally")
    
    args = parser.parse_args()

    return args

def read_config(config_file):
    print(f"Trying to read FLTB configuration file from '{config_file}'")

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
    for d in config_dict["devices"]:
        config_dict["client_types_to_generate"].extend([d["device_type"]]*d["count"])
        
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
        # Testing assumes code from /fl-testbed/user_code_example
        # We need to set context to /fl-testbed so we can copy the package
        context = os.path.dirname(user_code_path)
        assert os.path.isdir(os.path.join(context, "src", "fltb")), \
               f"Testing package. Expected to find src/fltb dir in '{context}'"

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

    exp_man = ExperimentManager()
    job_id = exp_man.launch_experiment(config_dict)

    print(f"Launched experiment with {job_id=}")
    print(f"Job metrics are available on the Grafana dashboard:\n{DASHBOARD_URL}&var-jobid={job_id}")
    print(f"You may need to create an SSH tunnel to see the dashboard")
    print(f"ssh -L 3000:localhost:3000 -N flserver")
    