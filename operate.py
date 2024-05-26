import os
import time
import subprocess
from datetime import datetime
import openstack
import sys

def display(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def generate_file(cloud, tag, privatekey, hosts_file="hosts", ssh_config_file="config", knownhosts_file="known_hosts"):
    if os.path.isfile(hosts_file):
        os.remove(hosts_file)
    if os.path.isfile(ssh_config_file):
        os.remove(ssh_config_file)
    if os.path.isfile(knownhosts_file):
        os.remove(knownhosts_file)

    bastion = cloud.compute.find_server(f"{tag}_bastion")
    haproxy1 = cloud.compute.find_server(f"{tag}_HAproxy")
    haproxy2 = cloud.compute.find_server(f"{tag}_HAproxy2")

    display("Done, updating playbook and rev1_SSHconfig")
    with open(ssh_config_file, 'a') as ssh_config, open(hosts_file, 'a') as hosts:
        if bastion:
            bastion_ip = cloud.compute.get_server(bastion.id).addresses['private'][0]['addr']
            ssh_config.write(f"Host {tag}_bastion\n")
            ssh_config.write(f"   User ubuntu\n")
            ssh_config.write(f"   HostName {bastion_ip}\n")
            ssh_config.write(f"   IdentityFile {os.getcwd()}/{privatekey}\n")
            ssh_config.write(f"   StrictHostKeyChecking no\n")
            ssh_config.write(f"   PasswordAuthentication no\n")
            hosts.write("[bastion]\n")
            hosts.write(f"{tag}_bastion\n\n")
        
        if haproxy1:
            haproxy1_ip = cloud.compute.get_server(haproxy1.id).addresses['private'][0]['addr']
            ssh_config.write(f"\nHost {tag}_HAproxy\n")
            ssh_config.write(f"  HostName {haproxy1_ip}\n")
            ssh_config.write(f"  User ubuntu\n")
            ssh_config.write(f"  IdentityFile {os.getcwd()}/{privatekey}\n")
            ssh_config.write(f"  StrictHostKeyChecking no\n")
            ssh_config.write(f"  PasswordAuthentication no\n")
            ssh_config.write(f"  ProxyJump {tag}_bastion\n")
            hosts.write("[HAproxy]\n")
            hosts.write(f"{tag}_HAproxy\n")
            hosts.write(f"{tag}_HAproxy2\n\n")
        
        if haproxy2:
            haproxy2_ip = cloud.compute.get_server(haproxy2.id).addresses['private'][0]['addr']
            ssh_config.write(f"\nHost {tag}_HAproxy2\n")
            ssh_config.write(f"  HostName {haproxy2_ip}\n")
            ssh_config.write(f"  User ubuntu\n")
            ssh_config.write(f"  IdentityFile {os.getcwd()}/{privatekey}\n")
            ssh_config.write(f"  StrictHostKeyChecking no\n")
            ssh_config.write(f"  PasswordAuthentication no\n")
            ssh_config.write(f"  ProxyJump {tag}_bastion\n")

        hosts.write("[primary_proxy]\n")
        hosts.write(f"{tag}_HAproxy\n\n")
        hosts.write("[backup_proxy]\n")
        hosts.write(f"{tag}_HAproxy2\n\n")
        hosts.write("[webservers]\n")
        
        servers = cloud.compute.servers(details=True, status='ACTIVE')
        for server in servers:
            if server.name.startswith(f"{tag}_dev"):
                server_ip = server.addresses['private'][0]['addr']
                ssh_config.write(f"\nHost {server.name}\n")
                ssh_config.write(f"  HostName {server_ip}\n")
                ssh_config.write(f"  User ubuntu\n")
                ssh_config.write(f"  IdentityFile {os.getcwd()}/{privatekey}\n")
                ssh_config.write(f"  UserKnownHostsFile=~/dev/null\n")
                ssh_config.write(f"  StrictHostKeyChecking no\n")
                ssh_config.write(f"  PasswordAuthentication no\n")
                ssh_config.write(f"  ProxyJump {tag}_bastion\n")
                hosts.write(f"{server.name}\n")
                display(f"Adding {server.name} into the new config file")
        
        hosts.write("\n[all:vars]\n")
        hosts.write(f"ansible_user=ubuntu\n")
        hosts.write(f"ansible_ssh_private_key_file={os.getcwd()}/{privatekey}\n")
        hosts.write(f"ansible_ssh_common_args=' -F {ssh_config_file} '\n")

    os.chmod(ssh_config_file, 0o600)
    display("Running playbook")
    subprocess.run(["ansible-playbook", "-i", hosts_file, "site.yaml"])

def create_delete_dev_servers(cloud, tag, required_count, privatekey):
    servers = list(cloud.compute.servers(details=True, status='ACTIVE'))
    dev_servers = [server for server in servers if server.name.startswith(f"{tag}_dev")]
    current_count = len(dev_servers)

    display(f"Checking solution, we have: {current_count} nodes.")
    
    if required_count > current_count:
        add = required_count - current_count
        display(f"Launching new node/s; {', '.join([f'{tag}_dev{current_count + i + 1}' for i in range(add)])}, waiting for completion.")
        for i in range(add):
            name = f"{tag}_dev{current_count + i + 1}"
            cloud.compute.create_server(
                name=name,
                image_id=cloud.compute.find_image("Ubuntu 20.04 Focal Fossa x86_64").id,
                flavor_id=cloud.compute.find_flavor("1C-2GB-50GB").id,
                networks=[{"uuid": cloud.network.find_network(f"{tag}_network").id}],
                key_name=f"{tag}_key",
                security_groups=[cloud.network.find_security_group(f"{tag}_security_group").id],
                wait=True
            )
            display(f"Created server {name}")
        display("Done, updating playbook and rev1_SSHconfig")
        generate_file(cloud, tag, privatekey)
    
    elif required_count < current_count:
        remove = current_count - required_count
        for i in range(remove):
            server = dev_servers[i]
            cloud.compute.delete_server(server.id, wait=True)
            display(f"Deleted server {server.name}")
        display("Done, updating playbook and rev1_SSHconfig")
        generate_file(cloud, tag, privatekey)
    
    else:
        display("Sleeping.")

def main():
    if len(sys.argv) != 4:
        print("Usage: operate <path_to_myRC> <tag_name> <path_to_id_rsa.pub>")
        sys.exit(1)
    
    openrcfile = sys.argv[1:][0]
    tag = sys.argv[2]
    ssh_key = sys.argv[3]
    privatekey = ssh_key.replace(".pub", "")
    
    display(f"Starting operation process to handle dev servers for tag:{tag} using {openrcfile} for credentials.")
    
    os.environ['OS_CLIENT_CONFIG_FILE'] = openrcfile
    cloud = openstack.connect(cloud='default')

    while True:
        display("Reading server.conf, we need {} nodes.".format(required_count))
        with open("servers.conf", "r") as f:
            required_count = int(f.read().strip())
        create_delete_dev_servers(cloud, tag, required_count, privatekey)
        time.sleep(30)

if __name__ == "__main__":
    main()
