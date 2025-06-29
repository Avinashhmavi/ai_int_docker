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

- Python 3.11+
- Docker (optional)
- OpenAI API Key (optional - app works with fallback questions)

## 🚀 Quick Start

### Local Development

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd interv
   ```

2. **Set up virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp env.example .env
   # Edit .env and add your OpenAI API key (optional)
   ```

5. **Run the application**
   ```bash
   python main.py
   ```

6. **Access the application**
   - Open http://localhost:5000 in your browser
   - Login with any credentials (demo mode)

### Docker Deployment

1. **Build and run with Docker Compose**
   ```bash
   docker-compose up --build
   ```

2. **For production deployment**
   ```bash
   docker-compose -f docker-compose.prod.yml up --build
   ```

## 📁 Project Structure

```
interv/
├── main.py                 # Main Flask application
├── index.html             # Main interview interface
├── login.html             # Login page
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
├── .env                   # Environment variables
├── env.example           # Environment template
├── Bank_Question.pdf     # Banking interview questions
├── MBA_Question.pdf      # MBA interview questions
├── static/               # Static assets
├── uploads/              # File uploads directory
└── docs/                 # Documentation
```

## 🔧 Configuration

### Environment Variables

Create a `.env` file based on `env.example`:

```env
OPENAI_API_KEY=your_openai_api_key_here
FLASK_ENV=development
FLASK_DEBUG=1
```

### OpenAI API Key (Optional)

The application works without an OpenAI API key using fallback questions. To enable AI features:

1. Get an API key from [OpenAI](https://platform.openai.com/)
2. Add it to your `.env` file
3. Restart the application

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

## 🐳 Docker Support

### Development
```bash
docker-compose up --build
```

### Production
```bash
docker-compose -f docker-compose.prod.yml up --build
```

### Testing
```bash
./test-docker.sh
```

## 🧪 Testing

### PDF Loading Test
```bash
python test_pdf_loading.py
```

### Docker Test
```bash
./test-docker.sh
```

## 📝 API Endpoints

- `GET /` - Main interview interface
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

## 🆘 Troubleshooting

### Common Issues

1. **PDF Loading Errors**: The app includes multiple fallback methods for PDF parsing
2. **Camera Access**: Ensure HTTPS in production or localhost for development
3. **OpenAI API Errors**: App works with fallback questions when API is unavailable
4. **Docker Issues**: Check the Docker troubleshooting guide in the docs

### Getting Help

- Check the logs for detailed error messages
- Ensure all dependencies are installed
- Verify environment variables are set correctly
- Test with the provided test scripts

## 🎉 Acknowledgments

- OpenAI for providing the AI capabilities
- Flask community for the web framework
- OpenCV for computer vision features
- All contributors and testers

---

**Note**: This application is designed for educational and demonstration purposes. For production use, ensure proper security measures and compliance with relevant regulations. # ai_int_docker
