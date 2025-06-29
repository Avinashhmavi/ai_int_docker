# AI-Powered Interview Application

An intelligent interview application that uses AI to conduct automated interviews with real-time question generation, answer evaluation, and visual analysis.

## 🚀 Features

- **AI-Powered Question Generation**: Uses OpenAI GPT models to generate contextual interview questions
- **Real-time Answer Evaluation**: Provides instant feedback and scoring for candidate responses
- **Visual Analysis**: Camera-based analysis for professional presentation assessment
- **Multiple Interview Tracks**: Support for MBA and Banking interviews with specialized question banks
- **Conversational AI**: Natural follow-up questions and conversational replies
- **Docker Support**: Easy deployment with Docker and Docker Compose
- **Fallback Mechanisms**: Works without OpenAI API key using comprehensive question banks

## 🛠️ Technology Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML5, CSS3, JavaScript
- **AI**: OpenAI GPT-4, GPT-4 Vision
- **Computer Vision**: OpenCV
- **Database**: SQLite
- **PDF Processing**: pdfplumber, PyPDF2
- **Deployment**: Docker, Gunicorn, Nginx

## 📋 Prerequisites

- Docker and Docker Compose installed
- OpenAI API Key (optional - app works with fallback questions)

## 🚀 Quick Start

### Docker Deployment (Recommended)

1. **Clone the repository**
   ```bash
   git clone https://github.com/Avinashhmavi/ai_int_docker.git
   cd ai_int_docker
   ```

2. **Set up environment variables**
   ```bash
   # Copy the environment template
   cp env.example .env
   
   # Edit .env and add your OpenAI API key (optional but recommended)
   # IMPORTANT: Do NOT add quotes around your API key
   # Correct: OPENAI_API_KEY=sk-your-api-key-here
   # Wrong:   OPENAI_API_KEY="sk-your-api-key-here"
   ```

3. **Run with Docker (Simple Method)**
   ```bash
   # Build and run the application
   docker run -d --name interview-app -p 5001:5001 --env-file .env \
     -v $(pwd)/uploads:/app/uploads \
     -v $(pwd)/logs:/app/logs \
     -v $(pwd)/users.db:/app/users.db \
     $(docker build -q .)
   ```

4. **Access the application**
   - Open http://localhost:5001 in your browser
   - Login with username: `Avinash` and password: `1234`

### Docker Compose Deployment

1. **Using docker-compose (Alternative method)**
   ```bash
   # Start the application
   docker-compose up --build
   
   # Or run in background
   docker-compose up -d --build
   ```

2. **Check application status**
   ```bash
   # Check if container is running
   docker ps
   
   # Check application health
   curl http://localhost:5001/health
   ```

3. **View logs**
   ```bash
   # View application logs
   docker logs interview-app
   
   # Follow logs in real-time
   docker logs -f interview-app
   ```

## 🔧 Configuration

### Environment Variables

Create a `.env` file based on `env.example`:

```env
# OpenAI API Key (required for AI features)
# IMPORTANT: Do NOT add quotes around the API key
OPENAI_API_KEY=sk-your-actual-api-key-here

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=1
```

### OpenAI API Key Setup

The application works without an OpenAI API key using fallback questions, but for full AI functionality:

1. **Get an API key** from [OpenAI Platform](https://platform.openai.com/)
2. **Add to .env file** without quotes:
   ```env
   OPENAI_API_KEY=sk-proj-your-api-key-here
   ```
3. **Restart the container**:
   ```bash
   docker restart interview-app
   ```

## 🐳 Docker Management

### Starting the Application
```bash
# Method 1: Direct Docker run
docker run -d --name interview-app -p 5001:5001 --env-file .env \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/users.db:/app/users.db \
  $(docker build -q .)

# Method 2: Using docker-compose
docker-compose up -d --build
```

### Stopping the Application
```bash
# Stop and remove container
docker stop interview-app && docker rm interview-app

# Or using docker-compose
docker-compose down
```

### Updating the Application
```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker stop interview-app && docker rm interview-app
docker run -d --name interview-app -p 5001:5001 --env-file .env \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/users.db:/app/users.db \
  $(docker build -q .)
```

### Checking Application Status
```bash
# Check container status
docker ps

# Check application health
curl http://localhost:5001/health

# View logs
docker logs interview-app
```

## 🧪 Testing

### Test OpenAI API Integration
```bash
# Test API key configuration
docker exec interview-app python3 /app/test_api.py

# Check health endpoint
curl http://localhost:5001/health
```

### Test PDF Loading
```bash
# Test PDF question loading
docker exec interview-app python3 /app/test_pdf_loading.py
```

## 🔍 Troubleshooting

### Common Issues

1. **"Invalid username or password" Error**
   - **Solution**: Ensure the `users.db` file is properly mounted
   - **Fix**: Restart container with correct volume mounts

2. **OpenAI API Not Working**
   - **Check**: API key format (no quotes)
   - **Verify**: `curl http://localhost:5001/health` shows `"openai_client": true`
   - **Fix**: Update API key in `.env` and restart container

3. **Same Visual Analysis Results**
   - **Cause**: OpenAI client not working, using fallback responses
   - **Fix**: Ensure OpenAI API key is properly configured

4. **Container Won't Start**
   - **Check**: Port 5001 is available
   - **Fix**: Stop existing containers or change port

5. **SSL Certificate Errors**
   - **Cause**: nginx trying to use non-existent SSL certificates
   - **Solution**: Use the direct Docker method instead of docker-compose

### Debugging Steps

1. **Check container logs**
   ```bash
   docker logs interview-app
   ```

2. **Verify environment variables**
   ```bash
   docker exec interview-app env | grep OPENAI
   ```

3. **Test API connectivity**
   ```bash
   docker exec interview-app python3 -c "
   import os
   from openai import OpenAI
   api_key = os.getenv('OPENAI_API_KEY')
   print('API Key present:', bool(api_key))
   print('API Key starts with sk:', api_key.startswith('sk-') if api_key else False)
   "
   ```

4. **Check database connectivity**
   ```bash
   docker exec interview-app ls -la /app/users.db
   ```

## 📁 Project Structure

```
ai_int_docker/
├── main.py                 # Main Flask application
├── index.html             # Main interview interface
├── login.html             # Login page
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
├── .env                   # Environment variables (create from env.example)
├── env.example           # Environment template
├── test_api.py           # OpenAI API testing script
├── Bank_Question.pdf     # Banking interview questions
├── MBA_Question.pdf      # MBA interview questions
├── users.db              # SQLite database with user credentials
├── static/               # Static assets
├── uploads/              # File uploads directory
└── logs/                 # Application logs
```

## 🎯 Interview Types

### MBA Interviews
- Resume-based questions
- School-specific questions (IIM, ISB, Other B-Schools)
- Interest area questions (General Business, Finance, Marketing, Operations)

### Banking Interviews
- Resume-based questions
- Bank-type specific questions (Public Sector, Private Banks, Regulatory)
- Technical & analytical questions (Banking Knowledge, Logical Reasoning, Situational Judgement)

## 📊 Features in Detail

### AI Question Generation
- Contextual questions based on previous answers
- Industry-specific question banks
- Dynamic difficulty adjustment

### Answer Evaluation
- Real-time scoring (0-10 scale)
- Detailed feedback on multiple criteria
- Confidence and clarity assessment

### Visual Analysis
- Professional presentation assessment
- Camera-based analysis (optional)
- Visual scoring integration

### Fallback System
- Comprehensive question banks when AI is unavailable
- Multiple PDF parsing methods (pdfplumber, PyPDF2, pdftotext)
- Robust error handling

## 📝 API Endpoints

- `GET /` - Main interview interface
- `POST /login` - User authentication
- `POST /start_interview` - Start new interview
- `POST /submit_answer` - Submit answer and get evaluation
- `POST /analyze_visuals` - Analyze camera feed
- `GET /health` - Health check endpoint

## 🔒 Security

- Environment variable protection
- Input validation and sanitization
- Secure file upload handling
- CORS configuration for camera access

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Getting Help

### Quick Health Check
```bash
# Check if everything is working
curl http://localhost:5001/health
```

### Expected Response
```json
{
  "status": "healthy",
  "openai_client": true,
  "camera_support": true
}
```

### Support
- Check the logs for detailed error messages
- Ensure all prerequisites are installed
- Verify environment variables are set correctly
- Test with the provided test scripts

## 🎉 Acknowledgments

- OpenAI for providing the AI capabilities
- Flask community for the web framework
- OpenCV for computer vision features
- All contributors and testers

---

**Note**: This application is designed for educational and demonstration purposes. For production use, ensure proper security measures and compliance with relevant regulations. 