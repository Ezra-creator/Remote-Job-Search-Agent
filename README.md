# Remote Job Search Agent (RJS)

An autonomous, private, zero-cost AI job search agent and workflow engine. RJS automates multi-board job sourcing, local LLM evaluation against a candidate profile, tailored resume bullet and cover letter drafting from a factual experience bank, and end-to-end application lifecycle tracking with a mobile-first Next.js UI accessible over private Tailscale networks.

---

## Architecture Overview

```
                          ┌────────────────────────┐
                          │     profile.json       │
                          │  (Candidate Profile &  │
                          │      Fact Bank)        │
                          └───────────┬────────────┘
                                      │
 ┌──────────────────────┐             ▼              ┌────────────────────────┐
 │   source_jobs.py     │──────▶  jobs.db  ◀─────────│    score_jobs.py       │
 │ (RemoteOK, WeWork,   │       (SQLite)             │ (Local Ollama LLM eval │
 │  Jobspresso, Hacker) │                            │  0-100 fit & flags)    │
 └──────────────────────┘             ▲              └────────────────────────┘
                                      │
                                      │
 ┌──────────────────────┐             │              ┌────────────────────────┐
 │  draft_materials.py  │─────────────┤              │    github_facts.py     │
 │ (Tailored bullets &  │             │              │  (Public repo README   │
 │  cover letters via   │             │              │   fact bank extractor) │
 │  Ollama local LLM)   │             │              └────────────────────────┘
 └──────────────────────┘             │
                                      ▼
                        ┌───────────────────────────┐
                        │      backend/main.py      │
                        │    (FastAPI REST API)     │
                        └─────────────┬─────────────┘
                                      │  (Tailscale / Localhost)
                                      ▼
                        ┌───────────────────────────┐
                        │      frontend/ (Next.js)  │
                        │  Dashboard / Review Queue │
                        │  Materials / Tracking UI  │
                        └───────────────────────────┘
```

---

## Core Components

### 1. Sourcing Pipeline (`source_jobs.py`)
- Ingests remote job listings across multiple public job feeds (RemoteOK RSS, WeWorkRemotely RSS, Jobspresso RSS, Hacker News "Who is hiring?").
- Normalizes data into SQLite `jobs.db` with schema deduplication on `(source, external_id)`.
- Pre-filters excluded companies and dealbreaker rules automatically.

### 2. Ollama Scoring Engine (`score_jobs.py`)
- Evaluates unscored jobs against `profile.json` using a local LLM via Ollama (`qwen3:8b` / `llama3.1:8b`).
- Computes an integer `fit_score` (0–100), detailed reasoning, and dealbreaker flags.
- Zero cloud API dependency, zero cost, completely private.

### 3. Application Material Drafter (`draft_materials.py`)
- Selects and ranks the 4–6 most relevant bullets from the user's `fact_bank` (never invents experience).
- Drafts a personalized cover letter directly addressing the company's requirements and culture.
- Enforces strict anti-cliché writing guidelines for natural, authentic engineer-to-hiring-manager correspondence.

### 4. GitHub Facts Extractor (`github_facts.py`)
- Scans public GitHub repositories via unauthenticated GitHub API.
- Extracts real accomplishments, architectures, and metrics from project READMEs to draft candidate entries for `fact_bank` in `profile.json`.

### 5. FastAPI Backend (`backend/main.py`)
- RESTful API managing the job lifecycle: `new` -> `scored` -> `approved` -> `materials_ready` -> `ready_to_apply` -> `applied`.
- Follow-up query engine for applications older than 7 days.
- Binds to `0.0.0.0:8000` for seamless access across private Tailscale tailnets.

### 6. Next.js Frontend (`frontend/`)
- Mobile-first Next.js (App Router, TypeScript) web application.
- Dedicated design system with custom color palette (`ink`, `paper`, `line`, `muted`, `accent`, `warn`) and IBM Plex typography.
- Four core views:
  - `/`: Pipeline overview metrics and stage breakdown.
  - `/review`: Swipeable/keyboard evaluation queue for scored listings.
  - `/materials`: In-browser editor for tailored resume bullets and cover letters.
  - `/applied`: 7-day follow-up tracker and comprehensive application history.

---

## Getting Started

### Prerequisites
- Python 3.10+
- Node.js 18+ & npm
- [Ollama](https://ollama.com/) running locally with your target model (e.g. `ollama run qwen3:8b`)

### 1. Setup Candidate Profile
Configure your candidate information, target roles, salary floor, dealbreakers, and experience fact bank in `profile.json`:
```json
{
  "candidate": {
    "name": "Your Name",
    "email": "your.email@example.com",
    "github_username": "your-github-handle",
    "timezone": "UTC",
    "current_role": "Software Engineer",
    "years_experience": 3
  },
  "target": {
    "roles": ["Senior Software Engineer", "Full Stack Developer", "Backend Engineer"],
    "seniority": ["Mid-Level", "Lead"],
    "salary_floor_usd": 130000,
    "remote_only": true,
    "visa_sponsorship_needed": false
  },
  "must_haves": ["Python or TypeScript", "Remote-first culture"],
  "nice_to_haves": ["PostgreSQL", "FastAPI", "React"],
  "dealbreakers": ["On-site requirement", "Unpaid internships"],
  "excluded_companies": ["Example Corp"],
  "skills": {
    "core": ["Python", "TypeScript", "React", "Next.js", "FastAPI", "PostgreSQL", "Docker"],
    "familiar": ["Kubernetes", "AWS", "GraphQL"]
  },
  "fact_bank": [
    {
      "id": "f001",
      "tags": ["experience", "backend"],
      "text": "Designed and deployed high-throughput FastAPI microservices serving 10M+ daily requests."
    }
  ]
}
```

### 2. Python Backend Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Run initial job sourcing
python source_jobs.py

# Score jobs with local Ollama model
python score_jobs.py

# Start FastAPI backend
cd backend
python main.py
```

### 3. Frontend Setup
```bash
cd frontend
npm install

# Copy environment template
cp .env.example .env.local

# Run development server
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Design System Tokens

| Token | Hex | Role |
| :--- | :--- | :--- |
| `ink` | `#171A21` | Primary text, navigation header |
| `paper` | `#F2F2EF` | Page background, content containers |
| `line` | `#D8D6CE` | Borders, dividers, subtle accents |
| `muted` | `#8A8A82` | Secondary text, timestamps, labels |
| `accent` | `#2B4C7E` | Primary buttons, links, score highlights ($\ge 70$) |
| `warn` | `#9C3B33` | Dealbreaker flags, overdue follow-ups, destructive actions |

---

## License
MIT License. Built for private, personal job search automation.
