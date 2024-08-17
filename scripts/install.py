#!/usr/bin/python3

import datetime
import time
import os
import sys
import openstack
import subprocess
import json
from openstack import connection


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
def create_keypair(conn, keypair_name, public_key_file):
    keypair = conn.compute.find_keypair(keypair_name)
    current_date_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{current_date_time} Checking for keypair {keypair_name}.")
    if not keypair:
        with open(public_key_file, 'r') as f:
            public_key = f.read().strip()
        keypair = conn.compute.create_keypair(name=keypair_name, public_key=public_key)
        print(f"{current_date_time} Created keypair {keypair_name}.")
    else:
        print(f"{current_date_time} Keypair {keypair_name} already exists.")
    
    return keypair.id

def setup_network(conn, tag_name, network_name, subnet_name, router_name, security_group_name):
    # Create network
    network = conn.network.find_network(network_name)
    if network:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Network {network_name} already exists.")
    else:
        network = conn.network.create_network(name=network_name)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created network {network_name}.")
    
    # Create subnet
    subnet = conn.network.find_subnet(subnet_name)
    if subnet:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Subnet {subnet_name} already exists.")
    else:
        subnet = conn.network.create_subnet(
            name=subnet_name, network_id=network.id, ip_version=4, cidr='10.10.0.0/24',
            allocation_pools=[{'start': '10.10.0.2', 'end': '10.10.0.30'}] )
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created subnet {subnet_name}.")
    
    # Create router
    router = conn.network.find_router(router_name)
    if not router:
        router = conn.network.create_router(name=router_name, external_gateway_info={'network_id': conn.network.find_network('ext-net').id})
        conn.network.add_interface_to_router(router, subnet_id=subnet.id)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created router {router_name} and attached subnet {subnet_name}.")

    # Create security group
    security_group = conn.network.find_security_group(security_group_name)
    if security_group:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Security group {security_group_name} already exists.")
    else:
        security_group = conn.network.create_security_group(name=security_group_name)
        rules = [
            {"protocol": "tcp", "port_range_min": 22, "port_range_max": 22, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "icmp", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 80, "port_range_max": 80, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 5000, "port_range_max": 5000, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 8080, "port_range_max": 8080, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "udp", "port_range_min": 6000, "port_range_max": 6000, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 9090, "port_range_max": 9090, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 9100, "port_range_max": 9100, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 3000, "port_range_max": 3000, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "udp", "port_range_min": 161, "port_range_max": 161, "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": 112, "remote_ip_prefix": "0.0.0.0/0"}  # VRRP protocol
        ]
        for rule in rules:
            conn.network.create_security_group_rule(
                security_group_id=security_group.id,
                direction='ingress',
                protocol=rule['protocol'],
                port_range_min=rule.get('port_range_min'),
                port_range_max=rule.get('port_range_max'),
                remote_ip_prefix=rule['remote_ip_prefix']
            )
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created security group {security_group_name} with rules.")
    network_id = network.id
    subnet_id = subnet.id
    security_group_id = security_group.id
    #print(f"Network ID: {network_id},Subnet ID: {subnet_id},Security Group ID: {security_group_id}")    
    return network_id, subnet_id, security_group_id

def wait_for_active_state(server, retries=5, delay=30):
    for _ in range(retries):
        status, _ = run_command(f"openstack server show {server} -c status -f value")
        if status.strip() == "ACTIVE":
            return True
        time.sleep(delay)
    return False

def wait_for_network_ready(server, retries=5, delay=30):
    for _ in range(retries):
        net_status, _ = run_command(f"openstack server show {server} -c addresses -f value")
        if net_status.strip():
            return True
        time.sleep(delay)
    return False

def create_and_associate_floating_ip(conn, target, network_name="ext-net"):
    external_network = conn.network.find_network(network_name)
    if not external_network:
        raise Exception(f"Network {network_name} not found")
    
    # Check for existing, unused floating IPs
    existing_fips = list(conn.network.ips(status='DOWN', floating_network_id=external_network.id))
    if existing_fips:
        floating_ip = existing_fips[0]
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Reusing floating IP {floating_ip.floating_ip_address}.")
    else:
        # Create a new floating IP if none are available
        floating_ip = conn.network.create_ip(floating_network_id=external_network.id)
    
    if isinstance(target, str):  # If target is a server name
        server_instance = conn.compute.find_server(target)
        if not server_instance:
            raise Exception(f"Server {target} not found")
        server_port = list(conn.network.ports(device_id=server_instance.id))
        if not server_port:
            raise Exception(f"Port not found for server {target}")
        server_port = server_port[0]
        conn.network.update_ip(floating_ip.id, port_id=server_port.id)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Assigned floating IP {floating_ip.floating_ip_address} to {target}.")
    else:  # If target is a port
        conn.network.update_ip(floating_ip.id, port_id=target.id)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Assigned floating IP {floating_ip.floating_ip_address} to port {target.name}.")
    
    return floating_ip.floating_ip_address

def create_port(conn, network_id, port_name, tags=None):
    
    existing_port = conn.network.find_port(port_name)
    if existing_port:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Port {port_name} already exists.")
        return existing_port
    port = conn.network.create_port(
        name=port_name,
        network_id=network_id,
        tags=tags or []
    )
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created port {port_name}.")
    return port

def attach_port_to_server(conn, server_name, port):
    server = conn.compute.find_server(server_name)
    if server:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Found server {server_name}.")
    else:
        raise Exception(f"Server {server_name} not found")
    conn.compute.create_server_interface(server=server.id, port_id=port.id)
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Attached port {port.id} to server {server_name}.")
    return port

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

def create_server(conn, name, image_id, flavor_id, keypair_name, security_group_name, network_id):
    server = conn.compute.create_server(
        name=name,
        image_id=image_id,
        flavor_id=flavor_id,
        key_name=keypair_name,
        security_groups=[{'name': security_group_name}],
        networks=[{"uuid": network_id}]
    )
    server = conn.compute.wait_for_server(server)
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Server {name} created.")
    return server

def create_fip_servers(conn, tag_name, uuids, existing_servers):
    server_fip_map = {}
    for server_name in ["bastion", "HAproxy", "HAproxy2"]:
        full_server_name = f"{tag_name}_{server_name}"
        if full_server_name in existing_servers:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Server {full_server_name} already exists.")
            # Assuming existing servers already have floating IPs assigned
            fip = get_floating_ip_for_server(conn, full_server_name)
            server_fip_map[full_server_name] = fip
        else:
            server = create_server(conn, full_server_name, uuids['image_id'], uuids['flavor_id'], uuids['keypair_name'], uuids['security_group_id'], uuids['network_id'])
            wait_for_active_state(server.name)
            fip = create_and_associate_floating_ip(conn, full_server_name)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created server {full_server_name} with floating IP {fip}.")
            server_fip_map[full_server_name] = fip
    return server_fip_map

def get_floating_ip_for_server(conn, server_name):
    server = conn.compute.find_server(server_name)
    if server:
        for address in server.addresses.values():
            for addr in address:
                if addr['OS-EXT-IPS:type'] == 'floating':
                    return addr['addr']
    return None


def generate_servers_fips_file(server_fip_map, file_path):
    with open(file_path, 'w') as f:
        for server, fip in server_fip_map.items():
            f.write(f"{server}: {fip}\n")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Generated servers_fips file at {file_path}.")


def create_dev_servers(conn, tag_name, uuids, existing_servers):
    dev_server_prefix = f"{tag_name}_dev"
    required_dev_servers = 3
    devservers_count = len([line for line in existing_servers.splitlines() if dev_server_prefix in line])
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Will need {required_dev_servers} dev servers, launching them.")
    
    if required_dev_servers > devservers_count:
        devservers_to_add = required_dev_servers - devservers_count
        sequence = devservers_count + 1
        while devservers_to_add > 0:
            devserver_name = f"{dev_server_prefix}{sequence}"
            create_server(conn, devserver_name, uuids['image_id'], uuids['flavor_id'], uuids['keypair_name'], uuids['security_group_id'], uuids['network_id'])
            devservers_to_add -= 1
            sequence += 1
    elif required_dev_servers < devservers_count:
        devservers_to_remove = devservers_count - required_dev_servers
        for _ in range(devservers_to_remove):
            servers = conn.compute.servers(details=True, status='ACTIVE', name=f"{tag_name}_dev")
            if servers:
                server_to_delete = servers[0]
                conn.compute.delete_server(server_to_delete.id, wait=True)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deleted {server_to_delete.name} server")
    else:
        print(f"Required number of dev servers ({required_dev_servers}) already exist.")


def get_port_by_name(port_name):
    ports_list, _ = run_command(f"openstack port list -f json")
    ports = json.loads(ports_list)
    for port in ports:
        if port['Name'] == port_name:
            return port['ID']
    return None

def find_or_create_vip_port(conn, network_id, tag_name, server_name):
    existing_ports = list(conn.network.ports(network_id=network_id, name=f"{tag_name}_vip_port"))
    if existing_ports:
        vip_port = existing_ports[0]
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {tag_name}_vip_port already exists.")
        
        # Check if the VIP port is associated with any server and has a floating IP
        floating_ips = list(conn.network.ips(port_id=vip_port.id))
        if floating_ips:
            floating_ip = floating_ips[0]
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {tag_name}_vip_port is already associated with floating IP {floating_ip.floating_ip_address}.")
            
            # Check if the port is active
            if vip_port.status != 'ACTIVE':
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {tag_name}_vip_port is not active. Attempting to reinitialize.")
                conn.network.update_port(vip_port.id, admin_state_up=True)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {tag_name}_vip_port reinitialized.")
            
            return vip_port, floating_ip.floating_ip_address
        else:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {tag_name}_vip_port exists but has no floating IP associated.")
            return vip_port, None
    else:
        vip_port = conn.network.create_port(
            network_id=network_id,
            name=f"{tag_name}_vip_port"
        )
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created VIP port {tag_name}_vip_port.")
        return vip_port, None

    
def generate_vip_addresses_file(vip_floating_ip):
    with open(os.path.join("vip_address"), "w") as f:
        f.write(f"{vip_floating_ip}\n")
    return vip_floating_ip

def generate_configs(tag_name, public_key_file):
    key_path = public_key_file.replace('.pub', '')
    command = f"python3 gen_config.py {tag_name} {key_path}"
    output, error = run_command(command)
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Configuration files generated.")
    if error:
        print(f"Error: {error}")
    else:
        print(output)
    return output

def run_ansible_playbook():
    ansible_command = "ansible-playbook -i hosts site.yaml"
    print(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "{ansible_command}")
    subprocess.run(ansible_command, shell=True)

def main(rc_file, tag_name, public_key_file):
    current_date_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{current_date_time} Starting deployment of {tag_name} using {rc_file} for credentials.")
    
    with open(rc_file) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
    
    conn = connect_to_openstack()
    network_name = f"{tag_name}_network"
    subnet_name = f"{tag_name}_subnet"
    router_name = f"{tag_name}_router"
    security_group_name = f"{tag_name}_security_group"
    keypair_name = f"{tag_name}_key"
    bastion_server = f"{tag_name}_bastion"
    haproxy_server = f"{tag_name}_HAproxy"
    haproxy_server2 = f"{tag_name}_HAproxy2"
    vip_port = f"{tag_name}_vip"

    create_keypair(conn, keypair_name, public_key_file)
    network_id, subnet_id, security_group_id = setup_network(conn, tag_name, network_name, subnet_name, router_name, security_group_name)
    uuids = fetch_server_uuids(conn, "Ubuntu 20.04 Focal Fossa x86_64", "1C-2GB-50GB", keypair_name, network_id, security_group_id)    
    existing_servers, _ = run_command("openstack server list --status ACTIVE --column Name -f value")

    server_fip_map = create_fip_servers(conn, tag_name, uuids, existing_servers)
    generate_servers_fips_file(server_fip_map, "servers_fip")

    create_dev_servers(conn, tag_name, uuids, existing_servers)
    
    vip_port, existing_fip = find_or_create_vip_port(conn, network_id, tag_name, haproxy_server2)
    if existing_fip:
        vip_floating_ip = existing_fip
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP floating IP {vip_floating_ip} already exists.")

    else:
        vip_floating_ip = create_and_associate_floating_ip(conn, vip_port)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP floating IP {vip_floating_ip} created.")
    
    generate_vip_addresses_file(vip_floating_ip)
    generate_configs(tag_name, public_key_file)
    #print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Waiting for 20 seconds before running Ansible playbook...")
    #run_ansible_playbook()
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deployment of {tag_name} completed.")
       
if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python install.py <rc_file> <tag_name> <public_key_file>")
        sys.exit(1)    
    rc_file = sys.argv[1]
    tag_name = sys.argv[2]
    public_key_file = sys.argv[3]
    main(rc_file, tag_name, public_key_file)
