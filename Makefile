PYTHON  ?= python
SERVICE ?= keep-tasks-mcp
REGION  ?= europe-west1
# Your Google Cloud project id: make gcloud-setup PROJECT=my-project
PROJECT ?=

PROJECT_FLAG = $(if $(PROJECT),--project $(PROJECT),)

.PHONY: help deps env env-keep env-outlook run gcloud-install gcloud-setup url

help:
	@echo First time:  make deps, make env, then make run to test locally
	@echo Cloud:       make gcloud-install, make gcloud-setup PROJECT=id, then deploy, then make url PROJECT=id
	@echo Optional:    make env-keep adds Google Keep, make env-outlook adds Outlook.com (read-only)

deps:
	$(PYTHON) -m pip install -r requirements.txt google-auth-oauthlib gpsoauth

# Browser login for Google Tasks + Gmail, generates MCP_SECRET -> env.yaml
env:
	$(PYTHON) scripts/setup_env.py login

env-keep:
	$(PYTHON) scripts/setup_env.py keep

# Device-code login for a personal Microsoft account -> env.yaml
env-outlook:
	$(PYTHON) scripts/setup_env.py outlook

# Start the server locally with the values from env.yaml
run:
	$(PYTHON) scripts/setup_env.py run

gcloud-install:
	winget install --id Google.CloudSDK -e

# Login and enable the APIs. The project needs billing linked.
gcloud-setup:
	gcloud auth login
	gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com tasks.googleapis.com gmail.googleapis.com $(PROJECT_FLAG)

url:
	$(PYTHON) scripts/setup_env.py url --service $(SERVICE) --region $(REGION) --project "$(PROJECT)"
