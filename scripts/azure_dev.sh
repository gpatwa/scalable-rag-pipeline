#!/usr/bin/env bash
# Provision and operate the isolated Azure remote Docker development host.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TF_DIR="$ROOT_DIR/infra/terraform/azure-dev"
STATE_DIR="${AZURE_DEV_STATE_DIR:-$ROOT_DIR/.local/azure-dev}"
STATE_FILE="$STATE_DIR/terraform.tfstate"
KEY_FILE="$STATE_DIR/id_ed25519"
KNOWN_HOSTS_FILE="$STATE_DIR/known_hosts"

NAME="${AZURE_DEV_NAME:-compass-dev}"
LOCATION="${AZURE_DEV_LOCATION:-westus2}"
ADMIN_USERNAME="${AZURE_DEV_ADMIN_USERNAME:-devuser}"
VM_SIZE="${AZURE_DEV_VM_SIZE:-Standard_D8as_v5}"
AUTO_SHUTDOWN_TIME_UTC="${AZURE_DEV_AUTO_SHUTDOWN_TIME_UTC:-2300}"
REMOTE_PATH="/opt/compass"

die() {
  echo "azure-dev: $*" >&2
  exit 1
}

log() {
  echo "azure-dev: $*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

ensure_tools() {
  require_command az
  require_command terraform
  require_command ssh
  require_command ssh-keygen
  require_command rsync
  require_command curl
}

ensure_azure_login() {
  if ! az account show >/dev/null 2>&1; then
    log "Azure CLI is not authenticated; starting device-code login"
    az login --use-device-code >/dev/null
  fi

  if [[ -n "${AZURE_DEV_SUBSCRIPTION_ID:-}" ]]; then
    az account set --subscription "$AZURE_DEV_SUBSCRIPTION_ID"
  fi

  export ARM_SUBSCRIPTION_ID
  export ARM_TENANT_ID
  ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
  ARM_TENANT_ID="$(az account show --query tenantId -o tsv)"
}

ensure_key() {
  mkdir -p "$STATE_DIR"
  chmod 700 "$STATE_DIR"
  if [[ ! -f "$KEY_FILE" ]]; then
    log "generating isolated SSH key at $KEY_FILE"
    ssh-keygen -q -t ed25519 -N "" -f "$KEY_FILE" -C "compass-azure-dev"
  fi
  chmod 600 "$KEY_FILE"
}

ssh_source_cidr() {
  if [[ -n "${AZURE_DEV_SSH_SOURCE_CIDR:-}" ]]; then
    printf '%s\n' "$AZURE_DEV_SSH_SOURCE_CIDR"
  else
    printf '%s/32\n' "$(curl -4 -fsS https://api.ipify.org)"
  fi
}

terraform_init() {
  mkdir -p "$STATE_DIR/tfdata"
  TF_DATA_DIR="$STATE_DIR/tfdata" terraform -chdir="$TF_DIR" init -input=false -backend-config="path=$STATE_FILE" >/dev/null
}

terraform_cmd() {
  TF_DATA_DIR="$STATE_DIR/tfdata" terraform -chdir="$TF_DIR" "$@"
}

terraform_apply() {
  local source_cidr
  source_cidr="$(ssh_source_cidr)"
  terraform_init
  log "applying remote Docker development infrastructure in $LOCATION"
  terraform_cmd apply -auto-approve -input=false \
    -var="name=$NAME" \
    -var="location=$LOCATION" \
    -var="admin_username=$ADMIN_USERNAME" \
    -var="vm_size=$VM_SIZE" \
    -var="auto_shutdown_time_utc=$AUTO_SHUTDOWN_TIME_UTC" \
    -var="ssh_public_key=$(tr -d '\n' < "$KEY_FILE.pub")" \
    -var="ssh_source_cidr=$source_cidr"
}

output() {
  terraform_cmd output -raw "$1"
}

connection_target() {
  printf '%s@%s\n' "$ADMIN_USERNAME" "$(output public_ip_address)"
}

ssh_exec() {
  ssh -i "$KEY_FILE" \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=30 \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile="$KNOWN_HOSTS_FILE" \
    "$(connection_target)" "$@"
}

wait_for_ssh() {
  local attempts=0
  until ssh_exec "true" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    [[ "$attempts" -lt 60 ]] || die "SSH did not become available within five minutes"
    sleep 5
  done
}

write_remote_env() {
  ssh_exec bash -s <<'EOF'
set -eu
cat > /opt/compass/.env.azure-dev <<'ENV'
ENV=dev
CLOUD_PROVIDER=azure
SECRETS_PROVIDER=env
STORAGE_PROVIDER=s3
S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET_NAME=rag-platform-docs-dev
LLM_PROVIDER=ray
EMBED_PROVIDER=ray
ENV
EOF
}

sync_repo() {
  local target
  target="$(connection_target):$REMOTE_PATH/"
  log "syncing source to $target"
  rsync -az --delete --delete-delay \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude '.git/' \
    --exclude '.local/' \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude 'node_modules/' \
    --exclude '.terraform/' \
    --exclude '*.tfstate' \
    -e "ssh -i $KEY_FILE -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$KNOWN_HOSTS_FILE" \
    "$ROOT_DIR/" "$target"
  write_remote_env
}

start_remote() {
  ssh_exec bash -s <<'EOF'
set -eu
cd /opt/compass
docker compose --env-file .env.azure-dev up -d
docker compose --env-file .env.azure-dev --profile search up -d opensearch
docker compose --env-file .env.azure-dev --profile products up --build -d
EOF
}

up() {
  ensure_tools
  ensure_azure_login
  ensure_key
  terraform_apply
  az vm start --resource-group "$(output resource_group_name)" --name "$(output vm_name)" >/dev/null
  wait_for_ssh
  sync_repo
  start_remote
  log "ready: $(connection_target)"
  log "run 'make azure-dev-tunnel' to open local app/API ports"
}

sync() {
  ensure_tools
  ensure_azure_login
  ensure_key
  terraform_init
  wait_for_ssh
  sync_repo
}

start() {
  ensure_tools
  ensure_azure_login
  terraform_init
  az vm start --resource-group "$(output resource_group_name)" --name "$(output vm_name)" >/dev/null
  wait_for_ssh
  start_remote
}

stop() {
  ensure_tools
  ensure_azure_login
  terraform_init
  log "deallocating VM; disks remain for the next start"
  az vm deallocate --resource-group "$(output resource_group_name)" --name "$(output vm_name)"
}

status() {
  ensure_tools
  ensure_azure_login
  terraform_init
  az vm show --show-details \
    --resource-group "$(output resource_group_name)" \
    --name "$(output vm_name)" \
    --query '{name:name,powerState:powerState,publicIp:publicIps,location:location}' \
    -o table
}

ssh_shell() {
  ensure_tools
  ensure_key
  terraform_init
  ssh_exec
}

tunnel() {
  ensure_tools
  ensure_key
  terraform_init
  log "forwarding web/API/search ports; press Ctrl-C to close"
  ssh -N -i "$KEY_FILE" \
    -o StrictHostKeyChecking=accept-new \
    -o UserKnownHostsFile="$KNOWN_HOSTS_FILE" \
    -L 5173:127.0.0.1:5173 \
    -L 5174:127.0.0.1:5174 \
    -L 8080:127.0.0.1:8080 \
    -L 8090:127.0.0.1:8090 \
    -L 9200:127.0.0.1:9200 \
    -L 6333:127.0.0.1:6333 \
    -L 7474:127.0.0.1:7474 \
    -L 7687:127.0.0.1:7687 \
    "$(connection_target)"
}

destroy() {
  [[ "${AZURE_DEV_CONFIRM_DESTROY:-}" == "1" || "${1:-}" == "--yes" ]] || \
    die "refusing to destroy without AZURE_DEV_CONFIRM_DESTROY=1 or --yes"
  ensure_tools
  ensure_azure_login
  ensure_key
  terraform_init
  terraform_cmd destroy -auto-approve -input=false \
    -var="name=$NAME" \
    -var="location=$LOCATION" \
    -var="admin_username=$ADMIN_USERNAME" \
    -var="vm_size=$VM_SIZE" \
    -var="auto_shutdown_time_utc=$AUTO_SHUTDOWN_TIME_UTC" \
    -var="ssh_public_key=$(tr -d '\n' < "$KEY_FILE.pub")" \
    -var="ssh_source_cidr=$(ssh_source_cidr)"
}

usage() {
  cat <<'EOF'
Usage: scripts/azure_dev.sh <command>

Commands:
  up       Provision/update the VM, sync this checkout, and start Compose
  sync     Sync this checkout without rebuilding services
  start    Start the deallocated VM and Compose services
  stop     Deallocate the VM while preserving Docker volumes
  status   Show VM power state and public endpoint
  ssh      Open an interactive SSH shell
  tunnel   Forward local web/API/search ports through SSH
  destroy  Destroy the isolated remote-dev resource group (requires --yes)

Overrides:
  AZURE_DEV_SUBSCRIPTION_ID, AZURE_DEV_LOCATION, AZURE_DEV_NAME,
  AZURE_DEV_VM_SIZE, AZURE_DEV_SSH_SOURCE_CIDR,
  AZURE_DEV_AUTO_SHUTDOWN_TIME_UTC, AZURE_DEV_STATE_DIR
EOF
}

command="${1:-}"
shift || true
case "$command" in
  up) up "$@" ;;
  sync) sync "$@" ;;
  start) start "$@" ;;
  stop) stop "$@" ;;
  status) status "$@" ;;
  ssh) ssh_shell "$@" ;;
  tunnel) tunnel "$@" ;;
  destroy) destroy "$@" ;;
  *) usage; [[ -z "$command" ]] || exit 2 ;;
esac
