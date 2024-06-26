#!/usr/bin/env python3

"""this file contains the script to generate the ssh_config and hosts file"""
import subprocess
import json
import os
def run_command(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    if process.returncode != 0:
        print(f"Error executing command: {command}\n{error.decode()}")
    return output.decode()

def fetch_internal_ips():
    """
    Fetch internal IPs
    """
    command = "openstack server list -f json"
    output = run_command(command)
    servers = json.loads(output)
    internal_ips = {}
    for server in servers:
        server_name = server['Name']
        if 'Networks' in server:
            networks = server['Networks']
            for network_name, ips in networks.items():
                for ip in ips:
                    if ip.startswith('10.'):  # Ensure we get internal IP (e.g., 10.x.x.x)
                        internal_ips[server_name] = ip
    return internal_ips

def fetch_floating_ips():
    """
    Fetch floating IPs
    """
    command = "openstack floating ip list -f json"
    output = run_command(command)
    fips = json.loads(output)
    fip_map = {fip['Fixed IP Address']: fip['Floating IP Address'] for fip in fips if fip['Fixed IP Address']}
    return fip_map

def generate_ssh_config(internal_ips, fip_map, tag_name):
    """
    Generate SSH config file
    """
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    with open('ssh_config', 'w') as f:
        f.write("Host *\n")
        f.write("\tUser ubuntu\n")
        f.write("\tStrictHostKeyChecking no\n")
        f.write("\tPasswordAuthentication no\n")
        f.write("\tForwardAgent yes\n")
        f.write("\tControlMaster auto\n")
        f.write("\tControlPath ~/.ssh/ansible-%r@%h:%p\n")
        f.write("\tControlPersist yes\n")
        f.write("\tProxyCommand ssh -W %h:%p bastion\n\n")

        for server_name, internal_ip in internal_ips.items():
            if 'dev' in server_name:
                f.write(f"Host {server_name}\n")
                f.write(f"    HostName {internal_ip}\n")
                f.write(f"    User ubuntu\n")
                f.write(f"    IdentityFile ~/.ssh/{tag_name}_{server_name}.pem\n\n")
            elif 'bastion' in server_name or 'HAproxy' in server_name:
                fip = fip_map.get(internal_ip)
                if fip:
                    f.write(f"Host {server_name}\n")
                    f.write(f"    HostName {fip}\n")
                    f.write(f"    User ubuntu\n")
                    f.write(f"    IdentityFile ~/.ssh/{tag_name}_{server_name}.pem\n\n")

def generate_host_file(internal_ips, fip_map, tag_name):
    """
    Generate host file
    """
    haproxy_server = f"{tag_name}_HAproxy"
    haproxy_server2 = f"{tag_name}_HAproxy2"
    bastion_server = f"{tag_name}_bastion"

    with open('hosts', 'w') as f:
        f.write("[bastion]\n")
        f.write(f"{bastion_server} ansible_host={fip_map.get(internal_ips[bastion_server])} ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/{tag_name}_key.pem\n\n")

        f.write("[haproxy]\n")
        if haproxy_server in internal_ips:
            f.write(f"{haproxy_server} ansible_host={internal_ips[haproxy_server]} ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/{tag_name}_key.pem ansible_ssh_common_args='-o ProxyCommand=\"ssh -W %h:%p -i ~/.ssh/{tag_name}_key.pem ubuntu@{fip_map.get(internal_ips[bastion_server])}\"'\n")
        if haproxy_server2 in internal_ips:
            f.write(f"{haproxy_server2} ansible_host={internal_ips[haproxy_server2]} ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/{tag_name}_key.pem ansible_ssh_common_args='-o ProxyCommand=\"ssh -W %h:%p -i ~/.ssh/{tag_name}_key.pem ubuntu@{fip_map.get(internal_ips[bastion_server])}\"'\n")
        f.write("\n[devservers]\n")
        for server_name, internal_ip in internal_ips.items():
            if 'dev' in server_name:
                f.write(f"{server_name} ansible_host={internal_ip} ansible_user=ubuntu ansible_ssh_private_key_file=~/.ssh/{tag_name}_key.pem ansible_ssh_common_args='-o ProxyCommand=\"ssh -W %h:%p -i ~/.ssh/{tag_name}_key.pem ubuntu@{fip_map.get(internal_ips[bastion_server])}\"'\n")




def main():
    command = "openstack floating ip list -f json"
    output = run_command(command)
    fips = json.loads(output)
    fip_map = {fip['Fixed IP Address']: fip['Floating IP Address'] for fip in fips if fip['Fixed IP Address']}
    tag_name = {"tag_name"}
    # Fetch internal IPs and floating IPs
    internal_ips = fetch_internal_ips()
    floating_ips = fetch_floating_ips()

    # Print the internal and floating IPs for debugging
    print("Internal IPs:", internal_ips)
    print("Floating IPs:", floating_ips)

    # Generate SSH config file
    generate_ssh_config(internal_ips, fip_map, tag_name)    # Generate host file
    generate_host_file(internal_ips, fip_map, tag_name)
if __name__ == "__main__":
    main()