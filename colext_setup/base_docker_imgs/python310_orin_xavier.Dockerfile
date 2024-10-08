FROM flserver:5000/colext/jetson-nano:torch1.10-r32.7.1-py38

ARG PY_VERSION=3.10

RUN add-apt-repository -y ppa:deadsnakes/ppa
RUN apt install -y \
    python3.10 python3.10-dev python3.10-distutils \
    curl

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3


RUN python3 -m pip install numpy==1.26.4
# torchvision, torchaudio compatibility https://pytorch.org/get-started/previous-versions/
COPY ./torch_wheels/orin_xavier torch_wheels
RUN find torch_wheels/${PY_VERSION} -name '*.whl' -exec python3 -m pip install {} +

# Confirm torch packages can be imported and torch can use cuda
RUN python3 --version && python3 -c "import torch; import torchvision; import torchaudio; \
                                        print(f'CUDA available? {torch.cuda.is_available()}')"