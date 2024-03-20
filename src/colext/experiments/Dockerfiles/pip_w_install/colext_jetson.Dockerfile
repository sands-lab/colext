FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3
# Comes with python 3.9.5
# dustynv/pytorch:2.0-r35.4.1
WORKDIR /fl_testbed
    
RUN python3 -m pip install --no-cache-dir --upgrade pip setuptools
# Based in https://medium.com/@tonistiigi/build-secrets-and-ssh-forwarding-in-docker-18-09-ae8161d066
RUN apt update && apt install -y openssh-client git gcc \
    && install -m 0600 -d ~/.ssh \
    && ssh-keyscan -p 443 ssh.github.com >> ~/.ssh/known_hosts

# Install the colext package
RUN --mount=type=ssh python3 -m pip install -I -U git+ssh://git@ssh.github.com:443/sands-lab/colext.git@sbc#egg=colext[jetson]

# Dockerfile assumes the context is set to the user's code path
COPY ./requirements.txt ./user_code/
# Installing torch on jetson environment will remove support for gpu
# Removing torch requirement to prevent this
RUN sed -i '/^torch/d' ./user_code/requirements.txt
    
RUN python3 -m pip install --no-cache-dir -r ./user_code/requirements.txt

COPY . ./user_code

WORKDIR /fl_testbed/user_code