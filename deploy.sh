#!/bin/bash

# AI Interviewer Docker Deployment Script
# This script sets up the complete Docker environment with SSL certificates

set -e

echo "🚀 Starting AI Interviewer Docker Deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if required files exist
if [ ! -f "main.py" ]; then
    print_error "main.py not found. Please run this script from the project root directory."
    exit 1
fi

if [ ! -f "index.html" ]; then
    print_error "index.html not found. Please run this script from the project root directory."
    exit 1
fi

# Create necessary directories
print_status "Creating necessary directories..."
mkdir -p uploads/snapshots
mkdir -p logs
mkdir -p ssl
mkdir -p static

# Copy static files
print_status "Setting up static files..."
cp -r static/* static/ 2>/dev/null || true
cp index.html static/ 2>/dev/null || true

# Check for OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    if [ -f ".env" ]; then
        print_status "Loading OpenAI API key from .env file..."
        export $(cat .env | grep -v '^#' | xargs)
    else
        print_warning "OPENAI_API_KEY not found in environment or .env file."
        print_status "Please set your OpenAI API key:"
        read -p "Enter your OpenAI API key: " OPENAI_API_KEY
        export OPENAI_API_KEY
    fi
fi

if [ -z "$OPENAI_API_KEY" ]; then
    print_error "OpenAI API key is required. Please set OPENAI_API_KEY environment variable or create a .env file."
    exit 1
fi

# Generate self-signed SSL certificates for development
print_status "Generating SSL certificates..."
if [ ! -f "ssl/cert.pem" ] || [ ! -f "ssl/key.pem" ]; then
    print_status "Creating self-signed SSL certificates..."
    openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem -days 365 -nodes -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
    print_success "SSL certificates generated successfully."
else
    print_status "SSL certificates already exist."
fi

# Set proper permissions
chmod 600 ssl/key.pem
chmod 644 ssl/cert.pem

# Build and start the application
print_status "Building Docker images..."
docker-compose build

print_status "Starting services..."
docker-compose up -d

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 10

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    print_success "Services are running!"
else
    print_error "Services failed to start. Check logs with: docker-compose logs"
    exit 1
fi

# Test the application
print_status "Testing application health..."
for i in {1..30}; do
    if curl -f -k https://localhost/health &>/dev/null; then
        print_success "Application is healthy and responding!"
        break
    fi
    if [ $i -eq 30 ]; then
        print_error "Application health check failed after 30 attempts."
        print_status "Check logs with: docker-compose logs"
        exit 1
    fi
    sleep 2
done

# Display access information
echo ""
print_success "🎉 AI Interviewer deployed successfully!"
echo ""
echo -e "${GREEN}Access URLs:${NC}"
echo -e "  HTTPS: ${GREEN}https://localhost${NC}"
echo -e "  HTTP:  ${GREEN}http://localhost${NC} (redirects to HTTPS)"
echo ""
echo -e "${GREEN}Management Commands:${NC}"
echo -e "  View logs:     ${YELLOW}docker-compose logs -f${NC}"
echo -e "  Stop services: ${YELLOW}docker-compose down${NC}"
echo -e "  Restart:       ${YELLOW}docker-compose restart${NC}"
echo -e "  Update:        ${YELLOW}docker-compose pull && docker-compose up -d${NC}"
echo ""
echo -e "${GREEN}Important Notes:${NC}"
echo -e "  • The application uses self-signed SSL certificates for development"
echo -e "  • For production, replace ssl/cert.pem and ssl/key.pem with real certificates"
echo -e "  • Camera access requires HTTPS (already configured)"
echo -e "  • OpenAI API key is configured and ready to use"
echo -e "  • Uploads are stored in ./uploads directory"
echo -e "  • Logs are stored in ./logs directory"
echo ""

# Check if OpenAI is working
print_status "Testing OpenAI integration..."
if curl -f -k https://localhost/health | grep -q '"openai_client": true'; then
    print_success "OpenAI integration is working correctly!"
else
    print_warning "OpenAI integration may not be working. Check the logs for details."
fi

print_success "Deployment complete! 🚀" 