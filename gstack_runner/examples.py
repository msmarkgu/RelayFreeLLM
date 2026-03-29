#!/usr/bin/env python3
"""
Example: Adapting more GStack skills for RelayFreeLLM

This shows the pattern for converting any GStack skill to work with 
any OpenAI-compatible LLM.
"""

# ============================================================================
# Pattern 1: Extract the core workflow
# ============================================================================

OFFICE_HOURS_PROMPT = """# YC Office Hours - Product Diagnostic

You are helping a founder think through their product idea. Ask these questions one at a time:

## The Six Forcing Questions

1. **Demand Reality**: Who specifically is this for? What's their specific pain? How do you know they want this?

2. **Status Quo**: What are they doing today to solve this problem? Why is that insufficient?

3. **Desperate Specificity**: What's the narrowest version of this that delivers value? Not "social network for X" - what's the actual first use case?

4. **Narrowest Wedge**: What's the smallest thing you could build that proves this hypothesis? What's the fastest way to get real signal?

5. **Observation**: What have you personally observed that tells you this is a real problem? Not surveys, not interviews - what have you SEEN?

6. **Future-Fit**: If this works, what does the path to a big business look like? What's the leverage?

## Output

After answering all questions, provide:
- One paragraph summary of the problem space
- 3 potential approaches with effort estimates
- Your recommendation for the narrowest wedge

Keep responses concise. Be direct. Don't hedge."""

# ============================================================================
# Pattern 2: Replace Claude Code-specific features
# ============================================================================

# Original AskUserQuestion:
# Use AskUserQuestion: "What's the strongest evidence?" Options: A) B) C)

# Adapted for generic LLM:
def ask_diagnostic_question(question: str, user_context: str = None) -> str:
    """Ask a diagnostic question and return user's answer."""
    if user_context:
        prompt = f"Context: {user_context}\n\n{question}"
    else:
        prompt = question
    
    # This would call RelayFreeLLM
    # response = call_relayfreellm(prompt)
    # return response
    pass


# ============================================================================
# Pattern 3: Create tool wrappers
# ============================================================================

TOOL_SCHEMA = {
    "Bash": {
        "description": "Execute shell commands",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to run"}
            },
            "required": ["command"]
        }
    },
    "Read": {
        "description": "Read file contents", 
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"}
            },
            "required": ["path"]
        }
    },
    "Grep": {
        "description": "Search for patterns in files",
        "parameters": {
            "type": "object", 
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "path": {"type": "string", "description": "Directory to search"}
            },
            "required": ["pattern"]
        }
    }
}


# ============================================================================
# Pattern 4: Simple skill runner template
# ============================================================================

SKILL_TEMPLATE = '''# {skill_name}

{extracted_instructions}

## Available Tools

{tool_descriptions}

## Execution

1. {step_1}
2. {step_2}
3. {step_3}

## Output Format

{output_format}
'''


def create_skill_runner(skill_name: str, instructions: str, tools: dict):
    """Template for creating a skill runner."""
    tool_descriptions = "\n".join([
        f"- {name}: {info['description']}"
        for name, info in tools.items()
    ])
    
    return SKILL_TEMPLATE.format(
        skill_name=skill_name,
        extracted_instructions=instructions,
        tool_descriptions=tool_descriptions,
        step_1="Run tool: Bash with git commands to get context",
        step_2="Analyze the data",
        step_3="Provide findings",
        output_format="Structured findings with severity and fix recommendations"
    )


# ============================================================================
# Example: Adapting /ship skill (simplified)
# ============================================================================

SHIP_PROMPT = """# Release Engineer - Ship to Production

You are a release engineer. Your job is to safely ship code to production.

## Workflow

1. Check for clean working tree
2. Run tests: `npm test` or `pytest` or `go test`
3. Check test coverage
4. Sync with main branch
5. Push changes
6. Create PR

## Rules

- Don't push to main directly (create PR)
- Run full test suite first
- Verify coverage meets minimum (60%)
- Ensure all checks pass

## Output

Provide status updates at each step.
Report any failures with specific error messages.
On success, provide PR link."""

print("To adapt a GStack skill:")
print("1. Extract core instructions from SKILL.md")
print("2. Remove Claude Code-specific syntax (AskUserQuestion, $B, etc.)")
print("3. Replace with standard prompts or CLI interaction")
print("4. Define tool schema for your LLM")
print("5. Create a simple runner")
