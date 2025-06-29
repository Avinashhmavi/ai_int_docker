#!/bin/bash

# AI Interviewer Docker Test Script
# This script tests the Docker setup and OpenAI integration

set -e

echo "🧪 Testing AI Interviewer Docker Setup..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[TEST]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    print_status "Running: $test_name"
    
    if eval "$test_command" >/dev/null 2>&1; then
        print_success "$test_name"
        ((TESTS_PASSED++))
    else
        print_error "$test_name"
        ((TESTS_FAILED++))
    fi
}

# Test 1: Check if Docker is running
run_test "Docker daemon is running" "docker info >/dev/null 2>&1"

# Test 2: Check if Docker Compose is available
run_test "Docker Compose is available" "docker-compose --version >/dev/null 2>&1"

# Test 3: Check if required files exist
run_test "Dockerfile exists" "[ -f Dockerfile ]"
run_test "docker-compose.yml exists" "[ -f docker-compose.yml ]"
run_test "requirements.txt exists" "[ -f requirements.txt ]"
run_test "main.py exists" "[ -f main.py ]"
run_test "index.html exists" "[ -f index.html ]"

# Test 4: Check if containers are running
if docker-compose ps | grep -q "Up"; then
    print_success "Containers are running"
    ((TESTS_PASSED++))
else
    print_warning "Containers are not running. Starting them..."
    docker-compose up -d
    sleep 10
    if docker-compose ps | grep -q "Up"; then
        print_success "Containers started successfully"
        ((TESTS_PASSED++))
    else
        print_error "Failed to start containers"
        ((TESTS_FAILED++))
    fi
fi

# Test 5: Check if application is responding
run_test "Application health endpoint" "curl -f -k https://localhost/health >/dev/null 2>&1"

# Test 6: Check OpenAI integration
if curl -f -k https://localhost/health 2>/dev/null | grep -q '"openai_client": true'; then
    print_success "OpenAI integration is working"
    ((TESTS_PASSED++))
else
    print_error "OpenAI integration is not working"
    ((TESTS_FAILED++))
fi

# Test 7: Check SSL certificates
if [ -f "ssl/cert.pem" ] && [ -f "ssl/key.pem" ]; then
    print_success "SSL certificates exist"
    ((TESTS_PASSED++))
else
    print_error "SSL certificates missing"
    ((TESTS_FAILED++))
fi

# Test 8: Check if HTTPS is working
run_test "HTTPS is accessible" "curl -f -k https://localhost >/dev/null 2>&1"

# Test 9: Check if HTTP redirects to HTTPS
if curl -I http://localhost 2>/dev/null | grep -q "301"; then
    print_success "HTTP redirects to HTTPS"
    ((TESTS_PASSED++))
else
    print_error "HTTP does not redirect to HTTPS"
    ((TESTS_FAILED++))
fi

# Test 10: Check container logs for errors
if docker-compose logs interview-app 2>&1 | grep -q "ERROR"; then
    print_warning "Found errors in application logs"
    ((TESTS_FAILED++))
else
    print_success "No errors found in application logs"
    ((TESTS_PASSED++))
fi

# Test 11: Check if required directories exist
run_test "Uploads directory exists" "[ -d uploads ]"
run_test "Logs directory exists" "[ -d logs ]"
run_test "SSL directory exists" "[ -d ssl ]"

# Test 12: Check file permissions
if [ -r "ssl/cert.pem" ] && [ -r "ssl/key.pem" ]; then
    print_success "SSL certificates are readable"
    ((TESTS_PASSED++))
else
    print_error "SSL certificates are not readable"
    ((TESTS_FAILED++))
fi

# Test 13: Check if nginx is working
if curl -f -k https://localhost/health 2>/dev/null | grep -q "healthy"; then
    print_success "Nginx is working correctly"
    ((TESTS_PASSED++))
else
    print_error "Nginx is not working correctly"
    ((TESTS_FAILED++))
fi

# Test 14: Check environment variables
if docker-compose exec -T interview-app env | grep -q "OPENAI_API_KEY"; then
    print_success "OpenAI API key is set in container"
    ((TESTS_PASSED++))
else
    print_error "OpenAI API key is not set in container"
    ((TESTS_FAILED++))
fi

# Test 15: Check if Python dependencies are installed
if docker-compose exec -T interview-app python -c "import openai, flask, cv2" 2>/dev/null; then
    print_success "Python dependencies are installed"
    ((TESTS_PASSED++))
else
    print_error "Python dependencies are missing"
    ((TESTS_FAILED++))
fi

# Display test results
echo ""
echo "=========================================="
echo "🧪 Test Results Summary"
echo "=========================================="
echo -e "${GREEN}Tests Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Tests Failed: $TESTS_FAILED${NC}"
echo "=========================================="

if [ $TESTS_FAILED -eq 0 ]; then
    echo ""
    print_success "🎉 All tests passed! Your Docker setup is working correctly."
    echo ""
    echo -e "${GREEN}Access your application at:${NC}"
    echo -e "  ${GREEN}https://localhost${NC}"
    echo ""
    echo -e "${GREEN}Useful commands:${NC}"
    echo -e "  View logs:     ${YELLOW}docker-compose logs -f${NC}"
    echo -e "  Stop services: ${YELLOW}docker-compose down${NC}"
    echo -e "  Restart:       ${YELLOW}docker-compose restart${NC}"
else
    echo ""
    print_error "❌ Some tests failed. Please check the issues above."
    echo ""
    echo -e "${YELLOW}Debugging tips:${NC}"
    echo -e "  1. Check logs: ${YELLOW}docker-compose logs -f${NC}"
    echo -e "  2. Check status: ${YELLOW}docker-compose ps${NC}"
    echo -e "  3. Rebuild: ${YELLOW}docker-compose down && docker-compose up -d --build${NC}"
    echo -e "  4. Check health: ${YELLOW}curl -k https://localhost/health${NC}"
fi

echo "" 