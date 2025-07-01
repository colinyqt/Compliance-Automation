# core/database_autodiscovery.py
import sqlite3
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

@dataclass
class TableInfo:
    name: str
    columns: List[str]
    primary_key: str
    foreign_keys: List[Dict[str, str]]
    row_count: int

@dataclass
class DatabaseSchema:
    path: str
    tables: Dict[str, TableInfo]
    relationships: List[Dict[str, Any]]
    suggested_queries: Dict[str, str]

class DatabaseAutoDiscovery:
    """Automatically discover database schema and generate smart queries"""
    
    def __init__(self):
        self.discovered_schemas = {}
    
    def discover_database(self, db_path: str) -> DatabaseSchema:
        """Analyze database and discover its structure"""
        
        if db_path in self.discovered_schemas:
            return self.discovered_schemas[db_path]
        
        print(f"🔍 Auto-discovering database schema: {os.path.basename(db_path)}")
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Get all tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                table_names = [row[0] for row in cursor.fetchall()]
                
                tables = {}
                relationships = []
                
                for table_name in table_names:
                    table_info = self._analyze_table(cursor, table_name)
                    tables[table_name] = table_info
                    
                    # Detect relationships
                    for fk in table_info.foreign_keys:
                        relationships.append({
                            'from_table': table_name,
                            'from_column': fk['column'],
                            'to_table': fk['referenced_table'],
                            'to_column': fk['referenced_column']
                        })
                
                # Generate smart queries based on discovered schema
                suggested_queries = self._generate_smart_queries(tables, relationships)
                
                schema = DatabaseSchema(
                    path=db_path,
                    tables=tables,
                    relationships=relationships,
                    suggested_queries=suggested_queries
                )
                
                self.discovered_schemas[db_path] = schema
                
                print(f"✅ Discovered {len(tables)} tables with {len(relationships)} relationships")
                return schema
                
        except Exception as e:
            print(f"❌ Error discovering database {db_path}: {e}")
            return DatabaseSchema(db_path, {}, [], {})
    
    def _analyze_table(self, cursor, table_name: str) -> TableInfo:
        """Analyze individual table structure"""
        
        # Get column information
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns_info = cursor.fetchall()
        
        columns = [col[1] for col in columns_info]
        primary_key = next((col[1] for col in columns_info if col[5] == 1), 'id')
        
        # Get foreign key information
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        fk_info = cursor.fetchall()
        
        foreign_keys = []
        for fk in fk_info:
            foreign_keys.append({
                'column': fk[3],
                'referenced_table': fk[2],
                'referenced_column': fk[4]
            })
        
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = cursor.fetchone()[0]
        
        return TableInfo(
            name=table_name,
            columns=columns,
            primary_key=primary_key,
            foreign_keys=foreign_keys,
            row_count=row_count
        )
    
    def _generate_smart_queries(self, tables: Dict[str, TableInfo], relationships: List[Dict]) -> Dict[str, str]:
        """Generate intelligent queries based on discovered schema"""
        
        queries = {}
        
        for table_name, table_info in tables.items():
            base_name = table_name.lower()
            
            # Basic queries
            queries[f"get_all_{base_name}"] = f"SELECT * FROM {table_name} ORDER BY {table_info.primary_key}"
            
            # Search by common patterns
            if 'name' in table_info.columns:
                queries[f"get_{base_name}_by_name"] = f"SELECT * FROM {table_name} WHERE name = :name"
                queries[f"search_{base_name}_by_name"] = f"SELECT * FROM {table_name} WHERE name LIKE :pattern"
            
            if 'model_name' in table_info.columns:
                queries[f"get_{base_name}_by_model"] = f"SELECT * FROM {table_name} WHERE model_name = :model_name"
            
            if 'series_name' in table_info.columns:
                queries[f"get_{base_name}_by_series"] = f"SELECT * FROM {table_name} WHERE series_name = :series_name"
        
        return queries

class SmartDatabaseWrapper:
    """Wrapper that provides intelligent database access in templates"""
    
    def __init__(self, db_path: str, discovery_engine: DatabaseAutoDiscovery):
        self.db_path = db_path
        self.schema = discovery_engine.discover_database(db_path)
        self.discovery_engine = discovery_engine
    
    def get_all(self, table_name: str = None) -> List[Dict]:
        """Get all records from main table or specified table"""
        if not table_name:
            table_name = self._detect_main_table()
        
        if not table_name or table_name not in self.schema.tables:
            return []
        
        query = f"SELECT * FROM {table_name} ORDER BY {self.schema.tables[table_name].primary_key} LIMIT 100"
        return self._execute_query(query)
    
    def get_by_series(self, series_name: str) -> List[Dict]:
        """Get records by series (auto-detects series column)"""
        main_table = self._detect_main_table()
        
        if main_table and 'series_name' in self.schema.tables[main_table].columns:
            query = f"SELECT * FROM {main_table} WHERE series_name = ? LIMIT 50"
            return self._execute_query(query, (series_name,))
        return []
    
    def get_specifications(self, model_name: str) -> Dict:
        """Get detailed specifications with related data"""
        main_table = self._detect_main_table()
        
        if not main_table:
            return {}
        
        # Start with basic query
        query = f"SELECT * FROM {main_table} WHERE model_name = ? LIMIT 1"
        results = self._execute_query(query, (model_name,))
        
        if not results:
            return {}
        
        base_result = results[0]
        
        # Add related data from foreign key relationships
        meter_id = base_result.get('id')
        if meter_id:
            # Get related specifications
            for rel in self.schema.relationships:
                if rel['from_table'] == main_table:
                    related_table = rel['to_table']
                    related_query = f"SELECT * FROM {related_table} WHERE {rel['to_column']} = ?"
                    related_data = self._execute_query(related_query, (meter_id,))
                    
                    if related_data:
                        base_result[f"{related_table.lower()}_data"] = related_data
        
        return base_result
    
    def get_series_summary(self) -> List[Dict]:
        """Get summary of available series"""
        main_table = self._detect_main_table()
        
        if main_table and 'series_name' in self.schema.tables[main_table].columns:
            query = f"""
                SELECT series_name, COUNT(*) as model_count,
                       GROUP_CONCAT(model_name, ', ') as sample_models
                FROM {main_table}
                GROUP BY series_name
                ORDER BY series_name
            """
            return self._execute_query(query)
        return []
    
    def search(self, criteria: Dict[str, Any]) -> List[Dict]:
        """Smart search based on provided criteria"""
        main_table = self._detect_main_table()
        
        if not main_table:
            return []
        
        where_clauses = []
        params = []
        
        for key, value in criteria.items():
            if key in self.schema.tables[main_table].columns:
                if isinstance(value, str) and '%' in value:
                    where_clauses.append(f"{key} LIKE ?")
                else:
                    where_clauses.append(f"{key} = ?")
                params.append(value)
        
        if where_clauses:
            query = f"SELECT * FROM {main_table} WHERE {' AND '.join(where_clauses)} LIMIT 50"
            return self._execute_query(query, params)
        
        return self.get_all()
    
    def _detect_main_table(self) -> str:
        """Auto-detect the main table (usually has most rows or central relationships)"""
        if not self.schema.tables:
            return ""
        
        # Heuristics for main table detection
        candidates = []
        
        for table_name, table_info in self.schema.tables.items():
            score = 0
            
            # Higher score for more rows
            score += table_info.row_count / 100
            
            # Higher score for tables that are referenced by others
            references = len([r for r in self.schema.relationships if r['to_table'] == table_name])
            score += references * 10
            
            # Higher score for common main table names
            if table_name.lower() in ['meters', 'products', 'items', 'main']:
                score += 50
            
            candidates.append((table_name, score))
        
        if candidates:
            return max(candidates, key=lambda x: x[1])[0]
        return ""
    
    def _execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute query and return results as dictionaries"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

    def query(self, sql, params=None):
        """Run a raw SQL query and return results as a list of dicts."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

class AutoDiscoveryDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self.schema = self._discover_schema()
    
    def _discover_schema(self):
        """Automatically discover database structure"""
        schema = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all tables
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    # Get columns for each table
                    cursor.execute(f"PRAGMA table_info({table})")
                    columns = [row[1] for row in cursor.fetchall()]
                    
                    # Get sample data
                    cursor.execute(f"SELECT * FROM {table} LIMIT 3")
                    sample_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    
                    schema[table] = {
                        'columns': columns,
                        'sample_data': sample_data,
                        'row_count': self._get_table_count(cursor, table)
                    }
                    
        except Exception as e:
            print(f"Schema discovery failed: {e}")
        
        return schema
    
    def _get_table_count(self, cursor, table):
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
    
    def query(self, sql, params=None):
        """Generic query method"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Query failed: {e}")
            return []
    
    def get_table_summary(self, table_name):
        """Get summary of any table"""
        if table_name not in self.schema:
            return {}
        
        return {
            'total_rows': self.schema[table_name]['row_count'],
            'columns': self.schema[table_name]['columns'],
            'sample_data': self.schema[table_name]['sample_data']
        }
    # In your pipeline setup
databases = {
    'meters': AutoDiscoveryDatabase('C:\\Users\\cyqt2\\Database\\testing.db')
}

# The YAML template will now have access to:
# - databases.meters.schema (auto-discovered structure)
# - databases.meters.query() (generic SQL queries)
# - databases.meters.get_table_summary() (table summaries)