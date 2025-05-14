# syntax=docker.io/docker/dockerfile:1.7-labs
# Required for COPY --exclude
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG TEST_REL_DIR
ARG BUILD_TYPE
ARG INSTALL_OPTIONS
WORKDIR /fl_testbed

RUN apt update && apt install -y git gcc
RUN python3 -m pip install --no-cache-dir --upgrade pip==24.0 setuptools==69.5.1

#Network Setup
RUN apt install -y iproute2 
RUN python3 -m pip install --no-cache-dir tcconfig pika

# DOCKER file assumes the context is set to root of the fltb project
COPY $TEST_REL_DIR/requirements.txt test_code/requirements.txt
COPY ./requirements.txt .

### Install requirements first ###
# Installing torch on jetson environment will remove support for gpu
# Removing torch requirement to prevent this
RUN if [ "$BUILD_TYPE" = 'jetson' ]; then \
        sed -i '/^torch/d' test_code/requirements.txt; \
    fi
# Putting this here to speed up install, this only works because fltb package dependency is commented out
RUN python3 -m pip install --no-cache-dir -r ./test_code/requirements.txt
RUN python3 -m pip install --no-cache-dir -r ./requirements.txt

# Copy rest of test code
COPY $TEST_REL_DIR/ test_code/
# Copy and install fltb package
COPY --exclude=colext_config.yaml,requirements.txt  . .
RUN python3 -m pip install .${INSTALL_OPTIONS}


WORKDIR /fl_testbed/test_code
