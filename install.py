import subprocess
import sys
import datetime
import time
import os
import openstack.connection
import openstack.exceptions
# Create connection to OpenStack
conn = openstack.connect(
    auth_url=os.getenv('OS_AUTH_URL'),
    project_name=os.getenv('OS_PROJECT_NAME'),
    username=os.getenv('OS_USERNAME'),
    password=os.getenv('OS_PASSWORD'),
    user_domain_name=os.getenv('OS_USER_DOMAIN_NAME'),
    project_domain_name=os.getenv('OS_PROJECT_DOMAIN_NAME')
)

def run_command(command):
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode().strip(), result.stderr.decode().strip()

def wait_for_active_state(server, retries=10, delay=30):
    for _ in range(retries):
        status, _ = run_command(f"openstack server show {server} -c status -f value")
        if status.strip() == "ACTIVE":
            return True
        time.sleep(delay)
    return False

def wait_for_network_ready(server, retries=5, delay=15):
    for _ in range(retries):
        net_status, _ = run_command(f"openstack server show {server} -c addresses -f value")
        if net_status.strip():
            return True
        time.sleep(delay)
    return False

def assign_floating_ip(server, floating_ip, retries=5, delay=15):
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
def generate_configs():
    """
    Invoke gen_config.py to generate SSH config and Ansible hosts file.
    """
    print("Generating configuration files...")
    run_command("python3 gen_config.py")

def main(rc_file, tag_name, publickey):
    privatekey = publickey.replace('.pub', '')
    required_dev_servers = 3
    current_date_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"{current_date_time} Starting deployment of {tag_name} using {rc_file} for credentials.")

    with open(rc_file) as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()
                
    network_name = f"{tag_name}_network"
    subnet_name = f"{tag_name}_subnet"
    keypair_name = f"{tag_name}_key"
    router_name = f"{tag_name}_router"
    security_group_name = f"{tag_name}_security_group"
    haproxy_server = f"{tag_name}_HAproxy"
    haproxy_server2 = f"{tag_name}_HAproxy2"
    bastion_server = f"{tag_name}_bastion"
    dev_server = f"{tag_name}_dev"
    vip_port = f"{tag_name}_vip"
    sshconfig = f"{tag_name}_SSHconfig"
    knownhosts = "known_hosts"
    hostsfile = "hosts"
    
    floating_ips, _ = run_command("openstack floating ip list --status DOWN -f value -c 'Floating IP Address'")
    for ip in floating_ips.splitlines():
        run_command(f"openstack floating ip delete {ip}")
    # Keypair check
    existing_keypairs, _ = run_command("openstack keypair list -f value --column Name")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Checking if we have {keypair_name} available.")
    if keypair_name in existing_keypairs:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {keypair_name} already exists")
    else:
        run_command(f"openstack keypair create --public-key {publickey} {keypair_name}")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Adding {keypair_name} associated with {publickey}.")

    # Network check
    existing_networks, _ = run_command(f"openstack network list --tag {tag_name} --column Name -f value")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Did not detect {network_name} in the OpenStack project, adding it.")
    if network_name in existing_networks:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {network_name} already exists")
    else:
        run_command(f"openstack network create --tag {tag_name} {network_name} -f json")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Added {network_name}.")

    # Subnet check
    existing_subnets, _ = run_command(f"openstack subnet list --tag {tag_name} --column Name -f value")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Did not detect {subnet_name} in the OpenStack project, adding it.")
    if subnet_name in existing_subnets:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {subnet_name} already exists")
    else:
        run_command(f"openstack subnet create --subnet-range 10.10.0.0/24 --allocation-pool start=10.10.0.2,end=10.10.0.30 --tag {tag_name} --network {network_name} {subnet_name} -f json")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Added {subnet_name}.")

    # Router check
    existing_routers, _ = run_command(f"openstack router list --tag {tag_name} --column Name -f value")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Did not detect {router_name} in the OpenStack project, adding it.")
    if router_name in existing_routers:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {router_name} already exists")
    else:
        run_command(f"openstack router create --tag {tag_name} {router_name}")
        run_command(f"openstack router set --external-gateway ext-net {router_name}")
        run_command(f"openstack router add subnet {router_name} {subnet_name}")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Added {router_name}")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Adding networks to router.")
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Done.")

    # Security group check
    existing_security_groups, _ = run_command(f"openstack security group list --tag {tag_name} -f value")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Adding security group(s).")
    if security_group_name not in existing_security_groups:
        run_command(f"openstack security group create --tag {tag_name} {security_group_name} -f json")
        rules = [
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 22 --protocol tcp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 80 --protocol icmp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 5000 --protocol tcp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 8080 --protocol tcp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 6000 --protocol udp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 9090 --protocol tcp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 9100 --protocol tcp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 3000 --protocol tcp --ingress {security_group_name}",
            f"openstack security group rule create --remote-ip 0.0.0.0/0 --dst-port 161 --protocol udp --ingress {security_group_name}",
            f"openstack security group rule create --protocol 112 {security_group_name}"  # VRRP protocol
        ]
        for rule in rules:
            run_command(rule)
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created security group {security_group_name}")
    else:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {security_group_name} already exists")

#     # Cleanup existing files
    file_names = [f"{tag_name}_{file}" for file in [sshconfig, knownhosts, hostsfile]]
    for file in file_names:
        if os.path.exists(file):
            os.remove(file)

        # Create bastion server
    existing_servers, _ = run_command("openstack server list --status ACTIVE --column Name -f value")

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
        # Allocate VIP port for HAproxy_server
    vip_port_haproxy, _ = run_command(f"openstack port create --network {network_name} {haproxy_server}_vip --tag {tag_name} -f json")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created VIP port {haproxy_server}_vip.")
    vip_floating_ip_haproxy, _ = run_command(f"openstack floating ip create ext-net -f json | jq -r '.floating_ip_address'")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Allocated floating IP {vip_floating_ip_haproxy} for VIP port.")
    run_command(f"openstack floating ip set --port {vip_port_haproxy} {vip_floating_ip_haproxy}")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Assigned floating IP {vip_floating_ip_haproxy} to VIP port {haproxy_server}_vip.")

    # Attach VIP port to HAproxy_server
    run_command(f"openstack server add port {haproxy_server} {vip_port_haproxy}")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Attached VIP port {haproxy_server}_vip to instance {haproxy_server}.")

    # Allocate VIP port for HAproxy_server2
    vip_port_haproxy2, _ = run_command(f"openstack port create --network {network_name} {haproxy_server2}_vip --tag {tag_name} -f json")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Created VIP port {haproxy_server2}_vip.")
    vip_floating_ip_haproxy2, _ = run_command(f"openstack floating ip create ext-net -f json | jq -r '.floating_ip_address'")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Allocated floating IP {vip_floating_ip_haproxy2} for VIP port.")
    run_command(f"openstack floating ip set --port {vip_port_haproxy2} {vip_floating_ip_haproxy2}")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Assigned floating IP {vip_floating_ip_haproxy2} to VIP port {haproxy_server2}_vip.")

    # Attach VIP port to HAproxy_server2
    run_command(f"openstack server add port {haproxy_server2} {vip_port_haproxy2}")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Attached VIP port {haproxy_server2}_vip to instance {haproxy_server2}.")

    devservers_count = len([line for line in existing_servers.splitlines() if dev_server in line])
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Will need {required_dev_servers} nodes (server.conf), launching them.")

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
    # Fetch assigned floating IPs for verification
    bastionfip, _ = run_command(f"openstack server list --name {bastion_server} -c Networks -f value | grep -Po '\\d+\\.\\d+\\.\\d+\\.\\d+' | awk 'NR==2'")
    haproxy_fip, _ = run_command(f"openstack server show {haproxy_server} -c addresses | grep -Po '\\d+\\.\\d+\\.\\d+\\.\\d+' | awk 'NR==1'")
    haproxy_fip2, _ = run_command(f"openstack server list --name {haproxy_server2} -c Networks -f value | grep -Po '\\d+\\.\\d+\\.\\d+\\.\\d+' | awk 'NR==1'")
    
    active_servers = [server.name for server in conn.compute.servers()]
    # Print instance name along with floating IP and fixed IP
    print(f"Bastion Server:")
    print(f"Instance Name: {bastion_server}")
    print(f"Floating IP: {bastionfip}")
    
    print(f"HAproxy Server:")
    print(f"Instance Name: {haproxy_server}")
    print(f"Floating IP: {haproxy_fip}")
    
    print(f"HAproxy2 Server:")
    print(f"Instance Name: {haproxy_server2}")
    print(f"Floating IP: {haproxy_fip2}")
    
    generate_configs()
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} Deployment of {tag_name} completed.")
if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3]) 
#The script is designed to be executed from the command line and accepts three arguments: the path to the OpenStack RC file, a tag name, and the path to the public key file.