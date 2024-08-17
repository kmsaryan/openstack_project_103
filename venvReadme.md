#execute commands via virtual environment 
    the virtual environment configured with necssary libaries required for scripts the following will be used mostly for our scripts 
    which is necessary you activate venv before executing scripts
##INSTALLATIONS 
    pip install python-openstackclient
    pip install os
    pip install argparse
    pip install subprocess32
    pip install python-openstacksdk
##Other installations:
    sudo apt install python3-openstackclient
    sudo apt install software-properties-common
    sudo add-apt-repository --yes --update ppa:ansible/ansible
    sudo apt install ansible


###commandline 
TO execute the scripts activate venv
``` source venv/bin/activate ```
To execute install you need a rc file and a token 
```source <path to rc file> ``` 
To generate token in openstack
``` openstack token issue ```
if your are facing auth error while executing script you need to generate your token 

####some openstack commands
    ``` openstack server list ```
    ``` openstack catalog show ```
#####some ansible commands to check:
```ansible all -i hosts -m ping ``` 
checks wheather the ansible is able to reach the intended hosts present in inventory file named 'hosts'
``` ansible-playbook -i hosts site.yaml ```
runs the ansible playbook
the haproxy was checked wheather functioning or not using the following steps:
first login into bastion host using 
``` ssh -i <key.pem path> ubuntu@<bastion ip address> ```
then curl was performed
``` curl http://<haproxy_server_ip>:5000/stats ```
for example the haproxy ip address was 91.123.203.239 and port 5000
the command resulted as 
```curl http://91.123.203.239:5000
08:59:33 10.10.0.24:45492 -- 10.10.0.23 (test7-dev1) 58 ```

the script accepts the follwoing command line arguments
``` python3 install.py  <path to rc file> <tag>  <path to id_rsa.pub> ```
    python3 install.py  madhav.rc tag1  /home/user/.ssh/id_rsa