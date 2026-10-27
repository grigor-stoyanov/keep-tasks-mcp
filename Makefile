PYTHON  ?= python
SERVICE ?= keep-tasks-mcp
REGION  ?= europe-west1
# Your Google Cloud project id: make gcloud-setup PROJECT=my-project
PROJECT ?=

PROJECT_FLAG = $(if $(PROJECT),--project $(PROJECT),)

# Shared server for friends (multiuser/), a separate Cloud Run service
FRIENDS_SERVICE ?= keep-tasks-friends
GCP_PROJECT = $(or $(PROJECT),$(shell gcloud config get-value project))
FRIENDS_IMAGE = $(REGION)-docker.pkg.dev/$(GCP_PROJECT)/cloud-run-source-deploy/$(FRIENDS_SERVICE)

.PHONY: help deps env env-keep env-outlook run gcloud-install gcloud-setup deploy url friends-setup deploy-friends share-friends

help:
	@echo First time:  make deps, make env, then make run to test locally
	@echo Cloud:       make gcloud-install, make gcloud-setup PROJECT=id, make deploy, then make url PROJECT=id
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

# Build remotely with Cloud Build and roll out a new revision of the same service (URL stays the same).
# --env-vars-file replaces all env vars with the contents of env.yaml.
deploy:
	gcloud run deploy $(SERVICE) --source . --region $(REGION) --allow-unauthenticated --env-vars-file env.yaml --max-instances 1 --memory 512Mi $(PROJECT_FLAG)

url:
	$(PYTHON) scripts/setup_env.py url --service $(SERVICE) --region $(REGION) --project "$(PROJECT)"

# One-time: the Firestore database that stores everyone's sign-ins (free tier: one per project)
friends-setup:
	gcloud services enable firestore.googleapis.com $(PROJECT_FLAG)
	gcloud firestore databases create --location=$(REGION) $(PROJECT_FLAG)

# Build with multiuser/Dockerfile, then deploy. One instance at most, so a busy friend can't scale up your bill.
deploy-friends:
	gcloud builds submit --config multiuser/cloudbuild.yaml --substitutions _IMAGE=$(FRIENDS_IMAGE) $(PROJECT_FLAG)
	gcloud run deploy $(FRIENDS_SERVICE) --image $(FRIENDS_IMAGE) --region $(REGION) --allow-unauthenticated --env-vars-file multiuser/env.yaml --max-instances 1 --concurrency 20 --memory 512Mi $(PROJECT_FLAG)

# Invite text for friends, linking to the server's /join page. ARGS="--name Alex --preview"
share-friends:
	$(PYTHON) multiuser/share.py $(ARGS)
