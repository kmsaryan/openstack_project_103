#!/usr/bin/python3.8
import sys
import subprocess
import datetime
import time

def log(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} {message}")

def run_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"Command failed: {command}\n{result.stderr}")
    return result.stdout.strip()

def read_required_servers(file_path):
    with open(file_path, 'r') as file:
        return int(file.read().strip())

def get_network_parameters(tag_name):
    """Fetches the network parameters from OpenStack based on the naming convention."""
    network_name = run_command(f"openstack network list -f value -c Name | grep '{tag_name}_network'")
    subnet_name = run_command(f"openstack subnet list -f value -c Name | grep '{tag_name}_subnet'")
    router_name = run_command(f"openstack router list -f value -c Name | grep '{tag_name}_router'")
    security_group_name = run_command(f"openstack security group list -f value -c Name | grep '{tag_name}_security_group'")
    keypair_name = f"{tag_name}_key"

    return network_name, subnet_name, router_name, security_group_name, keypair_name

def manage_dev_servers(existing_servers, tag_name, keypair_name, network_name, security_group_name, required_dev_servers):
    dev_server = f"{tag_name}_dev"
    devservers_count = len([line for line in existing_servers.splitlines() if dev_server in line])
    log(f"Checking solution, we have: {devservers_count} nodes.")
    if required_dev_servers > devservers_count:
        log(f"Detecting lost node; {dev_server}_{devservers_count + 1}")
        devservers_to_add = required_dev_servers - devservers_count
        sequence = devservers_count + 1
        while devservers_to_add > 0:
            devserver_name = f"{dev_server}{sequence}"
            log(f"Launching new nodes; {devserver_name}, waiting for completion.")
            run_command(f"openstack server create --image 'Ubuntu 20.04 Focal Fossa x86_64' {devserver_name} --key-name {keypair_name} --flavor '1C-2GB-50GB' --network {network_name} --security-group {security_group_name}")
            log(f"Done, created {devserver_name} server")
            devservers_to_add -= 1
            sequence += 1
    elif required_dev_servers < devservers_count:
        devservers_to_remove = devservers_count - required_dev_servers
        for _ in range(devservers_to_remove):
            server_to_delete = run_command(f"openstack server list --status ACTIVE -f value -c Name | grep -m1 -oP '{tag_name}_dev([1-9]+)'")
            log(f"Detecting excess node; {server_to_delete}")
            run_command(f"openstack server delete {server_to_delete} --wait")
            log(f"Deleted {server_to_delete} server")
    else:
        log(f"Required number of dev servers({required_dev_servers}) already exist. Sleeping.")

def generate_configs(tag_name, keypair_name):
    """Invoke gen_config.py to generate SSH config and Ansible hosts file."""
    log("Updating playbook and SSH config")
    output = run_command(f"python3 gen_config.py {tag_name} {keypair_name}")
    return output

def run_ansible_playbook():
    """Run the Ansible playbook using the generated configuration files."""
    log("Running playbook")
    ansible_command = "ansible-playbook -i hosts site.yaml"
    subprocess.run(ansible_command, shell=True)
    log("Done, solution has been deployed.")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python operate.py <source_of_rcfile> <tag_name> <public_key_file>")
        sys.exit(1)
    
    source_of_rcfile = sys.argv[1]
    tag_name = sys.argv[2]
    public_key_file = sys.argv[3]
    while True:
        num_nodes=read_required_servers('servers.conf')
        log(f"Checking, we have: {num_nodes} nodes.")
        required_dev_servers = read_required_servers('servers.conf')
        log(f"Required number of dev servers: {required_dev_servers}")
        existing_servers = run_command("openstack server list --status ACTIVE -f value -c Name")
        network_name, subnet_name, router_name, security_group_name, keypair_name = get_network_parameters(tag_name)
        manage_dev_servers(existing_servers, tag_name, keypair_name, network_name, security_group_name, required_dev_servers)
        time.sleep(30)
        log("sleeping for 30 seconds")
        generate_configs(tag_name, keypair_name)
        time.sleep(30)
        log("sleeping for 30 seconds")
        run_ansible_playbook()
        log(f"Checking solution, we have:{num_nodes} nodes. Sleeping.")
        time.sleep(30)