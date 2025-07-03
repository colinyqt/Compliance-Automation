from llama_index.core import SQLDatabase, Settings
from llama_index.core.query_engine import NLSQLTableQueryEngine
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from .database_context_provider import DatabaseContextProvider
import asyncio
from sqlalchemy import create_engine

class LlamaIndexQueryEngine:
    def __init__(self, db_path, llm_model="qwen2.5-coder:7b", smart_wrapper=None):
        self.db_path = db_path
        self.smart_wrapper = smart_wrapper
        
        # Get dynamic context
        self.context_provider = DatabaseContextProvider(db_path)
        self.db_context = self.context_provider.format_context_for_llm()
        
        print(f"🔧 Database context loaded:")
        print(self.db_context[:500] + "...")
        
        # Configure LLM with dynamic context
        self.llm = Ollama(
            model=llm_model,
            request_timeout=300.0,
            temperature=0.0,
            system_prompt=f"""You are a SQL expert. Use this database context to write accurate queries:

{self.db_context}

Always execute SQL and return actual data, never examples. Use the sample data patterns to understand the exact values and formats in the database."""
        )
        
        # Configure embeddings
        self.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        
        Settings.llm = self.llm
        Settings.embed_model = self.embed_model
        
        # Create SQL database
        engine = create_engine(f"sqlite:///{db_path}")
        self.sql_database = SQLDatabase(engine)
        
        # Create query engine
        self.query_engine = NLSQLTableQueryEngine(
            sql_database=self.sql_database,
            llm=self.llm,
            embed_model=self.embed_model,
            verbose=True,
            synthesize_response=True
        )

    async def query(self, natural_language_query: str) -> str:
        print(f"🦙 Query: {natural_language_query}")
        
        # Add database context to the query
        enhanced_query = f"""
        {natural_language_query}
        
        Use the database context provided in the system prompt to understand the exact data patterns and values.
        """
        
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, self.query_engine.query, enhanced_query),
                timeout=300
            )
            return str(result)
        except Exception as e:
            return f"Query failed: {str(e)}"
    
    def _simplify_query(self, query: str) -> str:
        """Simplify complex queries for better performance"""
        
        # Extract key requirements
        key_terms = []
        
        if "±0.5%" in query or "accuracy" in query.lower():
            key_terms.append("high accuracy measurement")
        
        if "rs485" in query.lower() or "tcp/ip" in query.lower() or "communication" in query.lower():
            key_terms.append("communication protocols")
        
        if "harmonic" in query.lower() or "thd" in query.lower():
            key_terms.append("power quality analysis")
        
        if "temperature" in query.lower() or "50°c" in query.lower():
            key_terms.append("temperature rating")
        
        if "data logging" in query.lower() or "memory" in query.lower():
            key_terms.append("data logging capabilities")
        
        # Create simplified query
        if key_terms:
            simplified = f"Find power meters that support {', '.join(key_terms[:3])}."
        else:
            simplified = "Find power meters with high accuracy measurement capabilities."
        
        return simplified

    def debug_context(self):
        """Debug method to check context loading"""
        print("=== LLAMAINDEX DEBUG ===")
        print(f"Database path: {self.db_path}")
        print(f"Context provider exists: {hasattr(self, 'context_provider')}")
        
        if hasattr(self, 'db_context'):
            print(f"Context length: {len(self.db_context)} characters")
            print("Context preview:")
            print(self.db_context[:300])
        
        print(f"LLM system prompt length: {len(self.llm.system_prompt) if hasattr(self.llm, 'system_prompt') else 'No system prompt'}")
        
        # Test context provider directly
        if hasattr(self, 'context_provider'):
            sample_data = self.context_provider.get_sample_data(rows_per_table=2)
            print(f"Sample data keys: {list(sample_data.keys())}")
            for table, data in sample_data.items():
                if isinstance(data, list) and data:
                    print(f"  {table}: {data[0]}")