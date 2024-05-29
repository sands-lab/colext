import argparse
import logging
import os
import sys
import yaml
from colext.common.logger import log
from .experiment_manager import ExperimentManager

def get_args():
    parser = argparse.ArgumentParser(description='Run an experiment on the FL Testbed')

    parser.add_argument('-c', '--config_file', type=str, default="./colext_config.yaml", help="Path to CoLExT config file.")
    parser.add_argument('-t', '--test_env', default=False, action='store_true', help="Test deployment in test environment.")
    parser.add_argument('-v', '--verify_only', default=False, action='store_true', help="Only verify if deployment is feasible.")
    parser.add_argument('-w', '--wait_for_experiment', default=True, action='store_true', help="Wait for experiment to finish.")
    # parser.add_argument('-d', '--delete_on_end', default=True, action='store_true', help="Delete FL pods .")

    args = parser.parse_args()

    return args

def read_config(config_file):
    try:
        print(f"Trying to read CoLExT configuration file from '{config_file}'")
        with open(config_file, "r") as stream:
            config_dict = yaml.safe_load(stream)
    except OSError as os_err:
        print(f"Could not read config file: {os_err}")
        sys.exit(1)
    except yaml.YAMLError as yaml_err:
        print(f"Error parsing configuration file: {yaml_err}")
        sys.exit(1)

    # Apply defaults
    if "path" not in config_dict["code"]:
        default_path = os.path.dirname(os.path.realpath(config_file))
        config_dict["code"]["path"] = default_path
        print(f"Could not find 'code.path' in config file. Assuming {default_path}")

    if "python_version" not in config_dict["code"]:
        default_py_version = "3.8"
        config_dict["code"]["python_version"] = default_py_version
        print(f"Could not find 'code.python_version' in config file. Assuming {default_py_version}")

    monitoring_defaults = {
        "live_metrics": True,
        "push_interval": 10,
        "scrapping_interval": 0.3,
        "measure_self": False,
    } # intervals are in seconds
    config_dict["monitoring"] = {**monitoring_defaults, **config_dict.get("monitoring", {})}

    # Validate
    if "devices" not in config_dict:
        print("Please specify at least one device to act as a client")
        sys.exit(1)

    valid_python_versions = ["3.8", "3.10"]
    if config_dict["code"]["python_version"] not in valid_python_versions:
        print(f"code.python_version can  only be set to {valid_python_versions}")
        sys.exit(1)

    # TODO Support specifying device type + count
    config_dict["client_types_to_generate"] = []
    n_clients = 0
    # count n_clients
    for dev in config_dict["devices"]:
        config_dict["client_types_to_generate"].extend([dev["device_type"]]*dev["count"])
        n_clients += dev["count"]
    config_dict["n_clients"] = n_clients

    print("CoLExT configuration read successfully")
    return config_dict

def print_dashboard_url(extra_grafana_vars: dict  = None):
    DASHBOARD_URL_BASE = ("http://localhost:3000/d/c9b9dcd9-9304-47d7-8dd2-92b8529725c8/colext-dashboard?"
                          "orgId=1&from=now-5m&to=now&refresh=5s")

    extra_grafana_vars = [f"&var-{k}={v}" for k, v in extra_grafana_vars.items()]
    dashboard_url = DASHBOARD_URL_BASE + "".join(extra_grafana_vars)

    print("Job logs and metrics are available on the Grafana dashboard:")
    print(dashboard_url)
    print("You may need to create an SSH tunnel to see the dashboard:")
    print("ssh -L 3000:localhost:3000 -N flserver")

def launch_experiment():
    log.setLevel(logging.DEBUG)
    print("Preparing to launch CoLExT")

    args = get_args()
    config_dict = read_config(args.config_file)

    e_manager = ExperimentManager(config_dict, args.test_env)

    if args.verify_only:
        feasible = e_manager.validate_feasibility()
        if feasible:
            print("Setup is feasible")
        else:
            print("Setup is not feasible")
        sys.exit(0)

    job_id = e_manager.launch_experiment()

    print("\n")
    print(f"Launched experiment with {job_id=}")

    grafana_vars = {
        "jobid": job_id,
        "clientid": "All",
    }
    print_dashboard_url(grafana_vars)

    print("\nExperiment running...")
    if args.wait_for_experiment:
        print("Waiting for experiment")
        e_manager.wait_for_job(job_id)
        print("Experiment complete.")
    else:
        print("Command will exit but experiment is still running.")
