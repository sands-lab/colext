import argparse
import logging
import os
import sys
import yaml
from colext.common.logger import log
from colext.exp_deployers import get_deployer
from colext.exp_deployers.db_utils import DBUtils
import re


#Network variables

network_dir = "./network_scripts"

# Global mappings for commands and validation regexes
COMMAND_MAPPING = {
    "bandwidth": "rate", "speed": "rate", "rate": "rate",
    "delay": "delay", "delay-time": "delay", "latency": "delay", "latency-time": "delay",
    "delay-distribution": "delay-distribution", "delay-distro": "delay-distro",
    "loss": "loss", "duplicate": "duplicate", "corrupt": "corrupt",
    "reordering": "reordering", "reorder": "reordering", "limit": "limit"
}

TIME_UNITS = r"(h|hour|hours|m|min|mins|minute|minutes|s|sec|secs|second|seconds|ms|msec|msecs|millisecond|milliseconds|us|usec|usecs|microsecond|microseconds)"
VALIDATION_MAPPING = {
    "rate": r"^\d{1,4}(\.\d+)?(Kbps|Mbps|Gbps)$",
    "delay": r"^\d+(\.\d+)?" + TIME_UNITS + "$",
    "delay-distro": r"^\d+(\.\d+)?" + TIME_UNITS + "$",
    "delay-distribution": r"^(normal|pareto|paretonormal|Normal|Pareto|ParetoNormal)$",
    "loss": r"^\d+(\.\d+)?%$",
    "duplicate": r"^\d+(\.\d+)?%$",
    "corrupt": r"^\d+(\.\d+)?%$",
    "reordering": r"^\d+(\.\d+)?%$",
    "limit": r"^\d+$"
}




def get_args():
    parser = argparse.ArgumentParser(description='Run an experiment on the FL Testbed')

    parser.add_argument('-c', '--config_file', type=str, default="./colext_config.yaml",
                        help="Path to CoLExT config file.")
    parser.add_argument('-t', '--test_env', default=False, action='store_true',
                        help="Test deployment in test environment.")
    parser.add_argument('-p', '--prepare_only', default=False, action='store_true',
                        help="Only prepare experiment for launch.")
    parser.add_argument('-w', '--wait_for_experiment', default=True, action='store_true',
                        help="Wait for experiment to finish.")
    parser.add_argument('-n', '--network_dir', type=str, default=network_dir,)
    # parser.add_argument('-d', '--delete_on_end', default=True, action='store_true', help="Delete FL pods .")

    args = parser.parse_args()

    return args

def read_config(config_file):
    db = DBUtils()

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
    # Override defaults by whatever is in the config
    config_dict["monitoring"] = {**monitoring_defaults, **config_dict.get("monitoring", {})}

    # Validate
    if "project" not in config_dict:
        print("Please specify the project name to associate this job with.")
        sys.exit(1)
    else:
        project_name = config_dict['project']
        if not db.project_exists(project_name):
            print_err(f"Could not find project named {project_name}. Please use a valid project name.")
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

    # Add fields
    config_dir_path = os.path.dirname(os.path.realpath(config_file))
    config_dict["code"]["path"] = os.path.join(config_dir_path, config_dict["code"]["path"])
    print(f'Code path = {config_dict["code"]["path"]}')


    client_defaults = {
        "count": 1
    }
    config_dict["clients"] = [{**client_defaults, **c} for c in config_dict["clients"]]

    config_dict["req_dev_types"] = list(set([client["dev_type"] for client in config_dict["clients"]]))
    config_dict["n_clients"] = sum(client["count"] for client in config_dict["clients"])
    
    config_dict["networks"] = read_network(config_dict)

    print("CoLExT configuration read successfully")
    return config_dict

# given in input dictonary config it will output a new dict with all the networks
def read_network(config):
    networks = config['network']
    clients = config['clients']
    
    # Create a mapping from network tag to clients using that tag.
    network_tags = {}
    
    # Process static network commands
    for net in networks:
        tag = net['tag']
        network_tags[tag] = {}
        if "dynamic" in net:
            network_tags[tag]["dynamic"] = {}  # prepare dict for dynamic config
            continue
        network_tags[tag]["commands"] = read_static(net)
        
    
    # Validate commands for non-dynamic networks
    for tag, net in network_tags.items():
        if "dynamic" not in net:
            for direction in ["upstream", "downstream"]:
                net["commands"][direction] = validate_static_commands(net["commands"][direction], tag)
    


    # Process dynamic network configuration and validate
    for net in [n for n in networks if "dynamic" in n]:
        tag = net['tag']
        network_tags[tag]["dynamic"] = read_validate_dynamic(net)


    print("Network tags:", network_tags)
    return network_tags

def read_static(net):
    # Build commands for upstream and downstream directions
    network_commands = {"upstream": [], "downstream": []}
    
    
    for direction in ["upstream", "downstream"]:
        cmd_value = net.get(direction)
        if isinstance(cmd_value, str):
            # example: (upstream/downstream): 2000Mbps 3ms 50% normal 
            # each string is a token
            tokens = cmd_value.split()
            if tokens:
                if len(tokens) > 0:
                    network_commands[direction].append(f"rate {tokens[0]}")
                if len(tokens) > 1:
                    network_commands[direction].append(f"delay {tokens[1]}")
                if len(tokens) > 2:
                    network_commands[direction].append(f"loss {tokens[2]}")
                if len(tokens) > 3:
                    network_commands[direction].append(f"delay-distribution {tokens[3]}")
        elif isinstance(cmd_value, dict):
            for rule, value in cmd_value.items():
                network_commands[direction].append(f"{rule} {value}")
    return network_commands

def validate_static_commands(commands, network_name):
    """
    Validate a list of command strings for a given network.
    input commands should be a list of command strings
    Returns a list of validated and formatted command strings.
    """
    # commands is the attributes defined for each network
    # example 
    validated = []
    for command in commands:
        command_split = command.split()
        if len(command_split) < 2:
            print(f"Missing value for command in network:{network_name}")
            sys.exit(1)
        if len(command_split) > 2:
            print(f"Too many tokens in command in network:{network_name}")
            sys.exit(1)
        
        rule_name = command_split[0]
        if rule_name not in COMMAND_MAPPING:
            print(f"Invalid command {rule_name} in network:{network_name}")
            sys.exit(1)
        
        rule_name = COMMAND_MAPPING[rule_name]
        if not re.match(VALIDATION_MAPPING[rule_name], command_split[1]):
            print(f"Invalid {rule_name} format: {command_split[1]} in network:{network_name}")
            sys.exit(1)
        
        validated.append(f"{rule_name} {command_split[1]}")
    return validated

def read_validate_dynamic(net):
    '''
    Read and validate dynamic network configuration from the given dict. 
    input net should be a dict that contains the original network config
    Returns a dict with validated and formatted dynamic network config.
    '''
    dynamic_config = {}
    tag = net['tag']
    #looping through the dynamic config and validating each entry aka each iterator defined with its list of commands
    for entry in net['dynamic']:
        
        #validate the iterator
        iterator = entry.get('iterator')
        if not iterator or iterator not in ['time', 'epochs']:
            print(f"Invalid or missing iterator in {tag}")
            sys.exit(1)
        if iterator in dynamic_config:
            print(f"Iterator {iterator} already exists in {tag} ignoring this entry")
            continue
        

        
        entry_temp = {}
        #validate structure
        structure = entry.get("structure", ['rate', 'delay']) # default to [rate,delay] if structure is not defined
        corrected = check_rules(structure)
        
        entry_temp["structure"] = corrected
        

        #check for script else take commands
        if 'script' in entry:
            if not os.path.exists(network_dir + entry["script"]):
                print(f"Script file {entry['script']} does not exist.")
                sys.exit(1)
            entry_temp["script"] = entry['script']
        else:
            entry_temp["script"] = False
            entry_temp["commands_dict"] = {}
            # Process each command entry excluding 'structure' and 'iterator'
            for key, command in entry.items():
                if key in ['structure', 'iterator']:
                    continue
                if not check_command(command, entry_temp["structure"]):
                    print(f"Invalid command: {command} in {tag}")
                    sys.exit(1)
                entry_temp["commands_dict"][key] = command
                #TODO some values may have -1 and that should be checked and removed accordingly

        
        dynamic_config[iterator] = entry_temp
    return dynamic_config

def check_command(command, structure):
    '''
    checks if the list of commands follow the given structure
    Returns True if the command is valid else False
    '''
    
    command_split = command.split() if isinstance(command, str) else command
    if len(command_split) - 2 != len(structure):
        print("Invalid command length")
        return False
    
    if command_split[0] not in ['set', 'del']:
        print(f"Invalid command name: {command_split[0]} in {command} only 'set' and 'del' are allowed")
        return False

    if command_split[1] not in ["incoming", "outgoing"]:
        print(f"Invalid direction: {command_split[1]} in {command} only 'incoming' and 'outgoing' are allowed")
        return False
    for i, rule in enumerate(structure):
        if command_split[i + 2] == -1:
            continue
        if not re.match(VALIDATION_MAPPING[rule], command_split[i + 2]):
            print(f"Invalid {rule} format: {command_split[i + 2]}")
            return False
    return True

def check_rules(structure):
    """
    Validate and correct a list of rule names using COMMAND_MAPPING.
    Returns a tuple (is_valid, corrected_structure).
    """
    corrected = []
    for rule in structure:
        if rule not in COMMAND_MAPPING:
            print(f"Invalid rule: {rule}. Valid rules are: {', '.join(COMMAND_MAPPING.keys())}")
            sys.exit(1)
        corrected.append(COMMAND_MAPPING[rule])
    return corrected




def print_err(msg):
    print(f"ERR: {msg}")

def print_dashboard_url(extra_grafana_vars: dict  = None):
    DASHBOARD_URL_BASE = ("http://colext:3000/d/c9b9dcd9-9304-47d7-8dd2-92b8529725c8/colext-dashboard?"
                          "orgId=1&from=now-5m&to=now&refresh=10s")

    extra_grafana_vars = [f"&var-{k}={v}" for k, v in extra_grafana_vars.items()]
    dashboard_url = DASHBOARD_URL_BASE + "".join(extra_grafana_vars)

    print("Job logs and metrics are available on the Grafana dashboard:")
    print(dashboard_url)

def launch_experiment():
    log.setLevel(logging.DEBUG)
    print("Preparing to launch CoLExT")

    args = get_args()
    config_dict = read_config(args.config_file)
    network_dir = args.network_dir
    Deployer = get_deployer(config_dict["deployer"])
    deployer = Deployer(config_dict, args.test_env)

    if args.prepare_only:
        deployer.prepare_deployment()
        print("Colext launch invoked as prepare only. Exiting.")
        return

    job_id = deployer.start()
    print("\n")
    print(f"Launched experiment with {job_id=}")

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
        print("Note that pods can take up to 10 minutes to start.")
        deployer.wait_for_job(job_id)
        print("Experiment complete.")
    else:
        print("Command will exit but experiment is still running.")
