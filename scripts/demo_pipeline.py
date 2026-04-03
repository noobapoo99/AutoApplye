#!/usr/bin/env python3
import time
import argparse
import sys
import random

BOLD = "\033[1m"
GREEN = "\033[92m"
AMBER = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"

def print_stage(name):
    print(f"\n{BOLD}{BLUE}========================================")
    print(f"STAGE: {name}")
    print(f"========================================{RESET}")

def main():
    parser = argparse.ArgumentParser(description="Demo Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run the demo pipeline")
    parser.add_argument("--query", type=str, default="Software Engineer", help="Query to run")
    args = parser.parse_args()

    if not args.dry_run:
        parser.print_help()
        sys.exit(1)

    print(f"{BOLD}{CYAN}Starting AutoApply Demo Pipeline...{RESET}")
    print(f"{GRAY}Query: {args.query}{RESET}")
    time.sleep(0.3)

    # Stage 1
    print_stage("JDScoutAgent")
    print(f"{GREEN}✓{RESET} Executing SerpAPI search: {args.query}")
    time.sleep(0.4)
    print(f"{GRAY}Found 2 potential LinkedIn URLs...{RESET}")
    time.sleep(0.3)
    print(f"{GRAY}Starting Playwright screenshot capture and OCR...{RESET}")
    time.sleep(0.3)
    print(f"{GREEN}✓{RESET} External apply URL detected: https://jobs.lever.co/example")
    time.sleep(0.2)
    print(f"{CYAN}→ IMMEDIATE ACK MESSAGE{RESET}")
    print(f"{CYAN}→ Published to jd.raw{RESET}")

    # Stage 2
    print_stage("CompanyResearchAgent")
    print(f"{GRAY}ResearcherFactory creating 3 parallel researchers...{RESET}")
    time.sleep(0.4)
    for site in ["Reddit", "Glassdoor", "LinkedIn"]:
        print(f"{GREEN}✓{RESET} Mock {site} results fetched")
        time.sleep(0.2)
    print(f"{GRAY}Calling Gemini text-embedding-004 (768 dims)...{RESET}")
    time.sleep(0.3)
    print(f"{GREEN}✓{RESET} ChromaDB upsert successful")
    print(f"{CYAN}→ Published to jd.enriched{RESET}")

    # Stage 3
    print_stage("ResumeEditorAgent")
    print(f"{GRAY}Strategy selected: KeywordInjection{RESET}")
    time.sleep(0.3)
    before_score = random.uniform(0.55, 0.85)
    print(f"Cosine similarity before edit: {AMBER}{before_score:.2f}{RESET}")
    time.sleep(0.2)
    print(f"{GRAY}Gap skills identified: Python, Kubernetes, CI/CD{RESET}")
    time.sleep(0.4)
    after_score = before_score + random.uniform(0.05, 0.15)
    print(f"Cosine similarity after edit: {GREEN}{after_score:.2f}{RESET}")
    
    # 6-dot hallucination score
    passed = random.randint(4, 6)
    dots = ("● " * passed) + ("○ " * (6 - passed))
    # 6 criteria: Company, Role, Skills, Resume, Contact, Score
    print(f"Hallucination checks: {GREEN if passed == 6 else AMBER}{dots}{RESET}")
    
    if passed >= 5 and after_score > 0.65:
        print(f"{CYAN}→ Decision: READY -> Published to jd.ready{RESET}")
    else:
        print(f"{AMBER}→ Decision: FLAGGED -> Published to jd.flagged{RESET}")

    # Stage 4
    print_stage("ApplicationAgent")
    print(f"{GRAY}Checking LeakyBucketRateLimiter...{RESET}")
    time.sleep(0.2)
    print(f"{GRAY}Token math: capacity=10, remaining=9{RESET}")
    time.sleep(0.3)
    print(f"{GREEN}✓{RESET} detect_ats() -> GreenhouseTemplate matched")
    print(f"{GRAY}Executing form fill steps...{RESET}")
    time.sleep(0.4)
    print(f"{GRAY}Exponential backoff available on failure{RESET}")
    print(f"{GREEN}✓{RESET} Confirmation message detected on DOM")

    # Stage 5
    print_stage("GmailTrackerAgent")
    print(f"{GRAY}Polling Gmail API...{RESET}")
    time.sleep(0.3)
    print(f"{GREEN}✓{RESET} 1 mock email found matching role")
    print(f"{GRAY}Calling Gemini for zero-shot classification...{RESET}")
    time.sleep(0.4)
    print(f"{GREEN}✓ Classification: interview_invite{RESET}")
    print(f"{GRAY}DLQ counter: 0/3 messages failed today{RESET}")
    time.sleep(0.2)
    print(f"{CYAN}→ Application status updated in DB{RESET}")

    # Summary
    print(f"\n{BOLD}{CYAN}========================================")
    print("PIPELINE SUMMARY")
    print("========================================")
    print(f"{RESET}")
    
    ascii_art = f"""
  [jd.raw] ---> [jd.enriched] ---> [jd.ready] 
      ^               |                |      
 ScoutAgent      ResearchAgent     ResumeAgent
    """
    print(ascii_art)
    
    print(f"\n{BOLD}Patterns Used:{RESET}")
    print(" - Template Pattern: BaseAgent.run()")
    print(" - Factory Pattern: AgentFactory.create()")
    print(" - Strategy Pattern: ResumeEditStrategy vs SummaryRewrite")

    print(f"\n{BOLD}Free Services Integrated:{RESET}")
    print(" - Gemini: 1M tokens/day")
    print(" - CloudAMQP: 1M msgs/mo")
    print(" - Upstash Redis: 10K cmds/day")
    print(" - Supabase PG: 50MB limits")
    time.sleep(0.2)

if __name__ == "__main__":
    main()
