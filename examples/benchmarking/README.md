# CoLExT Benchmarks

Current version requires jinja as a dependency

## Running a benchmark
```bash
$ ./run_benchmark.sh <path_to_benchmark_folder>
```
This script:
- Calls <benchmark_folder>/gen_configs.py to generate CoLExT configs
- Outputs configs to `<benchmark_folder>/output/colext_configs`
- Launches jobs based on each config and records the job id
- Writes job ids to `<benchmark_folder>/output/output_job_id_maps.txt`

## Plotting results
After the benchmark finishes, generate plots:
```bash
$ python3 plot_benchmark.py <path_to_benchmark_folder>
```
This script:
- Reads job ids from `<benchmark_folder>/output/output_job_id_maps.txt`
- Generates plots and saves them to `<benchmark_folder>/output/plots`

## Creating a benchmark

Benchmarks are defined by multiple colext_config.yaml files. To automate their creation, each benchmark folder contains a `gen_configs.py` script. This script generates all the necessary configuration files and outputs them to `<benchmark_folder>/output/colext_configs`. Refer to existing benchmark folders for examples.

Once `gen_configs.py` is in place, run the benchmark as described in  [Running a benchmark](#how-to-run-a-benchmark).