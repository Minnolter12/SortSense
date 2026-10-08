"""
Live Gemma smoke test script.

Run with: .venv\Scripts\python.exe tests\smoke_test_live.py

Gracefully skips if Ollama is unavailable.
"""

import sys

# --- check Ollama reachability first ---
try:
    import ollama
    c = ollama.Client(host="http://localhost:11434")
    c.list()
except Exception as e:
    print(f"SKIPPED: Ollama unavailable — {e}")
    sys.exit(0)

from app.ingestion import ingest_file
from app.analyzer import analyze_document, OllamaUnavailableError, AnalysisParseError
from app.validation import validate_analysis

doc = ingest_file("test_files/filemind_sample.pdf")
print(f"Ingested : {doc.file_name}  ({doc.character_count} chars, {doc.page_count} pages)")
print()

try:
    analysis = analyze_document(doc)
except OllamaUnavailableError as e:
    print(f"SKIPPED: {e}")
    sys.exit(0)
except AnalysisParseError as e:
    print(f"PARSE ERROR: {e}")
    sys.exit(1)

print("=== DOCUMENT ANALYSIS ===")
print(f"DOCUMENT TYPE    : {analysis.document_type}")
print(f"SUMMARY          : {analysis.summary}")
print(f"CONFIDENCE       : {analysis.confidence}")
print(f"EVIDENCE QUALITY : {analysis.evidence_quality}")
print(f"SUGGESTED ACTION : {analysis.suggested_action}")
print()

print(f"ENTITIES ({len(analysis.entities)}):")
for ent in analysis.entities:
    print(f"  [{ent.name}] = {ent.value!r}")
    print(f"    evidence: {ent.evidence!r}")

print()
print(f"FACTS ({len(analysis.facts)}):")
for i, fact in enumerate(analysis.facts, 1):
    print(f"  #{i}: {fact.fact}")
    print(f"    evidence: {fact.evidence!r}")

print()
print("=== VALIDATION ===")
result = validate_analysis(doc, analysis)
print(f"VALID            : {result.valid}")
print(f"EVIDENCE VERIFIED: {result.evidence_verified}")
no_issues = "none"
print(f"ISSUES           : {result.issues if result.issues else no_issues}")
