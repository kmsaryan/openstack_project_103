import openstack
import os
import argparse
import datetime
import openstack.exceptions
import subprocess
from contextlib import contextmanager


# Create connection to OpenStack
def connect_to_openstack():
    return openstack.connect(
        auth_url=os.getenv('OS_AUTH_URL'),
        project_name=os.getenv('OS_PROJECT_NAME'),
        username=os.getenv('OS_USERNAME'),
        password=os.getenv('OS_PASSWORD'),
        user_domain_name=os.getenv('OS_USER_DOMAIN_NAME'),
        project_domain_name=os.getenv('OS_PROJECT_DOMAIN_NAME')
    )

def delete_servers(conn, server_names, dev_server, devservers_count):
    for server_name in server_names:
        try:
            server = conn.compute.find_server(server_name)
            if server:
                # Iterate over all addresses associated with the server
                for network_name, address_list in server.addresses.items():
                    for address in address_list:
                        if address['OS-EXT-IPS:type'] == 'floating':
                            floating_ip = address['addr']
                            floating_ip_obj = conn.network.find_ip(floating_ip)
                            if floating_ip_obj:
                                conn.network.delete_ip(floating_ip_obj)
                                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Releasing floating IP {floating_ip} associated with {server_name}")
                            else:
                                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Floating IP {floating_ip} not found")
                
                # Delete the server after releasing the floating IP
                conn.compute.delete_server(server)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Releasing server {server_name}")
            else:
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, {server_name} not found")
        except openstack.exceptions.ResourceNotFound:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, {server_name} not found")

    # Delete dev servers
    for i in range(1, devservers_count + 1):
        devserver_name = f"{dev_server}{i}"
        try:
            server = conn.compute.find_server(devserver_name)
            if server:
                # Iterate over all addresses associated with the server
                for network_name, address_list in server.addresses.items():
                    for address in address_list:
                        if address['OS-EXT-IPS:type'] == 'floating':
                            floating_ip = address['addr']
                            floating_ip_obj = conn.network.find_ip(floating_ip)
                            if floating_ip_obj:
                                conn.network.delete_ip(floating_ip_obj)
                                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Releasing floating IP {floating_ip} associated with {devserver_name}")
                            else:
                                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Floating IP {floating_ip} not found")
                
                # Delete the server after releasing the floating IP
                conn.compute.delete_server(server)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, Releasing server {devserver_name}")
            else:
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, {devserver_name} not found")
        except openstack.exceptions.ResourceNotFound:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, {devserver_name} not found")


def delete_ports(conn, port_names):
    for port_name in port_names:
        try:
            port = conn.network.find_port(port_name)
            if port:
                conn.network.delete_port(port)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Removing {port_name}")
            else:
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{port_name} not found")
        except openstack.exceptions.ResourceNotFound:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{port_name} not found")

def delete_subnets(conn, subnet_names):
    for subnet_name in subnet_names:
        subnet = conn.network.find_subnet(subnet_name)
        if subnet:
            # Get all ports and filter those associated with the subnet
            all_ports = conn.network.ports()
            ports = [port for port in all_ports if any(fixed_ip['subnet_id'] == subnet.id for fixed_ip in port.fixed_ips)]
            for port in ports:
                try:
                    conn.network.delete_port(port)
                    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Detached port {port.id} associated with subnet {subnet_name}")
                except openstack.exceptions.ResourceNotFound:
                    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Port {port.id} not found")

            # Delete subnet
            try:
                conn.network.delete_subnet(subnet)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Removing subnet {subnet_name}")
            except openstack.exceptions.ConflictException as e:
               print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Unable to delete subnet {subnet_name}: {e}")
        else:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Subnet {subnet_name} not found")

def delete_router(conn, router_name):
    try:
        router = conn.network.find_router(router_name)
        if router:
            # Get all ports and filter those associated with the router
            all_ports = conn.network.ports(device_id=router.id)
            for port in all_ports:
                conn.network.remove_interface_from_router(router, port_id=port.id)
                print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Removed interface {port.id} from router {router_name}")
            conn.network.delete_router(router)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}Removing {router_name}")
        else:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{router_name} not found")
    except openstack.exceptions.ResourceNotFound:
        print(f"{router_name} not found")

def delete_network(conn, network_name):
    try:
        network = conn.network.find_network(network_name)
        if network:
            conn.network.delete_network(network)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}Removing {network_name}")
        else:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{network_name} not found")
    except openstack.exceptions.ResourceNotFound:
        print(f"{network_name} not found")

def delete_security_group(conn, security_group_name):
    try:
        security_group = conn.network.find_security_group(security_group_name)
        if security_group:
            conn.network.delete_security_group(security_group)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Removing {security_group_name}")
        else:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{security_group_name} not found")
    except openstack.exceptions.ResourceNotFound:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{security_group_name} not found")

def delete_keypair(conn, keypair_name):
    try:
        subprocess.check_output(['openstack', 'keypair', 'delete', keypair_name])
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Removing key pair {keypair_name}")
    except subprocess.CalledProcessError as e:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Error deleting key pair {keypair_name}: {str(e)}")

def delete_files(tag_name):
    # List of files to delete
    config_file = "config"
    files_to_delete = ['servers_fip.txt', 'vip_address.txt', 'hosts','ansible.cfg', config_file]
    for file_name in files_to_delete:
        try:
            os.remove(file_name)
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Removing {file_name}")
        except FileNotFoundError:
            print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{file_name} not found")

    known_hosts_file = "~/.ssh/known_hosts"
    if os.path.exists(os.path.expanduser(known_hosts_file)):
        os.remove(os.path.expanduser(known_hosts_file))
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Removing known_hosts file")
    else:
        print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},known_hosts file not found")

def cleanup_instances(conn, tag_name):
    network_name = f"{tag_name}_network"
    subnet_name = f"{tag_name}_subnet"
    keypair_name = f"{tag_name}_key"
    router_name = f"{tag_name}_router"
    security_group_name = f"{tag_name}_security_group"
    haproxy_server = f"{tag_name}_HAproxy"
    haproxy_server2 = f"{tag_name}_HAproxy2"
    bastion_server = f"{tag_name}_bastion"
    dev_server = f"{tag_name}_dev"
    devservers_count = len(list(conn.compute.servers(name=dev_server)))
    vip_port = f"{tag_name}_vip_port"

    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},$> cleanup {tag_name}")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},Cleaning up {tag_name} using myRC")
    print(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},We have {len([bastion_server, haproxy_server, haproxy_server2, dev_server])} nodes releasing them")
    delete_servers(conn, [bastion_server, haproxy_server, haproxy_server2], dev_server, devservers_count)
    delete_ports(conn, [vip_port])
    delete_router(conn, router_name)
    delete_subnets(conn, [subnet_name])
    delete_network(conn, network_name)
    delete_security_group(conn, security_group_name)
    delete_keypair(conn, keypair_name)
    delete_files(tag_name)

    instances = conn.compute.servers()
    instance_names = set()
    for instance in instances:
        if tag_name in instance.name:
            if instance.name in instance_names:
                print(f"Duplicate instance found: {instance.name}. Removing it.")
                conn.compute.delete_server(instance)
            else:
                instance_names.add(instance.name)

    print(f"Checking for {tag_name} in project.")
    print("(network)(subnet)(router)(security groups)(keypairs)")
    print("Cleanup done.")

# Parse arguments
parser = argparse.ArgumentParser()
parser.add_argument('rc_file', help='OpenStack RC file')
parser.add_argument('tag_name', help='Tag name for resources')
args = parser.parse_args()

# Load OpenStack RC file
with open(args.rc_file) as f:
    for line in f:
        if line.strip() and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

# Create connection to OpenStack
conn = connect_to_openstack()
# Cleanup instances
cleanup_instances(conn, args.tag_name)