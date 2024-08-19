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
def extract_public_key(private_key_path):
    public_key_path = private_key_path + '.pub'
    if not os.path.exists(public_key_path):
        command = f"ssh-keygen -y -f {private_key_path} > {public_key_path}"
        subprocess.run(command, shell=True, check=True)
    with open(public_key_path, 'r') as file:
        public_key = file.read().strip()    
    return public_key

def create_keypair(conn, keypair_name, private_key_path):
    keypair = conn.compute.find_keypair(keypair_name)
    current_date_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{current_date_time} Checking for keypair {keypair_name}.")
    if not keypair:
        public_key = extract_public_key(private_key_path)
        keypair = conn.compute.create_keypair(name=keypair_name, public_key=public_key)
        print(f"{current_date_time} Created keypair {keypair_name}.")
    else:
        print(f"{current_date_time} Keypair {keypair_name} already exists.")
    return keypair.id

def setup_network(conn, tag_name, network_name, subnet_name, router_name, security_group_name):
    # Create network
    network = conn.network.find_network(network_name)
    if not network:
        network = conn.network.create_network(name=network_name)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created network {network_name}.{network.id}")
        network_id = network.id

    else:
        network = conn.network.find_network(network_name)
        network_id = network.id
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Network {network_name}.{network_id} already exists.")

    # Create subnet
    subnet = conn.network.find_subnet(subnet_name)
    if not subnet:
        subnet = conn.network.create_subnet(
            name=subnet_name, network_id=network.id, ip_version=4, cidr='10.10.0.0/24',
            allocation_pools=[{'start': '10.10.0.2', 'end': '10.10.0.30'}] )
        subnet_id = subnet.id
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created subnet {subnet_name}.{subnet.id}")
    else:
        subnet = conn.network.find_subnet(subnet_name)
        subnet_id = subnet.id
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Subnet {subnet_name}.{subnet_id} already exists.")
    # Create router
    router = conn.network.find_router(router_name)
    if not router:
        router = conn.network.create_router(name=router_name, external_gateway_info={'network_id': conn.network.find_network('ext-net').id})
        conn.network.add_interface_to_router(router, subnet_id=subnet.id)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created router {router_name} and attached subnet {subnet_name}.")
        router_id = router.id
    else:
        router = conn.network.find_router(router_name)
        router_id = router.id
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Router {router_name}.{router_id} already exists.")

    # Create security group
    security_group = conn.network.find_security_group(security_group_name)
    if not security_group:
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
        security_group_id = security_group.id
    else:
        security_group = conn.network.find_security_group(security_group_name)
        security_group_id = security_group.id
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Security group {security_group_name}.{security_group_id} already exists.")  
    return network_id, subnet_id, router_id, security_group_id

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

def create_floating_ip(conn, network_name):
    floating_ips = conn.network.ips(floating_network_id=network_name)
    for floating_ip in floating_ips:
        if not floating_ip.port_id:
            return floating_ip.id, floating_ip.floating_ip_address
    
    external_network = conn.network.find_network(network_name)
    if not external_network:
        raise Exception(f"Network {network_name} not found")
    
    floating_ip = conn.network.create_ip(floating_network_id=external_network.id)
    return floating_ip

def associate_floating_ip(conn, server, floating_ip):
    server_instance = conn.compute.find_server(server)
    if not server_instance:
        raise Exception(f"Server {server} not found")
    server_port = list(conn.network.ports(device_id=server_instance.id))
    if not server_port:
        raise Exception(f"Port not found for server {server}")
    server_port = server_port[0]
    conn.network.update_ip(floating_ip.id, port_id=server_port.id)
    return floating_ip

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
def create_and_assign_fip(conn, server, network_name):
    floating_ips = conn.network.ips(floating_network_id=network_name)
    for floating_ip in floating_ips:
        if not floating_ip.port_id:
            return floating_ip.id, floating_ip.floating_ip_address
    
    external_network = conn.network.find_network(network_name)
    if not external_network:
        raise Exception(f"Network {network_name} not found")
    
    floating_ip = conn.network.create_ip(floating_network_id=external_network.id)
    return floating_ip.floating_ip_address, floating_ip.id

def get_floating_ip(addresses):
    for network, address_list in addresses.items():
        for address in address_list:
            if address['OS-EXT-IPS:type'] == 'floating':
                return address['addr']
    return None

def create_servers(conn, tag_name, image_id, flavor_id, keypair_name, security_group_name, network_id, existing_servers):
    fip_map = {}

    bastion_server_name = f"{tag_name}_bastion"

    if bastion_server_name in existing_servers:
        bastion_ser = conn.compute.find_server(bastion_server_name)
        fip = get_floating_ip(bastion_ser.addresses)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Bastion server {bastion_server_name} already exists. {fip}")
        bastion_fip=fip
    else:
        bastion_server = conn.compute.create_server(
            name=bastion_server_name,
            image_id=image_id,
            flavor_id=flavor_id,
            key_name=keypair_name,
            security_groups=[{'name': security_group_name}],
            networks=[{"uuid": network_id}]
        )
        bastion_server = conn.compute.wait_for_server(bastion_server)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} server {bastion_server.name} ")
        bastion_fip = create_floating_ip(conn, "ext-net")
        associate_floating_ip(conn, bastion_server_name, bastion_fip)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} server {bastion_server.name} assigned floating IP {bastion_fip.floating_ip_address}.")
        fip_map[bastion_server_name] = bastion_fip.floating_ip_address

    haproxy_server_name = f"{tag_name}_HAproxy"
    if haproxy_server_name in existing_servers:
        haproxy_ser = conn.compute.find_server(haproxy_server_name)
        fip1 = get_floating_ip(haproxy_ser.addresses)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} server {haproxy_server_name} already exists. {fip1}")
        haproxy_fip=fip1
    else:
        haproxy_server = conn.compute.create_server(
            name=haproxy_server_name,
            image_id=image_id,
            flavor_id=flavor_id,
            key_name=keypair_name,
            security_groups=[{'name': security_group_name}],
            networks=[{"uuid": network_id}]
        )
        haproxy_server = conn.compute.wait_for_server(haproxy_server)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} HAProxy server {haproxy_server.name} created.")
        haproxy_fip = create_floating_ip(conn, "ext-net")
        associate_floating_ip(conn, haproxy_server_name, haproxy_fip)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} HAProxy server {haproxy_server.name} assigned floating IP {haproxy_fip.floating_ip_address}.")
        fip_map[haproxy_server_name] = haproxy_fip.floating_ip_address

    haproxy_server2_name = f"{tag_name}_HAproxy2"
    if haproxy_server2_name in existing_servers:
        haproxy_ser2 = conn.compute.find_server(haproxy_server2_name)
        server_id = haproxy_ser2.id
        print(f"{server_id}")
        fip2 = get_floating_ip(haproxy_ser2.addresses)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} server {haproxy_server2_name} already exists. {fip2}")
        haproxy_fip2=fip2
    else:
        haproxy_server2 = conn.compute.create_server(
            name=haproxy_server2_name,
            image_id=image_id,
            flavor_id=flavor_id,
            key_name=keypair_name,
            security_groups=[{'name': security_group_name}],
            networks=[{"uuid": network_id}]
        )
        haproxy_server2 = conn.compute.wait_for_server(haproxy_server2)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} HAProxy server {haproxy_server2.name} created.")
        haproxy_fip2 = create_floating_ip(conn, "ext-net")
        associate_floating_ip(conn, haproxy_server2_name, haproxy_fip2)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} HAProxy server {haproxy_server2.name} assigned floating IP {haproxy_fip2.floating_ip_address}.")
        fip_map[haproxy_server2_name] = haproxy_fip2.floating_ip_address
        server_id = haproxy_server2.id  # Capture the server_id for the newly created server
    
    return fip_map, server_id

def manage_dev_servers(conn, existing_servers, tag_name, image_id, flavor_id, keypair_name, security_group_name, network_id):
    dev_ips = {}
    dev_server = f"{tag_name}_dev"
    required_dev_servers = 3
    devservers_count = len([line for line in existing_servers.splitlines() if dev_server in line])
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Will need {required_dev_servers} node, launching them.")        
    if required_dev_servers > devservers_count:
        devservers_to_add = required_dev_servers - devservers_count
        sequence = devservers_count + 1
        while devservers_to_add > 0:
            devserver_name = f"{dev_server}{sequence}"
            server = conn.compute.create_server(
                name=devserver_name,
                image_id=image_id,
                flavor_id=flavor_id,
                key_name=keypair_name,
                security_groups=[{'name': security_group_name}],
                networks=[{"uuid": network_id}]
            )
            server = conn.compute.wait_for_server(server)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created {devserver_name} server")
            if network_id in server.addresses and server.addresses[network_id]:
                internal_ip = server.addresses[network_id][0]['addr']
                dev_ips[devserver_name] = internal_ip
            devservers_to_add -= 1
            sequence += 1
    elif required_dev_servers < devservers_count:
        devservers_to_remove = devservers_count - required_dev_servers
        servers = list(conn.compute.servers(details=True, status='ACTIVE', name=f"{tag_name}_dev"))
        for _ in range(devservers_to_remove):
            if servers:
                server_to_delete = servers[0]
                conn.compute.delete_server(server_to_delete.id)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deleted {server_to_delete.name} server")
    else:
        print(f"Required number of dev servers({required_dev_servers}) already exist.")
    
    return dev_ips

def create_vip_port(conn, network_id, subnet_id, tag_name, server_name, existing_ports):
    vip_port_name = f"{tag_name}_vip_port"
    # Check if the port already exists using the OpenStack SDK
    existing_port = conn.network.find_port(vip_port_name)
    if existing_port:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {vip_port_name} already exists with ID {existing_port.id}.")
        return existing_port
    
    # Create a new VIP port if it does not exist
    vip_port = conn.network.create_port(
        name=vip_port_name,
        network_id=network_id,
        fixed_ips=[{"subnet_id": subnet_id}],
        security_groups=[],
        device_owner="network:loadbalancer",
        device_id=server_name
    )
    
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created VIP port {vip_port_name} with ID {vip_port.id}.")
    return vip_port

def assign_floating_ip_to_port(conn, vip_port):
    if vip_port is None:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port is None, cannot assign floating IP.")
        return None
    
    floating_ip_id, floating_ip_address = create_floating_ip(conn, "ext-net")
    if floating_ip_id is None:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Failed to create floating IP.")
        return None
    
    conn.network.update_ip(floating_ip_id, port_id=vip_port.id)
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Associated floating IP {floating_ip_address} with port {vip_port.id}.")
    return floating_ip_address, floating_ip_id

def attach_port_to_server(conn, server_name, vip_port):
    server_instance = conn.compute.find_server(server_name)
    server_interfaces = conn.compute.server_interfaces(server_instance)
    for interface in server_interfaces:
        if interface.port_id == vip_port.id:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {vip_port.id} is already attached to instance {server_name}.")
            return
    conn.compute.create_server_interface(
        server=server_instance.id,
        port_id=vip_port.id
    )
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Attached VIP port {vip_port.id} to instance {server_name}.")

def generate_vip_addresses_file(haproxy_server2, vip_floating_ip_haproxy2):
    with open("vip_address", "w") as f:
        f.write(f"{vip_floating_ip_haproxy2}\n")


def generate_servers_fips_file(server_fip_map, file_path):
    with open(file_path, 'w') as f:
        for server, fip in server_fip_map.items():
            f.write(f"{server}: {fip}\n")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Generated servers_fips file at {file_path}.")
    return file_path

def generate_configs(tag_name, private_key):
    print("Genrating Configuration files.")
    output = run_command(f"python3 gen_config.py {tag_name} {private_key}")
    print(output)
    return output

def run_ansible_playbook():
    print("Running Ansible playbook...")
    ansible_command = "ansible-playbook -i hosts site.yaml"
    subprocess.run(ansible_command, shell=True)

def main(rc_file, tag_name, private_key):
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

    create_keypair(conn, keypair_name, private_key)
    network_id, subnet_id, router_id, security_group_id = setup_network(conn, tag_name, network_name, subnet_name, router_name, security_group_name)
    uuids = fetch_server_uuids(conn, "Ubuntu 20.04 Focal Fossa x86_64", "1C-2GB-50GB", keypair_name, network_id, security_group_id)    
    existing_servers, _ = run_command("openstack server list --status ACTIVE --column Name -f value")
    fip_map, server_id =create_servers(conn, tag_name, uuids['image_id'], uuids['flavor_id'], uuids['keypair_name'], security_group_name, uuids['network_id'], existing_servers)
    generate_servers_fips_file(fip_map, "servers_fips")
    dev_ip_map=manage_dev_servers(conn, existing_servers, tag_name, uuids['image_id'], uuids['flavor_id'], uuids['keypair_name'], security_group_name, uuids['network_id'])
    existing_ports = conn.network.ports()
    vip_port_haproxy2 = create_vip_port(conn, network_id, subnet_id, tag_name, server_id, existing_ports)
    vip_floating_ip_haproxy2,vip_floating_ip_id = create_and_assign_fip(conn, vip_port_haproxy2, "ext-net")
    attach_port_to_server(conn, server_id, vip_port_haproxy2)
    generate_vip_addresses_file(server_id, vip_floating_ip_haproxy2)
    #generate_configs(tag_name,private_key)    
    #print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Configuration files generated.")
    #time.sleep(40) 
    #print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Waiting for 40 seconds before running Ansible playbook...")
    #run_ansible_playbook()
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deployment of {tag_name} completed.")
       
if __name__ == "__main__":
      if len(sys.argv) != 4:
        print("Usage: python install.py <rc_file> <tag_name> <private_key>")
        sys.exit(1)    
rc_file = sys.argv[1]
tag_name = sys.argv[2]
private_key = sys.argv[3]
main(rc_file, tag_name, private_key)
