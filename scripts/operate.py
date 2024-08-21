#!/usr/bin/python3

import sys
import time
import datetime
import openstack
import subprocess

def run_command(command):
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip(), result.stderr.decode().strip()

def connect_to_openstack():
    return openstack.connect()

def log(message):
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} {message}")

def read_required_servers(file_path):
    with open(file_path, 'r') as file:
        return int(file.read().strip())

def get_network_parameters(conn, tag_name):
    network_name = f"{tag_name}_network"
    subnet_name = f"{tag_name}_subnet"
    router_name = f"{tag_name}_router"
    security_group_name = f"{tag_name}_security_group"
    keypair_name = f"{tag_name}_key"

    network = conn.network.find_network(network_name)
    subnet = conn.network.find_subnet(subnet_name)
    router = conn.network.find_router(router_name)
    security_group = conn.network.find_security_group(security_group_name)

    return network, subnet, router, security_group, keypair_name

def manage_dev_servers(conn, existing_servers, tag_name, keypair_name, network, security_group, required_dev_servers):
    dev_server_prefix = f"{tag_name}_dev"
    
    if not existing_servers:
        log("No servers retrieved from OpenStack. Please check the connection and server details.")
        return
    existing_servers = list(existing_servers)  # Ensure it is a list
    devservers_count = len([server for server in existing_servers if server.name.startswith(dev_server_prefix)])
    log(f"Current number of dev servers: {devservers_count}")
    
    if required_dev_servers > devservers_count:
        devservers_to_add = required_dev_servers - devservers_count
        log(f"Need to add {devservers_to_add} dev servers.")
        

        for i in range(devservers_count + 1, devservers_count + devservers_to_add + 1):
            devserver_name = f"{dev_server_prefix}{i}"
            log(f"Creating server {devserver_name}...")
            conn.compute.create_server(
                name=devserver_name,image_id=conn.compute.find_image('Ubuntu 20.04 Focal Fossa x86_64').id,flavor_id=conn.compute.find_flavor('1C-2GB-50GB').id,networks=[{"uuid": network.id}],
                security_groups=[{"name": security_group.name}],key_name=keypair_name
            )
            log(f"Server {devserver_name} created successfully.")
    
    elif required_dev_servers < devservers_count:
        devservers_to_remove = devservers_count - required_dev_servers
        log(f"Need to remove {devservers_to_remove} dev servers.")

        for server in existing_servers:
            log(f"Checking server {server.name} for deletion criteria...")
            if server.name.startswith(dev_server_prefix) and devservers_to_remove > 0:
                log(f"Attempting to delete server {server.name}...")
                try:
                    conn.compute.delete_server(server.id)
                    log(f"Server {server.name} deleted successfully.")
                    devservers_to_remove -= 1
                    existing_servers = list(conn.compute.servers(details=True))  # Refresh server list after deletion
                except Exception as e:
                    log(f"Failed to delete server {server.name}: {e}")
                
    else:
        log(f"Required number of dev servers ({required_dev_servers}) already exist. No action needed.")


def generate_configs(tag_name, private_key):
    print("Generating Configuration files.")
    try:
        output = run_command(f"python3 gen_config.py {tag_name} {private_key}")
        if "No such file or directory" in output[1]:
            raise FileNotFoundError
    except FileNotFoundError:
        output = run_command(f"python3 scripts/gen_config.py {tag_name} {private_key}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None
    print(output)
    return output

def run_ansible_playbook():
    print("Running Ansible playbook...")
    ansible_command = "ansible-playbook -i hosts scripts/site.yaml"
    subprocess.run(ansible_command, shell=True)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python operate.py <source_of_rcfile> <tag_name> <private_key>")
        sys.exit(1)

    source_of_rcfile = sys.argv[1]
    tag_name = sys.argv[2]
    private_key = sys.argv[3]
    conn = connect_to_openstack()
    while True:
        try:
            required_dev_servers = read_required_servers('configurations/servers.conf')
        except FileNotFoundError:
            required_dev_servers = read_required_servers('scripts/servers.conf')
        log(f"Required number of dev servers: {required_dev_servers}")
        
        existing_servers = conn.compute.servers(details=True) 
        network, subnet, router, security_group, keypair_name = get_network_parameters(conn, tag_name)        
        manage_dev_servers(conn, existing_servers, tag_name, keypair_name, network, security_group, required_dev_servers)
        print ("Sleeping for 30 seconds.")
        time.sleep(30)
        generate_configs(tag_name, private_key)
        print("sleeping for 30 seconds...")        
        time.sleep(30)
        run_ansible_playbook()
        log("Sleeping for 30 seconds...")
        time.sleep(30)