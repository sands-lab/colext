# Federated Learning Test Bed (FLTB)
This repo contains the code devolped to deply and interact with the Federated Learning testbed.
This work is being developed such that if your code can be deployed using the Flower interface, it can seamlessly be deployed in FLTB.

## Overview
The repository contains two main sections:
- dev-config: Collection of Ansible scripts used to perform the initial configuration setup of Smartphones/IoT devices 
- fltb package: Used to deploy user code in the FLTB. 

## Usage 
- Decorate + Read FL server address from env variable
- Have a requirements.txt at the root folder
Create fltb_config.yaml

Exposed env variables:
<!-- Config -->
- name: FLTB_SERVER_ADDRESS
- name: FLTB_CLIENT_ID
<!-- Data -->
- name: FLTB_DATA_HOME_FOLDER
- name: FLTB_PYTORCH_DATASETS
<!-- Internal -->
- name: FLTB_JOB_ID
- name: FLTB_ENV
- name: FLTB_CLIENT_DB_ID

## Limitations
Currently only supports pytorch version 2.1
This is currently being imposed by the base image being used for the jetson docker

## Local development
Create a conda/virtual environment with python 3.8.
Install the package locally with the --editable flag.
To isolate pip from site-packages you might need to run:
```
echo "include-system-site-packages=false" >> $CONDA_PREFIX/pyvenv.cfg
```

```
pip install -e .
```

## How it works
It will start by containerizing the App.
Deploy to Kubernetes cluster.
Decorators collect performance measurements, collected on the DB.
Grafana dashboard to see the results.


Documentation:
https://www.notion.so/Device-first-time-setup-9d8c3d1256be476a9fc3642742b59d17


## Private KAUST network limitations

### Access to Github using ssh 
https://docs.github.com/en/authentication/troubleshooting-ssh/using-ssh-over-the-https-port
Github just asks that we specify the https port (443)
Configure .ssh/config to use port 443 for github.com 
You may also want to add your ssh key to the key agent in your local machine:
```
ssh-add -l # list keys in agent
ssh-add # add keys to agent
```

Local .ssh/config
```
 Host flserver
    Hostname 10.68.213.7
    ProxyJump 10.68.186.140
    ForwardAgent yes