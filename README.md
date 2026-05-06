# LumiSkin AI — Governed AI Skin Recommender

> A client-configurable GenAI prototype that converts Airtable-managed business rules into governed AI skincare recommendations via live MCP integration — no redeployment required when rules change.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-green)](https://flask.palletsprojects.com)
[![Claude](https://img.shields.io/badge/Claude-Sonnet%204-orange)](https://anthropic.com)
[![Airtable](https://img.shields.io/badge/Airtable-MCP-purple)](https://airtable.com)
[![Replit](https://img.shields.io/badge/Deployed-Replit-red)](https://replit.com)

---

## The Problem This Solves

In enterprise AI deployments, updating recommendation logic requires engineering cycles. A brand manager who needs to change a product recommendation for the UK market must:

1. File a ticket with engineering
2. Wait for a developer to update config files
3. Go through QA and validation
4. Wait for redeployment

**That process takes 3+ days minimum.**

This project eliminates that entirely. Brand managers edit rules directly in Airtable — a spreadsheet interface they already know. Claude fetches those rules live via MCP and generates updated recommendations instantly. **Three days becomes thirty seconds.**

---

## Architecture

```
User (Skin Scores + Market)
         │
         ▼
┌─────────────────────────┐
│      Flask App          │
│   app.py                │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│    Claude Sonnet 4      │
│   claude_client.py      │
│                         │
│   System Prompt         │  ← Governance layer
│   (governance rules)    │
│                         │
│   MCP Tools attached ───┼──→ get_rules()
│                         │    get_products()
│                         │    get_concern_priority()
│                         │    get_market_config()
└────────────┬────────────┘
             │ Claude calls tools itself
             ▼
┌─────────────────────────┐
│    MCP Server           │
│   mcp_server.py         │
│                         │
│   Exposes Airtable      │
│   data as callable      │
│   tools for Claude      │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│   Airtable Client       │
│   airtable_client.py    │
│                         │
│   Products              │
│   Business_Rules        │
│   Concern_Priority      │
│   Market_Config         │
└────────────┬────────────┘
             │
             ▼
        Airtable
   (Live business rules
    editable by brand
    managers — no code)
```

---

## What Makes This "Governed AI"

Most AI recommendation systems let the model decide freely. This system enforces three pillars:

| Pillar | What It Means | How We Implement It |
|---|---|---|
| **Traceability** | Every decision links to a specific rule | `rule_id` in every product recommendation |
| **Controllability** | Humans change rules without engineering | Airtable — brand managers edit directly |
| **Explainability** | AI explains WHY, not just WHAT | Claude's structured reasoning field |

### Claude Cannot Override a Business Rule

The system prompt enforces this hard constraint:

```
Claude reasons → Rules govern → Brand manager controls
```

If a rule says "UK market gets Oil Control Foam Wash for oily skin" — Claude applies that rule and explains it. Claude cannot substitute a different product based on its training data.

---

## Two-Layer Rules Engine

Directly modelled on real-world enterprise skincare recommendation systems:

### Layer 1: Base Regimen
```
Overall skin health tier → Base product set

Excellent  → Premium regimen
Very Good  → Standard regimen
Average    → Core regimen
Below Avg  → Intensive regimen
Poor       → Repair regimen
```

### Layer 2: Focused Treatment Overrides
```
IF specific concern = poor/below_average
THEN override base regimen slot with targeted product

Example:
IF acne = poor AND market = US
THEN Morning_Cleanser → "Purifying Acne Cleanser"
     rule_id: RUL_US_002
```

### Priority Arbitration
When multiple concerns are poor simultaneously, the `Concern_Priority` table determines which concern drives the override — preventing conflicting rules from producing inconsistent outputs.

---

## Live MCP Integration

This is the key architectural differentiator. Claude does not receive pre-fetched data stuffed into its prompt. Claude is given tools and fetches data itself during reasoning:

```python
# Claude's tool call (happens automatically during reasoning):
get_rules(market="UK")
→ fetches live from Airtable
→ returns rules active right now
→ Claude applies them
→ Claude cites rule_id in output
```

When a brand manager changes a rule in Airtable:
- No code change
- No redeployment  
- Next API call returns new recommendation

---

## Multi-Market Support

Supports 12 markets out of the box:

| Region | Markets |
|---|---|
| Americas | US, CA, BR, MX |
| Europe | UK, FR, DE |
| Asia Pacific | JP, SG, AU |
| Middle East & South Asia | AE, IN |

Adding a new market requires zero engineering — brand managers add a row to the `Market_Config` table in Airtable.

---

## Structured JSON Output

Every recommendation returns a fully typed, auditable JSON response:

```json
{
  "overall_tier": "average",
  "priority_concern": "acne",
  "morning_regimen": {
    "cleanser": {
      "product_name": "Purifying Gel Cleanser",
      "sku_id": "US-PGC-001",
      "rule_id": "RUL_US_002"
    },
    "treatment": {
      "product_name": "Clarifying Serum",
      "sku_id": "US-CS-003",
      "rule_id": "RUL_US_005"
    }
  },
  "night_regimen": { "..." },
  "reasoning": "Customer's acne score of 45 falls in the Poor tier. Priority arbitration table ranks acne #1 for US market at Average overall tier. Applied focused treatment rule RUL_US_002 overriding base Morning_Cleanser.",
  "rules_applied": ["RUL_US_001", "RUL_US_002"],
  "governance_note": "Rules fetched live from Airtable via MCP",
  "confidence": 0.95
}
```

---

## Project Structure

```
governed-ai-recommender/
│
├── app.py                 # Flask web server — routes and request handling
├── claude_client.py       # Claude API integration with MCP tools
├── mcp_server.py          # Exposes Airtable data as MCP tools for Claude
├── airtable_client.py     # Airtable REST API client with pagination
│
├── templates/
│   ├── index.html         # Skin quiz — market selector + score sliders
│   ├── results.html       # Recommendation display with audit trail
│   └── admin.html         # Business rules dashboard for stakeholders
│
├── requirements.txt       # Pinned dependencies
├── .env.example           # Environment variable template
└── .gitignore             # Excludes .env and credentials
```

---

## Airtable Schema

### Products Table
| Field | Type | Purpose |
|---|---|---|
| product_name | Text | Primary identifier |
| product_category | Single Select | Cleanser / Moisturizer / Sunscreen / Treatment |
| market | Single Select | 12 supported markets |
| sku_id | Text | Alphanumeric — market-specific SKU |
| description | Long Text | Product description |
| image_url | URL | Product image |
| buy_now_url | URL | Retailer link |
| skin_concern_tags | Multi Select | 10 concern tags |
| status | Single Select | Active / Discontinued |

### Business_Rules Table
| Field | Type | Purpose |
|---|---|---|
| rule_id | Text | Unique audit identifier (RUL_US_001) |
| rule_type | Single Select | Base_Regimen / Focused_Treatment |
| market | Single Select | Market or ALL |
| concern | Single Select | Concern or ALL |
| score_tier | Single Select | excellent / very_good / average / below_average / poor |
| slot | Single Select | Morning_Cleanser / Night_Treatment etc |
| product_name | Text | Product to recommend |
| priority_rank | Number | Arbitration order |
| is_active | Checkbox | Toggle rules on/off without deletion |
| rule_version | Text | Audit versioning (v1.0, v2.1) |
| last_updated | Date | Full audit trail |

---

## Setup & Deployment

### Prerequisites
- Python 3.11+
- Airtable account (free tier works)
- Anthropic API key
- Replit account (free tier works)

### Local Setup

```bash
# Clone the repo
git clone https://github.com/Niyanta5/Governed-AI-Recommender.git
cd Governed-AI-Recommender

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run
python app.py
```

### Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...
AIRTABLE_TOKEN=pat...
AIRTABLE_BASE_ID=app...
FLASK_SECRET_KEY=your-secret-key
```

### Replit Deployment

1. Import repo into Replit
2. Add environment variables to Replit Secrets
3. Run command: `gunicorn app:app --bind 0.0.0.0:5000`

---

## API Endpoint

```bash
POST /recommend
Content-Type: application/x-www-form-urlencoded

market=US&acne=45&redness=72&oiliness=65&moisture=80&
radiance=85&age_spots=90&texture=75&wrinkles=88&
dark_circles=70&firmness=82
```

```bash
GET /health
→ {"status": "ok", "mcp": "enabled", "markets": 3}

GET /admin
→ Business rules dashboard
```

---

## Why This Architecture Scales

| Challenge | How This System Handles It |
|---|---|
| New market launch | Add row to Market_Config in Airtable |
| New product | Add row to Products table |
| Rule change | Edit Business_Rules row — live immediately |
| New concern | Add to Concern_Priority table |
| Audit request | Query rule_id from recommendation JSON |
| Rollback | Set is_active=false on rule — instant |

---

## Technical Stack

| Component | Technology | Why |
|---|---|---|
| Web Framework | Flask 3.0 | Lightweight, Replit-compatible |
| AI Model | Claude Sonnet 4 | Best reasoning + tool use |
| Tool Protocol | MCP (Anthropic) | Live data fetching during reasoning |
| Rules Store | Airtable | Non-technical stakeholder friendly |
| Deployment | Replit | Zero-config cloud deployment |
| Language | Python 3.11 | Industry standard for AI/ML |

---

## Key Design Decisions

**Why Airtable over a database?**
Brand managers are not developers. Airtable looks like Excel. A PostgreSQL admin panel does not. The goal is zero-engineering rule updates — that requires a tool non-technical people can operate confidently.

**Why MCP over pre-fetching?**
Pre-fetching stuffs rules into the prompt before Claude reasons. MCP lets Claude decide what it needs and fetch it during reasoning. This produces traceable tool call logs — Claude tells you exactly which rule it fetched and why.

**Why deterministic rules before Claude?**
Claude is an exceptional reasoner but not a compliance system. The rules engine enforces hard constraints. Claude explains them. This separation ensures consistency — the same inputs always produce the same governed output regardless of model temperature or prompt variation.

---

## Built By

**Niyanta Pandey**  
AI/AR Engineer with experience deploying governed recommendation systems across 12 international markets.

[GitHub](https://github.com/Niyanta5) | [LinkedIn](https://linkedin.com/in/niyantapandey)
