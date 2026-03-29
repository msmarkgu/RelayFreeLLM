# GStack Skills Adapter for RelayFreeLLM

This directory contains a prototype for running GStack-style skills using RelayFreeLLM.

## Structure

```
gstack_runner/
├── runner.py          # Main code review runner
├── review_prompt.py   # Extracted review skill prompt
├── examples.py        # Examples for adapting other skills
└── README.md          # This file
```

## Quick Start

### 1. Start RelayFreeLLM

```bash
cd RelayFreeLLM
pip install -r requirements.txt
python -m src.server
```

### 2. Run the code review

```bash
cd gstack_runner

# Review current branch against main
python runner.py

# Review specific branch
python runner.py --branch my-feature

# Specify base branch
python runner.py --base master
```

## How It Works

### 1. Extract Core Instructions

From GStack's `review/SKILL.md`:
- Removed Claude Code-specific features (AskUserQuestion, $B, tool whitelists)
- Kept the core review checklist (SQL safety, race conditions, security)
- Simplified to work with any LLM

### 2. Replace Interactive Features

Original: `AskUserQuestion: "Fix this?" Options: A) Yes B) No`

Adapted: Output findings at the end, let user decide

### 3. Use RelayFreeLLM

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="relay-free"
)

response = client.chat.completions.create(
    model="meta-model",
    messages=[{"role": "user", "content": prompt}]
)
```

## Adapting Other Skills

### Pattern: Office Hours

```python
OFFICE_HOURS_PROMPT = """You are helping a founder think through their product.

Ask these questions one at a time:
1. Who specifically is this for?
2. What are they doing today?
3. What's the narrowest version that delivers value?

After all questions, provide a summary and recommendation."""
```

### Pattern: Ship

```python
SHIP_PROMPT = """You are a release engineer. Workflow:
1. Check clean working tree
2. Run tests
3. Check coverage
4. Push and create PR"""
```

### Pattern: QA

QA is harder - requires browser automation. You'd need to:
1. Use Playwright/Selenium directly
2. Replace `$B` browse commands with Playwright calls
3. Generate test scripts instead of interactive browser

## Limitations

Without Claude Code's tool calling, you lose:
- Automatic file editing (need to do manually)
- Interactive prompts (batch output instead)
- Multi-step agent loops (single prompt instead)

## Requirements

- RelayFreeLLM running on localhost:8000
- Git repository to review
- Python 3.10+

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| RELAYFREE_URL | http://localhost:8000/v1 | RelayFreeLLM API URL |
| RELAYFREE_KEY | relay-free | API key |
| RELAYFREE_MODEL | meta-model | Model to use |
