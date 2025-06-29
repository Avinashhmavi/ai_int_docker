# Production Deployment Guide for Camera Functionality

## Overview
This guide addresses the camera functionality issues in production deployment, including HTTPS requirements, security headers, and browser permissions.

## Key Issues and Solutions

### 1. HTTPS Requirement
**Problem**: Modern browsers require HTTPS for camera access (except on localhost)

**Solution**: 
- Deploy your application over HTTPS
- Use a reverse proxy (nginx/Apache) with SSL certificates
- For development: Use localhost or ngrok for HTTPS tunneling

### 2. Security Headers Configuration
**Problem**: Production servers need proper security headers for WebRTC

**Solution**: The application now includes:
- Content Security Policy (CSP) headers
- Cross-Origin Resource Sharing (CORS) configuration
- Permissions Policy for camera/microphone access
- Cross-Origin Embedder Policy (COEP) and Cross-Origin Opener Policy (COOP)

### 3. Browser Security Policies
**Problem**: Production domains have stricter security policies

**Solution**: 
- Added proper CSP headers in the Flask application
- Configured CORS for cross-origin requests
- Set appropriate permissions policies

## Deployment Options

### Option 1: Docker with Nginx Reverse Proxy (Recommended)

#### 1. Create nginx.conf
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/your/certificate.crt;
    ssl_certificate_key /path/to/your/private.key;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        proxy_pass http://localhost:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebRTC support
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

#### 2. Updated docker-compose.yml
```yaml
version: '3.8'

services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - ai-interviewer
    restart: unless-stopped

  ai-interviewer:
    build: .
    expose:
      - "5001"
    environment:
      - FLASK_APP=main.py
      - FLASK_ENV=production
      - PYTHONUNBUFFERED=1
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./uploads:/app/uploads
    restart: unless-stopped
```

### Option 2: Direct HTTPS with Gunicorn

#### 1. Update requirements.txt
```
flask
flask-cors
gunicorn
pdfplumber
python-docx
python-dotenv
openai
docx2txt
SpeechRecognition 
PyAudio
opencv-python
Pillow
opencv-contrib-python
aiohttp
```

#### 2. Create gunicorn.conf.py
```python
bind = "0.0.0.0:5001"
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 2
max_requests = 1000
max_requests_jitter = 100
preload_app = True
```

#### 3. Update Dockerfile
```dockerfile
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create uploads directory
RUN mkdir -p uploads/snapshots

# Expose port
EXPOSE 5001

# Set environment variables
ENV FLASK_APP=main.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Run with Gunicorn for production
CMD ["gunicorn", "--config", "gunicorn.conf.py", "main:app"]
```

### Option 3: Cloud Deployment (AWS/GCP/Azure)

#### AWS Example with ALB
1. Deploy to EC2 with HTTPS ALB
2. Configure security groups for port 443
3. Use AWS Certificate Manager for SSL
4. Set up proper health checks

#### GCP Example with Cloud Run
1. Deploy to Cloud Run with HTTPS
2. Configure environment variables
3. Set up proper IAM permissions

## Testing Camera Functionality

### 1. Local Testing
```bash
# Test with HTTPS using ngrok
ngrok http 5001

# Access via https://your-ngrok-url.ngrok.io
```

### 2. Production Testing Checklist
- [ ] HTTPS is enabled and working
- [ ] SSL certificate is valid
- [ ] Security headers are present
- [ ] Camera permissions are granted
- [ ] No mixed content warnings
- [ ] WebRTC is supported in browser

### 3. Browser Compatibility
- Chrome 53+ (Recommended)
- Firefox 36+
- Safari 11+
- Edge 79+

## Troubleshooting

### Common Issues

#### 1. "Camera access requires HTTPS"
**Solution**: Ensure your domain uses HTTPS or test on localhost

#### 2. "Camera access denied"
**Solution**: 
- Check browser permissions
- Clear site data and retry
- Ensure no other applications are using the camera

#### 3. "Camera not found"
**Solution**:
- Check hardware connections
- Verify camera drivers
- Try different camera constraints

#### 4. "Security headers blocking camera"
**Solution**: Verify CSP headers allow camera access

### Debug Steps
1. Check browser console for errors
2. Verify HTTPS certificate validity
3. Test camera access in browser settings
4. Check network tab for failed requests
5. Verify security headers in response

## Security Considerations

### 1. HTTPS Only
- Always use HTTPS in production
- Redirect HTTP to HTTPS
- Use valid SSL certificates

### 2. Content Security Policy
- Configure CSP to allow camera access
- Restrict script sources
- Enable strict CSP in production

### 3. Permissions
- Request minimal permissions
- Handle permission denials gracefully
- Provide clear user feedback

### 4. Data Privacy
- Process camera data securely
- Don't store video streams unnecessarily
- Implement proper data retention policies

## Performance Optimization

### 1. Video Constraints
- Use appropriate resolution (720p recommended)
- Set reasonable frame rates (15-30 fps)
- Optimize for network conditions

### 2. Frame Analysis
- Implement proper intervals (5 seconds)
- Use efficient image compression
- Handle network failures gracefully

### 3. Memory Management
- Clean up video streams properly
- Release camera resources
- Monitor memory usage

## Monitoring and Logging

### 1. Application Logs
- Monitor camera initialization
- Track permission requests
- Log error conditions

### 2. Performance Metrics
- Camera initialization time
- Frame analysis success rate
- Network request performance

### 3. User Experience
- Track camera permission grants/denials
- Monitor error rates
- Collect user feedback

## Support

For additional support:
1. Check browser compatibility
2. Verify HTTPS configuration
3. Test with different browsers
4. Review security headers
5. Check network connectivity 