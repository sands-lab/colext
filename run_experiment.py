import logging
from fltb.experiment_manager.experiment_manager import ExperimentManager
import argparse
import yaml
import subprocess
import pathlib

def get_args():
    parser = argparse.ArgumentParser(description='Run an experiment on the FL Testbed')
    
    parser.add_argument('-c', '--config', type=str, default="./fltb_config.yaml", help="path to FLTB config file")
    
    args = parser.parse_args()

    return args

# Useful: https://stackoverflow.com/a/43794480
def setup_logger():
    logger = logging.getLogger('fltb')
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()

    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

def parse_config(config_file):
    with open(config_file, "r") as stream:
        config_dict = yaml.safe_load(stream)

    config_dict["client_types_to_generate"] = []
    for d in config_dict["devices"]:
        config_dict["client_types_to_generate"].extend([d["device_type"]]*d["count"])
        
    return config_dict

def containerize_app(config_dict):
    project_name = config_dict["project"]
    user_code_path = config_dict["code"]["path"]
    base_dir = pathlib.Path(__file__).parent.resolve()
    return_code = subprocess.check_call([f"{base_dir}/build_push_pip_images.sh", project_name, user_code_path])

if __name__ == '__main__':
    print(f"Starting experiment manager")
    setup_logger()

    args = get_args()
    config_dict = parse_config(args.config)
    
    containerize_app(config_dict)

    exp_man = ExperimentManager()
    job_id = exp_man.launch_experiment(config_dict)

    print(f"Launched experiment with {job_id=}")