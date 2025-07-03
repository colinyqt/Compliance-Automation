import sqlite3
from typing import Dict, List, Any
import json

class DatabaseContextProvider:
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_full_context(self) -> Dict[str, Any]:
        """Get complete database context including schema and sample data"""
        context = {
            "schema": self.get_schema_info(),
            "sample_data": self.get_sample_data(),
            "data_patterns": self.analyze_data_patterns(),
            "query_hints": self.generate_query_hints()
        }
        return context
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get detailed schema information"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            schema_info = {}
            for table in tables:
                # Get column info
                cursor.execute(f"PRAGMA table_info({table});")
                columns = cursor.fetchall()
                
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                row_count = cursor.fetchone()[0]
                
                schema_info[table] = {
                    "columns": [{"name": col[1], "type": col[2], "nullable": not col[3]} for col in columns],
                    "row_count": row_count
                }
            
            return schema_info
    
    def get_sample_data(self, rows_per_table: int = 5) -> Dict[str, List[Any]]:
        """Get sample data from each table"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            sample_data = {}
            for table in tables:
                try:
                    cursor.execute(f"SELECT * FROM {table} LIMIT {rows_per_table};")
                    rows = cursor.fetchall()
                    
                    # Get column names
                    cursor.execute(f"PRAGMA table_info({table});")
                    columns = [col[1] for col in cursor.fetchall()]
                    
                    # Convert to list of dicts
                    sample_data[table] = [
                        dict(zip(columns, row)) for row in rows
                    ]
                except Exception as e:
                    sample_data[table] = f"Error: {str(e)}"
            
            return sample_data
    
    def analyze_data_patterns(self) -> Dict[str, Any]:
        """Analyze patterns in the data to help with querying"""
        patterns = {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            try:
                # Analyze common patterns in each table
                tables_to_analyze = ['CommunicationProtocols', 'Measurements', 'MeasurementAccuracy']
                
                for table in tables_to_analyze:
                    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
                    if cursor.fetchone():
                        patterns[table] = self._analyze_table_patterns(cursor, table)
                        
            except Exception as e:
                patterns['error'] = str(e)
        
        return patterns
    
    def _analyze_table_patterns(self, cursor, table: str) -> Dict[str, Any]:
        """Analyze patterns in a specific table"""
        patterns = {}
        
        try:
            # Get column info
            cursor.execute(f"PRAGMA table_info({table});")
            columns = [col[1] for col in cursor.fetchall()]
            
            # For text columns, get distinct values
            for column in columns:
                if column not in ['meter_id', 'id']:  # Skip ID columns
                    cursor.execute(f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT 10;")
                    distinct_values = [row[0] for row in cursor.fetchall()]
                    if distinct_values:
                        patterns[f"{column}_values"] = distinct_values
                        
        except Exception as e:
            patterns['error'] = str(e)
            
        return patterns
    
    def generate_query_hints(self) -> List[str]:
        """Generate hints for better querying based on data analysis"""
        hints = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            try:
                # Check for common relationships
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]
                
                if 'Meters' in tables and 'CommunicationProtocols' in tables:
                    hints.append("To find meters with specific communication: JOIN Meters with CommunicationProtocols on meter_id")
                
                if 'Meters' in tables and 'Measurements' in tables:
                    hints.append("To find meters with specific measurements: JOIN Meters with Measurements on meter_id")
                
                if 'Meters' in tables and 'MeasurementAccuracy' in tables:
                    hints.append("To find meters with specific accuracy: JOIN Meters with MeasurementAccuracy on meter_id")
                    
                # Analyze actual data patterns
                cursor.execute("SELECT protocol FROM CommunicationProtocols LIMIT 3;")
                protocols = [row[0] for row in cursor.fetchall()]
                if protocols:
                    hints.append(f"Common protocols include: {', '.join(set(protocols))}")
                
            except Exception as e:
                hints.append(f"Analysis error: {str(e)}")
        
        return hints
    
    def format_context_for_llm(self) -> str:
        """Format context in a way that's useful for LLMs"""
        context = self.get_full_context()
        
        formatted = "DATABASE CONTEXT:\n\n"
        
        # Schema summary
        formatted += "TABLES AND STRUCTURE:\n"
        for table, info in context['schema'].items():
            formatted += f"- {table} ({info['row_count']} rows): "
            col_names = [col['name'] for col in info['columns']]
            formatted += ", ".join(col_names) + "\n"
        
        formatted += "\nSAMPLE DATA PATTERNS:\n"
        for table, patterns in context['data_patterns'].items():
            if isinstance(patterns, dict):
                formatted += f"\n{table}:\n"
                for pattern_key, values in patterns.items():
                    if isinstance(values, list) and values:
                        formatted += f"  {pattern_key}: {', '.join(map(str, values[:5]))}\n"
        
        formatted += "\nQUERY HINTS:\n"
        for hint in context['query_hints']:
            formatted += f"- {hint}\n"
        
        return formatted