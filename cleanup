#!/bin/bash
#private key is to be given as 3rd argument.
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <openrc> <tag>"
    exit 1
fi

OPENRC=$1
TAG=$2

install_dependencies() {
    touch install.log
    chmod 777 install.log
    echo "Checking and installing necessary dependencies..."
    if ! command -v python3 &> install.log; then
        sudo apt update > install.log
        sudo apt install -y python3 > install.log
    fi
    if ! command -v pip3 &> install.log; then
        sudo apt install -y python3-pip > install.log
    fi
    if ! command -v openstack &> install.log; then
        sudo apt install -y python3-openstackclient > install.log
    fi
    if ! command -v ansible &> install.log; then
        sudo add-apt-repository --yes --update ppa:ansible/ansible > install.log
        sudo apt install -y ansible > install.log
    fi
    if ! dpkg-query -W -f='${Status}' software-properties-common 2>install.log | grep -q "ok installed"; then
        sudo apt install -y software-properties-common > install.log
    fi
    pip3 install python-openstackclient argparse subprocess32 python-openstacksdk > install.log
}


# Function to set up permissions
setup_permissions() {
    chmod 777 scripts/cleanup.py
}

# Function to invoke the Python script
invoke_python_script() {
    source $OPENRC
    echo "sourced $OPENRC"
    python3 scripts/cleanup.py $OPENRC $TAG || exit 1
}
# Main script execution
install_dependencies
setup_permissions
invoke_python_script
