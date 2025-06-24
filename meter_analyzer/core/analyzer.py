import os
import datetime
from typing import List, Dict

# Change to absolute imports
from meter_analyzer.models.data_models import MeterRequirement, MeterMatch
from meter_analyzer.core.database import MeterDatabase
from meter_analyzer.core.parser import DocumentParser

class MeterAnalyzer:
    """Main analyzer class with single Qwen model"""
    
    def __init__(self, db_path: str):
        self.database = MeterDatabase(db_path)
        self.parser = DocumentParser()
    
    def analyze_document(self, tender_file: str) -> List[Dict]:
        """Analyze tender document using Qwen"""
        print("SCHNEIDER ELECTRIC METER ANALYZER (Qwen Enhanced)")
        print("=" * 55)
        print(f"Database: {self.database.db_path}")
        print(f"Total meters available: {self.database.get_meter_count()}")
        print(f"AI Model: {self.database.model}")
        
        # Read and parse document (using Qwen)
        print(f"\n📄 Reading document with Qwen: {tender_file}")
        document_text = self.parser.read_document(tender_file)
        print(f"Document length: {len(document_text):,} characters")
        
        # Extract requirements (using Qwen)
        print("\n🧠 Qwen extracting meter requirements...")
        requirements = self.parser.extract_meter_requirements(document_text)
        print(f"Found {len(requirements)} actionable requirements")
        
        if not requirements:
            print("No actionable meter requirements found")
            return []
        
        # Find meter matches using Qwen
        print("\n🤖 Qwen analysis pipeline starting...")
        results = []
        
        # Rest of the analyze_document method...
        
    def export_to_txt(self, results: List[Dict], tender_file: str) -> str:
        """Export analysis results to a text file"""
        # Export method implementation...