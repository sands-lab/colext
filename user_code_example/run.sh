# Based in https://github.com/adap/flower/blob/main/examples/quickstart-pytorch/run.sh
#!/bin/bash

# Enable CTRL+C to stop all background processes
trap "echo 'Cleaning up' && trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

set -e
# Run commands as if launched on the script folder
cd "$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"/

# Add our python folder to the pythonpath so that python can find our package
# Only works because we already cded into the folder with this script
export PYTHONPATH="$(dirname `pwd`)/src:"

log_folder="./logs"
rm -fr $log_folder
mkdir $log_folder

# Hardcoded env vars to test
export COLEXT_ENV=1
export COLEXT_SERVER_ADDRESS="0.0.0.0:8080"
export COLEXT_JOB_ID=1
export COLEXT_CLIENT_DB_ID=25
export COLEXT_DEVICE_TYPE=FLServer
# export COLEXT_DATA_HOME_FOLDER=/colext/datasets
# export COLEXT_PYTORCH_DATASETS=/colext/pytorch_datasets
export COLEXT_MONITORING_LIVE_METRICS=True
export COLEXT_MONITORING_PUSH_INTERVAL=10
export COLEXT_MONITORING_SCRAPE_INTERVAL=1
export COLEXT_LOG_LEVEL=DEBUG

num_clients=1
num_rounds=1
echo ""
echo "Starting server"
python server.py -n $num_clients -r $num_rounds > ${log_folder}/server.out 2>&1 &
sleep 3  # Sleep for 3s to give the server enough time to start

for i in `seq 0 $((num_clients - 1))`; do
    echo "Starting client $i"
    export COLEXT_CLIENT_ID=$i
    python client.py > ${log_folder}/client_${i}.out 2>&1 &

    if [ "$i" -eq 0 ]; then
        # Delay start of next client
        # For some reason if 2 clients connect at the same time, the system won't start
        sleep 4 
    fi
done

tail -f ${log_folder}/client_0.out
# tail -f ${log_folder}/server.out

# Wait for all background processes to complete
wait