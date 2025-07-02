import os
import PyPDF2
import ollama
from typing import List, Dict, Tuple

MODEL_NAME = "qwen3:8b" 

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extracts all text from a PDF file."""
    print(f"📄 Processing PDF file: {pdf_path}")
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            print(f"📄 Extracting text from {len(reader.pages)} pages...")
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    # Add page markers to help the model understand the document structure
                    text += f"\n--- START OF PAGE {i + 1} ---\n"
                    text += page_text
        print("✅ Text extraction complete.")
        return text
    except Exception as e:
        print(f"❌ Error extracting PDF text: {e}")
        return ""

def build_prompt(document_text: str) -> str:
    """
    Builds the final prompt with explicit instructions for verbatim extraction.
    """
    instructions = """You are an expert AI assistant specializing in analyzing technical engineering and tender documents. Your task is to meticulously analyze the document text provided below and extract only the specific clauses that define distinct types of power meters.

**Your Instructions:**

You are an expert contract and technical document analyst. Analyze the following tender document text carefully.

Your task is to:

Identify all clauses that name specific types of power meters or measuring devices (e.g., "Digital Power Analyzer," "Multi-Function Meter," "DMMD").

For each such clause:
List the full clause number and title .
Extract and provide the full content of that clause in plain text format.
At the end, output a line with only the comma-separated list of clause numbers identified.

Instructions:
Only include clauses that refer to specific device types .
Exclude general requirement clauses (e.g., “General,” “Testing,” “Documentation”) unless they are sub-sections of a specific meter clause .
Exclude component-level clauses (e.g., “Current Transformers,” “Wiring”) unless they are part of a named meter section.
Do not summarize or paraphrase; provide the exact text as it appears in the document.
Do not include any additional commentary or analysis.

**Begin your analysis on the following document text:**
--- START OF DOCUMENT ---
"""
    
    return instructions + document_text + "\n--- END OF DOCUMENT ---"

def main():
    """
    Main function to run the LLM-based clause extraction.
    """
    print("📋 AI Clause Extractor")
    print(f"🧠 Using Model: {MODEL_NAME}")
    print("=" * 50)
    
    pdf_path = input("Enter the path to the tender document PDF: ").strip()
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        return

    # 1. Extract text from the PDF
    doc_text = extract_text_from_pdf(pdf_path)
    if not doc_text:
        return
        
    # 2. Build the full prompt for the LLM
    full_prompt = build_prompt(doc_text)
    
    # 3. Send the prompt to the local LLM
    print(f"\n🚀 Sending document and instructions to {MODEL_NAME}. This may take some time depending on document size...")
    
    try:
        response = ollama.generate(
            model=MODEL_NAME,
            prompt=full_prompt,
            stream=False 
        )
        
        print("✅ LLM processing complete.")
        
        # 4. Save the result
        llm_output = response['response']
        output_filename = os.path.splitext(pdf_path)[0] + "_extracted_clauses.txt"
        
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(llm_output)
            
        print("\n" + "="*80)
        print("✅ EXTRACTION COMPLETE")
        print(f"Results saved to: {output_filename}")
        print("="*80)

    except Exception as e:
        print(f"\n❌ An error occurred while communicating with the Ollama model: {e}")
        print(f"Please ensure Ollama is running and the model '{MODEL_NAME}' is available.")
        print("You can check available models by running 'ollama list' in your terminal.")

if __name__ == "__main__":
    main()