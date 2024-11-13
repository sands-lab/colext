# syntax=docker.io/docker/dockerfile:1.7-labs
# Required for COPY --exclude
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_TYPE
ARG INSTALL_OPTIONS

WORKDIR /fl_testbed

RUN python3 -m pip install --no-cache-dir --upgrade pip==24.0 setuptools==69.5.1
# Based in https://medium.com/@tonistiigi/build-secrets-and-ssh-forwarding-in-docker-18-09-ae8161d066
RUN apt update && apt install -y git
# RUN apt update && apt install -y openssh-client git gcc \
#     && install -m 0600 -d ~/.ssh \
#     && ssh-keyscan -p 443 ssh.github.com >> ~/.ssh/known_hosts

ARG COLEXT_COMMIT_HASH
# Install the colext package
RUN python3 -m pip install \
    git+https://git@github.com/sands-lab/colext.git@${COLEXT_COMMIT_HASH}#egg=colext${INSTALL_OPTIONS}

# Dockerfile assumes the context is set to the user's code path
COPY ./requirements.txt ./user_code/
# Installing torch on jetson environment will remove support for gpu
# Removing torch requirement to prevent this
RUN if [ "$BUILD_TYPE" = 'jetson' ]; then \
        sed -i '/^torch/d' ./user_code/requirements.txt; \
    fi
RUN python3 -m pip install --no-cache-dir -r ./user_code/requirements.txt

# Temp fix for jetson nano, with the latest version of setuptools we get the error:
# https://github.com/aws-neuron/aws-neuron-sdk/issues/893
RUN python3 -m pip install --no-cache-dir setuptools==69.5.1
COPY --exclude=colext_config.yaml,requirements.txt . ./user_code
WORKDIR /fl_testbed/user_code