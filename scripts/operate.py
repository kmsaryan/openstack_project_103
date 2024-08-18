#!/usr/bin/python3

import sys
import time
import datetime
import openstack
import subprocess
import os

def run_command(command):
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip(), result.stderr.decode().strip()

def connect_to_openstack():
    return openstack.connect(
        auth_url=os.getenv('OS_AUTH_URL'),
        project_name=os.getenv('OS_PROJECT_NAME'),
        username=os.getenv('OS_USERNAME'),
        password=os.getenv('OS_PASSWORD'),
        user_domain_name=os.getenv('OS_USER_DOMAIN_NAME'),
        project_domain_name=os.getenv('OS_PROJECT_DOMAIN_NAME')
    )

def fetch_instance_names(conn, tag_name):
    network_name = f"{tag_name}_network"
    subnet_name = f"{tag_name}_subnet"
    router_name = f"{tag_name}_router"
    security_group_name = f"{tag_name}_security_group"
    keypair_name = f"{tag_name}_key"
    keypair = conn.compute.find_keypair(keypair_name)
    network = conn.network.find_network(network_name)
    subnet = conn.network.find_subnet(subnet_name)
    router = conn.network.find_router(router_name)
    security_group = conn.network.find_security_group(security_group_name)
    
    network_id = network.id if network else None
    subnet_id = subnet.id if subnet else None
    router_id = router.id if router else None
    security_group_id = security_group.id if security_group else None
    
    return network_id, subnet_id, router_id, security_group_id, keypair

def fetch_server_uuids(conn, image_name, flavor_name, keypair_id, network_id, security_group_id):
    # Fetch image UUID
    image = conn.compute.find_image(image_name)
    if not image:
        raise Exception(f"Image {image_name} not found")
    image_id = image.id
    flavor = conn.compute.find_flavor(flavor_name)
    if not flavor:
        raise Exception(f"Flavor {flavor_name} not found")
    flavor_id = flavor.id
    return {
        'keypair_name': keypair_id,
        'image_id': image_id,
        'flavor_id': flavor_id,
        'network_id': network_id,
        'security_group_id': security_group_id
    }

def create_and_attach_port(conn, server_name, image_id, flavor_id, keypair_name, security_group_name, network_id):
    port_name = f"{server_name}_port"  # Naming the port based on the server name
    existing_port = conn.network.find_port(port_name)
    
    if existing_port:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Port {port_name} already exists.")
        port = existing_port
    else:
        port = conn.network.create_port(
            name=port_name,
            network_id=network_id
        )
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created port {port_name}.")
    
        server = conn.compute.create_server(
            name=server_name,
            image_id=image_id,
            flavor_id=flavor_id,
            key_name=keypair_name,
            security_groups=[{'name': security_group_name}],
            networks=[{"port": port.id}]  # Use the created port explicitly
        )
        server = conn.compute.wait_for_server(server)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Server {server_name} created with port {port_name}.")

        if server.status == 'ERROR':
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ConflictException: Retrying...")
            conn.network.delete_port(port.id)
            port = conn.network.create_port(
                name=port_name,
                network_id=network_id
            )
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Recreated port {port_name}.")
            server = conn.compute.create_server(
                name=server_name,
                image_id=image_id,
                flavor_id=flavor_id,
                key_name=keypair_name,
                security_groups=[{'name': security_group_name}],
                networks=[{"port": port.id}]  # Use the created port explicitly
            )
            server = conn.compute.wait_for_server(server)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Server {server_name} created with port {port_name}.")
        else:
            print() 
    
    return server, port

def create_dev_servers(conn, tag_name, uuids, existing_servers, file_name):
    dev_server_prefix = f"{tag_name}_dev"
    existing_servers = list(existing_servers)  # Convert generator to list
    with open(file_name, 'r') as file:
        required_dev_servers = int(file.read())
    devservers_count = len([server for server in existing_servers if dev_server_prefix in server.name])
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Will need {required_dev_servers} dev servers, launching them.")
    if required_dev_servers > devservers_count:
        devservers_to_add = required_dev_servers - devservers_count
        sequence = devservers_count + 1
        while devservers_to_add > 0:
            devserver_name = f"{dev_server_prefix}{sequence}"
            create_and_attach_port(conn, devserver_name, uuids['image_id'], uuids['flavor_id'], uuids['keypair_name'], uuids['security_group_id'], uuids['network_id'])
            devservers_to_add -= 1
            sequence += 1
    elif required_dev_servers < devservers_count:
        devservers_to_remove = devservers_count - required_dev_servers
        for _ in range(devservers_to_remove):
            servers = list(conn.compute.servers(details=True, status='ACTIVE', name=f"{tag_name}_dev"))
            if servers:
                server_to_delete = servers[0]
                interfaces = list(conn.compute.list_server_interfaces(server_to_delete.id))
                for interface in interfaces:
                    conn.network.delete_port(interface.port_id)
                conn.compute.delete_server(server_to_delete.id)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deleted {server_to_delete.name} server")
    else:
        print(f"Required number of dev servers ({required_dev_servers}) already exist.")

def generate_configs(tag_name, public_key_file):
    key_path = public_key_file.replace('.pub', '')
    command = f"python3 gen_config.py {tag_name} {key_path}"
    output, error = run_command(command)
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Configuration files generated.")
    if error:
        command = f"python3 scripts/gen_config.py {tag_name} {key_path}"
    else:
        print(output)
    return output

def run_ansible_playbook():
    ansible_command = "ansible-playbook -i hosts site.yaml"
    output, error = run_command(ansible_command)
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Configuration files generated.")
    if error:
        ansible_command = "ansible-playbook -i hosts scripts/site.yaml"
    else:
        print(output)
    return output

def main(rc_file, tag_name, private_key_file):
    conn = connect_to_openstack()
    network_name = f"{tag_name}_network"
    security_group_name = f"{tag_name}_security_group"
    keypair_name = f"{tag_name}_key"
    existing_servers = conn.compute.servers()
    fetch_instance = fetch_instance_names(conn, tag_name)
    uuids = fetch_server_uuids(conn, 'Ubuntu 20.04 Focal Fossa x86_64', '1C-2GB-50GB', keypair_name, fetch_instance[0], fetch_instance[3])
    
    while True:
        create_dev_servers(conn, tag_name, uuids, existing_servers, "servers.conf")
        generate_configs(tag_name, private_key_file)
        time.sleep(20)
        print("sleeping for 20 seconds")
        run_ansible_playbook()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python operate.py <rc_file> <tag_name> <public_key_file>")
        sys.exit(1)
    rc_file = sys.argv[1]
    tag_name = sys.argv[2]
    private_key_file = sys.argv[3]
    main(rc_file, tag_name, private_key_file)
