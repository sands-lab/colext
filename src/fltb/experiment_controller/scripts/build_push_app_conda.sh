#!/bin/bash
# https://stackoverflow.com/questions/62015144/conda-env-export-from-history-does-not-track-channels
# --from-history will not track channels passed as '-c'. we need to explicitly add the channel to the env
#  
# conda env export --from-history | egrep -v "^(name|prefix): " > environment.yaml
# Might be a good idea to install conda-lock. It fixes the conda environment to the specific os and platform
# conda env export --from-history | egrep -v "^(name|prefix): " > environment.yaml
# Does not support direct instalation with pip! 
conda env export --from-history | egrep -v "^(name|prefix): " > environment.yaml
conda-lock -f environment.yml -p linux-64 -p linux-aarch64

REGISTY=kw61463:5000/fltestbed

docker buildx build --platform linux/amd64,linux/arm64 \
    -f Dockerfiles/flwr_client -t $REGISTY/flwr_client:latest --push .

docker build -f Dockerfiles/flwr_server -t $REGISTY/flwr_server:latest --push .