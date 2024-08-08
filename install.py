#!/usr/bin/python3.8

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
    ssh_key_path = f"~/.ssh/{keypair_name}.pem"
    keypair = conn.compute.find_keypair(keypair_name)
    current_date_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if not keypair:
            keypair = conn.compute.create_keypair(name=keypair_name)
            with open(os.path.expanduser(ssh_key_path), 'w') as f:
                f.write(str(keypair.private_key))
            os.chmod(os.path.expanduser(ssh_key_path), 0o600)
            print(f"{current_date_time} Created key pair {keypair_name}.")

def setup_network(conn, tag_name, network_name, subnet_name, router_name, security_group_name):
    # Create network
    network = conn.network.find_network(network_name)
    if not network:
        network = conn.network.create_network(name=network_name)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created network {network_name}.")
    
    # Create subnet
    subnet = conn.network.find_subnet(subnet_name)
    if not subnet:
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
    return network, subnet, router, security_group

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

def assign_floating_ip(server, floating_ip, retries=5, delay=10):
    for _ in range(retries):
        result, _ = run_command(f"openstack server add floating ip {server} {floating_ip}")
        if result.strip() == "":
            return True
        time.sleep(delay)
    return False

def create_and_assign_fip(server, keypair_name, flavor, network_name, security_group_name):
    fip, _ = run_command(f"openstack floating ip create ext-net -f json | jq -r '.floating_ip_address'")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Creating floating IP for {server}.")
    run_command(f"openstack server create --image 'Ubuntu 20.04 Focal Fossa x86_64' {server} --key-name {keypair_name} --flavor '{flavor}' --network {network_name} --security-group {security_group_name}")
    if wait_for_active_state(server) and wait_for_network_ready(server):
        if not assign_floating_ip(server, fip):
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Error: Failed to assign floating IP {fip} to {server}")
            return None
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Floating IP {fip} assigned to {server}.")
        return fip
    else:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Error: {server} did not become active or network not ready.")
        return None

def create_servers(existing_servers, bastion_server, haproxy_server, haproxy_server2, tag_name, keypair_name, network_name, security_group_name):
        if bastion_server in existing_servers:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {bastion_server} already exists")
            bastion_fip, _ = run_command(f"openstack floating ip list --port {tag_name}_vip --column 'Floating IP Address' | awk 'NR==1 {{print $2}}'")
        else:
            bastion_fip = create_and_assign_fip(bastion_server, keypair_name, '1C-2GB-50GB', network_name, security_group_name)

        # Create HAproxy server
        if haproxy_server in existing_servers:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {haproxy_server} already exists")
            haproxy_fip, _ = run_command(f"openstack floating ip list --port {tag_name}_vip --column 'Floating IP Address' | awk 'NR==2 {{print $2}}'")
        else:
            haproxy_fip = create_and_assign_fip(haproxy_server, keypair_name, '1C-2GB-50GB', network_name, security_group_name)
        # Create Backup HAproxy server
        if haproxy_server2 in existing_servers:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {haproxy_server2} already exists")
            haproxy_fip2, _ = run_command(f"openstack floating ip list --port {tag_name}_vip --column 'Floating IP Address' | awk 'NR==3 {{print $2}}'")
        else:
            haproxy_fip2 = create_and_assign_fip(haproxy_server2, keypair_name, '1C-2GB-50GB', network_name, security_group_name)
                # Write server FIPs to file
        with open("servers_fip", "w") as f:
            f.write(f"{bastion_server}: {bastion_fip}\n")
            f.write(f"{haproxy_server}: {haproxy_fip}\n")
            f.write(f"{haproxy_server2}: {haproxy_fip2}\n")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Servers FIPs written to servers_fip file.")
def manage_dev_servers(existing_servers, tag_name, keypair_name, network_name, security_group_name):
    dev_server = f"{tag_name}_dev"
    required_dev_servers = 3
    devservers_count = len([line for line in existing_servers.splitlines() if dev_server in line])
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Will need {required_dev_servers} node, launching them.")        
    if required_dev_servers > devservers_count:
         devservers_to_add = required_dev_servers - devservers_count
         sequence = devservers_count + 1
         while devservers_to_add > 0:
              devserver_name = f"{dev_server}{sequence}"
              run_command(f"openstack server create --image 'Ubuntu 20.04 Focal Fossa x86_64' {devserver_name} --key-name {keypair_name} --flavor '1C-2GB-50GB' --network {network_name} --security-group {security_group_name}")
              print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created {devserver_name} server")
              devservers_to_add -= 1
              sequence += 1
    elif required_dev_servers < devservers_count:
         devservers_to_remove = devservers_count - required_dev_servers
         for _ in range(devservers_to_remove):
                    server_to_delete, _ = run_command(f"openstack server list --status ACTIVE -f value -c Name | grep -m1 -oP '{tag_name}_dev([1-9]+)'")
                    run_command(f"openstack server delete {server_to_delete} --wait")
                    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deleted {server_to_delete} server")
    else:
                    print(f"Required number of dev servers({required_dev_servers}) already exist.")

def get_port_by_name(port_name):
    ports_list, _ = run_command(f"openstack port list -f json")
    ports = json.loads(ports_list)
    for port in ports:
        if port['Name'] == port_name:
            return port['ID']  
    return None
def allocate_vip_port(network_name, tag_name, server_name):
        vip_port = get_port_by_name(f"{server_name}_vip")
        if not vip_port:
            vip_port, _ = run_command(f"openstack port create --network {network_name} {server_name}_vip --tag {tag_name} -f json")
            vip_port = json.loads(vip_port)['id']
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created VIP port {server_name}_vip.")
        else:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} VIP port {server_name}_vip already exists with ID {vip_port}.")
        return vip_port

def allocate_floating_ip():
        floating_ip, _ = run_command(f"openstack floating ip create ext-net -f json | jq -r '.floating_ip_address'")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Allocated floating IP {floating_ip} for VIP port.")
        return floating_ip

def assign_floating_ip_to_port(port_id, floating_ip):
        run_command(f"openstack floating ip set --port {port_id} {floating_ip}")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Assigned floating IP {floating_ip} to VIP port {port_id}.")

def attach_port_to_server(server_name, port_id):
        run_command(f"openstack server add port {server_name} {port_id}")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Attached VIP port {port_id} to instance {server_name}.")

def generate_vip_addresses_file(haproxy_server, vip_floating_ip_haproxy, haproxy_server2, vip_floating_ip_haproxy2):
        with open("vip_address", "w") as f:
            f.write(f"{vip_floating_ip_haproxy}\n")
            f.write(f"{vip_floating_ip_haproxy2}\n")
"""the generate_vip_addresses_file function writes the VIP addresses of the HAproxy servers to a file."""
def generate_configs(tag_name, keypair_name):
    """
    Invoke gen_config.py to generate SSH config and Ansible hosts file.
    """
    print("Genrating Configuration files.")
    output = run_command(f"python3 gen_config.py {tag_name} {keypair_name}")
    print(output)
    return output
"""the generate_configs function invokes the gen_config.py script to generate the SSH configuration file and the Ansible hosts file. The script is invoked with the tag name and the key pair name as arguments."""

def run_ansible_playbook():
    """
    Run the Ansible playbook using the generated configuration files.
    """
    print("Running Ansible playbook...")
    ansible_command = "ansible-playbook -i hosts site.yaml"
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

        create_keypair(conn, keypair_name, public_key_file)
        setup_network(conn, tag_name, network_name, subnet_name, router_name, security_group_name)
        existing_servers, _ = run_command("openstack server list --status ACTIVE --column Name -f value")
        create_servers(existing_servers, bastion_server, haproxy_server, haproxy_server2, tag_name, keypair_name, network_name, security_group_name)
        manage_dev_servers(existing_servers, tag_name, keypair_name, network_name, security_group_name)
        # Allocate VIP port for HAproxy_server
        vip_port_haproxy = allocate_vip_port(network_name, tag_name, haproxy_server)
        vip_floating_ip_haproxy = allocate_floating_ip()
        assign_floating_ip_to_port(vip_port_haproxy, vip_floating_ip_haproxy)
        attach_port_to_server(haproxy_server, vip_port_haproxy)
        # Allocate VIP port for HAproxy_server2
        vip_port_haproxy2 = allocate_vip_port(network_name, tag_name, haproxy_server2)
        vip_floating_ip_haproxy2 = allocate_floating_ip()
        assign_floating_ip_to_port(vip_port_haproxy2, vip_floating_ip_haproxy2)
        attach_port_to_server(haproxy_server2, vip_port_haproxy2)
        active_servers = [server.name for server in conn.compute.servers()]
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deployment of {tag_name} completed.")
        generate_vip_addresses_file(haproxy_server, vip_floating_ip_haproxy, haproxy_server2, vip_floating_ip_haproxy2)
        generate_configs(tag_name, keypair_name)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Configuration files generated.")
        time.sleep(40) 
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Waiting for 40 seconds before running Ansible playbook...")
        run_ansible_playbook()
        
if __name__ == "__main__":
      if len(sys.argv) != 4:
        print("Usage: python install.py <rc_file> <tag_name> <public_key_file>")
        sys.exit(1)    
rc_file = sys.argv[1]
tag_name = sys.argv[2]
public_key_file = sys.argv[3]
main(rc_file, tag_name, public_key_file)
