# Container Image
FROM python:3.9

# Install additional utils
RUN apt update --allow-insecure-repositories && apt install -y sudo \
                                 vim \
                                 git \
                                 zip \
                                 cloc \
                                 dnsutils \
                                 zsh \
                                 zsh-syntax-highlighting \
                                 zsh-doc \
                                 less \
                                 liquidprompt \
                                 software-properties-common

RUN apt -y dist-upgrade

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    #
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    # && apt-get update \ # redundant
    # && apt-get install -y sudo \ # redundant
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Install Python Packages
RUN pip install --upgrade pip
RUN pip install dotbot docutils rcvpapi Pyyaml lxml jsonrpclib ansible cvprac pyeapi jsonschema treelib

# Clone AVD and CVP Collections
#RUN git clone https://github.com/aristanetworks/ansible-avd.git collections/ansible-avd
#RUN git clone https://github.com/aristanetworks/ansible-cvp.git collections/ansible-cvp