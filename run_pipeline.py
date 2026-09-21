"""
run_pipeline.py - Master Automated Runner for Remote Job Search Agent

Executes the entire daily sourcing & scoring pipeline in one command:
1. Validates local Ollama LLM connectivity
2. Ingests fresh remote jobs (source_jobs.py)
3. Evaluates & scores unscored jobs with Ollama (score_jobs.py)
4. Displays updated pipeline metrics and review status
"""

import os
import sys
import subprocess
import requests

def check_ollama():
    try:
        res = requests.get("http://localhost:11434/api/tags", timeout=3)
        if res.status_code == 200:
            models = res.json().get("models", [])
            if models:
                print(f"[Ollama] Connected. Active model: {models[0]['name']}")
                return True
            else:
                print("[Ollama] Warning: Ollama is running but no models are installed.")
                return False
    except Exception:
        print("[Ollama] Warning: Ollama is not reachable on http://localhost:11434.")
        return False

def run_step(script_name: str, description: str):
    print(f"\n{'='*60}")
    print(f"  Step: {description} ({script_name})")
    print(f"{'='*60}")
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    result = subprocess.run([sys.executable, script_path])
    if result.returncode != 0:
        print(f"[Error] {script_name} exited with code {result.returncode}")
        return False
    return True

def main():
    print("============================================================")
    print("      Remote Job Search Agent - Daily Automated Pipeline    ")
    print("============================================================")

    ollama_ok = check_ollama()

    # Step 1: Sourcing
    if not run_step("source_jobs.py", "Sourcing fresh remote job listings"):
        sys.exit(1)

    # Step 2: Scoring
    if ollama_ok:
        if not run_step("score_jobs.py", "Scoring new jobs with local LLM"):
            sys.exit(1)
    else:
        print("\n[Notice] Skipping LLM scoring step until an Ollama model is available.")

    print("\n============================================================")
    print("  Pipeline complete! Open http://localhost:3000 to review.  ")
    print("============================================================\n")

if __name__ == "__main__":
    main()
