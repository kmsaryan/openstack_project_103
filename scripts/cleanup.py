import openstack
import os
import argparse
import logging
from datetime import datetime
import openstack.exceptions
import subprocess
from contextlib import contextmanager


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

@contextmanager
def suppress_logging(log_level):
    root_logger = logging.getLogger()
    original_level = root_logger.getEffectiveLevel()
    root_logger.setLevel(logging.ERROR)  
    try:
        yield
    finally:
        root_logger.setLevel(original_level)  


def connect_to_openstack():
    return openstack.connect(
        auth_url=os.getenv('OS_AUTH_URL'),
        project_name=os.getenv('OS_PROJECT_NAME'),
        username=os.getenv('OS_USERNAME'),
        password=os.getenv('OS_PASSWORD'),
        user_domain_name=os.getenv('OS_USER_DOMAIN_NAME'),
        project_domain_name=os.getenv('OS_PROJECT_DOMAIN_NAME')
    )

def delete_floating_ips(conn):
    floating_ips = conn.network.ips()
    for floating_ip in floating_ips:
        try:
            conn.network.delete_ip(floating_ip)
            logging.info(f"Releasing floating IP {floating_ip.floating_ip_address}")
        except openstack.exceptions.ResourceNotFound:
            logging.warning(f"Floating IP {floating_ip.floating_ip_address} not found")
        except Exception as e:
            logging.error(f"An error occurred while deleting floating IP {floating_ip.floating_ip_address}: {e}")

def delete_servers(conn, server_names, dev_server, devservers_count):
    for server_name in server_names:
        try:
            server = conn.compute.find_server(server_name)
            if server:
                conn.compute.delete_server(server)
                logging.info(f"Releasing {server_name}")
            else:
                logging.warning(f"{server_name} not found")
        except openstack.exceptions.ResourceNotFound:
            logging.warning(f"{server_name} not found")

    
    for i in range(1, devservers_count + 1):
        devserver_name = f"{dev_server}{i}"
        try:
            server = conn.compute.find_server(devserver_name)
            if server:
                conn.compute.delete_server(server)
                logging.info(f"Releasing {devserver_name}")
            else:
                logging.warning(f"{devserver_name} not found")
        except openstack.exceptions.ResourceNotFound:
            logging.warning(f"{devserver_name} not found")

def delete_ports(conn, port_names):
    for port_name in port_names:
        try:
            port = conn.network.find_port(port_name)
            if port:
                conn.network.delete_port(port)
                logging.info(f"Removing {port_name}")
            else:
                logging.warning(f"{port_name} not found")
        except openstack.exceptions.ResourceNotFound:
            logging.warning(f"{port_name} not found")

def delete_subnets(conn, subnet_names):
    for subnet_name in subnet_names:
        subnet = conn.network.find_subnet(subnet_name)
        if subnet:
            
            all_ports = conn.network.ports()
            ports = [port for port in all_ports if any(fixed_ip['subnet_id'] == subnet.id for fixed_ip in port.fixed_ips)]
            for port in ports:
                try:
                    conn.network.delete_port(port)
                    logging.info(f"Detached port {port.id} associated with subnet {subnet_name}")
                except openstack.exceptions.ResourceNotFound:
                    logging.warning(f"Port {port.id} not found")

            try:
                conn.network.delete_subnet(subnet)
                logging.info(f"Removing subnet {subnet_name}")
            except openstack.exceptions.ConflictException as e:
                logging.error(f"Unable to delete subnet {subnet_name}: {e}")
        else:
            logging.warning(f"Subnet {subnet_name} not found")

def delete_router(conn, router_name):
    try:
        router = conn.network.find_router(router_name)
        if router:
            all_ports = conn.network.ports(device_id=router.id)
            for port in all_ports:
                conn.network.remove_interface_from_router(router, port_id=port.id)
                logging.info(f"Removed interface {port.id} from router {router_name}")
            conn.network.delete_router(router)
            logging.info(f"Removing {router_name}")
        else:
            logging.warning(f"{router_name} not found")
    except openstack.exceptions.ResourceNotFound:
        logging.warning(f"{router_name} not found")

def delete_network(conn, network_name):
    try:
        network = conn.network.find_network(network_name)
        if network:
            conn.network.delete_network(network)
            logging.info(f"Removing {network_name}")
        else:
            logging.warning(f"{network_name} not found")
    except openstack.exceptions.ResourceNotFound:
        logging.warning(f"{network_name} not found")

def delete_security_group(conn, security_group_name):
    try:
        security_group = conn.network.find_security_group(security_group_name)
        if security_group:
            conn.network.delete_security_group(security_group)
            logging.info(f"Removing {security_group_name}")
        else:
            logging.warning(f"{security_group_name} not found")
    except openstack.exceptions.ResourceNotFound:
        logging.warning(f"{security_group_name} not found")

def delete_keypair(conn, keypair_name):
    try:
        subprocess.check_output(['openstack', 'keypair', 'delete', keypair_name])
        logging.info(f"Removing key pair {keypair_name}")
    except subprocess.CalledProcessError as e:
        logging.info(f"Error deleting key pair {keypair_name}: {str(e)}")

def delete_files(tag_name):
    # List of files to delete
    files_to_delete = ['servers_fip', 'vip_address', 'hosts']
    for file_name in files_to_delete:
        try:
            os.remove(file_name)
            logging.info(f"Removing {file_name}")
        except FileNotFoundError:
            logging.warning(f"{file_name} not found")

    key_file = f"~/.ssh/{tag_name}_key.pem"
    if os.path.exists(os.path.expanduser(key_file)):
        os.remove(os.path.expanduser(key_file))
        logging.info(f"Removing {key_file}")
    else:
        logging.warning(f"{key_file} not found")

    config_file = "~/.ssh/config"
    if os.path.exists(os.path.expanduser(config_file)):
        os.remove(os.path.expanduser(config_file))
        logging.info("Removing SSH config file")
    else:
        logging.warning("SSH config file not found")

    known_hosts_file = "~/.ssh/known_hosts"
    if os.path.exists(os.path.expanduser(known_hosts_file)):
        os.remove(os.path.expanduser(known_hosts_file))
        logging.info("Removing known_hosts file")
    else:
        logging.warning("known_hosts file not found")

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
    vip_port = f"{tag_name}_vip"

    logging.info(f"$> cleanup {tag_name}")
    logging.info(f"Cleaning up {tag_name} using myRC")
    logging.info(f"We have {len([bastion_server, haproxy_server, haproxy_server2, dev_server])} nodes releasing them")

    with suppress_logging(logging.INFO):
        delete_floating_ips(conn)

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
                logging.warning(f"Duplicate instance found: {instance.name}. Removing it.")
                conn.compute.delete_server(instance)
            else:
                instance_names.add(instance.name)

    logging.info(f"Checking for {tag_name} in project.")
    logging.info("(network)(subnet)(router)(security groups)(keypairs)")
    logging.info("Cleanup done.")

parser = argparse.ArgumentParser()
parser.add_argument('rc_file', help='OpenStack RC file')
parser.add_argument('tag_name', help='Tag name for resources')
args = parser.parse_args()

with open(args.rc_file) as f:
    for line in f:
        if line.strip() and not line.startswith('#'):
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()
conn = connect_to_openstack()
cleanup_instances(conn, args.tag_name)
