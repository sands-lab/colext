# CoLExT: Collaborative Learning Experimentation Testbed
CoLExT is a testbed built for machine learning researchers to realistically execute and profile Federated Learning (FL) algorithms on real edge devices and smartphones. This repo contains the software library developed to seamlessly deploy and monitor code compatible with the [Flower](https://github.com/adap/flower) Framework.
The testbed is hosted at the King Abdullah University of Science and Technology (KAUST).

> [!WARNING]
> CoLExT supports both SBC and Android deployments, but Android deployment is not yet available in this repo.

<p align="center">
  <img src="./images/CoLExT_schema.svg" alt="CoLExt Diagram" width="600">
</p>

# Using CoLExT
1. Access the CoLExT server. How to [access CoLExT](#accessing-the-colext-server).
1. Install the CoLExT package in a local Python environment, e.g. with venv.
    ```Python
    $ python3 -m venv .colext_env && source .colext_env/bin/activate

    # The plotting extras automatically generatess metric plots
    (.colext_env)$ python3 -m pip install colext[plotting] git+ssh://git@github.com/sands-lab/colext.git
    ```
1. In the FL code, import the `colext` decorators and wrap Flower's client and strategy classes.
   Note: If used outside of the testbed, these decorators do not modify the program behavior and thus can safely be included in the code in general.
    ```Python
    from colext import MonitorFlwrClient, MonitorFlwrStrategy

    @MonitorFlwrClient
    class FlowerClient(fl.client.NumPyClient):
      [...]
    @MonitorFlwrStrategy
    class FlowerStrategy(flwr.server.strategy.Strategy):
      [...]
    ```
1. Create a CoLExT configuration file `colext_config.yaml`. CoLExT exposes bash environment variables with information about the experiment.
   Please remember to pass the FL server address to the clients. Here's an example configuration file using SBC devices:
    ```YAML
    # colext_config.yaml
    project: colext_example

    code:
      client:
        # Assumes relative paths from the config file
        entrypoint: "./src/client.py"
        args: "--client_id=${COLEXT_CLIENT_ID} --server_addr=${COLEXT_SERVER_ADDRESS}"
      server:
        entrypoint: "./src/server.py"
        args: "--n_clients=${COLEXT_N_CLIENTS} --n_rounds=3"
    devices:
      - { dev_type: LattePandaDelta3, count: 4 }
      - { dev_type: OrangePi5B,  count: 2 }
      - { dev_type: JetsonOrinNano, count: 4 }
    monitoring:
      scraping_interval: 0.3  # in seconds
      push_to_db_interval: 10 # in seconds
    ```

1. Specify your Python dependencies using a `requirements.txt` file on the same directory as the CoLExT configuration file.
1. Deploy, monitor the experiment in real time, and download the collected performance metrics as CSV files.

    ```bash
    # Execute in the directory with the colext_config.yaml
    $ colext_launch_job
    # Prints a job-id and a dashboard link

    # After the job finishes, retrieve metrics for job-id as CSV files
    $ colext_get_metrics --job_id <job-id>
    ```

    Dashboard example:
    <p align="center">
      <img src="./images/power_gpu_some_dev.png" alt="CoLExt Dashboard" width="600">
    </p>

1. To confirm the deployment is working, try launching an example:
    ```bash
      $ cd colext/examples/flwr_tutorial
      $ colext_launch_job
    ```

Continue reading for more information on the above steps and check the tips section for the deployment type you're interested in:
- [SBC deployment](#tips-for-sbc-deployment)
- [Android deployment](#tips-for-android-deployment) (Not yet in this repo)

# CoLExT configuration file (colext_config.yaml)
This section describes the possible configuration options for the CoLExT configuration file.

### Currently available devices
```YAML
# SBCs
  - { device_type: JetsonAGXOrin,  count: 2 }
  - { device_type: JetsonOrinNano, count: 4 }
  - { device_type: JetsonXavierNX, count: 2 }
  - { device_type: JetsonNano, count: 6 }
  - { device_type: LattePandaDelta3, count: 6 }
  - { device_type: OrangePi5B, count: 8 }
# !!! Currently, this config file will not work with smartphones !!!
# Smartphones
  - { device_type: SamsungXCover6Pro, count: 3 }
  - { device_type: SamsungGalaxyM54, count: 2 }
  - { device_type: Xiaomi12, count: 2 }
  - { device_type: XiaomiPocoX5Pro, count: 2 }
  - { device_type: GooglePixel7, count: 5 }
  - { device_type: AsusRogPhone6, count: 2 }
  - { device_type: OnePlusNord2T5G, count: 2 }
```

### Exposed environment variables
CoLExT exposes several bash environment variables that are passed to the execution environment. These can be used as arguments in the `args` section of the client and server code by expanding the variables as `${ENV_VAR}`. See the [usage example](#using-colext) for an example.

|       Name       | Description                     |
| ---------------- | ------------------------------- |
|    COLEXT_CLIENT_ID     | ID of the client (0..n_clients) |
|    COLEXT_N_CLIENTS     | Number of clients in experiment |
|   COLEXT_DEVICE_TYPE    | Hardware type of the client     |
|  COLEXT_SERVER_ADDRESS  | Server address (host:port)      |
| COLEXT_PYTORCH_DATASETS | Pytorch datasets caching path   |
<!-- | COLEXT_DATA_HOME_FOLDER | Datasets path                   | -->

CoLExT also exposes the following variables which are meant to be used internally by the `colext` package.
|       Name        | Description                               |
| -------------------------- | ----------------------------------------- |
|            COLEXT_ENV             | True if inside a CoLExT environment |
|           COLEXT_JOB_ID           | Experiment job ID                         |
|        COLEXT_CLIENT_DB_ID        | Unique client ID on the database          |
|  COLEXT_MONITORING_LIVE_METRICS   | True if metrics are pushed in real-time   |
|  COLEXT_MONITORING_PUSH_INTERVAL  | Interval between metric push to DB        |
| COLEXT_MONITORING_SCRAPE_INTERVAL | Interval between HW metric scraping       |

### Performance monitoring options
```YAML
monitoring:
  live_metrics: True # True/False: True if metrics are pushed in real-time
  push_interval: 10 # in seconds: Metric buffer time before pushing metrics to the DB
  scraping_interval: 0.3 # in seconds: Interval between metric scraping
```

### Python version and deployers
Deployers:
- sbc (default) - Deployer for SBC experiments. It's the default deployer.
- local_py - Deployer that launches a local experiment. Clients and the server are launched in the CoLExT server.
- android (pending merge) - This deployer has been developed but needs to be merged here.

Python versions: 3.10 (default) | 3.8.
```
deployer: local_py
code:
  python_version: "3.8"
```

# Collected metrics
After calling `colext_get_metrics --job_id <job-id>`, csv files prepended with `colext_<job_id>_` are downloaded to the current directory.
Here are the contents for each CSV:

### client_round_timings.csv
- round_number: Number of the FL round
- stage: Stage of the round: FIT or EVAL
- start_time: Start of the round as measured by the FL server
- end_time: End of the round as measured by the FL server
- srv_accuracy: Evaluation of the server global model (Strategy evaluate result with dict key "accuracy")
- dist_accuracy: Result of aggregation of 'evaluate' results from clients (Strategy aggregate_evaluate result with dict key "accuracy"))

### client_info.csv
- client_id: ID of the client
- device_type: Device type as requested in the config file
- device_name: Name of the device with the associated device type

### client_round_timings.csv
- client_id: ID of the client
- round_number: Number of the FL round
- stage: Stage of the round: FIT or EVAL
- start_time: Start of the round as measured by the client
- end_time: End of the round as measured by the client

### hw_metrics.csv:
- client_id: ID of the client
- time: Local timestamp when the metrics were collected
- cpu_util: CPU Utilization (%) - Percentage over 100%, indicates multiple cores being used
- gpu_util: GPU Utilization (%)
- mem_util: Memory Utilization (Bytes) - The memory reported is the [RSS memory](https://en.wikipedia.org/wiki/Resident_set_size).
- n_bytes_sent: Number of bytes sent (Bytes)
- n_bytes_rcvd: Number of bytes received (Bytes)
- net_usage_out: Upload bandwidth usage (Bytes/s)
- net_usage_in: Download bandwidth usage (Bytes/s)
- power_consumption: Power consumption (Watts) - Reported power differs between devices
  - Nvidia Jetsons: Entire board power consumption
  - LattePandas: CPU power consumption
  - OrangePis: Can be measured using High Voltage Power Meter

### Summary data
Coming soon...

# Tips for SBC deployment
The SBC deployment containerizes user code and deploys it using Kubernetes.
Before starting the deployment process, it's recommended to make sure that a local deployment is working as expected.
Local deployment can be used by changing the deployer to `local_py`. More information on setting the deployer [here](#python-version-and-deployers).

Once this is verified, check the containarization is working as expected by running the `colext_launch_job` command in the "prepare" mode.
This mode will perform checks and containerize the application making sure all the dependencies can be installed in the container.
```Bash
# Prepares app for deployment
$ colext_launch_job -p
```

### Excluding files from CoLExT containerization
Files can be excluded from the automatic containerization by using a `.dockerignore` file on the same directory as the `colext_config.yaml`. For details on `.dockerignore`, check the [docker documentation](https://docs.docker.com/reference/dockerfile/#dockerignore-file).

### Debugging
Once the code is successfully deployed to CoLExT, it can be useful to debug issues using the Kubernetes CLI. In our deployment, we're using Microk8s with an alias to kubectl we called `mk`. Here are the most useful commands:
```Bash
# See current pods deployed in the cluster
$ mk get pods -o wide
# See and (f)ollow the logs of a specific pod
$ mk logs <pod_name> -f
# Read logs of a failed pod
$ mk logs <pod_name> -p
```

### Porting Poetry projects
Currently, CoLExT does not work with dependencies specified by Poetry. These can easily be converted to the supported requirements.txt format with these commands:
```
# Prevents Poetry resolver from being stuck waiting for a keyring that we don't need
export PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring
poetry export --without-hashes -f requirements.txt --output requirements.txt
```

# Tips for Android deployment
Coming soon...

# Accessing the CoLExT server
Currently, the CoLExT server is not reachable through a public IP. To enable access to the server, we're using [ZeroTier](https://www.zerotier.com/) to create a virtual private network. This allows external users to interact with the server as if they were directly on the same private network.

### Connect to CoLExT server:
1. [Install ZeroTier](https://www.zerotier.com/download/).
1. Get your ZeroTier device ID. The ID is displayed at installation and can be retrieved later with:
    ```
    sudo zerotier-cli info | awk '{print $3}'
    ```
1. Share your ZeroTier device ID and a public SSH key with your CoLExT contact point 
1. Add an SSH config. Note that you need to replace the username:
    ```
    # Add to ~/.ssh/config
    Host colext
        Username <your_username>
        Hostname 10.244.96.246
        ForwardAgent yes # Required to use local SSH keys in CoLExT
    ```
1. Add the CoLExT server to your hosts file.
    ```
    # Add to /etc/hosts
    10.244.96.246 colext
    ```
1. Wait for your device to be added to the ZeroTier network
1. Test connection to CoLExT server:
    ```bash
    # Confirm connectivity
    $ ping colext
    # Confirm ssh access
    $ ssh colext
    ```

Finally, to use CoLExT, you will need access to this (currently private) GitHub repo inside the CoLExT server. To have access, be sure you have an [SSH key associated with your GitHub account](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account) and add it to your SSH agent in your local machine. This allows you to use your private SSH key located on your local machine without copying it to the CoLExT server.

To add the key, disconnect from the CoLExT server if you were connected, and run the commands below from your local machine.
```bash
# On your local machine
$ ssh-add -l # list keys in the SSH agent
# if your key is not listed, add it
$ ssh-add # add keys to agent
$ ssh-add -l # confirm the key was added
# Connect to the CoLExT server
$ ssh colext
$ ssh-add -l # confirm the key is available in the CoLExT server
# You should now be able to install the Python package
```

If you're just getting started, continue reading the next step in the [using colext section](#using-colext).

# Developing the CoLExT package
Install the CoLExT package locally with the --editable flag.
```bash
$ python3 -m pip install -e <root_dir>
```
Useful:
- Experiment with launching an example using the local deployer
  ```YAML
  # colext_config.yaml
  deployer: local_py
  ```
- Prepare the deployment only by launching the job with the prepare flag:
  ```Bash
  $ colext_launch -p
  ```

### Repo overview
```
.
├── src/colext/     # Python package used to deploy user code and interact with results
│   ├── scripts/    # Folder with CoLExT CLI commands: launch_job + get_metrics
├── examples/       # Example of Flower code integrations with CoLExT
├── plotting/       # Ploting related code
├── colext_setup/   # CoLExT setup automation
│   ├── ansible/            # Ansible playbooks that perform the initial configuration of SBC devices
│   ├── db_setup/           # DB schema and initial DB populate file
│   ├── base_docker_imgs/   # Base docker images used when containerizing the code
```

# Testbed configuration notes (private):
[Notion page](https://www.notion.so/Device-first-time-setup-9d8c3d1256be476a9fc3642742b59d17)

### Maximizing jetson performance
Jetson clocks - maxes clocks and turns off dynamic voltage and frequency scaling (DVFS). Can be disabled with [jetson_stats](https://rnext.it/jetson_stats/reference/jetson_clocks.html#jtop.core.jetson_clocks.JetsonClocks).

### Nvidia Power Model Tool (NVP) models
- [Orin models](https://docs.nvidia.com/jetson/archives/r35.4.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html#supported-modes-and-power-efficiency)
- [Xavier NX](https://docs.nvidia.com/jetson/archives/l4t-archived/l4t-325/#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/power_management_jetson_xavier.html#wwpID0E0VO0HA)
- [Nano](https://docs.nvidia.com/jetson/archives/l4t-archived/l4t-3273/#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/power_management_nano.html#wwpID0E0FL0HA)

### Jetson power consumption measurements:
Total SBC power consumption.
```Python
  power_mw = jetson.power["tot"]["power"]
```
AGX Orin, Orin Nano - can separate CPU and GPU power from SOC power

# Limitations:
- Currently, CoLExT only directly supports FL code using the Flower framework 1.5 + 1.6.
- `tensorflow` package does not work with LattePandas.
  Tensorflow builds from PiPy for x86 arch expect them to have support for AVX instructions, but the LattePandas do not have them.
- Currently, Nvidia Jetsons defaults to supporting Pytorch 2.2.0. Except for Jetson Nanos, which only support up to Pytorch 1.13.
  Additional Pytorch versions can be supported upon request.
- Currently, only Python version 3.8 and 3.10 are supported.

# POTENTIAL FUTURE UPDATES
- Support more recent versions of Flower >= 1.7
- Support the new way of using Flwr client-server - Super link + Super node
- Look into the official Docker support for the new Flwr deployment option
- Add our Android template template as a Flwr template

### Consider supporting conda-lock
Alternative to requirements.txt.
Conda-lock grounds the conda environment to the specific os and platform
```
conda env export --from-history | egrep -v "^(name|prefix): " > environment.yaml
conda-lock -f environment.yml -p linux-64 -p linux-aarch64
```
