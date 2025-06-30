import sys
from modular.database import MeterDatabase
from modular.analysis import MeterSpecificationAnalyzer
from modular.reporting import ComplianceReporter
from modular.utils import safe_remove_duplicates

def main():
    # Example CLI for running the compliance analysis and reporting
    if len(sys.argv) < 4:
        print("Usage: python main.py <db_path> <model_number> <requirements_file> [output_format]")
        print("output_format: 1=Markdown, 2=Excel, 3=Both (default: 3)")
        sys.exit(1)

    db_path = sys.argv[1]
    model_number = sys.argv[2]
    requirements_file = sys.argv[3]
    output_format = sys.argv[4] if len(sys.argv) > 4 else "3"

    # Load requirements from file
    with open(requirements_file, 'r', encoding='utf-8') as f:
        requirements = [line.strip() for line in f if line.strip()]

    # Initialize modules
    db = MeterDatabase(db_path)
    analyzer = MeterSpecificationAnalyzer()
    reporter = ComplianceReporter()

    # Get meter specs
    meter_specs = db.find_meter_specs(model_number)
    if not meter_specs:
        print(f"❌ Meter '{model_number}' not found in database.")
        sys.exit(1)

    # Run compliance analysis
    analysis_result = analyzer.compare_requirements_with_specs(requirements, meter_specs, model_number)

    # Prepare output filenames
    base_name = model_number.replace(" ", "_")
    md_output = f"{base_name}_compliance_report.md"
    excel_output = f"{base_name}_compliance_report.xlsx"

    try:
        if output_format in ["1", "3"]:
            print("[INFO] Generating Markdown report...")
            reporter.generate_detailed_comparison(analysis_result.get("compliance_analysis", []), md_output)
            print(f"Markdown report generated: {md_output}")

        if output_format in ["2", "3"]:
            print("[INFO] Generating Excel report...")
            reporter.export_to_excel(analysis_result.get("compliance_analysis", []), excel_output)
            print(f"Excel report generated: {excel_output}")

        print("\nAnalysis complete!")

    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        print("The process encountered an error. Please check your input files and database.")

if __name__ == "__main__":
    main()