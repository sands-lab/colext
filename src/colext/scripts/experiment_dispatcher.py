import argparse
import logging
import os
import sys
import yaml
from colext.common.logger import log
from colext.exp_deployers import get_deployer
from colext.exp_deployers.db_utils import DBUtils

def get_args():
    parser = argparse.ArgumentParser(description='Run an experiment on the FL Testbed')

    parser.add_argument('-c', '--config_file', type=str, default="./colext_config.yaml",
                        help="Path to CoLExT config file.")
    parser.add_argument('-t', '--test_env', default=False, action='store_true',
                        help="Test deployment in test environment.")
    parser.add_argument('-p', '--prepare_only', default=False, action='store_true',
                        help="Only prepare experiment for launch.")
    parser.add_argument('-l', '--local_deployer', action='store_true',
                        help="Use a local deployer to debug experiment")
    parser.add_argument('-j', '--just_launcher', default=False, action='store_true',
                        help="If set, only uses the CoLExT launcher to deploy the experiment, without any monitoring. This is useful to test the experiment code without any interference from the CoLExT monitoring system.")
    parser.add_argument('-d', '--debug_local', action='store_true',
                        help="Run a local deployer using CoLExT just as the launcher for debugging outside of the colext environment. Equivalent to `--local_deployer --just_launcher`")
    parser.add_argument('-w', '--wait_for_experiment', default=True, action='store_true',
                        help="Wait for experiment to finish.")
    # parser.add_argument('-d', '--delete_on_end', default=True, action='store_true', help="Delete FL pods .")

    args = parser.parse_args()

    if args.debug_local:
        if args.local_deployer or args.just_launcher:
            print("Warning: '-d'/'--debug_local' forces '--local_deployer --just_launcher'.")
        args.local_deployer = True
        args.just_launcher = True

    return args

def read_config(config_file, args):
    try:
        print(f"Trying to read CoLExT configuration file from '{config_file}'")
        with open(config_file, "r", encoding="utf-8") as stream:
            config_dict = yaml.safe_load(stream)
    except OSError as os_err:
        print(f"Could not read config file: {os_err}")
        sys.exit(1)
    except yaml.YAMLError as yaml_err:
        print(f"Error parsing configuration file: {yaml_err}")
        sys.exit(1)

    # Apply defaults
    if "path" not in config_dict["code"]:
        config_dict["code"]["path"] = "."
        print("Could not find 'code.path' in config file. Assuming code is in same dir as config file.")

    if "python_version" not in config_dict["code"]:
        default_py_version = "3.10"
        config_dict["code"]["python_version"] = default_py_version
        print(f"Could not find 'code.python_version' in config file. Assuming {default_py_version}")

    if "deployer" not in config_dict:
        default_deployer = "sbc"
        config_dict["deployer"] = default_deployer

    monitoring_defaults = {
        "live_metrics": True,
        "push_interval": 10,
        "scraping_interval": 0.3,
        "measure_self": False,
    } # intervals are in seconds
    add_config_defaults(config_dict, "monitoring", monitoring_defaults)

    colext_defaults = {
        # "deployer": "sbc",
        "log_level": "INFO", # ERROR/INFO/DEBUG
        "just_launcher": "False" # True/False: True to only use the CoLExT launcher without collecting metrics
    }
    add_config_defaults(config_dict, "colext", colext_defaults)

    # Overrides
    if args.local_deployer:
        config_dict["deployer"] = "local_py"

    if args.just_launcher:
        config_dict["colext"]["just_launcher"] = "True"

    # Validate
    if "project" not in config_dict:
        print("Please specify the project name to associate this job with.")
        sys.exit(1)

    if "clients" not in config_dict:
        print_err("Please specify at least one client in the config file.")
        sys.exit(1)

    valid_python_versions = ["3.8", "3.10"]
    if config_dict["code"]["python_version"] not in valid_python_versions:
        print_err(f"code.python_version can  only be set to {valid_python_versions}")
        sys.exit(1)

    valid_deployers = ["sbc", "local_py"]
    if config_dict["deployer"] not in valid_deployers:
        print_err(f"deployer can  only be set to {valid_deployers}")
        sys.exit(1)

    valid_log_levels = ["ERROR", "INFO", "DEBUG"]
    if config_dict["colext"]["log_level"] not in valid_log_levels:
        print_err(f"colext.log_level can  only be set to {valid_log_levels}")
        sys.exit(1)

    valid_just_launcher_options = ["True", "False"]
    if config_dict["colext"]["just_launcher"] not in valid_just_launcher_options:
        print_err(f"colext.just_launcher can  only be set to {valid_just_launcher_options}")
        sys.exit(1)

    # Add fields
    config_dir_path = os.path.dirname(os.path.realpath(config_file))
    config_dict["code"]["path"] = os.path.join(config_dir_path, config_dict["code"]["path"])
    print(f'Code path = {config_dict["code"]["path"]}')

    config_dict["colext"]["monitor_job"] = str(config_dict["colext"]["just_launcher"] != "True")

    client_defaults = {
        "count": 1
    }
    config_dict["clients"] = [{**client_defaults, **c} for c in config_dict["clients"]]

    config_dict["req_dev_types"] = list(set([client["dev_type"] for client in config_dict["clients"]]))
    config_dict["n_clients"] = sum(client["count"] for client in config_dict["clients"])

    print("CoLExT configuration read successfully")
    return config_dict

def print_err(msg):
    print(f"ERR: {msg}")

def add_config_defaults(config_dict, key, defaults):
    config_dict[key] = {**defaults, **config_dict.get(key, {})}

def print_dashboard_url(extra_grafana_vars: dict  = None):
    DASHBOARD_URL_BASE = ("http://colext:3000/d/c9b9dcd9-9304-47d7-8dd2-92b8529725c8/colext-dashboard?"
                          "orgId=1&from=now-5m&to=now&refresh=10s")

    extra_grafana_vars = [f"&var-{k}={v}" for k, v in extra_grafana_vars.items()]
    dashboard_url = DASHBOARD_URL_BASE + "".join(extra_grafana_vars)

    print("Job logs and metrics are available on the Grafana dashboard:")
    print(dashboard_url)

def launch_experiment():
    print("Preparing to launch CoLExT")

    args = get_args()
    config_dict = read_config(args.config_file, args)

    Deployer = get_deployer(config_dict["deployer"])
    deployer = Deployer(config_dict, args.test_env)

    if args.prepare_only:
        deployer.prepare_deployment()
        print("Colext launch invoked as prepare only. Exiting.")
        return

    job_id = deployer.start()
    print(f"\nLaunched experiment with {job_id=}")

    if config_dict["colext"]["monitor_job"] == "True":
        grafana_vars = {
            "project": config_dict["project"],
            "jobid": job_id,
            "round_n": "All",
            "clientid": "All",
            "show_stages": "True",
        }
        print_dashboard_url(grafana_vars)

    print("\nExperiment running...")
    if args.wait_for_experiment:
        print("Waiting for experiment.")
        deployer.wait_for_job(job_id)
        print("Experiment complete.")
    else:
        print("Command will exit but experiment is still running.")
