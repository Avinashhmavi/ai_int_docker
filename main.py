import os
import json
import time
import sqlite3
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from flask_cors import CORS
from openai import OpenAI
import pdfplumber
import docx2txt
from dotenv import load_dotenv
from collections import defaultdict
import logging
import re
import threading
import cv2
import numpy as np
from datetime import datetime
import base64
import random

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

app = Flask(__name__, template_folder='.', static_folder='static')
app.secret_key = os.urandom(24)

# Enable CORS for production deployment
CORS(app, origins=['*'], supports_credentials=True)

# Security headers for camera access
@app.after_request
def add_security_headers(response):
    # Content Security Policy for camera access
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: blob: https:; "
        "media-src 'self' blob:; "
        "connect-src 'self' ws: wss:; "
        "frame-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'self'; "
        "upgrade-insecure-requests;"
    )
    
    response.headers['Content-Security-Policy'] = csp_policy
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=*, microphone=*, geolocation=()'
    
    # Allow camera and microphone access
    response.headers['Cross-Origin-Embedder-Policy'] = 'unsafe-none'
    response.headers['Cross-Origin-Opener-Policy'] = 'unsafe-none'
    
    return response

os.makedirs('uploads', exist_ok=True)
os.makedirs('uploads/snapshots', exist_ok=True)

# Initialize OpenAI client
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    try:
        client = OpenAI(api_key=api_key)
        logging.info("OpenAI client initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
        client = None
else:
    logging.warning("OPENAI_API_KEY not found in environment. OpenAI dependent features will not work.")
    client = None

qna_evaluations = []
current_use_voice_mode = False
listening_active = False
interview_context = {}
visual_analysis_thread = None
visual_analyses = []
visual_analyses_lock = threading.Lock()

interview_context_template = {
    'questions_list': [], 'current_q_idx': 0, 'previous_answers_list': [], 'scores_list': [],
    'question_depth_counter': 0, 'max_followup_depth': 2, 'current_interview_track': None,
    'current_sub_track': None, 'questions_already_asked': set(), 'current_job_description': None,
    'use_camera_feature': False,
    'generated_resume_questions_cache': [],
    'icebreaker_was_prepended': False,
    'prepended_icebreaker_text': None
}

structure = {
    'mba': {'resume_flow': [], 'school_based': defaultdict(list), 'interest_areas': defaultdict(list)},
    'bank': {'resume_flow': [], 'bank_type': defaultdict(list), 'technical_analytical': defaultdict(list)}
}
mba_pdf_path = "MBA_Question.pdf"
bank_pdf_path = "Bank_Question.pdf"

def normalize_text(text_input):
    if not text_input: return ""
    return " ".join(str(text_input).strip().split()).lower()

def strip_numbering(text_input):
    if not text_input: return ""
    return re.sub(r'^\d+\.\s*', '', str(text_input)).strip()

def load_questions_into_memory(pdf_path, section_type):
    if not os.path.exists(pdf_path):
        logging.error(f"PDF question file '{pdf_path}' not found.")
        return False
    
    # Try multiple PDF parsing methods
    full_text = ""
    
    # Method 1: Try pdfplumber with error handling
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Try to extract text page by page with individual error handling
            page_texts = []
            for i, page in enumerate(pdf.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        page_texts.append(page_text)
                except Exception as page_error:
                    logging.warning(f"Error extracting text from page {i+1} in {pdf_path}: {page_error}")
                    continue
            
            if page_texts:
                full_text = '\n'.join(page_texts)
                logging.info(f"Successfully extracted text from {len(page_texts)} pages using pdfplumber")
            else:
                logging.warning(f"No text could be extracted from {pdf_path} using pdfplumber")
                
    except Exception as e_pdfplumber:
        logging.warning(f"pdfplumber failed for {pdf_path}: {e_pdfplumber}")
        full_text = ""
    
    # Method 2: If pdfplumber failed, try PyPDF2 as fallback
    if not full_text:
        try:
            import PyPDF2
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                page_texts = []
                for page in pdf_reader.pages:
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            page_texts.append(page_text)
                    except Exception as page_error:
                        logging.warning(f"Error extracting text from page using PyPDF2: {page_error}")
                        continue
                
                if page_texts:
                    full_text = '\n'.join(page_texts)
                    logging.info(f"Successfully extracted text using PyPDF2 fallback")
                else:
                    logging.warning(f"No text could be extracted from {pdf_path} using PyPDF2")
                    
        except ImportError:
            logging.warning("PyPDF2 not available for fallback PDF parsing")
        except Exception as e_pypdf2:
            logging.warning(f"PyPDF2 fallback also failed for {pdf_path}: {e_pypdf2}")
    
    # Method 3: If both failed, try pdf2txt as last resort
    if not full_text:
        try:
            import subprocess
            result = subprocess.run(['pdftotext', pdf_path, '-'], capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                full_text = result.stdout
                logging.info(f"Successfully extracted text using pdftotext fallback")
            else:
                logging.warning(f"pdftotext failed for {pdf_path}")
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e_pdftotext:
            logging.warning(f"pdftotext fallback failed for {pdf_path}: {e_pdftotext}")
    
    # If all methods failed, return False
    if not full_text:
        logging.error(f"All PDF parsing methods failed for {pdf_path}")
        return False
    
    # Process the extracted text
    try:
        lines = full_text.split('\n')
        current_section = None
        current_subsection = None
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            if section_type == 'mba':
                if "1. Resume Flow" in line: current_section, current_subsection = 'resume_flow', None; continue
                elif "2. Pre-Defined Question Selection" in line: current_section, current_subsection = 'school_based', None; continue
                elif "3. Interface to Select Question Areas" in line: current_section, current_subsection = 'interest_areas', None; continue
                if current_section == 'school_based':
                    if "For IIMs" in line: current_subsection = 'IIM'; continue
                    elif "For ISB" in line: current_subsection = 'ISB'; continue
                    elif "For Other B-Schools" in line: current_subsection = 'Other'; continue
                if current_section == 'interest_areas':
                    if "General Business & Leadership" in line: current_subsection = 'General Business'; continue
                    elif "Finance & Economics" in line: current_subsection = 'Finance'; continue
                    elif "Marketing & Strategy" in line: current_subsection = 'Marketing'; continue
                    elif "Operations & Supply Chain" in line: current_subsection = 'Operations'; continue
            elif section_type == 'bank':
                if "Resume-Based Questions" in line: current_section, current_subsection = 'resume_flow', None; continue
                elif "Bank-Type Specific Questions" in line: current_section, current_subsection = 'bank_type', None; continue
                elif "Technical & Analytical Questions" in line: current_section, current_subsection = 'technical_analytical', None; continue
                elif "Current Affairs" in line: current_section, current_subsection = 'technical_analytical', 'Current Affairs'; continue
                if current_section == 'bank_type':
                    if "Public Sector Banks" in line: current_subsection = 'Public Sector Banks'; continue
                    elif "Private Banks" in line: current_subsection = 'Private Banks'; continue
                    elif "Regulatory Roles" in line: current_subsection = 'Regulatory Roles'; continue
                if current_section == 'technical_analytical' and current_subsection != 'Current Affairs':
                    if "Banking Knowledge" in line: current_subsection = 'Banking Knowledge'; continue
                    elif "Logical Reasoning" in line: current_subsection = 'Logical Reasoning'; continue
                    elif "Situational Judgement" in line: current_subsection = 'Situational Judgement'; continue
            
            if line and line[0].isdigit() and '.' in line.split()[0]:
                question_text = strip_numbering(line)
                if not question_text: continue
                is_sequence = bool(re.search(r'\d+,\s*\d+,\s*\d+.*,_', question_text))
                question_data = {'text': question_text, 'type': 'sequence' if is_sequence else 'standard'}
                if not question_data['text'].endswith('?'): question_data['text'] += '?'
                if current_section == 'resume_flow': structure[section_type]['resume_flow'].append(question_data)
                elif current_section and current_subsection: structure[section_type][current_section][current_subsection].append(question_data)
        
        logging.info(f"Successfully loaded questions for {section_type} from {pdf_path}.")
        return True
        
    except Exception as e_process:
        logging.error(f"Error processing extracted text from {pdf_path} for {section_type}: {e_process}", exc_info=True)
        return False

if not load_questions_into_memory(mba_pdf_path, 'mba'):
    logging.warning(f"Could not load MBA questions from '{mba_pdf_path}'. Using comprehensive fallback.")
    # Comprehensive MBA fallback questions
    structure['mba']['resume_flow'] = [
        {'text': "Tell me about your background and why you are pursuing an MBA?", 'type': 'standard'},
        {'text': "What are your career goals and how will an MBA help you achieve them?", 'type': 'standard'},
        {'text': "Can you walk me through your resume and highlight your key achievements?", 'type': 'standard'},
        {'text': "What challenges have you faced in your career and how did you overcome them?", 'type': 'standard'},
        {'text': "Why did you choose this particular MBA program?", 'type': 'standard'}
    ]
    structure['mba']['school_based']['IIM'] = [
        {'text': "What do you know about IIMs and why are you interested in joining?", 'type': 'standard'},
        {'text': "How do you plan to contribute to the IIM community?", 'type': 'standard'},
        {'text': "What sets IIMs apart from other business schools in your view?", 'type': 'standard'}
    ]
    structure['mba']['school_based']['ISB'] = [
        {'text': "Why are you interested in ISB specifically?", 'type': 'standard'},
        {'text': "How do you plan to leverage ISB's network and resources?", 'type': 'standard'},
        {'text': "What do you know about ISB's unique features and programs?", 'type': 'standard'}
    ]
    structure['mba']['interest_areas']['General Business'] = [
        {'text': "What leadership experiences have you had in your career?", 'type': 'standard'},
        {'text': "How do you handle conflict in a team setting?", 'type': 'standard'},
        {'text': "What is your leadership style and how has it evolved?", 'type': 'standard'}
    ]
    structure['mba']['interest_areas']['Finance'] = [
        {'text': "What interests you about finance and investment?", 'type': 'standard'},
        {'text': "How do you stay updated with financial markets and trends?", 'type': 'standard'},
        {'text': "What financial analysis skills do you possess?", 'type': 'standard'}
    ]

if not load_questions_into_memory(bank_pdf_path, 'bank'):
    logging.warning(f"Could not load Bank questions from '{bank_pdf_path}'. Using comprehensive fallback.")
    # Comprehensive Bank fallback questions
    structure['bank']['resume_flow'] = [
        {'text': "Why are you interested in a career in the banking sector?", 'type': 'standard'},
        {'text': "What do you know about the banking industry and current trends?", 'type': 'standard'},
        {'text': "Can you tell me about your relevant experience in finance or banking?", 'type': 'standard'},
        {'text': "What skills do you think are essential for a banking professional?", 'type': 'standard'},
        {'text': "How do you stay updated with banking regulations and policies?", 'type': 'standard'}
    ]
    structure['bank']['bank_type']['Public Sector Banks'] = [
        {'text': "What do you know about public sector banks in India?", 'type': 'standard'},
        {'text': "How do you think public sector banks differ from private banks?", 'type': 'standard'},
        {'text': "What role do you think public sector banks play in financial inclusion?", 'type': 'standard'}
    ]
    structure['bank']['bank_type']['Private Banks'] = [
        {'text': "What attracts you to private sector banking?", 'type': 'standard'},
        {'text': "How do you think private banks compete in the market?", 'type': 'standard'},
        {'text': "What innovations in private banking interest you most?", 'type': 'standard'}
    ]
    structure['bank']['technical_analytical']['Banking Knowledge'] = [
        {'text': "Can you explain the difference between retail and corporate banking?", 'type': 'standard'},
        {'text': "What do you understand about risk management in banking?", 'type': 'standard'},
        {'text': "How do you think digital banking is transforming the industry?", 'type': 'standard'}
    ]
    structure['bank']['technical_analytical']['Logical Reasoning'] = [
        {'text': "If a customer has a complex financial situation, how would you analyze it?", 'type': 'standard'},
        {'text': "How would you approach solving a banking-related problem step by step?", 'type': 'standard'},
        {'text': "Can you think of a situation where you had to use logical reasoning at work?", 'type': 'standard'}
    ]

def get_openai_response_generic(prompt_messages, temperature=0.7, max_tokens=500, model_override=None):
    if not client:
        logging.error("OpenAI client not available for API call.")
        return "OpenAI client not available."
    try:
        chosen_model = model_override if model_override else "gpt-4o-mini"
        response = client.chat.completions.create(
            model=chosen_model, messages=prompt_messages, temperature=temperature, max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()
    except Exception as e_openai:
        logging.error(f"OpenAI API call error with model {chosen_model}: {e_openai}", exc_info=True)
        return f"Error: OpenAI API Call Failed - {e_openai}"

def capture_initial_frame_data_for_question():
    """This function is kept for backward compatibility but is no longer used"""
    return None

def generate_environment_icebreaker_question(image_data_url):
    if not image_data_url:
        logging.warning("Icebreaker: No image data provided, using fallback")
        return "I see you're ready for the interview. How are you feeling about this opportunity?"
    
    # First try OpenAI
    if client:
        try:
            messages = [{"role": "user", "content": [
                {"type": "text", "text": (
                    "You are an interviewer conducting a formal interview. The candidate has enabled their camera. "
                    "To begin the interaction smoothly, observe their professional presentation or a general, neutral aspect of their visible environment from this image. "
                    "You can ask about something in their background (like a bookshelf, a plant, or artwork if it looks professional) or make a general positive observation about their setup or readiness. "
                    "If you observe something distinctly professional about their attire (e.g., a formal jacket, a tie) or a neat hairstyle that contributes to a professional image, you can make a brief, positive, and non-detailed comment that leads to a simple icebreaker question. Frame it carefully to be about their preparedness or professional setting. "
                    "If visible, you may make a brief, general comment on something professional in their attire (e.g., a blazer, shirt, or tie) or grooming that suggests preparedness."
                    "Ask a single, brief, and formal icebreaker question. The question must be polite, non-intrusive, and strictly professional. "
                    "Avoid any overly personal remarks or overly casual phrasing. Ensure the question is a complete sentence ending with a question mark. "
                    "Examples: 'I notice an interesting bookshelf behind you; do you have a favorite professional read?', 'Your setup looks very professional. Are you comfortable and ready to start?', 'That's a smart background choice. Does it help you focus for calls like these?'. "
                    "If commenting on attire/appearance, it should be very general and focused on professionalism, for example: 'You present very professionally. I hope you're feeling well-prepared for our discussion today?' "
                    "Do not thank the candidate for attending"
                    "The goal is a polite, initial engagement. If unsure, stick to the environment or general readiness."
                )},
                {"type": "image_url", "image_url": {"url": image_data_url, "detail": "low"}}
            ]}]
            
            response_text = get_openai_response_generic(messages, temperature=0.6, max_tokens=75, model_override="gpt-4-vision-preview")
            
            if "Error" not in response_text and "OpenAI client not available" not in response_text:
                question = response_text.strip()
                if question and question.endswith('?') and 3 <= len(question.split()) <= 35:
                    logging.info(f"Icebreaker: Generated formal question from OpenAI: {question}")
                    return question
                else:
                    logging.warning(f"Icebreaker: Generated question unsuitable: '{question}' (Words: {len(question.split()) if question else 0})")
                    # Fall through to fallback
            else:
                logging.warning(f"Icebreaker: OpenAI failed: {response_text}")
                # Fall through to fallback
                
        except Exception as e_ice:
            logging.error(f"Icebreaker: Exception with OpenAI: {e_ice}")
            # Fall through to fallback
    
    # Fallback icebreaker questions
    fallback_icebreakers = [
        "I see you're ready for the interview. How are you feeling about this opportunity?",
        "Your setup looks very professional. Are you comfortable and ready to start?",
        "I appreciate you taking the time for this interview. How are you feeling today?",
        "Thank you for joining us. Are you ready to begin our discussion?",
        "I can see you're well-prepared. How are you feeling about this opportunity?"
    ]
    
    # Select a random fallback question
    selected_icebreaker = random.choice(fallback_icebreakers)
    logging.info(f"Icebreaker: Using fallback question: {selected_icebreaker}")
    return selected_icebreaker

def get_fallback_questions_from_pdf(job_type, track, sub_track=''):
    """Get fallback questions from PDF structure when OpenAI fails"""
    try:
        fallback_questions = []
        
        if job_type == 'mba':
            if track == 'resume':
                # Get resume flow questions
                resume_questions = structure['mba']['resume_flow']
                fallback_questions.extend([q['text'] for q in resume_questions[:5]])
                
            elif track == 'school_based':
                # Get school-based questions
                school_questions = structure['mba']['school_based']
                if sub_track and sub_track in school_questions:
                    fallback_questions.extend([q['text'] for q in school_questions[sub_track][:3]])
                else:
                    # Get questions from all school types
                    for school_type, questions in school_questions.items():
                        fallback_questions.extend([q['text'] for q in questions[:2]])
                        
            elif track == 'interest_areas':
                # Get interest area questions
                interest_questions = structure['mba']['interest_areas']
                if sub_track and sub_track in interest_questions:
                    fallback_questions.extend([q['text'] for q in interest_questions[sub_track][:3]])
                else:
                    # Get questions from all interest areas
                    for area, questions in interest_questions.items():
                        fallback_questions.extend([q['text'] for q in questions[:2]])
                        
        elif job_type == 'bank':
            if track == 'resume':
                # Get resume flow questions
                resume_questions = structure['bank']['resume_flow']
                fallback_questions.extend([q['text'] for q in resume_questions[:5]])
                
            elif track == 'bank_type':
                # Get bank type questions
                bank_questions = structure['bank']['bank_type']
                if sub_track and sub_track in bank_questions:
                    fallback_questions.extend([q['text'] for q in bank_questions[sub_track][:3]])
                else:
                    # Get questions from all bank types
                    for bank_type, questions in bank_questions.items():
                        fallback_questions.extend([q['text'] for q in questions[:2]])
                        
            elif track == 'technical_analytical':
                # Get technical questions
                tech_questions = structure['bank']['technical_analytical']
                if sub_track and sub_track in tech_questions:
                    fallback_questions.extend([q['text'] for q in tech_questions[sub_track][:3]])
                else:
                    # Get questions from all technical areas
                    for tech_area, questions in tech_questions.items():
                        fallback_questions.extend([q['text'] for q in questions[:2]])
        
        # Add some generic questions if we don't have enough
        if len(fallback_questions) < 5:
            generic_questions = [
                "Tell me about your background and what led you to this opportunity?",
                "What are your key strengths that would be valuable in this role?",
                "Can you describe a challenging situation you've faced and how you handled it?",
                "What are your career goals and how does this position align with them?",
                "What motivates you in your work?"
            ]
            fallback_questions.extend(generic_questions[:5-len(fallback_questions)])
        
        logging.info(f"Generated {len(fallback_questions)} fallback questions from PDF for {job_type}/{track}")
        return fallback_questions[:10]  # Limit to 10 questions
        
    except Exception as e:
        logging.error(f"Error getting fallback questions from PDF: {e}")
        # Return basic fallback questions
        return [
            "Tell me about your background and what led you to this opportunity?",
            "What are your key strengths that would be valuable in this role?",
            "Can you describe a challenging situation you've faced and how you handled it?",
            "What are your career goals and how does this position align with them?",
            "What motivates you in your work?"
        ]

def generate_resume_questions(resume_text, job_type, asked_qs_set_normalized_global):
    if not resume_text or resume_text == "Resume content appears to be empty or could not be extracted.":
        logging.warning("Resume Q Gen: No resume text provided, using fallback questions")
        return get_fallback_questions_from_pdf(job_type, 'resume')
    
    # First try OpenAI
    if client:
        try:
            prompt_context = "an MBA program interview" if job_type == 'mba' else "a banking role interview"
            prompt = (
                f"You are an expert interviewer preparing for {prompt_context}. "
                f"Based only on the candidate's resume provided below, generate 10-12 unique, insightful questions. "
                f"Focus on their experiences, skills, achievements, and career progression as detailed in the resume. "
                f"Each question must be a complete sentence, concise, and end with a question mark. Avoid truncating questions mid-sentence."
                f"Do not ask generic questions not directly tied to the resume content. "
                f"interview questions tailored to the candidate's experience and background." 
                f"Avoid questions similar to these already considered (normalized sample): {list(asked_qs_set_normalized_global)[:3]}. "
                f"Resume Text: ```{resume_text[:2500]}```"
            )
            response_text = get_openai_response_generic([{"role": "user", "content": prompt}], max_tokens=1000, temperature=0.55)
            
            if "Error" not in response_text and "OpenAI client not available" not in response_text:
                generated_qs_raw_list = [strip_numbering(q.strip()) for q in response_text.split('\n') if q.strip()]
                final_resume_qs = []
                for q_text_candidate in generated_qs_raw_list:
                    if not q_text_candidate.endswith('?'): q_text_candidate += '?'
                    if 3 <= len(q_text_candidate.split()) <= 30:
                        if normalize_text(q_text_candidate) not in asked_qs_set_normalized_global:
                            final_resume_qs.append(q_text_candidate)
                
                if len(final_resume_qs) >= 5:
                    logging.info(f"Resume Q Gen: Successfully generated {len(final_resume_qs)} questions from OpenAI")
                    return final_resume_qs[:10]
                else:
                    logging.warning(f"Resume Q Gen: Only {len(final_resume_qs)} questions from OpenAI, supplementing with fallbacks")
                    # Supplement with fallback questions
                    fallback_qs = get_fallback_questions_from_pdf(job_type, 'resume')
                    for f_q_text in fallback_qs:
                        if normalize_text(f_q_text) not in {normalize_text(q) for q in final_resume_qs}:
                            final_resume_qs.append(f_q_text)
                    return final_resume_qs[:10]
            else:
                logging.warning(f"Resume Q Gen: OpenAI failed: {response_text}")
                # Fall through to PDF fallback
                
        except Exception as e:
            logging.error(f"Resume Q Gen: Exception with OpenAI: {e}")
            # Fall through to PDF fallback
    
    # Fallback to PDF questions
    logging.info("Resume Q Gen: Using fallback questions from PDF")
    return get_fallback_questions_from_pdf(job_type, 'resume')

def generate_answer_feedback(question, answer, job_description):
    # First try OpenAI
    if client:
        try:
            prompt = f"""
You are an expert interviewer for a role related to: {job_description}.
The candidate was asked: "{question}"
Candidate's Answer: "{answer}"
provide concise, constructive feedback to help the candidate improve their interview performance. Focus on clarity, detail, relevance to the question, and communication skills. Provide 2-3 sentences of specific, actionable advice tailored to the answer's content and weaknesses. Avoid repeating the question or answer verbatim, and do not include scores or numerical ratings. Ensure the feedback is encouraging, professional, and unique for each response.
Feedback:"""
            feedback = get_openai_response_generic([{"role": "user", "content": prompt}], temperature=0.65, max_tokens=160)
            
            if "Error" not in feedback and "OpenAI client not available" not in feedback:
                feedback_text = feedback.strip()
                if feedback_text and len(feedback_text.split()) > 5:
                    logging.info(f"Feedback: Generated from OpenAI: {feedback_text[:50]}...")
                    return feedback_text
            else:
                logging.warning(f"Feedback: OpenAI failed: {feedback}")
                # Fall through to fallback
                
        except Exception as e:
            logging.error(f"Feedback: Exception with OpenAI: {e}")
            # Fall through to fallback
    
    # Fallback feedback based on answer characteristics
    answer_length = len(answer.split())
    has_examples = any(keyword in answer.lower() for keyword in ['example', 'instance', 'specifically', 'when', 'project', 'team', 'result'])
    has_quantifiable = any(keyword in answer.lower() for keyword in ['increased', 'decreased', 'improved', 'achieved', 'resulted in', 'led to', 'percentage', '%'])
    
    if answer_length < 20:
        fallback_feedback = "Consider providing more detail in your responses. Include specific examples and experiences to make your answers more compelling and demonstrate your qualifications."
    elif answer_length < 50:
        if has_examples:
            fallback_feedback = "Good use of examples! To strengthen your response further, consider adding quantifiable results or outcomes to demonstrate the impact of your actions."
        else:
            fallback_feedback = "Your response shows good understanding. To make it even stronger, include specific examples from your experience that demonstrate your skills and achievements."
    else:
        if has_quantifiable:
            fallback_feedback = "Excellent response with specific examples and measurable results. This demonstrates strong communication skills and provides clear evidence of your capabilities."
        elif has_examples:
            fallback_feedback = "Strong response with good examples. Consider adding specific metrics or outcomes to quantify your achievements and make your answer even more impactful."
        else:
            fallback_feedback = "Comprehensive response with good detail. To enhance it further, include specific examples or case studies that illustrate your points and demonstrate your experience."
    
    logging.info(f"Feedback: Using fallback: {fallback_feedback[:50]}...")
    return fallback_feedback

CATEGORY_ALIASES_EVAL = {
    "ideas": "Ideas",
    "organization": "Organization",
    "accuracy": "Accuracy",
    "voice": "Voice",
    "grammar usage and sentence fluency": "Grammar Usage and Sentence Fluency",
    "stop words": "Stop words"
}
WEIGHTS_EVAL = {
    "Ideas": 0.25,
    "Organization": 0.25,
    "Accuracy": 0.25,
    "Voice": 0.15,
    "Grammar Usage and Sentence Fluency": 0.05,
    "Stop words": 0.05
}
def parse_evaluation_response(raw_response_text):
    parsed_eval = {}
    lines = [line.strip() for line in raw_response_text.split('\n') if line.strip()]
    current_category_key_eval = None
    for line in lines:
        match_eval = re.match(r'^Category:\s*(.+?)\s*\((\d{1,2})(?:/10)?\)$', line, re.IGNORECASE)
        if match_eval:
            category_name_raw_eval = match_eval.group(1).strip()
            canonical_name_eval = None
            for alias_key, canonical_val in CATEGORY_ALIASES_EVAL.items():
                if category_name_raw_eval.lower() == alias_key.lower() or category_name_raw_eval.lower() == canonical_val.lower():
                    canonical_name_eval = canonical_val; break
            if not canonical_name_eval: canonical_name_eval = category_name_raw_eval
            score_val = int(match_eval.group(2).strip())
            parsed_eval[canonical_name_eval] = {"score": score_val}
            current_category_key_eval = canonical_name_eval
            continue
        if current_category_key_eval and line.lower().startswith("justification:"):
            justification_text = line.split(":", 1)[1].strip()
            if current_category_key_eval in parsed_eval:
                 parsed_eval[current_category_key_eval]["justification"] = justification_text
            current_category_key_eval = None
    return parsed_eval

def calculate_weighted_evaluation_score(scores_dict_eval):
    total_weighted_score_val = 0.0; total_weight_applied_val = 0.0
    for category_name_eval, eval_values in scores_dict_eval.items():
        score_num = eval_values.get("score", 0)
        weight_val = WEIGHTS_EVAL.get(category_name_eval, 0)
        if weight_val > 0: total_weighted_score_val += score_num * weight_val; total_weight_applied_val += weight_val
    if total_weight_applied_val == 0: return 0.0
    
    # Apply score normalization to ensure good answers get higher scores
    raw_score = total_weighted_score_val
    normalized_score = raw_score
    
    # If the raw score is above 6.0, boost it slightly to reflect good performance
    if raw_score >= 6.0:
        # Boost scores in the 6-8 range to 7-9 range
        if raw_score <= 8.0:
            normalized_score = 7.0 + (raw_score - 6.0) * 1.0  # Linear boost
        else:
            # For scores above 8, give a small additional boost
            normalized_score = min(10.0, raw_score + 0.5)
    
    return round(normalized_score, 2)

def evaluate_sequence_response(question_text, answer_text):
    if "2, 5, 10, 17, 26" in question_text.replace(" ", ""):
        correct_ans_seq = "37"
        user_ans_digits = re.findall(r'\d+', str(answer_text))
        if user_ans_digits and user_ans_digits[0] == correct_ans_seq: return "[Correct sequence. Well done!] Score: 10/10", 10
        else: return f"[Incorrect sequence. Expected {correct_ans_seq}. Your answer: {answer_text}] Score: 0/10", 0
    return "[Sequence pattern not specifically programmed. Assessed qualitatively.] Score: 5/10", 5

def fallback_ai_evaluation(question_text, answer_text):
    answer_norm = normalize_text(answer_text)
    if not answer_norm or len(answer_norm) < 10: return "[Answer too brief/empty. Unable to evaluate using fallback.] Score: 0/10", 0
    
    # More generous scoring based on answer length and content
    word_count = len(answer_text.split())
    if word_count < 20:
        score_fb = 4  # Brief but present
    elif word_count < 50:
        score_fb = 6  # Moderate length
    elif word_count < 100:
        score_fb = 7  # Good length
    else:
        score_fb = 8  # Comprehensive answer
    
    # Boost score if answer seems relevant
    if any(keyword in answer_text.lower() for keyword in ['experience', 'work', 'project', 'team', 'leadership', 'goal', 'achieve', 'learn', 'develop']):
        score_fb = min(9, score_fb + 1)
    
    feedback_fb = ("[Fallback Eval: Answer relevant and reasonably detailed.]" if score_fb >= 6 else "[Fallback Eval: Answer relevant. Consider more detail/structure.]")
    return f"{feedback_fb} Score: {score_fb}/10", score_fb

def evaluate_response_with_ai_scoring(question_text, answer_text, job_description_context):
    if not answer_text or answer_text.strip() == "" or answer_text.lower() == "no answer provided by candidate.":
        return "[No effective answer provided for AI scoring.] Score: 0/10", 0
    if bool(re.search(r'\d+,\s*\d+,\s*\d+.*,_', question_text)): return evaluate_sequence_response(question_text, answer_text)
    prompt_eval = f"""
You are an AI Interview Performance Analyzer for a {job_description_context} role.
Evaluate the candidate's answer to the question below based on these exact six categories.
Use a GENEROUS and REALISTIC scoring scale where:
- 8-10/10: Excellent to outstanding performance
- 6-7/10: Good to very good performance  
- 4-5/10: Average to satisfactory performance
- 1-3/10: Below average to poor performance

1. Ideas:
The answer should focus on one clear idea, maintained throughout without tangents.
Score generously if the candidate demonstrates clear thinking and relevant ideas.

2. Organization:
Ideas should flow logically and cohesively.
Score generously if the answer has a logical structure, even if not perfect.

3. Accuracy:
The answer should fully address all parts of the question.
Score generously if the candidate addresses the main points of the question.

4. Voice:
The answer should be unique and not generic.
Score generously if the candidate shows personality or specific examples.

5. Grammar Usage and Sentence Fluency:
The answer should use correct grammar and sentence structure.
Score generously - minor grammar issues should not heavily penalize good content.

6. Stop words:
Minimize filler words (e.g., uhh, ahh, ummm).
Score generously - only heavily penalize excessive filler words.

IMPORTANT: Be GENEROUS in your scoring. A well-structured, relevant answer should score 7-9/10. Only give very low scores (1-3/10) for truly poor or irrelevant answers.

Provide a score (1-10, 1 lowest, 10 highest) for each category with a one-line justification.

Format the response exactly as:
Category: <category> (<score>/10)
Justification: <explanation>

List all six categories.
Question: {question_text}
Candidate's Answer: {answer_text}
"""
    try:
        ai_eval_text = get_openai_response_generic([{"role": "user", "content": prompt_eval}], temperature=0.5, max_tokens=500)
        if "Error:" in ai_eval_text or "OpenAI client not available" in ai_eval_text:
            logging.warning(f"AI Scoring: API/Client error. Using fallback. Error: {ai_eval_text}"); return fallback_ai_evaluation(question_text, answer_text)
        parsed_scores_from_ai = parse_evaluation_response(ai_eval_text)
        if not parsed_scores_from_ai or len(parsed_scores_from_ai) < 6:
            logging.warning(f"AI Scoring: Failed to parse categories. Response: '{ai_eval_text}'. Parsed: {parsed_scores_from_ai}. Using fallback."); return fallback_ai_evaluation(question_text, answer_text)
        final_weighted_score = calculate_weighted_evaluation_score(parsed_scores_from_ai)
        
        # Apply bonus scoring for exceptional answers
        answer_length = len(answer_text.split())
        has_specific_examples = any(keyword in answer_text.lower() for keyword in ['example', 'instance', 'specifically', 'when', 'project', 'team', 'result'])
        has_quantifiable_results = any(keyword in answer_text.lower() for keyword in ['increased', 'decreased', 'improved', 'achieved', 'resulted in', 'led to', 'percentage', '%'])
        
        # Bonus for comprehensive answers with examples
        if answer_length > 80 and has_specific_examples:
            final_weighted_score = min(10.0, final_weighted_score + 0.5)
        
        # Additional bonus for quantifiable results
        if has_quantifiable_results:
            final_weighted_score = min(10.0, final_weighted_score + 0.3)
        
        eval_details_for_record = ["[AI Detailed Scoring Complete]"]
        for cat_name_record, data_record in parsed_scores_from_ai.items():
            eval_details_for_record.append(f"{cat_name_record}: {data_record.get('score', 'N/A')}/10 ({data_record.get('justification', 'N/J')})")
        full_eval_details_str = " | ".join(eval_details_for_record) + f" | Final Weighted Score: {final_weighted_score}/10"
        return full_eval_details_str, final_weighted_score
    except Exception as e_ai_score:
        logging.error(f"AI Scoring: Exception: {e_ai_score}", exc_info=True); return fallback_ai_evaluation(question_text, answer_text)

def generate_next_question(prev_q_text, prev_ans_text, prev_score, interview_track_context, job_type_context, asked_qs_normalized_set_global, attempt_num=1):
    # If the answer is too short, skip OpenAI and use fallback questions.
    if len(prev_ans_text.split()) < 3:
        logging.info("Follow-up Gen: Answer too short. Using fallback question from PDF/resume.")
    else:
        # If answer is substantive, try OpenAI for a contextual follow-up.
        if attempt_num > 2: 
            logging.info("Follow-up Gen: Max attempts reached. No follow-up question will be generated.")
            return None
        
        if client:
            try:
                focus_map = {
                    'resume': 'candidate specific experiences, skills, or career goals mentioned in their resume or previous answer',
                    'school_based': 'their academic motivations, reasons for choosing a particular school, or how their studies relate to career goals',
                    'interest_areas': 'their passion for the chosen interest area, depth of knowledge, or practical application of their interests',
                    'bank_type': 'their understanding of the specific bank type, customer service approaches, or relevant operational aspects',
                    'technical_analytical': 'their technical banking knowledge, problem-solving abilities, or logical reasoning based on the previous answer'
                }
                focus_guidance = focus_map.get(interview_track_context, 'general relevance, impact, or lessons learned from their previous answer')
                
                prompt_fu = (
                    f"You are an interviewer for a {job_type_context} candidate. They just answered a question. "
                    f"Previous Question: \"{prev_q_text}\"\nCandidate's Answer: \"{prev_ans_text}\"\nThis answer was scored {prev_score}/10.\n"
                    f"Based on this, generate ONE insightful follow-up question that delves deeper into their response, focusing on {focus_guidance}. "
                    f"The follow-up should be natural, concise, a complete sentence, and end with a question mark. "
                    f"Do NOT repeat the previous question or ask something generic if a specific follow-up is possible. "
                    f"Avoid questions similar to these already considered (normalized sample): {list(asked_qs_normalized_set_global)[:3]}. Follow-up Question:"
                )
                
                fu_resp_text = get_openai_response_generic([{"role": "user", "content": prompt_fu}], max_tokens=110, temperature=0.6)
                
                if "Error" not in fu_resp_text and "OpenAI client not available" not in fu_resp_text:
                    fu_q_candidate = strip_numbering(fu_resp_text.strip())
                    if not fu_q_candidate.endswith('?'): 
                        fu_q_candidate += '?'
                    
                    if 3 <= len(fu_q_candidate.split()) <= 30:
                        norm_fu_q_candidate = normalize_text(fu_q_candidate)
                        if norm_fu_q_candidate not in asked_qs_normalized_set_global:
                            logging.info(f"Follow-up Gen: Generated question from OpenAI: {fu_q_candidate}")
                            return fu_q_candidate
                        else:
                            logging.info(f"Follow-up Gen: Generated question already asked, retrying...")
                            if attempt_num < 2:
                                return generate_next_question(prev_q_text, prev_ans_text, prev_score, interview_track_context, job_type_context, asked_qs_normalized_set_global, attempt_num + 1)
                    else:
                        logging.info(f"Follow-up Gen: Generated question failed validation, retrying...")
                        if attempt_num < 2:
                            return generate_next_question(prev_q_text, prev_ans_text, prev_score, interview_track_context, job_type_context, asked_qs_normalized_set_global, attempt_num + 1)
                else:
                    logging.warning(f"Follow-up Gen: OpenAI failed: {fu_resp_text}")
                    
            except Exception as e:
                logging.error(f"Follow-up Gen: Exception with OpenAI: {e}")

    # Fallback to PDF questions if OpenAI fails or is skipped.
    logging.info("Follow-up Gen: Using fallback questions from PDF")
    try:
        # Get relevant questions from PDF based on track
        fallback_questions = get_fallback_questions_from_pdf(job_type_context, interview_track_context)
        
        # Filter out already asked questions
        available_questions = []
        for q in fallback_questions:
            if normalize_text(q) not in asked_qs_normalized_set_global:
                available_questions.append(q)
        
        if available_questions:
            # Return the first available question
            selected_question = available_questions[0]
            logging.info(f"Follow-up Gen: Using fallback question: {selected_question}")
            return selected_question
        else:
            logging.warning("Follow-up Gen: No fallback questions available")
            return None
            
    except Exception as e:
        logging.error(f"Follow-up Gen: Error with fallback: {e}")
        return None

def generate_conversational_reply(answer_text, job_type_context):
    # First try OpenAI
    if client:
        try:
            sys_prompt_ack = (f"You are an engaging and human-like {'HR' if job_type_context == 'mba' else 'banking HR'} interviewer. "
                              f"The candidate has just finished their answer. Generate a short, complete sentence as a reply. "
                              f"Your reply should be engaging and human-like, providing feedback or encouragement without asking for further information. "
                              f"Ensure it's a full thought. The reply MUST be a statement (ending with a period or exclamation mark) and MUST NOT contain any questions (do not end with a question mark). "
                              f"Examples: 'That's a very insightful way to put it.', 'I appreciate you sharing that experience with such clarity!', 'Excellent point, that really highlights your skills.', 'Thanks for that detailed explanation.'")
            ans_summary_for_prompt = answer_text[:100] + ("..." if len(answer_text) > 100 else "")
            ack_resp_text = get_openai_response_generic(
                [{"role": "system", "content": sys_prompt_ack}, {"role": "user", "content": f"Candidate's answer (summary): {ans_summary_for_prompt}"}],
                temperature=0.75, max_tokens=45
            )
            
            if "Error" not in ack_resp_text and "OpenAI client not available" not in ack_resp_text:
                ack_reply = ack_resp_text.strip()
                if ack_reply:
                    if ack_reply.endswith('?'):
                        ack_reply = ack_reply[:-1] + '.'
                    if not re.search(r'[.!?]$', ack_reply):
                        ack_reply += '.'
                    if '?' in ack_reply:
                        ack_reply = ack_reply.replace('?', '.')
                    logging.info(f"Conversational Reply: Generated from OpenAI: {ack_reply}")
                    return ack_reply
            else:
                logging.warning(f"Conversational Reply: OpenAI failed: {ack_resp_text}")
                # Fall through to fallback
                
        except Exception as e:
            logging.error(f"Conversational Reply: Exception with OpenAI: {e}")
            # Fall through to fallback
    
    # Fallback conversational replies
    fallback_replies = [
        "Thank you for that detailed response.",
        "That's very insightful, I appreciate you sharing that.",
        "Excellent point, that really highlights your experience.",
        "I can see you've thought this through carefully.",
        "That's a great perspective on this topic.",
        "Thank you for being so thorough in your answer.",
        "I appreciate the depth of your response.",
        "That's a very thoughtful approach to this question.",
        "Thank you for sharing that experience with us.",
        "That demonstrates excellent understanding of the subject."
    ]
    
    # Select a fallback reply based on answer content
    if len(answer_text.split()) > 50:
        # For longer answers, use more appreciative responses
        selected_reply = random.choice(fallback_replies[:5])
    else:
        # For shorter answers, use more neutral responses
        selected_reply = random.choice(fallback_replies[5:])
    
    logging.info(f"Conversational Reply: Using fallback: {selected_reply}")
    return selected_reply

def authenticate_user_db_old(username_auth, password_auth):
    try:
        with sqlite3.connect('users.db') as conn_auth:
            cursor_auth = conn_auth.cursor()
            cursor_auth.execute('SELECT Allowed FROM users WHERE Username = ? AND Password = ?', (username_auth, password_auth))
            result_auth = cursor_auth.fetchone()
        return result_auth[0] if result_auth else None
    except sqlite3.Error as e_auth_db:
        logging.error(f"Authentication DB error for user '{username_auth}': {e_auth_db}", exc_info=True); return None
    except Exception as e_auth_generic:
        logging.error(f"Generic authentication error for user '{username_auth}': {e_auth_generic}", exc_info=True); return None

def analyze_frame_for_visuals(cv_frame):
    try:
        if cv_frame is None or cv_frame.size == 0:
            logging.warning("Visual Analysis: Empty frame received")
            return {
                'timestamp': datetime.now().isoformat(),
                'face_detected': False,
                'face_count': 0,
                'brightness': 0,
                'contrast': 0,
                'error': 'Empty frame'
            }

        # Convert frame to grayscale
        gray = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2GRAY)
        
        # Calculate brightness and contrast
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        
        # Detect faces
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        if face_cascade.empty():
            logging.error("Visual Analysis: Failed to load face cascade classifier")
            return {
                'timestamp': datetime.now().isoformat(),
                'face_detected': False,
                'face_count': 0,
                'brightness': brightness,
                'contrast': contrast,
                'error': 'Failed to load face detector'
            }
        
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )
        
        # Initialize analysis result
        analysis = {
            'timestamp': datetime.now().isoformat(),
            'face_detected': len(faces) > 0,
            'face_count': len(faces),
            'face_locations': faces.tolist() if len(faces) > 0 else [],
            'brightness': brightness,
            'contrast': contrast
        }
        
        logging.debug(f"Visual Analysis: Processed frame - Faces: {len(faces)}, Brightness: {brightness:.2f}, Contrast: {contrast:.2f}")
        return analysis

    except Exception as e:
        logging.error(f"Error in analyze_frame_for_visuals: {str(e)}")
        return {
            'timestamp': datetime.now().isoformat(),
            'face_detected': False,
            'face_count': 0,
            'brightness': 0,
            'contrast': 0,
            'error': str(e)
        }

def calculate_visual_score():
    if not visual_analyses: return 0.0, "No visual data was captured for scoring."
    try:
        num_samples_va = len(visual_analyses)
        
        # Eye contact (face detected) component
        ec_frames = sum(1 for item in visual_analyses if item.get('face_detected', False))
        ec_ratio_va = ec_frames / num_samples_va
        score_ec_comp = ec_ratio_va * 10
        
        # Visual clarity (confidence) component based on brightness and contrast
        avg_brightness = sum(item.get('brightness', 0) for item in visual_analyses) / num_samples_va
        avg_contrast = sum(item.get('contrast', 0) for item in visual_analyses) / num_samples_va
        
        # Score brightness (ideal: 100-180)
        brightness_score = 10.0 if 100 <= avg_brightness <= 180 else max(0, 10 - abs(avg_brightness - 140) / 15)
        
        # Score contrast (ideal: > 50)
        contrast_score = 10.0 if avg_contrast >= 50 else max(0, avg_contrast / 5)
        
        # Combine into a "visual clarity" score
        clarity_score = (brightness_score + contrast_score) / 2
        
        # Weights for final score
        w_ec = 0.60  # 60% for eye contact
        w_clarity = 0.40  # 40% for visual clarity
        
        final_visual_score_val = (score_ec_comp * w_ec) + (clarity_score * w_clarity)
        
        feedback_text_va = (f"Estimated face presence was maintained in {round(ec_ratio_va*100)}% of samples. "
                            f"Average video brightness was {round(avg_brightness)} and contrast was {round(avg_contrast)}, "
                            f"resulting in a visual clarity score of {round(clarity_score, 1)}/10.")
                            
        return round(final_visual_score_val, 1), feedback_text_va
        
    except ZeroDivisionError: 
        logging.warning("Calculate Visual Score: Division by zero.")
        return 0.0, "Not enough visual data."
    except Exception as e_cvs: 
        logging.error(f"Calculate Visual Score: Error: {e_cvs}", exc_info=True)
        return 0.0, "Error calculating visual score."

@app.route('/')
def index_route():
    if 'allowed_user_type' not in session: return redirect(url_for('login_html_route'))
    return render_template('index.html')

@app.route('/login.html')
def login_html_route(): return render_template('login.html')

@app.route('/test-camera')
def test_camera_route():
    """Camera test page for debugging production issues"""
    return render_template('test-camera.html')

@app.route('/login', methods=['POST'])
def login_post_route():
    try:
        username_form = request.form.get('username'); password_form = request.form.get('password')
        if not username_form or not password_form: return jsonify({'success': False, 'error': 'Username and password are required.'}), 400
        allowed_user_type_from_db = authenticate_user_db_old(username_form, password_form)
        if allowed_user_type_from_db:
            session['allowed_user_type'] = allowed_user_type_from_db; session['username'] = username_form
            logging.info(f"User '{username_form}' logged in as type '{allowed_user_type_from_db}'.")
            return jsonify({'success': True, 'allowed': allowed_user_type_from_db})
        else:
            logging.warning(f"Failed login attempt for username: '{username_form}'.")
            return jsonify({'success': False, 'error': 'Invalid username or password.'}), 401
    except Exception as e_login:
        logging.error(f"Login Error for user '{request.form.get('username', 'N/A')}': {e_login}", exc_info=True)
        return jsonify({'success': False, 'error': 'An internal server error occurred during login.'}), 500

@app.route('/logout')
def logout_route():
    global visual_analysis_thread, visual_analyses, interview_context, qna_evaluations
    username_logout = session.get('username', 'User')
    logging.info(f"Logout initiated for user {username_logout}.")
    try:
        current_ic_ref = interview_context
        if current_ic_ref and current_ic_ref.get('use_camera_feature', False) and visual_analysis_thread and visual_analysis_thread.is_alive():
            logging.info(f"Logout: Signaling visual analysis thread to stop for {username_logout}.")
            current_ic_ref['use_camera_feature'] = False
            visual_analysis_thread.join(timeout=1.5)
            if visual_analysis_thread.is_alive():
                 logging.warning(f"Logout: Visual analysis thread for {username_logout} did not terminate gracefully.")
            visual_analysis_thread = None
        session.clear()
        visual_analyses = []
        qna_evaluations = []
        interview_context = {}
        logging.info(f"User {username_logout} logged out. Session and global states have been reset.")
        return redirect(url_for('login_html_route'))
    except Exception as e_logout:
        logging.error(f"Error during logout for {username_logout}: {e_logout}", exc_info=True)
        session.clear()
        visual_analysis_thread = None; visual_analyses = []; interview_context = {}; qna_evaluations = []
        return redirect(url_for('login_html_route'))

@app.route('/capture_snapshot', methods=['POST'])
def capture_snapshot_route():
    try:
        if 'allowed_user_type' not in session: return jsonify({"error": "Unauthorized"}), 401
        data = request.get_json()
        image_data_url_snap = data.get('image_data_url')
        if not image_data_url_snap: return jsonify({"error": "No image data (image_data_url) received for snapshot."}), 400
        try:
            img_header, img_encoded_data = image_data_url_snap.split(",", 1); img_bytes = base64.b64decode(img_encoded_data)
            snap_ts = datetime.now().strftime("%Y%m%d_%H%M%S_frontend_snap"); snap_fname_fe = f"fe_snapshot_{snap_ts}.jpg"
            snap_fpath_fe = os.path.join('uploads', 'snapshots', snap_fname_fe)
            with open(snap_fpath_fe, "wb") as f_snap: f_snap.write(img_bytes)
            conn = sqlite3.connect('interview_data.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO snapshots (username, timestamp, image_path)
                VALUES (?, ?, ?)
            ''', (
                session.get('username', 'anonymous'),
                datetime.now().isoformat(),
                snap_fpath_fe
            ))
            conn.commit()
            conn.close()
            logging.info(f"Frontend snapshot saved successfully: {snap_fpath_fe}")
            return jsonify({"message": f"Snapshot captured from frontend and saved as {snap_fname_fe}."}), 200
        except ValueError: return jsonify({"error": "Invalid image data URL format for snapshot."}), 400
        except Exception as e_save_snap:
            logging.error(f"Error processing/saving frontend snapshot: {e_save_snap}", exc_info=True)
            return jsonify({"error": "Failed to process or save the snapshot data."}), 500
    except Exception as e_snap_route:
        logging.error(f"Error in /capture_snapshot route: {e_snap_route}", exc_info=True)
        return jsonify({"error": "Server error handling snapshot."}), 500

@app.route('/analyze_visuals', methods=['POST'])
def analyze_visuals_route():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        image_file = request.files['image']
        if not image_file.filename:
            return jsonify({'error': 'No image file selected'}), 400

        # Read image file
        image_bytes = image_file.read()
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({'error': 'Failed to decode image'}), 400

        # Analyze frame
        analysis_result = analyze_frame_for_visuals(frame)
        
        # Store analysis result
        with visual_analyses_lock:
            visual_analyses.append(analysis_result)
            # Keep only last 10 analyses
            if len(visual_analyses) > 10:
                visual_analyses.pop(0)

        return jsonify({'success': True, 'analysis': analysis_result})

    except Exception as e:
        logging.error(f"Error in analyze_visuals_route: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/start_interview', methods=['POST'])
def start_interview_route():
    global qna_evaluations, current_use_voice_mode, interview_context, listening_active, visual_analysis_thread, visual_analyses
    try:
        if 'allowed_user_type' not in session:
            return jsonify({"error": "Unauthorized"}), 401
            
        qna_evaluations = []
        visual_analyses = []
        current_use_voice_mode = request.form.get('mode') == 'voice'
        allowed_user_type_sess = session.get('allowed_user_type', 'MBA')
        job_key_map = 'mba' if allowed_user_type_sess == 'MBA' else 'bank'
        track_form = request.form.get('interview_track', 'resume')
        sub_track_form = request.form.get('sub_track', '')
        resume_file_form = request.files.get('resume')
        use_camera_feature = request.form.get('use_camera') == 'true'

        if not resume_file_form:
            return jsonify({"error": "No resume file provided"}), 400

        interview_context = interview_context_template.copy()
        interview_context['questions_already_asked'] = set()
        interview_context['generated_resume_questions_cache'] = []
        if visual_analysis_thread and visual_analysis_thread.is_alive():
            logging.warning("Start Interview: Previous visual analysis thread was active. Signaling it to stop.")
            old_thread = visual_analysis_thread
            visual_analysis_thread = None
            if old_thread and old_thread.is_alive():
                old_thread.join(timeout=0.5)
                if old_thread.is_alive():
                    logging.warning("Start Interview: Old visual thread did not stop quickly.")
            visual_analysis_thread = None
        visual_analysis_thread = None
        interview_context.update({
            'current_interview_track': track_form, 'current_sub_track': sub_track_form,
            'use_camera_feature': use_camera_feature,
            'current_job_description': f"{allowed_user_type_sess} Candidate for {track_form} track"
        })
        job_key_map = 'mba' if allowed_user_type_sess == 'MBA' else 'bank'
        resume_text_content = ""
        temp_resume_path_start = os.path.join('uploads', f"temp_resume_{session.get('username','default')}_{resume_file_form.filename}")
        try:
            resume_file_form.save(temp_resume_path_start)
            if temp_resume_path_start.lower().endswith('.pdf'):
                with pdfplumber.open(temp_resume_path_start) as pdf_doc: resume_text_content = ''.join(p.extract_text() or '' for p in pdf_doc.pages if p.extract_text())
            elif temp_resume_path_start.lower().endswith('.docx'): resume_text_content = docx2txt.process(temp_resume_path_start)
            else: return jsonify({"error": "Unsupported resume file type (PDF or DOCX only)."}), 400
            if not resume_text_content.strip(): resume_text_content = "Resume content seems empty or could not be extracted."
        except Exception as e_res_proc:
            logging.error(f"Error processing resume '{resume_file_form.filename}': {e_res_proc}", exc_info=True); return jsonify({"error": f"Could not process resume: {str(e_res_proc)}"}), 500
        finally:
            if os.path.exists(temp_resume_path_start):
                try: os.remove(temp_resume_path_start)
                except OSError as e_del_res: logging.warning(f"Could not delete temp resume file '{temp_resume_path_start}': {e_del_res}")
        if not interview_context['generated_resume_questions_cache']:
             interview_context['generated_resume_questions_cache'] = generate_resume_questions(resume_text_content, job_key_map, interview_context['questions_already_asked'])
        for q_res_gen in interview_context['generated_resume_questions_cache']:
            interview_context['questions_already_asked'].add(normalize_text(q_res_gen))
        current_q_list_intermediate = []
        job_specific_pdf_structure = structure.get(job_key_map, {})
        if job_key_map == 'mba':
            if track_form == "resume":
                predef_qs = [q_obj['text'] for q_obj in job_specific_pdf_structure.get('resume_flow', [])[:3]]
                current_q_list_intermediate = list(interview_context['generated_resume_questions_cache'])
                for q_pd in predef_qs:
                    if normalize_text(q_pd) not in interview_context['questions_already_asked']: current_q_list_intermediate.append(q_pd)
            elif track_form == "school_based":
                school_data = job_specific_pdf_structure.get('school_based', defaultdict(list))
                school_qs_track = [q_obj['text'] for q_obj in school_data.get(sub_track_form, [])]
                if not school_qs_track: school_qs_track = [q_obj['text'] for sub_list in school_data.values() for q_obj in sub_list]
                current_q_list_intermediate = list(interview_context['generated_resume_questions_cache'][:5])
                for q_school in school_qs_track:
                    if normalize_text(q_school) not in interview_context['questions_already_asked']: current_q_list_intermediate.append(q_school)
            elif track_form == "interest_areas":
                interest_data = job_specific_pdf_structure.get('interest_areas', defaultdict(list))
                interest_qs_track = [q_obj['text'] for q_obj in interest_data.get(sub_track_form, [])]
                if not interest_qs_track: interest_qs_track = [q_obj['text'] for sub_list in interest_data.values() for q_obj in sub_list]
                current_q_list_intermediate = list(interview_context['generated_resume_questions_cache'][:5])
                for q_interest in interest_qs_track:
                     if normalize_text(q_interest) not in interview_context['questions_already_asked']: current_q_list_intermediate.append(q_interest)
        elif job_key_map == 'bank':
            if track_form == "resume":
                predef_qs_bank = [q_obj['text'] for q_obj in job_specific_pdf_structure.get('resume_flow', [])[:3]]
                current_q_list_intermediate = list(interview_context['generated_resume_questions_cache'])
                for q_pd_bank in predef_qs_bank:
                    if normalize_text(q_pd_bank) not in interview_context['questions_already_asked']: current_q_list_intermediate.append(q_pd_bank)
            elif track_form == "bank_type":
                bank_type_data = job_specific_pdf_structure.get('bank_type', defaultdict(list))
                bank_qs_track = [q_obj['text'] for q_obj in bank_type_data.get(sub_track_form, [])]
                if not bank_qs_track: bank_qs_track = [q_obj['text'] for sub_list in bank_type_data.values() for q_obj in sub_list]
                current_q_list_intermediate = list(interview_context['generated_resume_questions_cache'][:5])
                for q_bank_type in bank_qs_track:
                    if normalize_text(q_bank_type) not in interview_context['questions_already_asked']: current_q_list_intermediate.append(q_bank_type)
            elif track_form == "technical_analytical":
                tech_ana_data = job_specific_pdf_structure.get('technical_analytical', defaultdict(list))
                tech_qs_track = [q_obj['text'] for q_obj in tech_ana_data.get(sub_track_form, [])]
                if not tech_qs_track: tech_qs_track = [q_obj['text'] for sub_list in tech_ana_data.values() for q_obj in sub_list]
                current_q_list_intermediate = list(interview_context['generated_resume_questions_cache'][:5])
                for q_tech in tech_qs_track:
                    if normalize_text(q_tech) not in interview_context['questions_already_asked']: current_q_list_intermediate.append(q_tech)
        final_interview_questions_for_session = []
        temp_asked_this_specific_list_build = set()
        for q_text_final_candidate in current_q_list_intermediate:
            stripped_q_final = strip_numbering(q_text_final_candidate)
            norm_stripped_q_final = normalize_text(stripped_q_final)
            if norm_stripped_q_final not in interview_context['questions_already_asked'] and \
               norm_stripped_q_final not in temp_asked_this_specific_list_build:
                final_interview_questions_for_session.append(stripped_q_final)
                temp_asked_this_specific_list_build.add(norm_stripped_q_final)
        interview_context['questions_list'] = final_interview_questions_for_session
        for q_final_sess in final_interview_questions_for_session:
            interview_context['questions_already_asked'].add(normalize_text(q_final_sess))
        if not interview_context['questions_list']:
            logging.warning(f"User's original logic yielded no questions for '{track_form}/{sub_track_form}'. Attempting to generate questions from OpenAI...")
            
            # Try to generate questions from OpenAI first
            try:
                if resume_text_content and resume_text_content != "Resume content appears to be empty or could not be extracted.":
                    # Try to generate more resume-based questions
                    additional_resume_qs = generate_resume_questions(resume_text_content, job_key_map, interview_context['questions_already_asked'])
                    if additional_resume_qs and len(additional_resume_qs) > 0:
                        interview_context['questions_list'] = additional_resume_qs[:5]  # Limit to 5 questions
                        for q_add in interview_context['questions_list']:
                            interview_context['questions_already_asked'].add(normalize_text(q_add))
                        logging.info(f"Generated {len(interview_context['questions_list'])} additional resume questions from OpenAI.")
                    else:
                        # If OpenAI fails, use minimal hardcoded fallbacks
                        logging.warning("OpenAI question generation failed. Using minimal hardcoded fallbacks.")
                        interview_context['questions_list'] = ["Please describe your most relevant experience.", "What are your key strengths for this role/program?"]
                        for q_fb_final in interview_context['questions_list']: 
                            interview_context['questions_already_asked'].add(normalize_text(q_fb_final))
                else:
                    # If no resume content, use minimal hardcoded fallbacks
                    logging.warning("No resume content available. Using minimal hardcoded fallbacks.")
                    interview_context['questions_list'] = ["Please describe your most relevant experience.", "What are your key strengths for this role/program?"]
                    for q_fb_final in interview_context['questions_list']: 
                        interview_context['questions_already_asked'].add(normalize_text(q_fb_final))
            except Exception as e_gen_qs:
                logging.error(f"Error generating additional questions: {e_gen_qs}. Using minimal hardcoded fallbacks.")
                interview_context['questions_list'] = ["Please describe your most relevant experience.", "What are your key strengths for this role/program?"]
                for q_fb_final in interview_context['questions_list']: 
                    interview_context['questions_already_asked'].add(normalize_text(q_fb_final))
        interview_context['icebreaker_was_prepended'] = False
        interview_context['prepended_icebreaker_text'] = None
        
        if not interview_context['questions_list']:
            logging.error("FATAL: No questions available for interview.")
            return jsonify({"error": "System could not prepare any questions."}), 500
            
        interview_context['current_q_idx'] = 0
        listening_active = True
        
        if interview_context['use_camera_feature']:
            visual_analyses = []
            visual_analysis_thread = threading.Thread(target=capture_and_analyze_visuals_thread_func, daemon=True)
            visual_analysis_thread.start()
            logging.info("Visual analysis background thread started.")
            
        logging.info(f"Interview starting for {allowed_user_type_sess}, track '{track_form}'. Total questions in list: {len(interview_context['questions_list'])}")
        return jsonify({
            "message": f"Starting {allowed_user_type_sess} interview. Focus: {track_form}.",
            "total_questions": len(interview_context['questions_list']),
            "current_question": interview_context['questions_list'][0],
            "question_number": 1,
            "use_voice": current_use_voice_mode,
            "use_camera": interview_context['use_camera_feature'],
            "listening_active": listening_active if current_use_voice_mode else False
        })
    except Exception as e_start_interview:
        logging.error(f"Critical error in /start_interview route: {e_start_interview}", exc_info=True)
        return jsonify({"error": f"A major server error occurred during interview setup: {str(e_start_interview)}"}), 500

def calculate_final_overall_score(current_qna_evaluations, visual_score_0_to_10_val=None):
    try:
        qna_max_score_contribution = 90.0; visual_max_score_contribution = 10.0
        actual_qna_score_total = sum(item.get("score", 0) for item in current_qna_evaluations if isinstance(item.get("score"), (int, float)))
        possible_qna_score_total = len(current_qna_evaluations) * 10
        if not current_qna_evaluations or possible_qna_score_total == 0:
            qna_percentage_achieved = 0.0
        else:
            qna_percentage_achieved = actual_qna_score_total / possible_qna_score_total
        qna_weighted_contribution = qna_percentage_achieved * qna_max_score_contribution
        visual_weighted_contribution = 0.0
        if isinstance(visual_score_0_to_10_val, (int, float)) and visual_score_0_to_10_val is not None:
            visual_percentage_achieved = visual_score_0_to_10_val / 10.0
            visual_weighted_contribution = visual_percentage_achieved * visual_max_score_contribution
        final_overall_score_calculated = qna_weighted_contribution + visual_weighted_contribution
        return round(max(0.0, min(100.0, final_overall_score_calculated)), 2)
    except Exception as e_calc_score:
        logging.error(f"Error calculating final overall score: {e_calc_score}", exc_info=True); return 0.0

@app.route('/submit_answer', methods=['POST'])
def submit_answer_route():
    global qna_evaluations, current_use_voice_mode, interview_context, listening_active, visual_analysis_thread
    try:
        if 'allowed_user_type' not in session:
            return jsonify({"error": "Unauthorized. Session may have expired."}), 401
        if not interview_context or 'questions_list' not in interview_context or \
           not isinstance(interview_context.get('questions_list'), list) or \
           'current_q_idx' not in interview_context:
            logging.error("Submit Answer: Interview context corrupted or not initialized.")
            visual_score_result = calculate_visual_score()
            calculated_final_visual_score = visual_score_result[0]
            visual_feedback_on_error = visual_score_result[1]
            overall_score_on_error = calculate_final_overall_score(qna_evaluations, calculated_final_visual_score)
            if interview_context.get('use_camera_feature', False) and visual_analysis_thread and visual_analysis_thread.is_alive():
                interview_context['use_camera_feature'] = False
                visual_analysis_thread.join(timeout=0.7)
                visual_analysis_thread = None
            return jsonify({
                "reply": "Critical error with session. Interview ending.",
                "finished": True,
                "evaluations": qna_evaluations,
                "overall_score": overall_score_on_error,
                "visual_score_details": {
                    "score": calculated_final_visual_score,
                    "feedback": visual_feedback_on_error
                },
                "status": "Error: Session Failure"
            }), 500
        if not request.is_json:
            return jsonify({"error": "Invalid request: JSON expected."}), 400
        data_payload = request.get_json()
        answer_text_from_user = data_payload.get('answer', "").strip()
        stop_interview_phrases = ["stop this interview", "end this interview", "stop the interview", "end the interview"]
        normalized_answer_for_check = answer_text_from_user.lower()
        user_wants_to_stop = any(stop_phrase in normalized_answer_for_check for stop_phrase in stop_interview_phrases)
        if user_wants_to_stop:
            user_name_log = session.get('username', 'N/A_User')
            logging.info(f"User '{user_name_log}' requested to stop/end interview. Answer: '{answer_text_from_user}'.")
            visual_score_result = calculate_visual_score()
            calculated_final_visual_score = visual_score_result[0]
            visual_feedback_on_stop = visual_score_result[1]
            overall_score_on_stop = calculate_final_overall_score(qna_evaluations, calculated_final_visual_score)
            job_description_for_feedback_gen = interview_context.get("current_job_description", f"{session.get('allowed_user_type', 'Candidate')} Profile")
            for eval_item_on_stop in qna_evaluations:
                if not eval_item_on_stop.get('feedback'):
                    eval_item_on_stop['feedback'] = generate_answer_feedback(
                        eval_item_on_stop.get('question', 'Unknown'),
                        eval_item_on_stop.get('answer', ''),
                        job_description_for_feedback_gen
                    )
            listening_active = False
            if interview_context.get('use_camera_feature', False) and visual_analysis_thread and visual_analysis_thread.is_alive():
                interview_context['use_camera_feature'] = False
                visual_analysis_thread.join(timeout=0.7)
                visual_analysis_thread = None
            return jsonify({
                "reply": "Interview stopped as per your request.",
                "finished": True,
                "evaluations": qna_evaluations,
                "overall_score": overall_score_on_stop,
                "visual_score_details": {
                    "score": calculated_final_visual_score,
                    "feedback": visual_feedback_on_stop
                },
                "status": "Disqualified: User Request"
            })
        current_question_idx_val = interview_context.get('current_q_idx', -1)
        if not (0 <= current_question_idx_val < len(interview_context['questions_list'])):
            logging.error(f"Submit Answer: Invalid current_q_idx ({current_question_idx_val}). List len ({len(interview_context.get('questions_list',[]))}). Ending.")
            vis_score_idx_err, vis_feed_idx_err = calculate_visual_score()
            overall_score_idx_err = calculate_final_overall_score(qna_evaluations, vis_score_idx_err)
            if interview_context.get('use_camera_feature', False) and visual_analysis_thread and visual_analysis_thread.is_alive():
                interview_context['use_camera_feature'] = False
                visual_analysis_thread.join(timeout=0.7)
                visual_analysis_thread = None
            return jsonify({
                "reply": "Issue with question sequence. Interview concluding.",
                "finished": True,
                "evaluations": qna_evaluations,
                "overall_score": overall_score_idx_err,
                "visual_score_details": {"score": vis_score_idx_err, "feedback": vis_feed_idx_err},
                "status": "Error: Q Index Problem"
            }), 500
        question_text_being_answered = interview_context['questions_list'][current_question_idx_val]
        answer_text_to_process = answer_text_from_user if answer_text_from_user else "No specific answer was provided."
        is_current_question_the_icebreaker = False
        if interview_context.get('icebreaker_was_prepended') and \
           current_question_idx_val == 0 and \
           question_text_being_answered == interview_context.get('prepended_icebreaker_text'):
            is_current_question_the_icebreaker = True
        job_key_for_ai = 'mba' if session.get('allowed_user_type') == 'MBA' else 'bank'
        job_desc_for_ai = interview_context.get("current_job_description", f"{session.get('allowed_user_type', 'Candidate')} Profile")
        conversational_ack_reply = generate_conversational_reply(answer_text_to_process, job_key_for_ai)
        ai_detailed_eval_str, ai_weighted_score_val = evaluate_response_with_ai_scoring(
            question_text_being_answered, answer_text_to_process, job_desc_for_ai
        )
        user_summary_feedback_str = generate_answer_feedback(
            question_text_being_answered, answer_text_to_process, job_desc_for_ai
        )
        qna_evaluations.append({
            "question": question_text_being_answered,
            "answer": answer_text_to_process,
            "evaluation": ai_detailed_eval_str,
            "score": ai_weighted_score_val,
            "feedback": user_summary_feedback_str
        })
        interview_context["previous_answers_list"].append(answer_text_to_process)
        interview_context["scores_list"].append(ai_weighted_score_val)
        interview_context['questions_already_asked'].add(normalize_text(question_text_being_answered))
        if is_current_question_the_icebreaker:
            logging.info("Answer to icebreaker received. Skipping follow-up for it. Resetting depth counter.")
            interview_context["question_depth_counter"] = 0
        else:
            current_depth = interview_context.get("question_depth_counter", 0)
            max_depth = interview_context.get("max_followup_depth", 2)
            if current_depth < max_depth:
                follow_up_q_generated_text = generate_next_question(
                    question_text_being_answered, answer_text_to_process, ai_weighted_score_val,
                    interview_context.get("current_interview_track", "unknown"), job_key_for_ai,
                    interview_context.get('questions_already_asked', set())
                )
                if follow_up_q_generated_text:
                    interview_context['questions_list'].insert(current_question_idx_val + 1, follow_up_q_generated_text)
                    interview_context['questions_already_asked'].add(normalize_text(follow_up_q_generated_text))
                    interview_context["question_depth_counter"] = current_depth + 1
                    logging.info(f"Follow-up inserted: '{follow_up_q_generated_text}'. Depth: {interview_context['question_depth_counter']}")
                else:
                    interview_context["question_depth_counter"] = 0
            else:
                interview_context["question_depth_counter"] = 0
        interview_context['current_q_idx'] += 1
        if interview_context['current_q_idx'] < len(interview_context['questions_list']):
            next_question_to_ask_text = interview_context['questions_list'][interview_context['current_q_idx']]
            # Ensure listening_active is set correctly for voice mode
            listening_active = current_use_voice_mode
            logging.debug(f"Submit Answer: Voice mode: {current_use_voice_mode}, Listening active: {listening_active}, Next question: '{next_question_to_ask_text[:50]}...'")
            return jsonify({
                "reply": conversational_ack_reply,
                "current_question": next_question_to_ask_text,
                "question_number": interview_context['current_q_idx'] + 1,
                "total_questions": len(interview_context['questions_list']),
                "next_question": True,
                "listening_active": listening_active,
                "use_voice": current_use_voice_mode
            })
        else:
            logging.info("All questions asked. Interview concluding normally.")
            visual_score_result = calculate_visual_score()
            final_visual_score_val_norm = visual_score_result[0]
            visual_feedback_text_norm = visual_score_result[1]
            overall_score_val_norm = calculate_final_overall_score(qna_evaluations, final_visual_score_val_norm)
            for eval_item_norm in qna_evaluations:
                if not eval_item_norm.get('feedback'):
                    eval_item_norm['feedback'] = generate_answer_feedback(
                        eval_item_norm.get('question', 'Unknown'),
                        eval_item_norm.get('answer', 'N/A'),
                        job_desc_for_ai
                    )
            listening_active = False
            if interview_context.get('use_camera_feature', False) and visual_analysis_thread and visual_analysis_thread.is_alive():
                interview_context['use_camera_feature'] = False
                visual_analysis_thread.join(timeout=0.7)
                visual_analysis_thread = None
            logging.debug(f"Interview End: Voice mode: {current_use_voice_mode}, Listening active: {listening_active}, Overall score: {overall_score_val_norm}")
            return jsonify({
                "reply": "Thank you for completing the interview.",
                "finished": True,
                "evaluations": qna_evaluations,
                "overall_score": overall_score_val_norm,
                "visual_score_details": {
                    "score": final_visual_score_val_norm,
                    "feedback": visual_feedback_text_norm
                },
                "status": "Completed Successfully"
            })
    except Exception as e_submit_ans:
        logging.error(f"Critical error in /submit_answer: {e_submit_ans}", exc_info=True)
        vis_score_exc, vis_feed_exc = calculate_visual_score()
        overall_score_exc = calculate_final_overall_score(qna_evaluations, vis_score_exc)
        if interview_context and interview_context.get('use_camera_feature', False) and visual_analysis_thread and visual_analysis_thread.is_alive():
            interview_context['use_camera_feature'] = False
            visual_analysis_thread.join(timeout=0.7)
            visual_analysis_thread = None
        logging.debug(f"Submit Answer Error: Voice mode: {current_use_voice_mode}, Listening active: {listening_active}")
        return jsonify({
            "error": f"Critical server error: {str(e_submit_ans)}.",
            "reply": "Unexpected problem processing answer.",
            "finished": True,
            "evaluations": qna_evaluations,
            "overall_score": overall_score_exc,
            "visual_score_details": {"score": vis_score_exc, "feedback": vis_feed_exc},
            "status": "Error: Unhandled Exception"
        }), 500

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.get_json()
        question = data.get('question')
        feedback = data.get('feedback')
        if not question or not feedback:
            return jsonify({'success': False, 'error': 'Incomplete data received.'}), 400
        feedback_entry = f"{datetime.now()} - Question: {question}\nFeedback: {feedback}\n\n"
        with open('feedback_log.txt', 'a', encoding='utf-8') as f:
            f.write(feedback_entry)
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error saving feedback: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Server error while saving feedback.'}), 500

@app.route('/submit_bulk_feedback', methods=['POST'])
def submit_bulk_feedback():
    try:
        data = request.get_json()
        entries = data.get('entries', [])
        if not entries:
            return jsonify({'success': False, 'error': 'No feedback entries received.'}), 400
        with open('bulk_feedback_log.txt', 'a', encoding='utf-8') as f:
            for entry in entries:
                question = entry.get('question')
                feedback = entry.get('feedback')
                f.write(f"{datetime.now()} - Question: {question}\nFeedback: {feedback}\n\n")
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Bulk feedback error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal error.'}), 500

@app.route('/generate_speech', methods=['POST'])
def generate_speech_route():
    try:
        if 'allowed_user_type' not in session:
            return jsonify({"error": "Unauthorized access."}), 401
        if not client:
            return jsonify({"error": "TTS service unavailable."}), 503
        if not request.is_json:
            return jsonify({"error": "Invalid request: JSON expected."}), 400
        # Log request details
        logging.debug(f"TTS Request: Content-Type: {request.content_type}, Headers: {dict(request.headers)}, JSON: {request.get_json()}")
        data_tts = request.get_json()
        text_for_speech = data_tts.get('text', '').strip()
        voice_model_selection = data_tts.get('voice', 'alloy')
        if not text_for_speech:
            logging.warning("TTS Request: No text provided for speech generation.")
            return jsonify({"error": "Text for speech required."}), 400
        supported_openai_voices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer', 'sage']
        final_voice_model = voice_model_selection if voice_model_selection in supported_openai_voices else 'alloy'
        logging.info(f"TTS Request: Generating speech for text '{text_for_speech[:50]}...' with voice '{final_voice_model}'.")
        openai_tts_response = client.audio.speech.create(
            model="tts-1",
            voice=final_voice_model,
            input=text_for_speech,
            response_format="mp3"
        )
        logging.info(f"TTS Response: Successfully generated audio for '{text_for_speech[:50]}...'.")
        return Response(openai_tts_response.content, mimetype='audio/mp3')
    except Exception as e_tts_route:
        logging.error(f"TTS Generation Error: {e_tts_route}", exc_info=True)
        error_message = f"TTS generation failed: {str(e_tts_route)}"
        if hasattr(e_tts_route, 'response') and e_tts_route.response:
            try:
                err_content = e_tts_route.response.json()
                error_message = f"TTS generation failed: {err_content.get('error', {}).get('message', str(e_tts_route))}"
            except:
                pass
        return jsonify({"error": error_message}), 500

def init_db():
    conn = sqlite3.connect('interview_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            timestamp TEXT,
            image_path TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            question TEXT,
            answer TEXT,
            evaluation TEXT,
            score INTEGER,
            feedback TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/submit_evaluations', methods=['POST'])
def submit_evaluations():
    try:
        data = request.get_json()
        evaluations = data.get('evaluations', [])
        conn = sqlite3.connect('interview_data.db')
        cursor = conn.cursor()
        for eval in evaluations:
            cursor.execute('''
                INSERT INTO evaluations (username, question, answer, evaluation, score, feedback, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                session.get('username', 'anonymous'),
                eval.get('question'),
                eval.get('answer'),
                eval.get('evaluation'),
                eval.get('score'),
                eval.get('feedback', ''),
                datetime.now().isoformat()
            ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error saving evaluations: {e}", exc_info=True)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/capture_initial_frame', methods=['POST'])
def capture_initial_frame_route():
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file provided'}), 400

        image_file = request.files['image']
        if not image_file.filename:
            return jsonify({'error': 'No image file selected'}), 400

        # Read and process the image
        image_bytes = image_file.read()
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return jsonify({'error': 'Failed to decode image'}), 400

        # Save the frame
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        frame_filename = f"initial_frame_{timestamp}.jpg"
        frame_path = os.path.join('uploads', 'snapshots', frame_filename)
        cv2.imwrite(frame_path, frame)

        # Convert frame to base64 for OpenAI
        _, buffer = cv2.imencode('.jpg', frame)
        image_data_url = f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"

        # Generate icebreaker question
        icebreaker_question = generate_environment_icebreaker_question(image_data_url)
        if not icebreaker_question:
            logging.warning("Failed to generate icebreaker question, using fallback")
            icebreaker_question = "I see you're ready for the interview. How are you feeling about this opportunity?"

        logging.info(f"Generated icebreaker question: {icebreaker_question}")
        
        return jsonify({
            'success': True,
            'icebreaker_question': icebreaker_question,
            'frame_saved': frame_filename
        })

    except Exception as e:
        logging.error(f"Error in capture_initial_frame_route: {str(e)}")
        return jsonify({'error': str(e)}), 500

def capture_and_analyze_visuals_thread_func():
    global visual_analyses, visual_analysis_thread, interview_context
    cap_visual = None; logging.info("Visual Analysis Thread: Started.")
    try:
        cap_visual = cv2.VideoCapture(0)
        if not cap_visual.isOpened(): logging.error("Visual Analysis Thread: Failed to open webcam."); return
        last_snapshot_taken_time = 0; snapshot_capture_interval = 30
        while True:
            current_context_active = interview_context
            use_camera_in_context = current_context_active.get('use_camera_feature', False) if current_context_active else False
            if not use_camera_in_context or visual_analysis_thread != threading.current_thread():
                logging.info(f"Visual Analysis Thread: Stopping. use_camera_in_context: {use_camera_in_context}, thread_match: {visual_analysis_thread == threading.current_thread()}.")
                break
            ret_frame, cv_frame_cap = cap_visual.read()
            if not ret_frame or cv_frame_cap is None:
                logging.warning("Visual Analysis Thread: Failed to capture frame."); time.sleep(0.25); continue
            analysis_data = analyze_frame_for_visuals(cv_frame_cap)
            with visual_analyses_lock:
                visual_analyses.append(analysis_data)
                # Keep only last 10 analyses
                if len(visual_analyses) > 10:
                    visual_analyses.pop(0)
            current_ts = time.time()
            if current_context_active.get('use_camera_feature', False) and (current_ts - last_snapshot_taken_time >= snapshot_capture_interval):
                dt_str_snap = datetime.now().strftime("%Y%m%d_%H%M%S")
                snap_filename_va = f"va_snapshot_{dt_str_snap}.jpg"
                snap_filepath_va = os.path.join('uploads', 'snapshots', snap_filename_va)
                try: cv2.imwrite(snap_filepath_va, cv_frame_cap); logging.info(f"Visual Analysis Thread: Snapshot saved: {snap_filepath_va}"); last_snapshot_taken_time = current_ts
                except Exception as e_snap_va: logging.error(f"Visual Analysis Thread: Failed to save snapshot: {e_snap_va}")
            time.sleep(0.3)
    except Exception as e_thread_va:
        logging.error(f"Visual Analysis Thread: Exception in main loop: {e_thread_va}", exc_info=True)
    finally:
        if cap_visual: cap_visual.release()
        logging.info("Visual Analysis Thread: Terminated and camera released.")

@app.route('/health')
def health_check():
    """Health check endpoint for production monitoring"""
    try:
        # Basic health checks
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'openai_client': client is not None,
            'camera_support': True,  # OpenCV is available
            'version': '1.0.0'
        }
        return jsonify(health_status), 200
    except Exception as e:
        logging.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001, host="0.0.0.0")
