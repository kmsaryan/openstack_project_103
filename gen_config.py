import subprocess
import json

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
            for network_entry in networks.split(','):
                if '=' in network_entry:
                    network_name, ip = network_entry.split('=')
                    if ip.startswith('10.'):  # Ensure we get internal IP (e.g., 10.x.x.x)
                        internal_ips[server_name] = ip
                else:
                    (f"Skipping invalid network entry: {network_entry}")

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

def generate_ssh_config(internal_ips, fip_map):
    """
    Generate SSH config file
    """
    with open('ssh_config', 'w') as f:
        f.write("Host *\n")
        f.write("\tUser ubuntu\n")
        f.write("\tIdentityFile ~/.ssh/id_rsa\n")
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
                f.write(f"    IdentityFile ~/.ssh/id_rsa\n\n")
            elif 'bastion' in server_name or 'HAproxy' in server_name:
                fip = fip_map.get(internal_ip)
                if fip:
                    f.write(f"Host {server_name}\n")
                    f.write(f"    HostName {fip}\n")
                    f.write(f"    User ubuntu\n")
                    f.write(f"    IdentityFile ~/.ssh/id_rsa\n\n")

def generate_host_file(internal_ips, fip_map):
    """
    Generate host file
    """
    with open('hosts', 'w') as f:
        f.write("[haproxy]\n")
        for server_name, internal_ip in internal_ips.items():
            if 'HAproxy' in server_name:
                f.write(f"{server_name}\n")

        f.write("\n[webservers]\n")
        for server_name, internal_ip in internal_ips.items():
            if 'dev' in server_name:
                f.write(f"{server_name}\n")

        f.write("\n[all:vars]\n")
        f.write("ansible_user=ubuntu\n")

def main():
    # Fetch internal IPs and floating IPs
    internal_ips = fetch_internal_ips()
    floating_ips = fetch_floating_ips()

    # Print the internal and floating IPs for debugging
    print("Internal IPs:", internal_ips)
    print("Floating IPs:", floating_ips)

    # Generate SSH config file
    generate_ssh_config(internal_ips, floating_ips)

    # Generate host file
    generate_host_file(internal_ips, floating_ips)

    

if __name__ == "__main__":
    main()
