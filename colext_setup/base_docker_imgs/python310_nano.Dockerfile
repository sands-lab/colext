FROM colext:5000/colext/jetson-nano:torch1.10-r32.7.1-py38

# Before we can abstract this we will also need to have the associated torch wheel
# ARG PYTHON_VERSION=python3.10

ENV HOME="/root"
WORKDIR ${HOME}
# Install Python dependencies
RUN apt update; apt install -y build-essential libssl-dev zlib1g-dev \
    libbz2-dev libreadline-dev libsqlite3-dev curl git \
    libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
RUN curl https://pyenv.run | bash
# https://stackoverflow.com/questions/65768775/how-do-i-integrate-pyenv-poetry-and-docker
ENV PYENV_ROOT="$HOME/.pyenv"
ENV PATH="${PYENV_ROOT}/shims:${PYENV_ROOT}/bin:${PATH}"

ENV PYTHON_VERSION=3.10
ENV MAKEFLAGS="-j$(nproc)"
ENV PYTHON_MAKEFLAGS="-j$(nproc)"
RUN pyenv install ${PYTHON_VERSION}
RUN pyenv global ${PYTHON_VERSION}

RUN python3 -m pip install numpy==1.26.4
COPY ./wheels/nano/${PYTHON_VERSION} /wheels
RUN find /wheels -name '*.whl' -exec python3 -m pip install {} +

# Confirm torch packages can be imported and torch can use cuda
RUN python3 --version && python3 -c "import torch; import torchvision; import torchaudio; \
                                        assert torch.cuda.is_available(), 'CUDA not available'"
