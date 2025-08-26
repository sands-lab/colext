#!/bin/bash

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <benchmark_folder>"
    exit 1
fi

if [ ! -d "$1" ]; then
    echo "Benchmark folder $1 does not exist"
    exit 1
fi

benchmark_folder=$(basename $1)
echo "Running benchmark for folder at $benchmark_folder"
mkdir -p "$benchmark_folder/output"
mkdir -p "$benchmark_folder/output/logs"

echo "Creating CoLExT configs using gen_configs.py for this benchmark"
python3 $benchmark_folder/gen_configs.py

# As jobs finish, print job ids as a map between job id and name. Eg. 1223=ResNet152
job_id_maps_file="$benchmark_folder/output/output_job_id_maps_`date +%Y_%m_%d-%H_%M_%S`.txt"
echo "Prepared output file for job id maps '$job_id_maps_file'"
echo

for config in "$benchmark_folder"/output/colext_configs/*; do
    config_id=$(basename "$config" .yaml)
    log_file="$benchmark_folder/output/logs/${config_id}.log"

    echo "Launching job based on: $config"
    echo "Log file: $log_file"
    colext_launch_job -c $config > "$log_file" 2>&1
    echo "Job finished"

    # Get job_id from pod labels
    job_id=$(mk get pod fl-server  -o=jsonpath='{.metadata.labels.colext-job-id}')
    if [ -z $job_id ]; then
        echo "ERROR: Could not find job id in fl-server pod labels. Stopping benchmark."
        exit 1
    fi
    echo "Finished experiment with job id = $job_id"
    echo

    # Append job id map to output file
    echo "$job_id=$config_id" >> $job_id_maps_file
done

echo
echo "Finished all experiments. Resulting job ids:"
cat $job_id_maps_file

