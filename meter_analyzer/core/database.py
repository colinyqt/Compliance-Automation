import sqlite3
import re
import json
import ollama
import os
from typing import List, Dict, Optional

# Change to absolute import
from meter_analyzer.models.data_models import MeterRequirement, MeterMatch

class MeterDatabase:
    """Single-AI interface to meters.db using Qwen"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._validate_database()
        self.model = "qwen2.5-coder:7b"  # Single model for everything
    
    def _validate_database(self):
        """Ensure database exists and has expected structure"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                if 'Products' not in tables:
                    raise ValueError("Products table not found in database")
        except Exception as e:
            raise ValueError(f"Database validation failed: {e}")
    
    def get_meter_count(self) -> int:
        """Get total number of meters in database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Products")
            return cursor.fetchone()[0]
    
    def search_meters(self, requirement: MeterRequirement) -> List[MeterMatch]:
        """AI-enhanced meter search with contextual understanding"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get all potentially relevant meters (broader search)
            candidate_meters = self._get_candidate_meters(cursor, requirement)
            
            if not candidate_meters:
                return []
            
            # Use AI to analyze and rank meters contextually
            ranked_meters = self._ai_rank_meters(requirement, candidate_meters)
            
            return ranked_meters[:5]  # Return top 5 matches
            
    # Include all other MeterDatabase methods here
    # _get_candidate_meters, _fallback_conditions, _ai_rank_meters, etc.