#!/bin/bash

###############################################################################
# Test Each Application - Individual Verification Script
# 
# Purpose: Test and verify status of each application one by one
# Usage: ./test-each-application.sh [app-name]
#        ./test-each-application.sh              # Test all apps
#        ./test-each-application.sh mi.dev.mareana.com  # Test specific app
###############################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REGION="us-east-1"
CLUSTER_NAME="mi-eks-cluster"
TABLE_NAME="eks-app-controller-registry"
API_URL="https://6ic7xnfjga.execute-api.us-east-1.amazonaws.com"

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

###############################################################################
# Helper Functions
###############################################################################

print_header() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${BLUE}$1${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

print_section() {
    echo ""
    echo -e "${YELLOW}▶ $1${NC}"
    echo "────────────────────────────────────────────────────────────────"
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
}

print_info() {
    echo -e "   $1"
}

###############################################################################
# Test Functions
###############################################################################

test_dynamodb_status() {
    local APP_NAME=$1
    print_section "TEST 1: DynamoDB Registry Check"
    
    # Get app data from DynamoDB
    APP_DATA=$(aws dynamodb get-item \
        --table-name "$TABLE_NAME" \
        --key "{\"app_name\": {\"S\": \"$APP_NAME\"}}" \
        --region "$REGION" 2>/dev/null)
    
    if [ -z "$APP_DATA" ] || [ "$APP_DATA" == "null" ]; then
        print_failure "Application not found in DynamoDB"
        return 1
    fi
    
    # Extract status
    STATUS=$(echo "$APP_DATA" | jq -r '.Item.status.S // "UNKNOWN"')
    LAST_CHECK=$(echo "$APP_DATA" | jq -r '.Item.last_health_check.S // "NEVER"')
    
    print_info "Status in DynamoDB: $STATUS"
    print_info "Last health check: $(date -r $LAST_CHECK 2>/dev/null || echo $LAST_CHECK)"
    
    if [ "$STATUS" == "UP" ] || [ "$STATUS" == "DOWN" ] || [ "$STATUS" == "DEGRADED" ]; then
        print_success "Valid status in DynamoDB: $STATUS"
        return 0
    else
        print_failure "Invalid status in DynamoDB: $STATUS"
        return 1
    fi
}

test_kubernetes_pods() {
    local APP_NAME=$1
    print_section "TEST 2: Kubernetes Pods Check"
    
    # Try to determine namespace from app name
    NAMESPACE=$(echo "$APP_NAME" | cut -d'.' -f1)
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        print_warning "Namespace '$NAMESPACE' not found"
        print_info "This app might not have a dedicated namespace"
        return 0
    fi
    
    # Get pods in namespace
    PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    RUNNING_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    
    print_info "Total pods: $PODS"
    print_info "Running pods: $RUNNING_PODS"
    
    if [ "$RUNNING_PODS" -gt 0 ]; then
        # Show first few pods
        kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | head -3 | while read line; do
            print_info "  → $line"
        done
        print_success "Kubernetes pods are running ($RUNNING_PODS pods)"
        return 0
    else
        print_warning "No running pods found"
        return 0
    fi
}

test_kubernetes_services() {
    local APP_NAME=$1
    print_section "TEST 3: Kubernetes Services Check"
    
    NAMESPACE=$(echo "$APP_NAME" | cut -d'.' -f1)
    
    if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
        print_warning "Namespace not found, skipping service check"
        return 0
    fi
    
    # Get services
    SERVICES=$(kubectl get svc -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l)
    
    if [ "$SERVICES" -gt 0 ]; then
        print_info "Services found: $SERVICES"
        kubectl get svc -n "$NAMESPACE" --no-headers 2>/dev/null | while read line; do
            print_info "  → $line"
        done
        print_success "Kubernetes services configured"
        return 0
    else
        print_warning "No services found"
        return 0
    fi
}

test_kubernetes_ingress() {
    local APP_NAME=$1
    print_section "TEST 4: Kubernetes Ingress Check"
    
    # Search for ingress across all namespaces that match this app
    INGRESS_DATA=$(kubectl get ingress --all-namespaces -o json 2>/dev/null | \
        jq -r ".items[] | select(.spec.rules[]?.host == \"$APP_NAME\") | 
        .metadata.namespace + \" \" + .metadata.name + \" \" + 
        (.spec.rules[0].host // \"N/A\")" 2>/dev/null)
    
    if [ -n "$INGRESS_DATA" ]; then
        print_info "Ingress found:"
        echo "$INGRESS_DATA" | while read ns name host; do
            print_info "  Namespace: $ns"
            print_info "  Name: $name"
            print_info "  Host: $host"
        done
        print_success "Ingress configured for $APP_NAME"
        return 0
    else
        print_warning "No ingress found for $APP_NAME"
        return 0
    fi
}

test_ingress_accessibility() {
    local APP_NAME=$1
    print_section "TEST 5: Ingress HTTP Accessibility"
    
    print_info "Testing: https://$APP_NAME"
    
    # Try to access the ingress endpoint
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$APP_NAME" 2>/dev/null || echo "000")
    
    print_info "HTTP Response Code: $HTTP_CODE"
    
    if [ "$HTTP_CODE" == "200" ] || [ "$HTTP_CODE" == "302" ] || [ "$HTTP_CODE" == "301" ]; then
        print_success "Application is accessible (HTTP $HTTP_CODE)"
        return 0
    elif [ "$HTTP_CODE" == "000" ]; then
        print_failure "Connection timeout or refused"
        return 1
    else
        print_warning "HTTP $HTTP_CODE (may be expected for some apps)"
        return 0
    fi
}

test_nodegroups() {
    local APP_NAME=$1
    print_section "TEST 6: NodeGroup Status Check"
    
    # Get NodeGroup info from DynamoDB
    NODEGROUPS=$(aws dynamodb get-item \
        --table-name "$TABLE_NAME" \
        --key "{\"app_name\": {\"S\": \"$APP_NAME\"}}" \
        --region "$REGION" \
        --query 'Item.nodegroups.L[].M.{name:name.S,desired:desired_size.N}' \
        --output json 2>/dev/null)
    
    if [ "$NODEGROUPS" == "[]" ] || [ -z "$NODEGROUPS" ] || [ "$NODEGROUPS" == "null" ]; then
        print_warning "No NodeGroups associated with this app"
        print_info "This app may share NodeGroups or be Ingress-only"
        return 0
    fi
    
    # Check each NodeGroup
    echo "$NODEGROUPS" | jq -r '.[] | .name + " " + .desired' | while read NG_NAME DESIRED; do
        print_info "NodeGroup: $NG_NAME"
        
        # Get actual NodeGroup status
        ACTUAL_DESIRED=$(aws eks describe-nodegroup \
            --cluster-name "$CLUSTER_NAME" \
            --nodegroup-name "$NG_NAME" \
            --region "$REGION" \
            --query 'nodegroup.scalingConfig.desiredSize' \
            --output text 2>/dev/null || echo "ERROR")
        
        if [ "$ACTUAL_DESIRED" == "ERROR" ]; then
            print_failure "Failed to query NodeGroup $NG_NAME"
            return 1
        fi
        
        print_info "  Desired size: $ACTUAL_DESIRED"
        
        if [ "$ACTUAL_DESIRED" -gt 0 ]; then
            print_success "NodeGroup is scaled UP (desired=$ACTUAL_DESIRED)"
        else
            print_warning "NodeGroup is scaled DOWN (desired=$ACTUAL_DESIRED)"
        fi
    done
    
    return 0
}

test_databases() {
    local APP_NAME=$1
    print_section "TEST 7: Database Status Check"
    
    # Get database info from DynamoDB
    DB_DATA=$(aws dynamodb get-item \
        --table-name "$TABLE_NAME" \
        --key "{\"app_name\": {\"S\": \"$APP_NAME\"}}" \
        --region "$REGION" \
        --query 'Item.{postgres:postgres_instances.L[].S,neo4j:neo4j_instances.L[].S}' \
        --output json 2>/dev/null)
    
    POSTGRES_IDS=$(echo "$DB_DATA" | jq -r '.postgres[]? // empty')
    NEO4J_IDS=$(echo "$DB_DATA" | jq -r '.neo4j[]? // empty')
    
    if [ -z "$POSTGRES_IDS" ] && [ -z "$NEO4J_IDS" ]; then
        print_warning "No databases associated with this app"
        return 0
    fi
    
    # Check PostgreSQL instances
    if [ -n "$POSTGRES_IDS" ]; then
        print_info "PostgreSQL instances:"
        echo "$POSTGRES_IDS" | while read INSTANCE_ID; do
            STATE=$(aws ec2 describe-instances \
                --instance-ids "$INSTANCE_ID" \
                --region "$REGION" \
                --query 'Reservations[0].Instances[0].State.Name' \
                --output text 2>/dev/null || echo "ERROR")
            
            SHARED=$(aws ec2 describe-instances \
                --instance-ids "$INSTANCE_ID" \
                --region "$REGION" \
                --query 'Reservations[0].Instances[0].Tags[?Key==`Shared`].Value | [0]' \
                --output text 2>/dev/null || echo "false")
            
            print_info "  $INSTANCE_ID: $STATE (Shared: $SHARED)"
            
            if [ "$STATE" == "running" ]; then
                print_success "PostgreSQL instance is running"
            else
                print_warning "PostgreSQL instance is $STATE"
            fi
        done
    fi
    
    # Check Neo4j instances
    if [ -n "$NEO4J_IDS" ]; then
        print_info "Neo4j instances:"
        echo "$NEO4J_IDS" | while read INSTANCE_ID; do
            STATE=$(aws ec2 describe-instances \
                --instance-ids "$INSTANCE_ID" \
                --region "$REGION" \
                --query 'Reservations[0].Instances[0].State.Name' \
                --output text 2>/dev/null || echo "ERROR")
            
            SHARED=$(aws ec2 describe-instances \
                --instance-ids "$INSTANCE_ID" \
                --region "$REGION" \
                --query 'Reservations[0].Instances[0].Tags[?Key==`Shared`].Value | [0]' \
                --output text 2>/dev/null || echo "false")
            
            print_info "  $INSTANCE_ID: $STATE (Shared: $SHARED)"
            
            if [ "$STATE" == "running" ]; then
                print_success "Neo4j instance is running"
            else
                print_warning "Neo4j instance is $STATE"
            fi
        done
    fi
    
    return 0
}

test_api_endpoint() {
    local APP_NAME=$1
    print_section "TEST 8: API Gateway Endpoint Check"
    
    print_info "Testing: $API_URL/apps/$APP_NAME"
    
    # Query API Gateway
    API_RESPONSE=$(curl -s "$API_URL/apps/$APP_NAME" 2>/dev/null)
    
    if [ -n "$API_RESPONSE" ] && [ "$API_RESPONSE" != "null" ]; then
        API_STATUS=$(echo "$API_RESPONSE" | jq -r '.status // "UNKNOWN"')
        print_info "API Status: $API_STATUS"
        print_success "API endpoint responding"
        return 0
    else
        print_failure "API endpoint not responding or app not found"
        return 1
    fi
}

test_status_consistency() {
    local APP_NAME=$1
    print_section "TEST 9: Status Consistency Verification"
    
    # Get DynamoDB status
    DB_STATUS=$(aws dynamodb get-item \
        --table-name "$TABLE_NAME" \
        --key "{\"app_name\": {\"S\": \"$APP_NAME\"}}" \
        --region "$REGION" \
        --query 'Item.status.S' \
        --output text 2>/dev/null)
    
    # Get Kubernetes status (simplified check)
    NAMESPACE=$(echo "$APP_NAME" | cut -d'.' -f1)
    K8S_PODS=0
    if kubectl get namespace "$NAMESPACE" &>/dev/null; then
        K8S_PODS=$(kubectl get pods -n "$NAMESPACE" --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
    fi
    
    # Get Ingress status
    INGRESS_EXISTS=$(kubectl get ingress --all-namespaces -o json 2>/dev/null | \
        jq -r ".items[] | select(.spec.rules[]?.host == \"$APP_NAME\") | .metadata.name" 2>/dev/null | wc -l)
    
    print_info "DynamoDB Status: $DB_STATUS"
    print_info "Kubernetes Pods: $K8S_PODS running"
    print_info "Ingress Exists: $([ "$INGRESS_EXISTS" -gt 0 ] && echo 'Yes' || echo 'No')"
    
    # Determine expected status
    if [ "$K8S_PODS" -gt 0 ] || [ "$INGRESS_EXISTS" -gt 0 ]; then
        EXPECTED="UP"
    else
        EXPECTED="DOWN"
    fi
    
    print_info "Expected Status: $EXPECTED"
    
    if [ "$DB_STATUS" == "$EXPECTED" ]; then
        print_success "Status is CONSISTENT: $DB_STATUS = $EXPECTED"
        return 0
    else
        print_failure "Status MISMATCH: DynamoDB=$DB_STATUS, Expected=$EXPECTED"
        return 1
    fi
}

###############################################################################
# Main Test Function
###############################################################################

test_application() {
    local APP_NAME=$1
    
    print_header "Testing Application: $APP_NAME"
    
    # Reset counters for this app
    APP_TESTS=0
    APP_PASSED=0
    APP_FAILED=0
    
    # Run all tests
    test_dynamodb_status "$APP_NAME"
    test_kubernetes_pods "$APP_NAME"
    test_kubernetes_services "$APP_NAME"
    test_kubernetes_ingress "$APP_NAME"
    test_ingress_accessibility "$APP_NAME"
    test_nodegroups "$APP_NAME"
    test_databases "$APP_NAME"
    test_api_endpoint "$APP_NAME"
    test_status_consistency "$APP_NAME"
    
    # Summary for this app
    echo ""
    echo "────────────────────────────────────────────────────────────────"
    echo -e "${BLUE}Summary for $APP_NAME:${NC}"
    echo "  Total tests: $TOTAL_TESTS"
    echo -e "  ${GREEN}Passed: $PASSED_TESTS${NC}"
    if [ $FAILED_TESTS -gt 0 ]; then
        echo -e "  ${RED}Failed: $FAILED_TESTS${NC}"
    fi
    echo "────────────────────────────────────────────────────────────────"
}

###############################################################################
# Main Script
###############################################################################

main() {
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  Individual Application Testing                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "Region: $REGION"
    echo "Cluster: $CLUSTER_NAME"
    echo "Table: $TABLE_NAME"
    echo ""
    
    # Check if specific app provided
    if [ -n "$1" ]; then
        test_application "$1"
    else
        # Get all apps from DynamoDB
        echo "Fetching all applications from DynamoDB..."
        APPS=$(aws dynamodb scan \
            --table-name "$TABLE_NAME" \
            --region "$REGION" \
            --projection-expression "app_name" \
            --output json | jq -r '.Items[].app_name.S' | sort)
        
        APP_COUNT=$(echo "$APPS" | wc -l)
        echo "Found $APP_COUNT applications"
        echo ""
        
        # Test each app
        CURRENT=0
        echo "$APPS" | while read APP; do
            ((CURRENT++))
            echo ""
            echo "═══════════════════════════════════════════════════════════════"
            echo "Application $CURRENT of $APP_COUNT"
            echo "═══════════════════════════════════════════════════════════════"
            test_application "$APP"
            
            # Pause between apps
            if [ $CURRENT -lt $APP_COUNT ]; then
                echo ""
                echo "Press Enter to continue to next app (or Ctrl+C to stop)..."
                read -t 5 || true
            fi
        done
    fi
    
    # Final summary
    print_header "FINAL TEST SUMMARY"
    echo ""
    echo "Total Tests Run: $TOTAL_TESTS"
    echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
    if [ $FAILED_TESTS -gt 0 ]; then
        echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    else
        echo -e "${GREEN}All tests passed! ✅${NC}"
    fi
    echo ""
}

# Run main function
main "$@"


