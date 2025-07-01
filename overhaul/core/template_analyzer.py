# core/template_analyzer.py
import re
import os
from typing import Dict, List, Any

class TemplateAnalyzer:
    """Analyzes YAML templates and validates database function calls"""
    
    def __init__(self, function_registry):
        self.registry = function_registry
    
    def validate_template(self, yaml_config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a YAML prompt configuration"""
        
        errors = []
        warnings = []
        
        # Check basic structure
        if 'name' not in yaml_config:
            warnings.append("No 'name' specified in configuration")
        
        # Check if databases exist
        databases = yaml_config.get('databases', {})
        for db_name, db_path in databases.items():
            if not os.path.exists(db_path):
                errors.append(f"Database file not found: {db_path}")
        
        # Check processing steps
        steps = yaml_config.get('processing_steps', [])
        if not steps:
            warnings.append("No processing steps defined")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }