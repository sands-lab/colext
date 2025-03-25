import argparse
import logging
import os
import sys
import yaml
from colext.common.logger import log
from colext.exp_deployers import get_deployer
from colext.exp_deployers.db_utils import DBUtils
import re


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

    config_dict = apply_config_defaults(config_dict)
    config_dict = apply_config_overrides(config_dict, args)
    config_dict = validate_config(config_dict)
    config_dict = add_config_fields(config_dict, config_file)

    print("CoLExT configuration read successfully")
    return config_dict


def apply_config_defaults(config_dict):
    if "path" not in config_dict["code"]:
        config_dict["code"]["path"] = "."
        print("Could not find 'code.path' in config file. Assuming code is in same dir as config file.")

    if "python_version" not in config_dict["code"]:
        default_py_version = "3.10"
        config_dict["code"]["python_version"] = default_py_version
        print(f"Could not find 'code.python_version' in config file. Assuming {default_py_version}")

    monitoring_defaults = {
        "live_metrics": True,
        "push_interval": 10,
        "scraping_interval": 0.3,
        "measure_self": False,
    } # intervals are in seconds
    add_config_defaults(config_dict, "monitoring", monitoring_defaults)

    colext_defaults = {
        "deployer": "sbc",
        "log_level": "INFO", # ERROR/INFO/DEBUG
        "just_launcher": "False" # True/False: True to only use the CoLExT launcher without collecting metrics
    }
    add_config_defaults(config_dict, "colext", colext_defaults)

    return config_dict


def apply_config_overrides(config_dict, args):
    if args.local_deployer:
        config_dict["colext"]["deployer"] = "local_py"

    if args.just_launcher:
        config_dict["colext"]["just_launcher"] = "True"

    return config_dict


def validate_config(config_dict):
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
    if config_dict["colext"]["deployer"] not in valid_deployers:
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

    return config_dict


def add_config_fields(config_dict, config_file):
    if not os.path.isabs(config_dict["code"]["path"]):
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
    
    config_dict["networks"] = read_network(config_dict)

    return config_dict

# given in input dictonary config it will output a new dict with all the networks
def read_network(config):
    networks = config['network']

    network_tags = {}

    #create a tcconfig commands list for each network
    for network in networks:
        network_tags[network['tag']] = {}
        network_commands = network_tags[network['tag']]["commands"] = { "upstream": [] , "downstream": [] }
        for direction in ["upstream", "downstream"]:
            if isinstance(network[direction], str):
                commands = str(network[direction]).split()
                if len(commands) > 0:
                    network_commands[direction].append(f"--rate {commands[0]} ")
                if len(commands) > 1:
                    network_commands[direction].append(f"--delay {commands[1]} ")
                if len(commands) > 2:
                    network_commands[direction].append(f"--loss {commands[2]} ")
                if len(commands) > 3:
                    network_commands[direction].append(f"--delay-distribution {commands[3]} ")
            elif isinstance(network[direction], dict):
                for rule, value in network[direction].items():
                    network_commands[direction].append(f"--{rule} {value} ")
    print(network_tags)

    #clean commands and validate all rules and finalize commands
    for network_name, network in network_tags.items():
        for direction in ["upstream", "downstream"]:
            network["commands"][direction] = " ".join(validate_network_commands(network["commands"][direction], network_name))

    print(f"Network tags: {network_tags}")
    return network_tags


def validate_network_commands(commands, network_name):
    #input command mapping
    command_mapping = {
        "--bandwidth": "--rate",
        "--speed": "--rate",
        "--rate": "--rate",
        "--delay": "--delay",
        "--delay-time": "--delay",
        "--latency": "--delay",
        "--latency-time": "--delay",
        "--delay-distribution": "--delay-distribution",
        "--delay-distro": "--delay-distro",
        "--loss": "--loss",
        "--duplicate": "--duplicate",
        "--corrupt": "--corrupt",
        "--reordering": "--reordering",
        "--reorder": "--reordering",
        "--limit": "--limit",
    }

    # input value validation mapping
    TIME_UNITS = r"(h|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds|ms|msec|msecs|millisecond|milliseconds|us|usec|usecs|microsecond|microseconds)"

    validation_mapping = {
        "--rate": r"^\d{1,4}(\.\d+)?(Kbps|Mbps|Gbps)$",
        "--delay": r"^\d+(\.\d+)?" + TIME_UNITS + "$",
        "--delay-distro": r"^\d+(\.\d+)?" + TIME_UNITS + "$",
        "--delay-distribution": r"^(normal|pareto|paretonormal|Normal|Pareto|ParetoNormal)$",
        "--loss": r"^\d+(\.\d+)?%$",
        "--duplicate": r"^\d+(\.\d+)?%$",
        "--corrupt": r"^\d+(\.\d+)?%$",
        "--reordering": r"^\d+(\.\d+)?%$",
        "--limit": r"^\d+$",
    }

    new_commands = []
    for rule in commands:
            rule_split = rule.split()

            #check if the rule and value exist

            if len(rule_split) < 1:
                # should not be possible but added for testing
                log.error(f"empty value in network:{network_name} ")
                sys.exit(1)
            elif len(rule_split) < 2:
                # value is not there
                log.error(f"invlid {rule_split[0].lstrip('-')} value: None in network:{network_name} ")
                sys.exit(1)
            elif len(rule_split) > 2:
                # should not be possible but added for testing
                log.error(f"invalid size (< 2) for value in network :{network_name} ")
                sys.exit(1)

            # check the validity of the rule

            if rule_split[0] not in command_mapping.keys():
                # invlid command rule
                log.error(f"invlid {rule_split[0]} Command in network:{network_name} ")
                sys.exit(1)
            else:
                rule_split[0] = command_mapping[rule_split[0]]

            # check the validity of the value

            if not bool(re.match(validation_mapping[rule_split[0]], rule_split[1])):
                    #invalid input
                log.error(f"invlid {rule_split[0].lstrip('-')} format:{rule_split[1]} in network:{network_name}.")
                sys.exit(1)
            
            rule = " ".join(rule_split)
            new_commands.append(rule)

    return new_commands



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

    Deployer = get_deployer(config_dict["colext"]["deployer"])
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
