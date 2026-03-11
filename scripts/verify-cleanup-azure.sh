#!/bin/bash
# scripts/verify-cleanup-azure.sh
# Run AFTER terraform destroy to catch orphaned Azure resources still billing you.
# This is the Azure equivalent of scripts/verify-cleanup.sh (AWS).
#
# Usage:
#   ./scripts/verify-cleanup-azure.sh              # Check only (default)
#   ./scripts/verify-cleanup-azure.sh --delete     # Check + delete orphans

set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-rag-platform-rg}"
CLUSTER_NAME="${CLUSTER_NAME:-rag-platform-aks}"
PROJECT_TAG="Enterprise-RAG"
DELETE=false
FOUND_RESOURCES=false

[ "${1:-}" = "--delete" ] && DELETE=true

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=============================================="
echo "  POST-DESTROY VERIFICATION (Azure)"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Mode: $([ "$DELETE" = true ] && echo 'CHECK + DELETE' || echo 'CHECK ONLY')"
echo "=============================================="
echo ""

# ── Pre-check: az CLI logged in ──────────────
if ! az account show &>/dev/null; then
    echo -e "  ${RED}ERROR: Not logged in to Azure CLI. Run 'az login' first.${NC}"
    exit 1
fi

SUBSCRIPTION=$(az account show --query "name" -o tsv)
echo "  Subscription: $SUBSCRIPTION"
echo ""

# ── 1. Resource Group ──────────────────────────
echo "1/10  Checking Resource Group..."
RG_EXISTS=$(az group exists --name "$RESOURCE_GROUP" 2>/dev/null || echo "false")
if [ "$RG_EXISTS" = "true" ]; then
    RG_RESOURCES=$(az resource list --resource-group "$RESOURCE_GROUP" --query "length([])" -o tsv 2>/dev/null || echo "0")
    echo -e "  ${RED}FOUND: $RESOURCE_GROUP ($RG_RESOURCES resources inside)${NC}"
    echo "  !! Resource group exists — may contain billable resources"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        echo "  Deleting entire resource group $RESOURCE_GROUP (this removes all contained resources)..."
        az group delete --name "$RESOURCE_GROUP" --yes --no-wait
        echo "    Resource group deletion initiated (takes 5-15 min)"
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 2. AKS Clusters ───────────────────────────
echo "2/10  Checking AKS clusters..."
AKS_CLUSTERS=$(az aks list --query "[?contains(name, 'rag')].{Name:name,RG:resourceGroup,State:provisioningState}" -o tsv 2>/dev/null || echo "")
if [ -n "$AKS_CLUSTERS" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $AKS_CLUSTERS"
    echo "  !! AKS costs include node VMs + management fee"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for cluster in $(az aks list --query "[?contains(name, 'rag')].name" -o tsv 2>/dev/null); do
            rg=$(az aks list --query "[?name=='$cluster'].resourceGroup" -o tsv 2>/dev/null)
            echo "  Deleting AKS cluster $cluster in $rg..."
            az aks delete --name "$cluster" --resource-group "$rg" --yes --no-wait 2>/dev/null
            echo "    Cluster deletion initiated (takes ~10 min)"
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 3. PostgreSQL Flexible Servers ─────────────
echo "3/10  Checking PostgreSQL Flexible Servers..."
PG_SERVERS=$(az postgres flexible-server list \
    --query "[?contains(name, 'rag') || contains(name, 'ragplatform')].{Name:name,RG:resourceGroup,State:state,SKU:sku.name}" \
    -o tsv 2>/dev/null || echo "")
if [ -n "$PG_SERVERS" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $PG_SERVERS"
    echo "  !! PostgreSQL Flexible Server bills even when stopped (storage charges)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for server in $(az postgres flexible-server list --query "[?contains(name, 'rag') || contains(name, 'ragplatform')].name" -o tsv 2>/dev/null); do
            rg=$(az postgres flexible-server list --query "[?name=='$server'].resourceGroup" -o tsv 2>/dev/null)
            echo "  Deleting PostgreSQL server $server..."
            az postgres flexible-server delete --name "$server" --resource-group "$rg" --yes 2>/dev/null
            echo "    Deleted."
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 4. Azure Cache for Redis ──────────────────
echo "4/10  Checking Redis caches..."
REDIS_CACHES=$(az redis list \
    --query "[?contains(name, 'rag')].{Name:name,RG:resourceGroup,SKU:sku.name,State:provisioningState}" \
    -o tsv 2>/dev/null || echo "")
if [ -n "$REDIS_CACHES" ]; then
    echo -e "  ${RED}FOUND:${NC}"
    echo "  $REDIS_CACHES"
    echo "  !! Redis Basic C0 costs ~\$16/month"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for cache in $(az redis list --query "[?contains(name, 'rag')].name" -o tsv 2>/dev/null); do
            rg=$(az redis list --query "[?name=='$cache'].resourceGroup" -o tsv 2>/dev/null)
            echo "  Deleting Redis cache $cache..."
            az redis delete --name "$cache" --resource-group "$rg" --yes 2>/dev/null
            echo "    Deletion initiated."
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 5. Container Registry (ACR) ───────────────
echo "5/10  Checking Container Registries..."
ACR_REPOS=$(az acr list \
    --query "[?contains(name, 'rag')].{Name:name,RG:resourceGroup,SKU:sku.name}" \
    -o tsv 2>/dev/null || echo "")
if [ -n "$ACR_REPOS" ]; then
    echo -e "  ${YELLOW}FOUND:${NC}"
    echo "  $ACR_REPOS"
    echo "  (ACR Basic costs ~\$5/month)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for acr in $(az acr list --query "[?contains(name, 'rag')].name" -o tsv 2>/dev/null); do
            rg=$(az acr list --query "[?name=='$acr'].resourceGroup" -o tsv 2>/dev/null)
            echo "  Deleting ACR $acr..."
            az acr delete --name "$acr" --resource-group "$rg" --yes 2>/dev/null
            echo "    Deleted."
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 6. Storage Accounts ───────────────────────
echo "6/10  Checking Storage Accounts..."
STORAGE=$(az storage account list \
    --query "[?contains(name, 'rag')].{Name:name,RG:resourceGroup,Kind:kind,SKU:sku.name}" \
    -o tsv 2>/dev/null || echo "")
if [ -n "$STORAGE" ]; then
    echo -e "  ${YELLOW}FOUND:${NC}"
    echo "  $STORAGE"
    echo "  (Storage cost is minimal — keep Terraform state account if you plan to redeploy)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for acct in $(az storage account list --query "[?contains(name, 'rag') && !contains(name, 'terraform')].name" -o tsv 2>/dev/null); do
            rg=$(az storage account list --query "[?name=='$acct'].resourceGroup" -o tsv 2>/dev/null)
            echo "  Deleting storage account $acct..."
            az storage account delete --name "$acct" --resource-group "$rg" --yes 2>/dev/null
            echo "    Deleted."
        done
        # Warn about terraform state account
        TF_ACCT=$(az storage account list --query "[?contains(name, 'rag') && contains(name, 'terraform')].name" -o tsv 2>/dev/null || echo "")
        if [ -n "$TF_ACCT" ]; then
            echo -e "  ${YELLOW}KEPT: $TF_ACCT (Terraform state — delete manually if not redeploying)${NC}"
        fi
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 7. Key Vault ──────────────────────────────
echo "7/10  Checking Key Vaults..."
KV=$(az keyvault list \
    --query "[?contains(name, 'rag')].{Name:name,RG:resourceGroup,State:properties.provisioningState}" \
    -o tsv 2>/dev/null || echo "")
# Also check soft-deleted vaults
KV_DELETED=$(az keyvault list-deleted \
    --query "[?contains(name, 'rag')].{Name:name,ScheduledPurge:scheduledPurgeDate}" \
    -o tsv 2>/dev/null || echo "")
if [ -n "$KV" ]; then
    echo -e "  ${YELLOW}FOUND (active):${NC}"
    echo "  $KV"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for vault in $(az keyvault list --query "[?contains(name, 'rag')].name" -o tsv 2>/dev/null); do
            echo "  Deleting Key Vault $vault..."
            az keyvault delete --name "$vault" 2>/dev/null
            echo "  Purging Key Vault $vault..."
            az keyvault purge --name "$vault" 2>/dev/null || echo "    (Purge failed — may have purge protection enabled)"
        done
    fi
fi
if [ -n "$KV_DELETED" ]; then
    echo -e "  ${YELLOW}FOUND (soft-deleted):${NC}"
    echo "  $KV_DELETED"
    echo "  (Soft-deleted vaults may block reuse of the same name)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for vault in $(az keyvault list-deleted --query "[?contains(name, 'rag')].name" -o tsv 2>/dev/null); do
            echo "  Purging soft-deleted vault $vault..."
            az keyvault purge --name "$vault" 2>/dev/null || echo "    (Purge protection may prevent this)"
        done
    fi
fi
if [ -z "$KV" ] && [ -z "$KV_DELETED" ]; then
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 8. Virtual Networks ───────────────────────
echo "8/10  Checking Virtual Networks..."
VNETS=$(az network vnet list \
    --query "[?contains(name, 'rag')].{Name:name,RG:resourceGroup,CIDR:addressSpace.addressPrefixes[0]}" \
    -o tsv 2>/dev/null || echo "")
if [ -n "$VNETS" ]; then
    echo -e "  ${YELLOW}FOUND:${NC}"
    echo "  $VNETS"
    echo "  (VNets are free, but may contain billable sub-resources)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for vnet in $(az network vnet list --query "[?contains(name, 'rag')].name" -o tsv 2>/dev/null); do
            rg=$(az network vnet list --query "[?name=='$vnet'].resourceGroup" -o tsv 2>/dev/null)
            echo "  Deleting VNet $vnet..."
            az network vnet delete --name "$vnet" --resource-group "$rg" 2>/dev/null || echo "    (May fail if sub-resources exist)"
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 9. Managed Identities ─────────────────────
echo "9/10  Checking Managed Identities..."
IDENTITIES=$(az identity list \
    --query "[?contains(name, 'rag')].{Name:name,RG:resourceGroup}" \
    -o tsv 2>/dev/null || echo "")
if [ -n "$IDENTITIES" ]; then
    echo -e "  ${YELLOW}FOUND:${NC}"
    echo "  $IDENTITIES"
    echo "  (Managed Identities are free, but clean up for hygiene)"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        for id_name in $(az identity list --query "[?contains(name, 'rag')].name" -o tsv 2>/dev/null); do
            rg=$(az identity list --query "[?name=='$id_name'].resourceGroup" -o tsv 2>/dev/null)
            echo "  Deleting identity $id_name..."
            az identity delete --name "$id_name" --resource-group "$rg" 2>/dev/null
        done
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# ── 10. Load Balancers & Public IPs ────────────
echo "10/10 Checking Load Balancers & Public IPs..."
# AKS creates a managed resource group with LBs and public IPs
AKS_MC_RG="MC_${RESOURCE_GROUP}_${CLUSTER_NAME}_centralus"
MC_EXISTS=$(az group exists --name "$AKS_MC_RG" 2>/dev/null || echo "false")
if [ "$MC_EXISTS" = "true" ]; then
    MC_RESOURCES=$(az resource list --resource-group "$AKS_MC_RG" --query "length([])" -o tsv 2>/dev/null || echo "0")
    echo -e "  ${RED}FOUND: AKS managed resource group $AKS_MC_RG ($MC_RESOURCES resources)${NC}"
    echo "  !! Contains Load Balancers and Public IPs created by AKS"
    FOUND_RESOURCES=true
    if [ "$DELETE" = true ]; then
        echo "  Deleting managed resource group $AKS_MC_RG..."
        az group delete --name "$AKS_MC_RG" --yes --no-wait 2>/dev/null
        echo "    Deletion initiated."
    fi
else
    echo -e "  ${GREEN}None found${NC}"
fi

# Also check for orphaned public IPs in the main resource group
if [ "$RG_EXISTS" = "true" ]; then
    PUB_IPS=$(az network public-ip list --resource-group "$RESOURCE_GROUP" \
        --query "[].{Name:name,IP:ipAddress}" -o tsv 2>/dev/null || echo "")
    if [ -n "$PUB_IPS" ]; then
        echo -e "  ${YELLOW}Orphaned Public IPs in $RESOURCE_GROUP:${NC}"
        echo "  $PUB_IPS"
        FOUND_RESOURCES=true
    fi
fi

# ── Summary ─────────────────────────────────
echo ""
echo "=============================================="
if [ "$FOUND_RESOURCES" = true ]; then
    echo -e "  ${RED}ORPHANED RESOURCES DETECTED${NC}"
    echo ""
    echo "  Run with --delete to clean up:"
    echo "    ./scripts/verify-cleanup-azure.sh --delete"
    echo ""
    echo "  Or check Azure Cost Management:"
    echo "    https://portal.azure.com/#view/Microsoft_Azure_CostManagement"
    echo ""
    echo "  Nuclear option (deletes EVERYTHING in the resource group):"
    echo "    az group delete --name $RESOURCE_GROUP --yes"
else
    echo -e "  ${GREEN}ALL CLEAR — No orphaned Azure resources found${NC}"
fi
echo "=============================================="
