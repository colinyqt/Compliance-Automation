import PyPDF2
import re
import json
import ollama
from typing import List, Dict, Optional

# Change to absolute import
from meter_analyzer.models.data_models import MeterRequirement

class DocumentParser:
    """Clean document parsing for tender files using Qwen"""
    
    @staticmethod
    def read_document(file_path: str) -> str:
        """Read PDF or text document"""
        file_path = file_path.strip('"\'')
        
        if file_path.lower().endswith('.pdf'):
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                return "\n".join(page.extract_text() for page in pdf_reader.pages)
        else:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
    
    @staticmethod
    def extract_meter_requirements(text: str) -> List[MeterRequirement]:
        """Extract meter requirements from document"""
        requirements = []
        
        # Look for structured meter clauses (like 1.20.x)
        meter_sections = DocumentParser._find_meter_sections(text)
        
        for section in meter_sections:
            req = DocumentParser._parse_meter_section(section)
            if req:
                requirements.append(req)
        
        return requirements
        
    # Include all other DocumentParser methods here
    # _find_meter_sections, _fallback_section_detection, etc.