#!/bin/bash

# If needing password, install sshpass and uncomment the following line
# export PASSWORD="password"
# 
# Sample modification to the Ansible calls:
#     ansible-playbook \
#        -i inventory.yaml \
#        -e ansible_password='{{ lookup("env", "PASSWORD") }}' \
#        Ansible/Deployment/deploy_scoring_services.yml



# If no option is provided, we will default to "complete"
if [ -z "$1" ]; then
    DEPLOYMENT_OPTION="complete"
else
    DEPLOYMENT_OPTION=$1
fi

echo "Deployment option: $DEPLOYMENT_OPTION"


# If the deployment option is "complete", we will deploy the entire scoring engine
if [ "$DEPLOYMENT_OPTION" == "complete" ]; then

    echo "[!] Deploying the entire scoring engine"
    echo "[!] Setting up Docker swarm manager"

    ansible-playbook \
        -i inventory.yaml \
        Ansible/Deployment/init_swarm_manager.yml    

    echo "[+] Swarm Manager initialized. Waiting for 5 seconds before initializing workers"

    sleep 5

    echo "[!] Setting up Docker swarm workers"

    ansible-playbook \
        -i inventory.yaml \
        Ansible/Deployment/init_swarm_worker.yml

    echo "[+] Swarm Workers initialized. Waiting for 5 seconds before deploying services"

    sleep 5
fi


# If we get a redeploy, then we will redeploy the scoring engine services
if [ "$DEPLOYMENT_OPTION" == "redeploy" ]; then    

    echo "[!] Redeploying the scoring engine services"
    ansible-playbook \
        -i inventory.yaml \
        Ansible/Deployment/cleanup_scoring_services.yml

    echo "[+] Removed existing services"
fi

# Deploy the scoring services.
if [ "$DEPLOYMENT_OPTION" == "complete" ] || [ "$DEPLOYMENT_OPTION" == "partial" ] || [ "$DEPLOYMENT_OPTION" == "redeploy" ]; then

    echo "[!] Building Docker images"
    ansible-playbook \
    -i inventory.yaml \
    --extra-vars "dns_server_password=ScoreStack" \
    Ansible/Deployment/build_docker_images.yml

    echo "[+] Docker images built. Waiting for 5 seconds before deploying services"

    sleep 5

    echo "[!] Deploying scoring services"
    ansible-playbook \
        -i inventory.yaml \
        Ansible/Deployment/deploy_scoring_services.yml

    echo "[+] Scoring services deployed!"
fi


# Deploy the agents.
if [ "$DEPLOYMENT_OPTION" == "complete" ] || [ "$DEPLOYMENT_OPTION" == "agents" ]; then

    # Deploy the agents.
    echo "[!] Deploying Agents..."

    # Deploy the agents
    ansible-playbook \
    -i inventory.yaml \
    Ansible/Agent-Initialization/deploy-agents.yml

    echo "[+] Agents initialized and started!"
fi