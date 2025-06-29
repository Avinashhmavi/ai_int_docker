#!/bin/bash

# Production Deployment Script for AI Interviewer with Camera Support
# This script sets up HTTPS and ensures camera functionality works in production

set -e  # Exit on any error

echo "🚀 AI Interviewer Production Deployment"
echo "======================================"

# Check if running as root (needed for port 80/443)
if [[ $EUID -eq 0 ]]; then
   echo "⚠️  Running as root - this is required for HTTPS ports"
else
   echo "❌ This script needs to be run as root for HTTPS setup"
   echo "   Please run: sudo ./deploy-production.sh"
   exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✅ Docker and Docker Compose are available"

# Create SSL directory
echo "📁 Creating SSL directory..."
mkdir -p ssl

# Check for existing SSL certificates
if [ -f "ssl/certificate.crt" ] && [ -f "ssl/private.key" ]; then
    echo "✅ SSL certificates found"
else
    echo "⚠️  SSL certificates not found"
    echo "   You have two options:"
    echo "   1. Place your SSL certificates in the ssl/ directory:"
    echo "      - ssl/certificate.crt"
    echo "      - ssl/private.key"
    echo "   2. Use Let's Encrypt (recommended for production)"
    echo ""
    read -p "Do you want to continue with self-signed certificates for testing? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔐 Generating self-signed SSL certificate..."
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout ssl/private.key \
            -out ssl/certificate.crt \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
        echo "✅ Self-signed certificate generated"
    else
        echo "❌ Please add SSL certificates to ssl/ directory and run again"
        exit 1
    fi
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found"
    read -p "Do you want to create a .env file? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Please enter your OpenAI API key:"
        read -s OPENAI_API_KEY
        echo "OPENAI_API_KEY=\"$OPENAI_API_KEY\"" > .env
        echo "✅ .env file created"
    else
        echo "❌ .env file is required for OpenAI functionality"
        exit 1
    fi
else
    echo "✅ .env file found"
fi

# Set proper permissions for SSL files
chmod 600 ssl/private.key
chmod 644 ssl/certificate.crt

echo "🔧 Building and starting services..."

# Stop any existing containers
docker-compose down 2>/dev/null || true

# Build and start services
docker-compose up --build -d

echo "⏳ Waiting for services to start..."
sleep 10

# Check if services are running
if docker-compose ps | grep -q "Up"; then
    echo "✅ Services are running"
else
    echo "❌ Services failed to start"
    docker-compose logs
    exit 1
fi

# Test the application
echo "🧪 Testing application..."

# Wait a bit more for full startup
sleep 5

# Test health endpoint
if curl -f -s http://localhost/health > /dev/null; then
    echo "✅ Health check passed"
else
    echo "⚠️  Health check failed (this might be normal if using HTTPS)"
fi

# Test HTTPS redirect
if curl -f -s -I http://localhost | grep -q "301"; then
    echo "✅ HTTPS redirect working"
else
    echo "⚠️  HTTPS redirect not working (check nginx logs)"
fi

echo ""
echo "🎉 Deployment completed!"
echo ""
echo "📋 Next steps:"
echo "   1. Access your application:"
echo "      - HTTP:  http://localhost (will redirect to HTTPS)"
echo "      - HTTPS: https://localhost"
echo ""
echo "   2. Test camera functionality:"
echo "      - Visit: https://localhost/test-camera"
echo "      - This will help diagnose any camera issues"
echo ""
echo "   3. For production use:"
echo "      - Replace self-signed certificates with real ones"
echo "      - Update nginx.conf with your domain name"
echo "      - Configure your domain's DNS to point to this server"
echo ""
echo "🔍 Troubleshooting:"
echo "   - View logs: docker-compose logs"
echo "   - Restart services: docker-compose restart"
echo "   - Stop services: docker-compose down"
echo ""
echo "📚 For more information, see PRODUCTION_DEPLOYMENT.md" 