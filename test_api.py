import os
from openai import OpenAI

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Get API key
api_key = os.getenv('OPENAI_API_KEY')
print('API Key present:', bool(api_key))
print('API Key length:', len(api_key) if api_key else 0)
print('API Key starts with sk:', api_key.startswith('sk-') if api_key else False)
print('API Key has quotes:', api_key.startswith('"') if api_key else False)
print('API Key first 10 chars:', api_key[:10] if api_key else 'None')

# Try to create client
try:
    client = OpenAI(api_key=api_key)
    print('Client created successfully')
    
    # Test a simple API call
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10
    )
    print('API call successful:', response.choices[0].message.content)
    
except Exception as e:
    print('Error:', e) 