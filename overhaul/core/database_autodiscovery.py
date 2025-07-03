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
                    
                    # Detect explicit foreign key relationships
                    for fk in table_info.foreign_keys:
                        relationships.append({
                            'from_table': table_name,
                            'from_column': fk['column'],
                            'to_table': fk['referenced_table'],
                            'to_column': fk['referenced_column']
                        })
                
                # Detect implicit relationships based on naming conventions
                implicit_relationships = self._detect_implicit_relationships(tables)
                print(f"🔍 Detected {len(implicit_relationships)} implicit relationships")
                for rel in implicit_relationships:
                    print(f"   {rel['from_table']}.{rel['from_column']} -> {rel['to_table']}.{rel['to_column']}")
                
                relationships.extend(implicit_relationships)
                
                # Remove duplicate relationships
                seen = set()
                unique_relationships = []
                for rel in relationships:
                    key = (rel['from_table'], rel['from_column'], rel['to_table'], rel['to_column'])
                    if key not in seen:
                        seen.add(key)
                        unique_relationships.append(rel)
                
                # Generate smart queries based on discovered schema
                suggested_queries = self._generate_smart_queries(tables, unique_relationships)
                
                schema = DatabaseSchema(
                    path=db_path,
                    tables=tables,
                    relationships=unique_relationships,
                    suggested_queries=suggested_queries
                )
                
                self.discovered_schemas[db_path] = schema
                
                print(f"✅ Discovered {len(tables)} tables with {len(relationships)} relationships")
                print(f"✅ Generated {len(suggested_queries)} smart functions")
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
        primary_key = next((col[1] for col in columns_info if col[5] == 1), None)
        
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
            primary_key=primary_key or "",
            foreign_keys=foreign_keys,
            row_count=row_count
        )
    def _detect_implicit_relationships(self, tables: Dict[str, TableInfo]) -> List[Dict]:
        """Dynamically detect implicit relationships based on naming conventions and data patterns"""
        relationships = []
        
        # Get all table names and their primary keys
        table_primary_keys = {name: info.primary_key for name, info in tables.items()}
        
        for table_name, table_info in tables.items():
            for column in table_info.columns:
                # Pattern 1: column_name_id -> table_name.id (exact match)
                if column.endswith('_id') and column != table_info.primary_key:
                    potential_table = column[:-3]  # Remove '_id' suffix
                    if potential_table in tables:
                        relationships.append({
                            'from_table': table_name,
                            'from_column': column,
                            'to_table': potential_table,
                            'to_column': tables[potential_table].primary_key
                        })
                    else:
                        # Pattern 2: Try singular/plural variations
                        # Try singular form (e.g., meter_id -> Meter)
                        if potential_table in tables:
                            relationships.append({
                                'from_table': table_name,
                                'from_column': column,
                                'to_table': potential_table,
                                'to_column': tables[potential_table].primary_key
                            })
                        else:
                            # Try plural form (e.g., meter_id -> Meters)
                            potential_table_plural = potential_table + 's'
                            if potential_table_plural in tables:
                                relationships.append({
                                    'from_table': table_name,
                                    'from_column': column,
                                    'to_table': potential_table_plural,
                                    'to_column': tables[potential_table_plural].primary_key
                                })
                
                # Pattern 3: column_name -> table_name.column_name (for direct matches)
                elif column in tables and column != table_name:
                    relationships.append({
                        'from_table': table_name,
                        'from_column': column,
                        'to_table': column,
                        'to_column': tables[column].primary_key
                    })
        
        return relationships
    
    def _generate_smart_queries(self, tables: Dict[str, TableInfo], relationships: List[Dict]) -> Dict[str, str]:
        """Generate intelligent queries based on discovered schema"""
        
        queries = {}
        
        for table_name, table_info in tables.items():
            base_name = table_name.lower()
            
            # Basic queries
            if table_info.primary_key and table_info.primary_key in table_info.columns:
                queries[f"get_all_{base_name}"] = f"SELECT * FROM {table_name} ORDER BY {table_info.primary_key}"
            else:
                queries[f"get_all_{base_name}"] = f"SELECT * FROM {table_name}"
            
            # Search by common patterns for any column ending with 'name'
            name_columns = [col for col in table_info.columns if col.endswith('name')]
            for name_col in name_columns:
                queries[f"get_{base_name}_by_{name_col}"] = f"SELECT * FROM {table_name} WHERE {name_col} = :{name_col}"
                queries[f"search_{base_name}_by_{name_col}"] = f"SELECT * FROM {table_name} WHERE {name_col} LIKE :pattern"
            
            # Search by any ID column
            id_columns = [col for col in table_info.columns if col.endswith('id') and col != table_info.primary_key]
            for id_col in id_columns:
                queries[f"get_{base_name}_by_{id_col}"] = f"SELECT * FROM {table_name} WHERE {id_col} = :{id_col}"
            
            # Search by any category-like column
            category_columns = [col for col in table_info.columns if any(keyword in col.lower() for keyword in ['type', 'category', 'class', 'group', 'series'])]
            for cat_col in category_columns:
                queries[f"get_{base_name}_by_{cat_col}"] = f"SELECT * FROM {table_name} WHERE {cat_col} = :{cat_col}"
        
        # Generate relationship-aware queries
        for rel in relationships:
            from_table = rel['from_table']
            to_table = rel['to_table']
            from_col = rel['from_column']
            to_col = rel['to_column']
            
            # Join queries
            queries[f"get_{from_table}_with_{to_table}"] = f"""
                SELECT {from_table}.*, {to_table}.* 
                FROM {from_table} 
                LEFT JOIN {to_table} ON {from_table}.{from_col} = {to_table}.{to_col}
            """
            
            # Reverse join queries
            queries[f"get_{to_table}_with_{from_table}"] = f"""
                SELECT {to_table}.*, {from_table}.* 
                FROM {to_table} 
                LEFT JOIN {from_table} ON {to_table}.{to_col} = {from_table}.{from_col}
            """
        
        return queries

class SmartDatabaseWrapper:
    """Wrapper that provides intelligent database access in templates"""
    
    def __init__(self, db_path: str, discovery_engine: DatabaseAutoDiscovery):
        self.db_path = db_path
        self.schema = discovery_engine.discover_database(db_path)
        self.discovery_engine = discovery_engine
        
        print(f"🔧 SmartDatabaseWrapper created for {os.path.basename(db_path)}")
        print(f"🔧 Schema has {len(self.schema.suggested_queries)} suggested queries")
    
    def get_available_functions(self) -> List[str]:
        """Return list of all available database functions - CRITICAL METHOD"""
        functions = list(self.schema.suggested_queries.keys())
        print(f"🔧 get_available_functions() returning {len(functions)} functions: {functions}")
        return functions
    
    def get_all(self, table_name: Optional[str] = None) -> List[Dict]:
        """Get all records from main table or specified table"""
        if not table_name:
            table_name = self._detect_main_table()
        
        if not table_name or table_name not in self.schema.tables:
            return []
        
        table_info = self.schema.tables[table_name]
        if table_info.primary_key and table_info.primary_key in table_info.columns:
            query = f"SELECT * FROM {table_name} ORDER BY {table_info.primary_key} LIMIT 100"
        else:
            query = f"SELECT * FROM {table_name} LIMIT 100"
        return self._execute_query(query)
    
    def get_by_category(self, category_column: str, category_value: str) -> List[Dict]:
        """Get records by any category column (auto-detects available category columns)"""
        main_table = self._detect_main_table()
        
        if main_table and category_column in self.schema.tables[main_table].columns:
            query = f"SELECT * FROM {main_table} WHERE {category_column} = ? LIMIT 50"
            return self._execute_query(query, (category_value,))
        return []
    
    def get_detailed_record(self, record_id: Any, id_column: Optional[str] = None) -> Dict:
        """Get detailed record with all related data using discovered relationships"""
        main_table = self._detect_main_table()
        
        if not main_table:
            return {}
        
        # Determine the ID column to use
        if not id_column:
            id_column = self.schema.tables[main_table].primary_key
        
        # Start with basic query
        query = f"SELECT * FROM {main_table} WHERE {id_column} = ? LIMIT 1"
        results = self._execute_query(query, (record_id,))
        
        if not results:
            return {}
        
        base_result = results[0]
        
        # Add related data from foreign key relationships
        record_id_value = base_result.get(id_column)
        if record_id_value:
            # Get related data
            for rel in self.schema.relationships:
                if rel['from_table'] == main_table:
                    related_table = rel['to_table']
                    related_query = f"SELECT * FROM {related_table} WHERE {rel['to_column']} = ?"
                    related_data = self._execute_query(related_query, (record_id_value,))
                    
                    if related_data:
                        base_result[f"{related_table.lower()}_data"] = related_data
        
        return base_result
    
    def get_category_summary(self, category_column: str) -> List[Dict]:
        """Get summary of any category column (auto-detects available category columns)"""
        main_table = self._detect_main_table()
        
        if main_table and category_column in self.schema.tables[main_table].columns:
            table_info = self.schema.tables[main_table]
            pk = table_info.primary_key if table_info.primary_key and table_info.primary_key in table_info.columns else None
            if pk:
                query = f"""
                    SELECT {category_column}, COUNT(*) as count,
                           GROUP_CONCAT({pk}, ', ') as sample_ids
                    FROM {main_table}
                    GROUP BY {category_column}
                    ORDER BY {category_column}
                """
            else:
                query = f"""
                    SELECT {category_column}, COUNT(*) as count
                    FROM {main_table}
                    GROUP BY {category_column}
                    ORDER BY {category_column}
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
    
    # GENERIC SCHEMA-AWARE METHODS (work with ANY database)
    def get_all_with_related_data(self, table_name: Optional[str] = None) -> List[Dict]:
        """Get all records from a table with all related data using discovered schema"""
        if not table_name:
            table_name = self._detect_main_table()
        
        if not table_name or table_name not in self.schema.tables:
            return []
        
        table_info = self.schema.tables[table_name]
        if table_info.primary_key and table_info.primary_key in table_info.columns:
            base_query = f"SELECT * FROM {table_name} ORDER BY {table_info.primary_key} LIMIT 100"
        else:
            base_query = f"SELECT * FROM {table_name} LIMIT 100"
        base_data = self._execute_query(base_query)
        
        # If no relationships exist, just return the base data
        if not self.schema.relationships:
            return base_data
        
        # Try to build comprehensive query with relationships
        try:
            select_parts = [f"{table_name}.*"]
            join_parts = []
            
            for rel in self.schema.relationships:
                if rel['from_table'] == table_name:
                    related_table = rel['to_table']
                    select_parts.append(f"{related_table}.*")
                    join_parts.append(f"LEFT JOIN {related_table} ON {table_name}.{rel['from_column']} = {related_table}.{rel['to_column']}")
                elif rel['to_table'] == table_name:
                    related_table = rel['from_table']
                    select_parts.append(f"{related_table}.*")
                    join_parts.append(f"LEFT JOIN {related_table} ON {table_name}.{rel['to_column']} = {related_table}.{rel['from_column']}")
            
            if join_parts:
                query = f"""
                    SELECT {', '.join(select_parts)}
                    FROM {table_name}
                    {' '.join(join_parts)}
                    ORDER BY {table_name}.{table_info.primary_key}
                    LIMIT 100
                """
                return self._execute_query(query)
            else:
                return base_data
                
        except Exception as e:
            print(f"⚠️ Relationship query failed, falling back to base data: {e}")
            return base_data
    
    def get_table_data(self, table_name: str, limit: int = 100) -> List[Dict]:
        """Get data from any table by name"""
        if table_name not in self.schema.tables:
            return []
        
        table_info = self.schema.tables[table_name]
        if table_info.primary_key and table_info.primary_key in table_info.columns:
            query = f"SELECT * FROM {table_name} ORDER BY {table_info.primary_key} LIMIT {limit}"
        else:
            query = f"SELECT * FROM {table_name} LIMIT {limit}"
        return self._execute_query(query)
    
    def get_related_data(self, table_name: str, record_id: Any, id_column: str = 'id') -> Dict[str, List[Dict]]:
        """Get all related data for a specific record"""
        if table_name not in self.schema.tables:
            return {}
        
        related_data = {}
        
        for rel in self.schema.relationships:
            if rel['from_table'] == table_name:
                related_table = rel['to_table']
                related_query = f"SELECT * FROM {related_table} WHERE {rel['to_column']} = ?"
                data = self._execute_query(related_query, (record_id,))
                if data:
                    related_data[related_table] = data
            elif rel['to_table'] == table_name:
                related_table = rel['from_table']
                related_query = f"SELECT * FROM {related_table} WHERE {rel['from_column']} = ?"
                data = self._execute_query(related_query, (record_id,))
                if data:
                    related_data[related_table] = data
        
        return related_data
    
    def find_tables_by_keyword(self, keyword: str) -> List[str]:
        """Find tables that contain a keyword in their name"""
        keyword_lower = keyword.lower()
        return [table_name for table_name in self.schema.tables if keyword_lower in table_name.lower()]
    
    def get_tables_with_column(self, column_name: str) -> List[str]:
        """Find all tables that have a specific column"""
        matching_tables = []
        for table_name, table_info in self.schema.tables.items():
            if column_name in table_info.columns:
                matching_tables.append(table_name)
        return matching_tables
    
    def get_table_summary(self, table_name: str) -> Dict[str, Any]:
        """Get summary information about a table"""
        if table_name not in self.schema.tables:
            return {}
        
        table_info = self.schema.tables[table_name]
        
        # Get sample data
        sample_query = f"SELECT * FROM {table_name} LIMIT 3"
        sample_data = self._execute_query(sample_query)
        
        return {
            'name': table_name,
            'columns': table_info.columns,
            'primary_key': table_info.primary_key,
            'row_count': table_info.row_count,
            'foreign_keys': table_info.foreign_keys,
            'sample_data': sample_data
        }
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get comprehensive schema information for LLM context"""
        main_table = self._detect_main_table()
        return {
            'tables': {
                name: {
                    'columns': info.columns,
                    'primary_key': info.primary_key,
                    'row_count': info.row_count,
                    'foreign_keys': info.foreign_keys
                }
                for name, info in self.schema.tables.items()
            },
            'relationships': self.schema.relationships,
            'suggested_queries': self.schema.suggested_queries,
            'main_table': main_table or ""
        }
    
    def execute_suggested_query(self, query_name: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """Execute one of the auto-generated suggested queries"""
        if query_name not in self.schema.suggested_queries:
            return []
        query = self.schema.suggested_queries[query_name]
        return self._execute_query(query, params or {})
    
    def _detect_main_table(self) -> Optional[str]:
        """Auto-detect the main table (usually has most rows or central relationships)"""
        if not self.schema.tables:
            return None
        
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
            if table_name.lower() in ['meters', 'products', 'items', 'main', 'data', 'records']:
                score += 50
            
            candidates.append((table_name, score))
        
        if candidates:
            return max(candidates, key=lambda x: x[1])[0]
        return None
    
    def _execute_query(self, query: str, params: Any = None) -> List[Dict]:
        """Execute query and return results as dictionaries"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                if isinstance(params, dict):
                    # Named parameters
                    cursor.execute(query, params)
                elif isinstance(params, (tuple, list)):
                    # Positional parameters
                    cursor.execute(query, params)
                else:
                    # No parameters
                    cursor.execute(query)
                    
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

    def query(self, sql, params=None):
        """Run a raw SQL query and return results as a list of dicts."""
        return self._execute_query(sql, params)