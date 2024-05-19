FROM nvcr.io/nvidia/l4t-pytorch:r35.2.1-pth2.0-py3

# Before we can abstract this we will also need to have the associated torch wheel
# ARG PYTHON_VERSION=python3.10

RUN add-apt-repository -y ppa:deadsnakes/ppa
RUN apt install -y \
    python3.10 python3.10-dev python3.10-distutils \
    curl
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.10
COPY ./torch_wheels/torch-2.2.0-cp310-cp310-linux_aarch64.whl .
RUN python3.10 -m pip install torch-2.2.0-cp310-cp310-linux_aarch64.whl
# torchvision, torchaudio compatibility https://pytorch.org/get-started/previous-versions/
RUN python3.10 -m pip install numpy==1.26.4 torchvision==0.17.0 torchaudio==2.2.0

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1

# Confirm torch can be imported
RUN python3 --version && python3 -c "import torch"