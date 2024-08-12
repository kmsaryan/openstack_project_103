# Project Overview

This project automates the management of development servers on OpenStack, including provisioning, configuration, and cleanup. The project consists of several Python scripts and an Ansible playbook that handle different aspects of the server lifecycle.

## PIP INSTALLATIONS 
    pip install python-openstackclient
    pip install python-openstacksdk
    pip install os
    pip install argparse
    pip install subprocess32
## Scripts

1. `install.py`: This script is responsible for the initial setup and installation of required packages and dependencies on the servers.

the script accepts the follwoing command line arguments
``` python3 install.py  <path to rc file> <tag>  <path to id_rsa.pub> ```

2. `operate.py`: This script manages the lifecycle of development servers. It ensures that the required number of development servers are running, generates necessary configuration files, and runs Ansible playbooks to configure the servers.

``` python3 operate.py  <path to rc file> <tag>  <path to id_rsa.pub> ```
### Usage
`<source_of_rcfile>`: The source of the OpenStack RC file.
`<tag_name>`: The tag name used for naming conventions.
`<public_key_file>`: The public key file for SSH access.

3. `gen_config.py`: This script generates SSH configuration and Ansible hosts files based on the current state of the development servers.

#### Usage

`<tag_name>`: The tag name used for naming conventions.
`<keypair_name>`: The name of the keypair used for SSH access.

4. `cleanup.py`: This script is used to clean up and delete the development servers and associated resources.

#### Usage
5. `site.yaml`: This is the main Ansible playbook that configures the development servers. It includes tasks for setting up the environment, installing necessary packages, and configuring services.

### hosts File
The hosts file is an Ansible inventory file that lists the servers and their connection details.
