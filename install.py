import openstack
import os
import argparse
import subprocess

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


def create_network(conn, network_name, subnet_name, tag_name):
    """Create a network and a subnet."""
    # Check if the network already exists
    existing_networks = list(conn.network.networks(name=network_name))
    if existing_networks:
        print(f"Network {network_name} already exists.")
        network = existing_networks[0]
    else:
        network = conn.network.create_network(name=network_name)
        print(f"Created network {network_name}")

    # Check if the subnet already exists
    existing_subnets = list(conn.network.subnets(name=subnet_name))
    if existing_subnets:
        print(f"Subnet {subnet_name} already exists.")
        subnet = existing_subnets[0]
    else:
        subnet = conn.network.create_subnet(
            network_id=network.id,
            name=subnet_name,
            ip_version=4,
            cidr="192.168.0.0/24",
            gateway_ip="192.168.0.1"
        )
        print(f"Created subnet {subnet_name}")

    return network, subnet

def create_router(conn, router_name, network_name, subnet_name, tag_name):
    """Create or reuse a router and attach the subnet to it."""
    # Get the network ID of the external network
    external_network = conn.network.find_network('ext-net')
    if not external_network:
        print("External network 'ext-net' not found.")
        return
    external_network_id = external_network.id

    router = conn.network.find_router(router_name)
    if router:
        print(f"{router_name} already exists")
    else:
        router = conn.network.create_router(name=router_name, external_gateway_info={"network_id": external_network_id})
        conn.network.add_interface_to_router(router, subnet_id=conn.network.find_subnet(subnet_name).id)
        print(f"Created router {router_name} and attached subnet {subnet_name}")


def create_security_group(conn, security_group_name, tag_name):
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
    haproxy_name2 = f"{args.tag}_ha-proxy-2"
    dev_prefix = f"{args.tag}_dev-server-"
    dev_count = 3

    # Create keypair
    create_keypair(conn, keypair_name, args.public_key)

    # Create network and subnet
    create_network(conn, network_name, subnet_name, args.tag)

    # Create router and attach subnet
    create_router(conn, router_name, network_name, subnet_name, args.tag)

    # Create security group with rules
    create_security_group(conn, security_group_name, args.tag)

if __name__ == "__main__":
    main()