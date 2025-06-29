#!/usr/bin/env python3
"""
Test script to verify PDF loading functionality
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Add current directory to path to import main module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_pdf_loading():
    """Test the PDF loading functionality"""
    
    # Import the function from main.py
    try:
        from main import load_questions_into_memory, structure
    except ImportError as e:
        print(f"Error importing from main.py: {e}")
        return False
    
    # Test files
    test_files = [
        ('MBA_Question.pdf', 'mba'),
        ('Bank_Question.pdf', 'bank')
    ]
    
    success_count = 0
    
    for pdf_file, section_type in test_files:
        print(f"\n{'='*50}")
        print(f"Testing {pdf_file} for {section_type} section")
        print(f"{'='*50}")
        
        if not os.path.exists(pdf_file):
            print(f"❌ File {pdf_file} not found")
            continue
        
        # Clear the structure for this section type
        if section_type == 'mba':
            structure['mba']['resume_flow'] = []
            structure['mba']['school_based'] = {'IIM': [], 'ISB': [], 'Other': []}
            structure['mba']['interest_areas'] = {'General Business': [], 'Finance': [], 'Marketing': [], 'Operations': []}
        elif section_type == 'bank':
            structure['bank']['resume_flow'] = []
            structure['bank']['bank_type'] = {'Public Sector Banks': [], 'Private Banks': [], 'Regulatory Roles': []}
            structure['bank']['technical_analytical'] = {'Banking Knowledge': [], 'Logical Reasoning': [], 'Situational Judgement': [], 'Current Affairs': []}
        
        # Test loading
        result = load_questions_into_memory(pdf_file, section_type)
        
        if result:
            print(f"✅ Successfully loaded {pdf_file}")
            success_count += 1
            
            # Count questions loaded
            total_questions = 0
            if section_type == 'mba':
                total_questions += len(structure['mba']['resume_flow'])
                for school_type in structure['mba']['school_based'].values():
                    total_questions += len(school_type)
                for area in structure['mba']['interest_areas'].values():
                    total_questions += len(area)
            elif section_type == 'bank':
                total_questions += len(structure['bank']['resume_flow'])
                for bank_type in structure['bank']['bank_type'].values():
                    total_questions += len(bank_type)
                for tech_area in structure['bank']['technical_analytical'].values():
                    total_questions += len(tech_area)
            
            print(f"📊 Loaded {total_questions} questions total")
            
            # Show some sample questions
            if section_type == 'mba' and structure['mba']['resume_flow']:
                print(f"📝 Sample resume question: {structure['mba']['resume_flow'][0]['text']}")
            elif section_type == 'bank' and structure['bank']['resume_flow']:
                print(f"📝 Sample resume question: {structure['bank']['resume_flow'][0]['text']}")
                
        else:
            print(f"❌ Failed to load {pdf_file}")
    
    print(f"\n{'='*50}")
    print(f"Test Results: {success_count}/{len(test_files)} files loaded successfully")
    print(f"{'='*50}")
    
    return success_count == len(test_files)

if __name__ == "__main__":
    print("Testing PDF Loading Functionality")
    print("This script tests the improved PDF loading with multiple fallback methods")
    
    success = test_pdf_loading()
    
    if success:
        print("\n🎉 All tests passed! PDF loading is working correctly.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Check the logs above for details.")
        sys.exit(1) 