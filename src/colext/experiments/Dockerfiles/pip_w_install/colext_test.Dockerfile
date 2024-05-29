ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG BUILD_TYPE
ARG INSTALL_OPTIONS
WORKDIR /fl_testbed

RUN apt update && apt install -y git gcc
RUN python3 -m pip install --no-cache-dir --upgrade pip==24.0 setuptools==69.5.1

# DOCKER file assumes the context is set to root of the fltb project
# Install requirements first
COPY ./requirements.txt .
COPY ./user_code_example/requirements.txt ./user_code_example/

# Installing torch on jetson environment will remove support for gpu
# Removing torch requirement to prevent this
RUN if [ "$BUILD_TYPE" = 'jetson' ]; then \
        sed -i '/^torch/d' ./user_code_example/requirements.txt; \
    fi

# Putting this here to speed up install, this only works because fltb package dependency is commented out
RUN python3 -m pip install --no-cache-dir -r ./user_code_example/requirements.txt
RUN python3 -m pip install --no-cache-dir -r ./requirements.txt

# Copy fltb package
COPY . .
# Install fltb package
RUN python3 -m pip install .${INSTALL_OPTIONS}

WORKDIR /fl_testbed/user_code_example