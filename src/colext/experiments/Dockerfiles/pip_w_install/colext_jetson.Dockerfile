FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3
# dustynv/pytorch:2.0-r35.4.1
# Comes with Python 3.8.10
WORKDIR /fl_testbed

RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools
# Taken from https://medium.com/@tonistiigi/build-secrets-and-ssh-forwarding-in-docker-18-09-ae8161d066
RUN apt install --no-cache openssh-client git
# Download public key for github.com
RUN mkdir -p -m 0600 ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts
# Clone our private repository
RUN --mount=type=ssh git clone git@github.com:sands-lab/fl-testbed.git
# Install fltb package
RUN python3 -m pip install .[jetson]

# DOCKER script assumes the context is set to the user's code path
COPY ./requirements.txt ./user_code/
RUN python3 -m pip install --no-cache-dir -r ./user_code/requirements.txt

COPY . ./user_code

WORKDIR /fl_testbed/user_code