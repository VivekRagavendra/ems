#!/bin/bash

###############################################################################
# Test All Applications - Batch Mode (No Pauses)
# 
# Purpose: Test all applications automatically without pauses
# Usage: ./test-all-apps-batch.sh
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
REGION="us-east-1"
CLUSTER_NAME="mi-eks-cluster"
TABLE_NAME="eks-app-controller-registry"
API_URL="https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com"

# Counters
TOTAL_APPS=0
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
WARNING_TESTS=0

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}$1${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
    ((PASSED_TESTS++))
    ((TOTAL_TESTS++))
}

print_failure() {
    echo -e "${RED}❌ $1${NC}"
    ((FAILED_TESTS++))
    ((TOTAL_TESTS++))
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    ((WARNING_TESTS++))
}

###############################################################################
# Quick Tests (Essential Only)
###############################################################################

test_app_quick() {
    local APP_NAME=$1
    local APP_NUM=$2
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "Application $APP_NUM of $TOTAL_APPS: $APP_NAME"
    echo "═══════════════════════════════════════════════════════════════"
    
    # Test 1: DynamoDB Status
    DB_STATUS=$(aws dynamodb get-item \
        --table-name "$TABLE_NAME" \
        --key "{\"app_name\": {\"S\": \"$APP_NAME\"}}" \
        --region "$REGION" \
        --query 'Item.status.S' \
        --output text 2>/dev/null || echo "ERROR")
    
    if [ "$DB_STATUS" != "ERROR" ] && [ -n "$DB_STATUS" ]; then
        print_success "DynamoDB Status: $DB_STATUS"
    else
        print_failure "DynamoDB check failed"
    fi
    
    # Test 2: Kubernetes Pods
    NAMESPACE=$(echo "$APP_NAME" | cut -d'.' -f1)
    if kubectl get namespace "$NAMESPACE" &>/dev/null; then
        RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
        if [ "$RUNNING_PODS" -gt 0 ]; then
            print_success "Kubernetes: $RUNNING_PODS pod(s) running"
        else
            print_warning "Kubernetes: No running pods"
        fi
    else
        print_warning "Namespace not found (may be normal)"
    fi
    
    # Test 3: Ingress Check
    INGRESS_EXISTS=$(kubectl get ingress --all-namespaces -o json 2>/dev/null | \
        jq -r ".items[] | select(.spec.rules[]?.host == \"$APP_NAME\") | .metadata.name" 2>/dev/null | wc -l)
    
    if [ "$INGRESS_EXISTS" -gt 0 ]; then
        print_success "Ingress: Configured"
    else
        print_warning "Ingress: Not found"
    fi
    
    # Test 4: HTTP Accessibility
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "https://$APP_NAME" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "302" ] || [ "$HTTP_CODE" == "301" ]; then
        print_success "HTTP: Accessible (HTTP $HTTP_CODE)"
    elif [ "$HTTP_CODE" == "000" ]; then
        print_failure "HTTP: Connection failed"
    else
        print_warning "HTTP: Response $HTTP_CODE"
    fi
    
    # Test 5: Status Consistency
    if [ "$RUNNING_PODS" -gt 0 ] || [ "$INGRESS_EXISTS" -gt 0 ]; then
        EXPECTED="UP"
    else
        EXPECTED="DOWN"
    fi
    
    if [ "$DB_STATUS" == "$EXPECTED" ]; then
        print_success "Status Consistency: PASS"
    else
        print_failure "Status Mismatch: DB=$DB_STATUS, Expected=$EXPECTED"
    fi
    
    echo "────────────────────────────────────────────────────────────────"
}

###############################################################################
# Main
###############################################################################

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  Batch Application Testing (All Apps)                          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Region: $REGION"
echo "Cluster: $CLUSTER_NAME"
echo ""

# Get all apps
echo "Fetching applications from DynamoDB..."
APPS=$(aws dynamodb scan \
    --table-name "$TABLE_NAME" \
    --region "$REGION" \
    --projection-expression "app_name" \
    --output json | jq -r '.Items[].app_name.S' | sort)

TOTAL_APPS=$(echo "$APPS" | wc -l | tr -d ' ')
echo "Found $TOTAL_APPS applications"
echo ""

# Test each app
CURRENT=0
echo "$APPS" | while read APP; do
    ((CURRENT++))
    test_app_quick "$APP" "$CURRENT"
done

# Final Summary
print_header "FINAL TEST SUMMARY"
echo ""
echo "Applications Tested: $TOTAL_APPS"
echo "Total Tests Run: $TOTAL_TESTS"
echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
echo -e "${YELLOW}Warnings: $WARNING_TESTS${NC}"
if [ $FAILED_TESTS -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
else
    echo -e "${GREEN}Failed: 0 ✅${NC}"
fi
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ ALL CRITICAL TESTS PASSED!                                 ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ⚠️  SOME TESTS FAILED - REVIEW RESULTS ABOVE                  ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════════════════════╝${NC}"
    exit 1
fi


