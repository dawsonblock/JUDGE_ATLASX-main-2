#!/bin/bash
set -e

echo "=== JudgeTracker Atlas Infrastructure Prep ==="

# Ensure required tools are available
if ! command -v az &> /dev/null; then
    echo "ERROR: Azure CLI (az) is not installed"
    exit 1
fi

if ! command -v azd &> /dev/null; then
    echo "ERROR: Azure Developer CLI (azd) is not installed"
    echo "Install: curl -fsSL https://aka.ms/install-azd.sh | bash"
    exit 1
fi

# Login check
echo "Checking Azure login..."
az account show &> /dev/null || {
    echo "Not logged in to Azure. Running az login..."
    az login
}

# Check azd login
echo "Checking azd auth..."
azd auth login --check-status &> /dev/null || {
    echo "Not logged in to azd. Running azd auth login..."
    azd auth login
}

echo "=== Prep complete ==="
