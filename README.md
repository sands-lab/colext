# Collaborative Learning Experimentation Testbed (CoLExT)
This repo contains the code devolped to depoly and interact with the Collaborative Learning Testbed.
This work is being developed such that if your code can be deployed using the Flower interface, it can seamlessly be deployed in COLEXT.

## Overview
The repository contains two main sections:
- dev-config: Collection of Ansible scripts used to perform the initial configuration setup of Smartphones/IoT devices
- colext package: Used to deploy user code in the CoLExT.

## Usage
- Decorate + Read FL server address from env variable
- Have a requirements.txt at the root folder
Create colext_config.yaml

### Exposed environment variables

|      Client Vars      |                                                             |
| :-------------------: | ----------------------------------------------------------- |
| COLEXT_SERVER_ADDRESS | Server address (host:port)                                  |
|   COLEXT_N_CLIENTS    | Number of clients                                           |
|   COLEXT_CLIENT_ID    | ID of the client (0..n_clients)                             |
|  COLEXT_DEVICE_TYPE   | Hardware type of the client as requested in the config file |

|      Server Vars      |                                                             |
| :-------------------: | ----------------------------------------------------------- |
|   COLEXT_N_CLIENTS    | Number of clients                                           |

|        Dataset Vars        |                  |
| :---------------------: | ---------------- |
| COLEXT_DATA_HOME_FOLDER | Datasets path    |
| COLEXT_PYTORCH_DATASETS | Pytorch datasets |

|           Internal Vars           |                                                                     |
| :-------------------------------: | ------------------------------------------------------------------- |
|           COLEXT_JOB_ID           | Experiment job id                                                   |
|            COLEXT_ENV             | Presence of this variable identifies COLEXT environment             |
|        COLEXT_CLIENT_DB_ID        | Unique client ID on the database                                    |
|  COLEXT_MONITORING_LIVE_METRICS   | Indicates if metrics are periodically sent to DB or only at the end |
|  COLEXT_MONITORING_PUSH_INTERVAL  | Interval between metric push to DB                                  |
| COLEXT_MONITORING_SCRAPE_INTERVAL | Interval between HW metric scraping                                 |

## Available client types
- JetsonAGXOrin
- JetsonOrinNano

## Limitations
Currently only supports pytorch version 2.0
This is being imposed by the base image being used for the jetson docker image.

# Local development

## Connect to flserver
Currently development happens inside the flserver machine.
The flserver is part of an isolated KAUST network due to RC3 concerns.

To access the flserver, provide your public ssh key and kaust username.
Then add this config to your local .ssh/config
```
Host flserver
    Hostname 10.68.213.7
    ProxyJump 10.68.186.140
    ForwardAgent yes
```
Test connection to flserver:
```bash
ssh <username>@flserver
```

## Access to Github repo using ssh authentication
Before installing the package, you need to be able to access the github repo.
The flserver network does not allow outgoing communication through port 22, blocking the default ssh port.
However, we can communicate using port 443 using this trick:
https://docs.github.com/en/authentication/troubleshooting-ssh/using-ssh-over-the-https-port

Add this to your .ssh/config inside the flserver (not in your local machine)
```
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
```

You may also want to add your ssh key to the ssh agent in your local machine.
This allows you to use your private ssh key from your local machine without copying it to the flserver.
```bash
ssh-add -l # list keys in local agent
# if your key is not listed add it
ssh-add # add keys to agent
```

## Install package
```bash
# Create a conda/virtual environment with python 3.9.
mamba create -n colext_env_user python=3.9
# To isolate pip from system site-packages you might need to run:
echo "include-system-site-packages=false" >> $CONDA_PREFIX/pyvenv.cfg

# Install the package locally with the --editable flag.
# Note: Requires access to private colext repo
python3 -m pip install git+ssh://git@github.com/sands-lab/colext.git@sbc#egg=colext

# Fetch latest changes
python3 -m pip install -U -I git+ssh://git@github.com/sands-lab/colext.git@sbc
```

## How it works
It will start by containerizing the App.
It then deploys it to the Kubernetes cluster.
Decorators obtain performance measurements, gathered on the DB.
Grafana dashboard plots the results.

# Testbed detailed configuration:
https://www.notion.so/Device-first-time-setup-9d8c3d1256be476a9fc3642742b59d17


# Maximizing jetson performance
Jetson clocks - I think it turns off dynamic voltage and frequency scaling (DVFS)
https://rnext.it/jetson_stats/reference/jetson_clocks.html#jtop.core.jetson_clocks.JetsonClocks

# Nvidia Power Model Tool (NVP) models
- [Orin models](https://docs.nvidia.com/jetson/archives/r35.4.1/DeveloperGuide/text/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html#supported-modes-and-power-efficiency)
- [Xavier NX](https://docs.nvidia.com/jetson/archives/l4t-archived/l4t-325/#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/power_management_jetson_xavier.html#wwpID0E0VO0HA)
- [Nano](https://docs.nvidia.com/jetson/archives/l4t-archived/l4t-3273/#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/power_management_nano.html#wwpID0E0FL0HA)


Jetson power consumption:
Total consumption.
```
    power_mw = jetson.power["tot"]["power"]
```

Can separate cpu and gpu power in AGX Orin.
Can seperate CPU and GPU from SOC power in Orin Nano.


Fix this for flower 1.7:
```
    client_instructions = self.strategy.configure_fit(
  File "/usr/local/lib/python3.9/site-packages/colext/metric_collection/decorators/flwr_server_decorator.py", line 108, in configure_fit
    self.configure_clients_in_round(client_instructions, round_id)
  File "/usr/local/lib/python3.9/site-packages/colext/metric_collection/decorators/flwr_server_decorator.py", line 86, in configure_clients_in_round
    client_db_id = self.get_client_db_id(proxy)
  File "/usr/local/lib/python3.9/site-packages/colext/metric_collection/decorators/flwr_server_decorator.py", line 65, in get_client_db_id
    ip_address = re.search(r'ipv4:(\d+\.\d+\.\d+\.\d+):\d+', client_proxy.cid.__str__()).group(1)
AttributeError: 'NoneType' object has no attribute 'group'
```

docker login
specify which address the fl server expects to use

## Known issues:
sudo modprobe nf_conntrack


# Considering supporting conda-lock
Conda-lock fixes the conda environment to the specific os and platform
```
conda env export --from-history | egrep -v "^(name|prefix): " > environment.yaml
conda-lock -f environment.yml -p linux-64 -p linux-aarch64
```

https://github.com/canonical/microk8s/issues/2110
https://github.com/tekn0ir/toe
