# core/file_processor.py
import os
from pathlib import Path
from typing import Dict, Any

class FileProcessor:
    """Handle different file types for input processing"""
    
    def process_file(self, file_path: str) -> Dict[str, Any]:
        """Process a file and return its content with metadata"""
        
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        content = ""
        # Read content based on file type
        if path.suffix.lower() in ['.txt', '.md']:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        elif path.suffix.lower() == '.pdf':
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(path))
                content = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                content = f"[Binary file: {path.name}]"
        else:
            # For now, treat everything else as text
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(path, 'rb') as f:
                    content = f"[Binary file: {path.name}]"
        
        return {
            'name': path.name,
            'basename': path.stem,
            'extension': path.suffix,
            'size': path.stat().st_size,
            'content': content,
            'path': str(path.absolute())
        }