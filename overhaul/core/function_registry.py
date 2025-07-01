# core/function_registry.py
from typing import Dict, List, Any

class DatabaseFunctionRegistry:
    """Registry of available database functions with metadata"""
    
    def __init__(self):
        self.functions = {}
    
    def register_database(self, db_name: str, wrapper):
        """Register all available functions for a database"""
        
        schema = wrapper.schema
        main_table = wrapper._detect_main_table()
        
        # Standard functions (always available)
        functions = {
            'get_all': {
                'description': f'Get all records from {main_table}',
                'parameters': [],
                'returns': 'List[Dict]',
                'example': f'databases.{db_name}.get_all()'
            },
            'search': {
                'description': 'Search records with criteria',
                'parameters': [{'name': 'criteria', 'type': 'Dict[str, Any]'}],
                'returns': 'List[Dict]',
                'example': f'databases.{db_name}.search({{"series_name": "PM5000"}})'
            },
            'get_series_summary': {
                'description': 'Get summary of available series',
                'parameters': [],
                'returns': 'List[Dict]',
                'example': f'databases.{db_name}.get_series_summary()'
            }
        }
        
        # Column-based functions
        if main_table in schema.tables:
            table_info = schema.tables[main_table]
            
            if 'series_name' in table_info.columns:
                functions['get_by_series'] = {
                    'description': 'Get records by series name',
                    'parameters': [{'name': 'series_name', 'type': 'str'}],
                    'returns': 'List[Dict]',
                    'example': f'databases.{db_name}.get_by_series("PM5000")'
                }
            
            if 'model_name' in table_info.columns:
                functions['get_specifications'] = {
                    'description': 'Get detailed specifications for a model',
                    'parameters': [{'name': 'model_name', 'type': 'str'}],
                    'returns': 'Dict',
                    'example': f'databases.{db_name}.get_specifications("PM5560")'
                }
        
        self.functions[db_name] = functions
    
    def get_available_functions(self, db_name: str) -> Dict[str, Any]:
        """Get all available functions for a database"""
        return self.functions.get(db_name, {})





