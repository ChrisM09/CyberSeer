#!/bin/bash

# Need agent file
# Pipfile
# Pipfile.lock

cd /home/blackteam/ && \
	pipenv install && \
	pipenv run python3 agent.py
