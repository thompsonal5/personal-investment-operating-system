#!/bin/bash
# init_structure.sh - Fortress Edition PIOS Initialization Script
# Creates all necessary directories and initial configuration files

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== PIOS Fortress Edition Initialization ===${NC}"

# Core directories
DIRS=(
    "data/cache"
    "portfolio"
    "watchlists"
    "reports/daily"
    "reports/weekly"
    "reports/monthly"
    "logs"
    "mcp-servers/robinhood"
    "mcp-servers/trayd"
    "mcp-servers/fiscal"
    "governance-protocol/validators"
    "governance-protocol/models"
    "governance-protocol/tests"
    "tactical-execution/order-handlers"
    "tactical-execution/market-interfaces"
    "tactical-execution/tests"
    "portfolio-management/allocation"
    "portfolio-management/rebalancing"
    "portfolio-management/tests"
    "risk-management/guardrails"
    "risk-management/compliance"
    "risk-management/tests"
    "data-ingestion/providers"
    "data-ingestion/etl"
    "data-ingestion/tests"
    "utils"
    "templates/html"
    "templates/email"
    ".github/workflows"
)

for dir in "${DIRS[@]}"; do
    mkdir -p "$PROJECT_ROOT/$dir"
    echo -e "${GREEN}✓${NC} Created: $dir"
done

# Create .gitkeep files for empty directories
find "$PROJECT_ROOT" -type d -not -path '*/\.*' | while read dir; do
    if [ -z "$(ls -A "$dir")" ]; then
        touch "$dir/.gitkeep"
    fi
done

echo -e "${BLUE}=== Initialization Complete ===${NC}"
echo "Project structure ready for deployment."
