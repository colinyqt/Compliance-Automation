from core.database_context_provider import DatabaseContextProvider

# Test the context provider directly
db_path = r"C:\Users\cyqt2\Database\overhaul\databases\meters.db"
provider = DatabaseContextProvider(db_path)

print("=== SCHEMA INFO ===")
schema = provider.get_schema_info()
for table, info in schema.items():
    print(f"{table}: {info['row_count']} rows")

print("\n=== SAMPLE DATA ===")
sample_data = provider.get_sample_data(rows_per_table=3)
for table, data in sample_data.items():
    print(f"\n{table}:")
    if isinstance(data, list) and data:
        print(f"  Sample: {data[0]}")

print("\n=== DATA PATTERNS ===")
patterns = provider.analyze_data_patterns()
print(patterns)

print("\n=== FORMATTED CONTEXT ===")
context = provider.format_context_for_llm()
print(context[:500])