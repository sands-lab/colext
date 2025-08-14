import shutil
from pathlib import Path
from jinja2 import Template

# YAML template as a string
# NOTE: Generated configs will be placed in ./output/colext_configs, set path accordingly
EXPERIMENT_TEMPLATE = """\
name: benchmark_example
project: colext_example

code:
  path": "../../../flwr_tutorial_1_8"
  client:
    command: >-
      python3 ./client.py
      --flserver_address=${COLEXT_SERVER_ADDRESS}
      {{ extra_args }}
  server:
    command: >-
      python3 ./server.py
      --num_clients=${COLEXT_N_CLIENTS}
      --num_rounds=3

clients:
  - dev_type: JetsonAGXOrin
    count: 2
  - dev_type: JetsonOrinNano
    count: 2
  - dev_type: JetsonXavierNX
    count: 2
  - dev_type: JetsonNano
    count: 2
  - dev_type: OrangePi5B
    count: 2
"""


def prepare_experiments(template: str):
    """
    Generate all experiment configurations based on template and variable combinations.

    Returns a list of tuples: (filename_suffix, final_yaml)
    """
    experiments = []
    max_steps_list = [50, 100, 200]

    config_id = 0
    for step in max_steps_list:
        extra_args = f"--max_steps {step}"

        # Render template
        template_obj = Template(template)
        final_yaml = template_obj.render(extra_args=extra_args)

        filename_suffix = f"{config_id}_maxsteps_{step}"
        experiments.append((filename_suffix, final_yaml))
        config_id += 1

    return experiments

def write_experiments(output_dir: Path, experiments: list):
    """Write all experiment YAML strings to files."""

    for filename_suffix, exp_yaml in experiments:
        file_path = output_dir / f"{filename_suffix}.yaml"
        file_path.write_text(exp_yaml, encoding="utf-8")
        print(f"Generated {file_path}")

if __name__ == "__main__":
    # Clean existing output dir before we create new configs
    script_dir = Path(__file__).resolve().parent
    config_dir = script_dir / "output" / "colext_configs"

    # Clean previous output in a single line
    shutil.rmtree(config_dir, ignore_errors=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    experiments = prepare_experiments(EXPERIMENT_TEMPLATE)
    write_experiments(config_dir, experiments)
