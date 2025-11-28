#!/bin/bash
# Prerequisites verification script

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "Prerequisites Check"
echo "========================================="
echo ""

ERRORS=0

# Check AWS CLI
echo -n "Checking AWS CLI... "
if command -v aws >/dev/null 2>&1; then
    AWS_VERSION=$(aws --version 2>&1 | head -n1)
    echo -e "${GREEN}✓${NC} $AWS_VERSION"
else
    echo -e "${RED}✗ Not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check OpenTofu
echo -n "Checking OpenTofu... "
if command -v tofu >/dev/null 2>&1; then
    TOFU_VERSION=$(tofu version -json 2>/dev/null | grep -o '"terraform_version":"[^"]*' | cut -d'"' -f4 || tofu version | head -n1 | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+')
    if [[ -n "$TOFU_VERSION" ]]; then
        TOFU_MAJOR=$(echo "$TOFU_VERSION" | cut -d'.' -f1)
        if [[ $TOFU_MAJOR -ge 1 ]]; then
            echo -e "${GREEN}✓${NC} v$TOFU_VERSION"
        else
            echo -e "${RED}✗ Version < 1.0 (found v$TOFU_VERSION)${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    else
        echo -e "${GREEN}✓${NC} (installed)"
    fi
else
    echo -e "${YELLOW}⚠ Not found (Terragrunt will download automatically)${NC}"
fi

# Check Terragrunt
echo -n "Checking Terragrunt... "
if command -v terragrunt >/dev/null 2>&1; then
    TG_VERSION=$(terragrunt --version | grep -o '[0-9]\+\.[0-9]\+\.[0-9]\+' | head -n1)
    TG_MAJOR=$(echo "$TG_VERSION" | cut -d'.' -f1)
    TG_MINOR=$(echo "$TG_VERSION" | cut -d'.' -f2)
    if [[ $TG_MAJOR -ge 0 ]] && [[ $TG_MINOR -ge 50 ]]; then
        echo -e "${GREEN}✓${NC} v$TG_VERSION"
    else
        echo -e "${RED}✗ Version < 0.50.0 (found v$TG_VERSION)${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}✗ Not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check Python
echo -n "Checking Python... "
if command -v python3 >/dev/null 2>&1; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d'.' -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d'.' -f2)
    if [[ $PY_MAJOR -ge 3 ]] && [[ $PY_MINOR -ge 11 ]]; then
        echo -e "${GREEN}✓${NC} $PY_VERSION"
    else
        echo -e "${RED}✗ Version < 3.11 (found $PY_VERSION)${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}✗ Not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check Node.js
echo -n "Checking Node.js... "
if command -v node >/dev/null 2>&1; then
    NODE_VERSION=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d'.' -f1)
    if [[ $NODE_MAJOR -ge 18 ]]; then
        echo -e "${GREEN}✓${NC} v$NODE_VERSION"
    else
        echo -e "${RED}✗ Version < 18 (found v$NODE_VERSION)${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "${RED}✗ Not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check npm
echo -n "Checking npm... "
if command -v npm >/dev/null 2>&1; then
    NPM_VERSION=$(npm --version)
    echo -e "${GREEN}✓${NC} v$NPM_VERSION"
else
    echo -e "${RED}✗ Not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check kubectl
echo -n "Checking kubectl... "
if command -v kubectl >/dev/null 2>&1; then
    KUBE_VERSION=$(kubectl version --client --short 2>&1 | head -n1)
    echo -e "${GREEN}✓${NC} $KUBE_VERSION"
else
    echo -e "${RED}✗ Not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "========================================="
echo "AWS Configuration Check"
echo "========================================="
echo ""

# Check AWS credentials
echo -n "Checking AWS credentials... "
if aws sts get-caller-identity >/dev/null 2>&1; then
    AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    AWS_USER=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null)
    echo -e "${GREEN}✓${NC}"
    echo "  Account: $AWS_ACCOUNT"
    echo "  Identity: $AWS_USER"
else
    echo -e "${RED}✗ Not configured${NC}"
    echo "  Run: aws configure"
    ERRORS=$((ERRORS + 1))
fi

# Check EKS access
echo -n "Checking EKS access... "
if aws eks list-clusters >/dev/null 2>&1; then
    CLUSTER_COUNT=$(aws eks list-clusters --query 'clusters | length(@)' --output text 2>/dev/null || echo "0")
    echo -e "${GREEN}✓${NC} ($CLUSTER_COUNT cluster(s) found)"
else
    echo -e "${YELLOW}⚠ Cannot list clusters (may need permissions)${NC}"
fi

# Check EC2 access
echo -n "Checking EC2 access... "
if aws ec2 describe-instances --max-items 1 >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠ Cannot describe instances (may need permissions)${NC}"
fi

echo ""
echo "========================================="
echo "Kubernetes Access Check"
echo "========================================="
echo ""

# Check kubectl cluster access
echo -n "Checking Kubernetes cluster access... "
if kubectl get nodes >/dev/null 2>&1; then
    NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
    echo -e "${GREEN}✓${NC} ($NODE_COUNT node(s) accessible)"
else
    echo -e "${RED}✗ Cannot access cluster${NC}"
    echo "  Run: aws eks update-kubeconfig --name <cluster-name> --region <region>"
    ERRORS=$((ERRORS + 1))
fi

# Check Ingress access
echo -n "Checking Ingress read access... "
if kubectl get ingress -A >/dev/null 2>&1; then
    INGRESS_COUNT=$(kubectl get ingress -A --no-headers 2>/dev/null | wc -l | tr -d ' ')
    echo -e "${GREEN}✓${NC} ($INGRESS_COUNT Ingress resource(s) found)"
else
    echo -e "${YELLOW}⚠ Cannot read Ingress (may need RBAC permissions)${NC}"
fi

echo ""
echo "========================================="
echo "Dependencies Check"
echo "========================================="
echo ""

# Check Python dependencies
echo -n "Checking Python dependencies... "
if python3 -c "import boto3, kubernetes, requests" >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}⚠ Missing dependencies${NC}"
    echo "  Run: pip3 install -r requirements.txt"
fi

# Check Node dependencies (if ui directory exists)
if [ -d "ui" ]; then
    echo -n "Checking Node dependencies... "
    if [ -d "ui/node_modules" ]; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}⚠ Not installed${NC}"
        echo "  Run: cd ui && npm install"
    fi
fi

echo ""
echo "========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ All prerequisites met!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Tag your resources (see docs/TAGGING.md)"
    echo "2. Configure terraform.tfvars"
    echo "3. Run: terraform apply"
    exit 0
else
    echo -e "${RED}❌ Found $ERRORS critical issue(s)${NC}"
    echo ""
    echo "Please fix the issues above before proceeding."
    echo "See docs/PREREQUISITES.md for detailed setup instructions."
    exit 1
fi

