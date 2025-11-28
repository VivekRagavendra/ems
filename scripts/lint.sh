#!/bin/bash
# Comprehensive linting script for the codebase

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

echo "========================================="
echo "Linting Codebase"
echo "========================================="
echo ""

# Check if tools are installed
check_tool() {
    if ! command -v $1 &> /dev/null; then
        echo -e "${YELLOW}⚠ $1 not found. Install with: $2${NC}"
        return 1
    fi
    return 0
}

# Lint Python files
lint_python() {
    echo -e "${BLUE}Linting Python files...${NC}"
    
    # Check for Python linters
    HAS_RUFF=false
    HAS_FLAKE8=false
    HAS_PYLINT=false
    HAS_BLACK=false
    
    if command -v ruff &> /dev/null; then
        HAS_RUFF=true
    fi
    if command -v flake8 &> /dev/null; then
        HAS_FLAKE8=true
    fi
    if command -v pylint &> /dev/null; then
        HAS_PYLINT=true
    fi
    if command -v black &> /dev/null; then
        HAS_BLACK=true
    fi
    
    if [ "$HAS_RUFF" = false ] && [ "$HAS_FLAKE8" = false ] && [ "$HAS_PYLINT" = false ]; then
        echo -e "${YELLOW}⚠ No Python linters found. Install with:${NC}"
        echo "  pip install ruff flake8 pylint black"
        echo ""
        return
    fi
    
    # Find Python files
    PYTHON_FILES=$(find "$PROJECT_ROOT/lambdas" -name "*.py" -type f)
    
    if [ -z "$PYTHON_FILES" ]; then
        echo -e "${YELLOW}No Python files found${NC}"
        return
    fi
    
    # Run ruff (fastest, recommended)
    if [ "$HAS_RUFF" = true ]; then
        echo "Running ruff..."
        if ruff check "$PROJECT_ROOT/lambdas" 2>&1; then
            echo -e "${GREEN}✓ ruff passed${NC}"
        else
            echo -e "${RED}✗ ruff found issues${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    fi
    
    # Run flake8
    if [ "$HAS_FLAKE8" = true ]; then
        echo "Running flake8..."
        if flake8 "$PROJECT_ROOT/lambdas" 2>&1; then
            echo -e "${GREEN}✓ flake8 passed${NC}"
        else
            echo -e "${RED}✗ flake8 found issues${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    fi
    
    # Run black (format check)
    if [ "$HAS_BLACK" = true ]; then
        echo "Checking code formatting with black..."
        if black --check "$PROJECT_ROOT/lambdas" 2>&1; then
            echo -e "${GREEN}✓ black formatting OK${NC}"
        else
            echo -e "${YELLOW}⚠ Code formatting issues found (run: black lambdas/)${NC}"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
    
    echo ""
}

# Lint JavaScript/JSX files
lint_javascript() {
    echo -e "${BLUE}Linting JavaScript/JSX files...${NC}"
    
    if ! command -v eslint &> /dev/null; then
        echo -e "${YELLOW}⚠ ESLint not found. Install with: npm install -g eslint eslint-plugin-react${NC}"
        echo ""
        return
    fi
    
    if [ ! -d "$PROJECT_ROOT/ui" ]; then
        echo -e "${YELLOW}No UI directory found${NC}"
        echo ""
        return
    fi
    
    cd "$PROJECT_ROOT/ui"
    
    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo "Installing dependencies..."
        npm install --silent
    fi
    
    echo "Running ESLint..."
    if npx eslint src/ --ext .js,.jsx 2>&1; then
        echo -e "${GREEN}✓ ESLint passed${NC}"
    else
        echo -e "${RED}✗ ESLint found issues${NC}"
        ERRORS=$((ERRORS + 1))
    fi
    
    cd "$PROJECT_ROOT"
    echo ""
}

# Lint Terraform/OpenTofu files
lint_terraform() {
    echo -e "${BLUE}Linting Terraform/OpenTofu files...${NC}"
    
    if ! command -v tflint &> /dev/null && ! command -v tofu &> /dev/null; then
        echo -e "${YELLOW}⚠ tflint or tofu not found. Skipping Terraform linting${NC}"
        echo ""
        return
    fi
    
    if [ ! -d "$PROJECT_ROOT/infrastructure" ]; then
        echo -e "${YELLOW}No infrastructure directory found${NC}"
        echo ""
        return
    fi
    
    cd "$PROJECT_ROOT/infrastructure"
    
    # Try tofu fmt check
    if command -v tofu &> /dev/null; then
        echo "Checking Terraform formatting..."
        if tofu fmt -check -recursive . 2>&1; then
            echo -e "${GREEN}✓ Terraform formatting OK${NC}"
        else
            echo -e "${YELLOW}⚠ Formatting issues found (run: tofu fmt -recursive .)${NC}"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
    
    # Try tflint
    if command -v tflint &> /dev/null; then
        echo "Running tflint..."
        if tflint --init 2>&1 > /dev/null; then
            if tflint . 2>&1; then
                echo -e "${GREEN}✓ tflint passed${NC}"
            else
                echo -e "${RED}✗ tflint found issues${NC}"
                ERRORS=$((ERRORS + 1))
            fi
        fi
    fi
    
    cd "$PROJECT_ROOT"
    echo ""
}

# Check shell scripts
lint_shell() {
    echo -e "${BLUE}Linting shell scripts...${NC}"
    
    if ! command -v shellcheck &> /dev/null; then
        echo -e "${YELLOW}⚠ shellcheck not found. Install with: brew install shellcheck${NC}"
        echo ""
        return
    fi
    
    SHELL_SCRIPTS=$(find "$PROJECT_ROOT/scripts" -name "*.sh" -type f)
    
    if [ -z "$SHELL_SCRIPTS" ]; then
        echo -e "${YELLOW}No shell scripts found${NC}"
        echo ""
        return
    fi
    
    for script in $SHELL_SCRIPTS; do
        echo "Checking $script..."
        if shellcheck "$script" 2>&1; then
            echo -e "${GREEN}✓ $script OK${NC}"
        else
            echo -e "${RED}✗ $script has issues${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done
    
    echo ""
}

# Main execution
main() {
    lint_python
    lint_javascript
    lint_terraform
    lint_shell
    
    echo "========================================="
    if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
        echo -e "${GREEN}✅ All linting passed!${NC}"
        exit 0
    elif [ $ERRORS -eq 0 ]; then
        echo -e "${YELLOW}⚠ Linting completed with $WARNINGS warning(s)${NC}"
        exit 0
    else
        echo -e "${RED}❌ Linting failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
        exit 1
    fi
}

main


