#!/bin/bash 

# Remove the old checks from the Ansible files
rm -r Ansible/roles/upload-checks/files/output-checks/*

# Remove local old checks. NOTE: Ansible will remove from the remote server
rm -r output-checks/*

python3 check-generator.py


# Copy the checks to Ansible directory
cp -r output-checks Ansible/roles/upload-checks/files/

# Change the directory to Ansible
cd Ansible

# export PASSWORD="1qazxsW@1"

# ansible-playbook \
#     -i inventory.ini \
#     -e ansible_password='{{ lookup("env", "PASSWORD") }}' \
#     upload-checks.yml 

ansible-playbook \
    -i ../../inventory.yaml \
    upload-checks.yml
