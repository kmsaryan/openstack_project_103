import openstack
import os
import sys
import subprocess

def run_command(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    if process.returncode != 0:
        print(f"Error executing command: {command}\n{error.decode()}")
        sys.exit(1)
    return output.decode()

def fetch_internal_ips(conn, tag_name):
    servers = conn.compute.servers(details=True, all_projects=False, filters={"name": f"{tag_name}*"})
    internal_ips = {}
    
    for server in servers:
        server_name = server.name
        networks = server.addresses
        
        for network_name, ip_list in networks.items():
            for ip_info in ip_list:
                ip_address = ip_info['addr']
                # Check if IP is an internal IP (assuming internal IPs are in the range 10.x.x.x)
                if ip_address.startswith('10.'):
                    internal_ips[server_name] = ip_address
                    
    return internal_ips

def read_fip_file(file_path):
    fip_map = {}
    with open(file_path, 'r') as f:
        for line in f:
            server_name, fip = line.strip().split(':')
            fip_map[server_name] = fip
            #add_to_known_hosts(fip)
    return fip_map
"""
def add_to_known_hosts(ip_address):
    command = f"ssh-keyscan -H {ip_address} >> ~/.ssh/known_hosts"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result
"""

def generate_ssh_config(internal_ips, fip_map, tag_name, key_path):
    bastion_name = f"{tag_name}_bastion"
    haproxy_server = f"{tag_name}_HAproxy"
    haproxy_server2 = f"{tag_name}_HAproxy2"
    bastion_fip = fip_map.get(bastion_name, "")
    haproxy_fip1 = fip_map.get(haproxy_server, "")
    haproxy_fip2 = fip_map.get(haproxy_server2, "")
    
    with open('config', 'w') as f:
        f.write("Host *\n")
        f.write("\tUser ubuntu\n")
        f.write(f"\tIdentityFile {key_path}\n")
        f.write("\tStrictHostKeyChecking no\n")
        f.write("\tPasswordAuthentication no\n")
        f.write("\tServerAliveInterval 60\n")
        f.write("\tForwardAgent yes\n")
        f.write("\tControlMaster auto\n")
        f.write("\tControlPath ~/.ssh/ansible-%r@%h:%p\n")
        f.write("\tControlPersist yes\n\n")

        if bastion_fip:
            f.write(f"Host {bastion_name}\n")
            f.write(f"\tHostName {bastion_fip}\n")
        if haproxy_fip1:
            f.write(f"Host {haproxy_server}\n")
            f.write(f"\tHostName {haproxy_fip1}\n")
            f.write(f"\tProxyJump {bastion_name}\n")
        if haproxy_fip2:
            f.write(f"Host {haproxy_server2}\n")
            f.write(f"\tHostName {haproxy_fip2}\n")
            f.write(f"\tProxyJump {bastion_name}\n")

        for server_name, internal_ip in internal_ips.items():
            if 'dev' in server_name:
                f.write(f"Host {server_name}\n")
                f.write(f"\tHostName {internal_ip}\n")
                f.write(f"\tProxyJump {bastion_name}\n")

def generate_ansible_config(tag_name, fip_map, bastion_name, key_path):
    with open('ansible.cfg', 'w') as f:
        f.write("[defaults]\n")
        f.write("inventory = hosts\n")
        f.write("remote_user = ubuntu\n")
        f.write(f"private_key_file = {key_path}\n")
        f.write("host_key_checking = False\n")
        f.write("control_path = ~/.ssh/ansible-%r@%h:%p\n")
        f.write("control_master = auto\n")
        f.write("control_persist = yes\n")
        f.write("ssh_args = -o ForwardAgent=yes\n")
        f.write(f"ansible_ssh_common_args = -o ProxyJump=ubuntu@{fip_map.get(bastion_name, '')}-o IdentityFile={key_path}\n")

def generate_host_file(internal_ips, fip_map, tag_name, key_path):
    bastion_name = f"{tag_name}_bastion"
    haproxy_server = f"{tag_name}_HAproxy"
    haproxy_server2 = f"{tag_name}_HAproxy2"

    with open('hosts', 'w') as f:
        f.write("[bastion]\n")
        if bastion_name in internal_ips:
            f.write(f"{bastion_name} ansible_host={fip_map.get(bastion_name, '')} ansible_user=ubuntu ansible_ssh_private_key_file={key_path}\n\n")

        f.write("[main_proxy]\n")
        if haproxy_server in internal_ips:
            f.write(f"{haproxy_server} ansible_host={fip_map.get(haproxy_server, '')} ansible_user=ubuntu ansible_ssh_private_key_file={key_path} ansible_ssh_common_args='-o ProxyJump=ubuntu@{fip_map.get(bastion_name, '')} -i {key_path}'\n")
        
        f.write("\n[standby_proxy]\n")
        if haproxy_server2 in internal_ips:
            f.write(f"{haproxy_server2} ansible_host={fip_map.get(haproxy_server2, '')} ansible_user=ubuntu ansible_ssh_private_key_file={key_path} ansible_ssh_common_args='-o ProxyJump=ubuntu@{fip_map.get(bastion_name, '')} -i {key_path}'\n")

        f.write("\n[devservers]\n")
        for server_name, internal_ip in internal_ips.items():
            if 'dev' in server_name:
                f.write(f"{server_name} ansible_host={internal_ip} ansible_user=ubuntu ansible_ssh_private_key_file={key_path} ansible_ssh_common_args='-o ProxyJump=ubuntu@{fip_map.get(bastion_name, '')} -i {key_path}'\n")

def main(tag_name, key_path):
    print(f"Received tag_name: {tag_name}, key_path: {key_path}")
    
    # Establish connection with OpenStack
    conn = openstack.connect()

    internal_ips = fetch_internal_ips(conn, tag_name)
    fip_map = read_fip_file('servers_fip')
    print("Internal IPs:", internal_ips)
    print("Floating IPs:", fip_map)
    generate_ssh_config(internal_ips, fip_map, tag_name, key_path)
    print("Generated SSH config.")
    generate_ansible_config(tag_name, fip_map, f"{tag_name}_bastion", key_path)
    print("Generated Ansible config.")
    generate_host_file(internal_ips, fip_map, tag_name, key_path)
    print("Generated hosts file.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: gen_config.py <tag_name> <key_path>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
