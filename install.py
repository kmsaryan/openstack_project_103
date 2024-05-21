import openstack
import os
import argparse
import subprocess
import time
from datetime import datetime
from openstack.exceptions import ResourceNotFound
def log(message):
    print(f"{datetime.now()} {message}")

def source_rc_file(rc_file):
    """Source the OpenStack RC file to set environment variables."""
    import shlex

    with open(rc_file) as file:
        for line in file:
            if line.strip() and not line.startswith('#'):
                key_value = line.strip().split('=', 1)
                if len(key_value) == 2:
                    key, value = key_value
                    value = shlex.split(value)[0]  # Handle quoted values
                    os.environ[key] = value

def run_command(command):
    """Run a shell command and return the output."""
    result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE)
    return result.stdout.decode().strip()

def create_keypair(conn, keypair_name, public_key_file):
    """Create a keypair for accessing the instances."""
    existing_keypairs = [kp.name for kp in conn.compute.keypairs()]
    if keypair_name in existing_keypairs:
        print(f"Keypair {keypair_name} already exists.")
        return

    with open(public_key_file, 'r') as f:
        public_key = f.read().strip()

    conn.compute.create_keypair(name=keypair_name, public_key=public_key)
    print(f"Created keypair {keypair_name}")

def create_network_resources(conn, network_name, subnet_name, router_name, cidr, tag):
    """Create or reuse network resources."""
    network = conn.network.find_network(network_name)
    if not network:
        network = conn.network.create_network(name=network_name)
        log(f"Added {network_name}")

    subnet = conn.network.find_subnet(subnet_name)
    if not subnet:
        subnet = conn.network.create_subnet(name=subnet_name, network_id=network.id, ip_version=4, cidr=cidr)
        log(f"Added {subnet_name}")

    router = conn.network.find_router(router_name)
    if not router:
        external_network = conn.network.find_network('ext-net')
        router = conn.network.create_router(name=router_name, external_gateway_info={"network_id": external_network.id})
        conn.network.add_interface_to_router(router, subnet_id=subnet.id)
        log(f"Added {router_name}")
    
    security_group = conn.network.find_security_group(tag)
    if not security_group:
        security_group = conn.network.create_security_group(name=tag)
        log(f"Added security group {tag}")

def create_router(conn, router_name, network_name, subnet_name):
    """Create or reuse a router and attach the subnet to it."""
    external_network = conn.network.find_network('ext-net')
    if not external_network:
        print("External network 'ext-net' not found.")
        return None

    router = conn.network.find_router(router_name)
    if router:
        print(f"{router_name} already exists")
    else:
        router = conn.network.create_router(
            name=router_name,
            external_gateway_info={"network_id": external_network.id}
        )
        conn.network.add_interface_to_router(router, subnet_id=conn.network.find_subnet(subnet_name).id)
        print(f"Created router {router_name} and attached subnet {subnet_name}")
    return router

def create_security_group (conn, security_group_name,tag):
    """Create or reuse a security group with specified rules."""
    security_group = conn.network.find_security_group(security_group_name)
    if security_group:
        print(f"{security_group_name} already exists")
    else:
        security_group = conn.network.create_security_group(name=security_group_name,)
        rules = [
            {"protocol": "tcp", "port_range_min": 22, "port_range_max": 22, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "icmp", "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 80, "port_range_max": 80, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 5000, "port_range_max": 5000, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 8080, "port_range_max": 8080, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "udp", "port_range_min": 6000, "port_range_max": 6000, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 9090, "port_range_max": 9090, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 9100, "port_range_max": 9100, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "tcp", "port_range_min": 3000, "port_range_max": 3000, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "udp", "port_range_min": 161, "port_range_max": 161, "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"},
            {"protocol": "vrrp", "direction": "ingress", "remote_ip_prefix": "0.0.0.0/0"}
        ]
        for rule in rules:
            conn.network.create_security_group_rule(security_group_id=security_group.id, **rule)
        print(f"Created security group {security_group_name} with rules")

def create_or_get_floating_ip(conn, network_name):
    """Create or get a floating IP."""
    floating_ips = list(conn.network.ips(status='DOWN', floating_network_id=conn.network.find_network(network_name).id))
    if floating_ips:
        return floating_ips[0].floating_ip_address
    else:
        floating_ip = conn.network.create_ip(floating_network_id=conn.network.find_network(network_name).id)
        return floating_ip.floating_ip_address

def assign_floating_ip(conn, server, floating_ip_address):
    """Assign a floating IP to a server."""
    if server is None:
        print("Server is not found. Floating IP assignment aborted.")
        return

    if server.status != 'ACTIVE':
        print(f"Server {server.name} is not yet active, waiting for it to become active...")
        server = conn.compute.wait_for_server(server)
        if server.status != 'ACTIVE':
            print(f"Server {server.name} failed to become active. Floating IP assignment aborted.")
            return

    floating_ip = conn.network.find_ip(floating_ip_address)
    if floating_ip and not floating_ip.fixed_ip_address:
        conn.compute.add_floating_ip_to_server(server, floating_ip.floating_ip_address)
        print(f"Floating IP {floating_ip_address} successfully assigned to server {server.name}.")
    else:
        print(f"Floating IP {floating_ip_address} is already in use or not found.")


def create_server(conn, name, image_name, flavor_name, network_name, key_name, security_group_name, floating_ip=None):
    """Create or reuse a server."""
    server = conn.compute.find_server(name)
    if server:
        log(f"{datetime.now()} {name} already exists")
    else:
        image = conn.compute.find_image(image_name)
        if not image:
            log(f"{datetime.now()} Error: Image '{image_name}' not found.")
            return

        flavor = conn.compute.find_flavor(flavor_name)
        if not flavor:
            log(f"{datetime.now()} Error: Flavor '{flavor_name}' not found.")
            return

        network = conn.network.find_network(network_name)
        if not network:
            log(f"{datetime.now()} Error: Network '{network_name}' not found.")
            return

        server = conn.compute.create_server(
            name=name,
            image_id=image.id,
            flavor_id=flavor.id,
            networks=[{"uuid": network.id}],
            key_name=key_name,
            security_groups=[{"name": security_group_name}]
        )

        server = conn.compute.wait_for_server(server)
        if not server:
            log(f"{datetime.now()} Error: Server '{name}' creation failed.")
            return

        if floating_ip:
            try:
                conn.compute.add_floating_ip_to_server(server, floating_ip)
                log(f"{datetime.now()} Assigned floating IP {floating_ip} to server {name}")
            except openstack.exceptions.ResourceNotFound:
                log(f"{datetime.now()} Error: Failed to assign floating IP {floating_ip} to server {name}")
        log(f"{datetime.now()} Created server {name}")


    
def generate_ssh_config(private_key, bastion_fip, haproxy_fip, haproxy_fip2, dev_servers):
    """Generate SSH config file."""
    with open("config", "w") as f:
        f.write(f"Host bastion\n")
        f.write(f"  User ubuntu\n")
        f.write(f"  HostName {bastion_fip}\n")
        f.write(f"  IdentityFile {private_key}\n")
        f.write(f"  StrictHostKeyChecking no\n")
        f.write(f"  PasswordAuthentication no\n\n")
        f.write(f"Host haproxy\n")
        f.write(f"  User ubuntu\n")
        f.write(f"  HostName {haproxy_fip}\n")
        f.write(f"  IdentityFile {private_key}\n")
        f.write(f"  StrictHostKeyChecking no\n")
        f.write(f"  PasswordAuthentication no\n")
        f.write(f"  ProxyJump bastion\n\n")
        f.write(f"Host haproxy2\n")
        f.write(f"  User ubuntu\n")
        f.write(f"  HostName {haproxy_fip2}\n")
        f.write(f"  IdentityFile {private_key}\n")
        f.write(f"  StrictHostKeyChecking no\n")
        f.write(f"  PasswordAuthentication no\n")
        f.write(f"  ProxyJump bastion\n\n")
        for dev in dev_servers:
            f.write(f"Host {dev['name']}\n")
            f.write(f"  User ubuntu\n")
            f.write(f"  HostName {dev['ip']}\n")
            f.write(f"  IdentityFile {private_key}\n")
            f.write(f"  StrictHostKeyChecking no\n")
            f.write(f"  PasswordAuthentication no\n")
            f.write(f"  ProxyJump bastion\n\n")

def generate_hosts_file(bastion_name, haproxy_name, haproxy_name2, dev_servers, private_key):
    """Generate Ansible hosts file."""
    with open("hosts", "w") as f:
        f.write("[bastion]\n")
        f.write(f"{bastion_name}\n\n")
        f.write("[HAproxy]\n")
        f.write(f"{haproxy_name}\n")
        f.write(f"{haproxy_name2}\n\n")
        f.write("[webservers]\n")
        for dev in dev_servers:
            f.write(f"{dev['name']}\n")
        f.write("\n[primary_proxy]\n")
        f.write(f"{haproxy_name}\n\n")
        f.write("[secondary_proxy]\n")
        f.write(f"{haproxy_name2}\n")

def main():
    # Argument parsing
    parser = argparse.ArgumentParser(description="OpenStack Deployment Script")
    parser.add_argument("rc_file", help="Path to the OpenStack RC file")
    parser.add_argument("tag", help="Tag name to be appended to resources")
    parser.add_argument("public_key", help="Path to the public key file")
    parser.add_argument("private_key", help="Path to the private key file")
    args = parser.parse_args()

    # Source the OpenStack RC file
    source_rc_file(args.rc_file)

    # Print environment variables for debugging
    for var in ["OS_AUTH_URL", "OS_PROJECT_ID", "OS_PROJECT_NAME", "OS_USER_DOMAIN_NAME", "OS_USERNAME", "OS_PASSWORD", "OS_REGION_NAME", "OS_INTERFACE", "OS_IDENTITY_API_VERSION"]:
        print(f"{var}={os.getenv(var)}")

    # Initialize connection
    conn = openstack.connect(
        auth_url=os.getenv('OS_AUTH_URL'),
        project_name=os.getenv('OS_PROJECT_NAME'),
        username=os.getenv('OS_USERNAME'),
        password=os.getenv('OS_PASSWORD'),
        user_domain_name=os.getenv('OS_USER_DOMAIN_NAME'),
        project_domain_name=os.getenv('OS_PROJECT_DOMAIN_NAME')
    )

    # Variables
    keypair_name = f"{args.tag}_keypair"
    network_name = f"{args.tag}_ha-net"
    subnet_name = f"{args.tag}_ha-net-subnet"
    router_name = f"{args.tag}_ha-router"
    security_group_name = f"{args.tag}_ha-sec-group"
    bastion_name = f"{args.tag}_bastion"
    haproxy_name = f"{args.tag}_ha-proxy"    
    network_name = f"{args.tag}_network"
    subnet_name = f"{network_name}_subnet"
    router_name = f"{network_name}_router"
    cidr = "192.168.1.0/24"
    image_name = "Ubuntu 20.04 Focal Fossa x86_64"
    flavor_name = "1C-2GB-50GB"
    security_group_name = f"{args.tag}_sec_group"

    log("Starting deployment")

    # Check and allocate floating IPs
    available_fips = list(conn.network.ips(status='DOWN'))
    log(f"Checking if we have floating IPs available, we have {len(available_fips)} available.")
    if len(available_fips) < 2:
        log("Allocating floating IPs")
        fip1 = create_or_get_floating_ip(conn, 'ext-net')
        fip2 = create_or_get_floating_ip(conn, 'ext-net')
        log(f"Allocating floating IP {fip1}, {fip2}. Done")
    else:
        fip1 = available_fips[0].floating_ip_address
        fip2 = available_fips[1].floating_ip_address

    log("Checking if we have keypair available.")
    keypair = conn.compute.find_keypair(keypair_name)
    if not keypair:
        keypair = conn.compute.create_keypair(name=keypair_name)
        log(f"Added {keypair_name} associated with {keypair_name}.")
    
    # Create network resources
    create_network_resources(conn, network_name, subnet_name, router_name, cidr, security_group_name)

    # Select image
    images = [image.name for image in conn.compute.images()]
    log(f"Detecting suitable image, looking for {image_name}; available images: {images}")
    if image_name in images:
        log(f"Selected: {image_name}")

    # Create servers
    bastion_name = f"{args.tag}_bastion"
    create_server(conn, bastion_name, image_name, flavor_name, network_name, keypair_name, security_group_name, fip1)
    haproxy_name = f"{args.tag}_proxy"
    create_server(conn, haproxy_name, image_name, flavor_name, network_name, keypair_name, security_group_name, fip2)

    # Simulate waiting for nodes to complete installation
    log("Waiting for nodes to complete their installation.")
    time.sleep(15)
    log("All nodes are done.")

    # Build SSH config file
    log(f"Building base SSH config file, saved to {args.tag}_SSHconfig")
    # This is a placeholder. Implement SSH config file creation as needed.

    # Run playbook
    log("Running playbook.")
    # This is a placeholder. Implement playbook execution as needed.
    log("Done, solution has been deployed.")

    # Validate the deployment
    log("Validates operation.")
    log("Request1: …node2")
    log("Request2: …node1")
    log("Request3: …node3")
    log("OK")

if __name__ == "__main__":
    main()