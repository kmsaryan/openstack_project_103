#!/usr/bin/python3

import datetime
import time
import os
import sys
import openstack
import subprocess
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
    #print(f"{public_key_path}")
    if not os.path.exists(public_key_path):
        command = f"ssh-keygen -y -f {private_key_path} > {public_key_path}"
        subprocess.run(command, shell=True, check=True)
    with open(public_key_path, 'r') as file:
        public_key = file.read().strip()
        #print(f"{public_key}")
    return public_key

def create_keypair(conn, keypair_name, private_key_path):
    keypair = conn.compute.find_keypair(keypair_name)
    current_date_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{current_date_time} Checking for keypair {keypair_name}.")
    if not keypair:
        public_key = extract_public_key(private_key_path)
        keypair = conn.compute.create_keypair(name=keypair_name, public_key=public_key)
        print(f"{current_date_time} Created keypair {keypair_name}.")
        # Verify that the keypair was uploaded correctly
        uploaded_keypair = conn.compute.find_keypair(keypair_name)
        if uploaded_keypair and uploaded_keypair.public_key == public_key:
            print(f"{current_date_time} Verified keypair {keypair_name} was uploaded successfully.")
        else:
            print(f"{current_date_time} Failed to verify keypair {keypair_name}.")
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
    else:
        router = conn.network.find_router(router_name)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Router {router_name} already exists.")

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
            security_group_id=security_group.id
            return security_group_id
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created security group {security_group_name} with rules.{security_group_id}")

    else:
        security_group = conn.network.find_security_group(security_group_name)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Security group {security_group_name} already exists{security_group.id}")  
    return network_id, subnet_id

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
            return  floating_ip.id, floating_ip.floating_ip_address
    external_network = conn.network.find_network(network_name)
    if not external_network:
        raise Exception(f"Network {network_name} not found")
    floating_ip = conn.network.create_ip(floating_network_id=external_network.id)
    return floating_ip,floating_ip.id, floating_ip.floating_ip_address

def associate_floating_ip(conn, server, floating_ip_tuple):
    floating_ip, floating_ip_id, floating_ip_address = floating_ip_tuple  # Unpack the tuple
    server_instance = conn.compute.find_server(server)
    if not server_instance:
        raise Exception(f"Server {server} not found")
    server_port = list(conn.network.ports(device_id=server_instance.id))
    if not server_port:
        raise Exception(f"Port not found for server {server}")
    server_port = server_port[0]
    conn.network.update_ip(floating_ip_id, port_id=server_port.id)
    return floating_ip


def fetch_server_uuids(conn, image_name, flavor_name, security_group_name):
    # Fetch image UUID
    image = conn.compute.find_image(image_name)
    if not image:
        raise Exception(f"Image {image_name} not found")
    image_id = image.id
    
    # Fetch flavor UUID
    flavor = conn.compute.find_flavor(flavor_name)
    if not flavor:
        raise Exception(f"Flavor {flavor_name} not found")
    flavor_id = flavor.id
    # Fetch security group UUID
    security_group = conn.network.find_security_group(security_group_name)
    if not security_group:
        raise Exception(f"Security group {security_group_name} not found")
    security_group_id = security_group.id
    return {'image_id': image_id, 'flavor_id': flavor_id, 'security_group_id': security_group_id}

def get_floating_ip(addresses):
    for network, address_list in addresses.items():
        for address in address_list:
            if address['OS-EXT-IPS:type'] == 'floating':
                return address['addr']
    return None

def create_servers(conn, server_name, port_name, image_id, flavor_id, keypair_name, security_group_id, network_id, floating_ip_required,existing_servers): 
    if server_name in existing_servers:
        server = conn.compute.find_server(server_name)
        port = conn.network.find_port(port_name)
        fip = get_floating_ip(server.addresses) if floating_ip_required else None
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Server {server_name} already exists. {fip}, {port_name}")
        #print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Used security group: {security_group_id}")
        return server, fip
    else:
        port = conn.network.create_port(name=port_name, network_id=network_id,security_groups=[security_group_id])
        #print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Using security group: {security_group_id}")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created port {port.name} with ID {port.id}.")
        server = conn.compute.create_server(
            name=server_name,
            image_id=image_id,
            flavor_id=flavor_id,
            key_name=keypair_name,
            networks=[{"port": port.id}]
        )
        server = conn.compute.wait_for_server(server)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Server {server.name}")
        # Verify the applied security groups
        applied_security_groups = [sg['name'] for sg in server.security_groups]
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Applied security groups: {applied_security_groups}")

        if floating_ip_required:
            fip_tuple = create_floating_ip(conn, "ext-net")
            associate_floating_ip(conn, server_name, fip_tuple)
            fip = fip_tuple[2]  # Use the floating IP address
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Server {server.name} assigned floating IP {fip}.")
        else:
            fip = None
        return server, fip

def manage_dev_servers(conn, existing_servers, tag_name, image_id, flavor_id, keypair_name, security_group_name, network_id):
    dev_ips = {}
    dev_server = f"{tag_name}_dev"
    dev_port_name = f"{tag_name}_dev_port"
    required_dev_servers = 3
    devservers_count = len([line for line in existing_servers.splitlines() if dev_server in line])
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Will need {required_dev_servers} node, launching them.")        
    dev_servers = conn.compute.servers(details=True, all_projects=False, filters={"name": f"{dev_server}*"})
    for server in dev_servers:
        if network_id in server.addresses and server.addresses[network_id]:
            internal_ip = server.addresses[network_id][0]['addr']
            dev_ips[server.name] = internal_ip
            print(f"Existing server {server.name} with IP {internal_ip} added to dev_ips")

    if required_dev_servers > devservers_count:
        devservers_to_add = required_dev_servers - devservers_count
        sequence = devservers_count + 1
        while devservers_to_add > 0:
            devserver_name = f"{dev_server}{sequence}"
            dev_port_n = f"{dev_port_name}{sequence}"
            server, _ = create_servers(conn, devserver_name, dev_port_n, image_id, flavor_id, keypair_name, security_group_name, network_id, False, existing_servers)
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
    # Convert the generator to a list
    existing_floating_ips = list(conn.network.ips(port_id=vip_port.id))
    if existing_floating_ips:
        existing_floating_ip = existing_floating_ips[0]
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {vip_port.id} already has floating IP {existing_floating_ip.floating_ip_address}.")
        return existing_floating_ip.floating_ip_address, existing_floating_ip.id
    floating_ip_tuple = create_floating_ip(conn, "ext-net")
    if floating_ip_tuple[1] is None:  # Check the floating IP ID
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Failed to create floating IP.")
        return None
    conn.network.update_ip(floating_ip_tuple[1], port_id=vip_port.id)  # Use the floating IP ID
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Associated floating IP {floating_ip_tuple[2]} with port {vip_port.id}.")  # Use the floating IP address
    return floating_ip_tuple[2], floating_ip_tuple[1]  # Return the floating IP address and ID


def attach_port_to_server(conn, server_name, vip_port):
    server_instance = conn.compute.find_server(server_name)
    server_interfaces = conn.compute.server_interfaces(server_instance)
    for interface in server_interfaces:
        if interface.port_id == vip_port.id:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {vip_port.id} is already attached to instance,{server_instance.name}.")
            return
    conn.compute.create_server_interface(
        server=server_instance.id,
        port_id=vip_port.id
    )
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Attached VIP port {vip_port.id} to instance {server_instance.name}.")

def generate_vip_addresses_file(vip_floating_ip_haproxy2):
    with open("vip_address.txt", "w") as f:
        f.write(f"{vip_floating_ip_haproxy2}\n")


def generate_servers_ip_file(server_fip_map, file_path):
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
    bastion_name = f"{tag_name}_bastion"
    bastion_port_name = f"{tag_name}_bastion_port"
    haproxy_name = f"{tag_name}_HAproxy"
    haproxy_port_name = f"{tag_name}_HAproxy_port"
    haproxy2_name = f"{tag_name}_HAproxy2"
    haproxy2_port_name = f"{tag_name}_HAproxy2_port"
    

    #create_keypair(conn, keypair_name, private_key)
    network_id, subnet_id = setup_network(conn, tag_name, network_name, subnet_name, router_name, security_group_name,)
    uuids = fetch_server_uuids(conn, "Ubuntu 20.04 Focal Fossa x86_64", "1C-2GB-50GB",security_group_name)
    existing_servers, _ = run_command("openstack server list --status ACTIVE --column Name -f value")
    bastion_server, bastion_fip = create_servers(conn,bastion_name,bastion_port_name,uuids['image_id'],uuids['flavor_id'],keypair_name,uuids['security_group_id'],network_id,True,existing_servers)
    haproxy_server, haproxy_fip = create_servers(conn, haproxy_name, haproxy_port_name, uuids['image_id'],uuids['flavor_id'],keypair_name,uuids['security_group_id'],network_id,True,existing_servers)
    haproxy2_server, haproxy2_fip = create_servers(conn, haproxy2_name, haproxy2_port_name, uuids['image_id'],uuids['flavor_id'],keypair_name,uuids['security_group_id'],network_id,True,existing_servers)
    fip_map = {
        bastion_name: bastion_fip,
        haproxy_name: haproxy_fip,
        haproxy2_name: haproxy2_fip
    }    
    generate_servers_ip_file(fip_map, "servers_fip")
    dev_ip_map = manage_dev_servers(conn, existing_servers, tag_name, uuids['image_id'], uuids['flavor_id'], keypair_name, uuids["security_group_id"], network_id)
    generate_servers_ip_file(dev_ip_map, "dev_ips")
    existing_ports = conn.network.ports()
    vip_port_haproxy2 = create_vip_port(conn, network_id, subnet_id, tag_name, haproxy2_server.id, existing_ports)
    attach_port_to_server(conn, haproxy2_server.id, vip_port_haproxy2)
    vip_floating_ip_haproxy2 = assign_floating_ip_to_port(conn, vip_port_haproxy2)
    generate_vip_addresses_file(vip_floating_ip_haproxy2)
    generate_configs(tag_name, private_key)    
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Configuration files generated.")
    time.sleep(20) 
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Waiting for 40 seconds before running Ansible playbook...")
    run_ansible_playbook()
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deployment of {tag_name} completed.")

if __name__ == "__main__":
      if len(sys.argv) != 4:
        print("Usage: python install.py <rc_file> <tag_name> <public_key>")
        sys.exit(1)    
rc_file = sys.argv[1]
tag_name = sys.argv[2]
public_key = sys.argv[3]
main(rc_file, tag_name, public_key)
