#!/usr/bin/env python3
"""
GStack-style code review runner using RelayFreeLLM.

Usage:
    python runner.py                    # Review current branch
    python runner.py --branch feature   # Review specific branch
    python runner.py --base main        # Specify base branch
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from openai import OpenAI

# Import the prompts
from review_prompt import CORE_REVIEW_PROMPT, SYSTEM_PROMPT, get_user_prompt


def run_command(cmd: str) -> tuple[str, int]:
    """Run a shell command and return output and exit code."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True
    )
    return result.stdout.strip(), result.returncode


def get_diff(branch: str | None = None, base_branch: str | None = None) -> tuple[str, str, str]:
    """Get the git diff for review."""
    # Get current branch
    current_branch, _ = run_command("git branch --show-current")
    branch = branch or (current_branch or "unknown")
    
    # Get base branch
    if not base_branch:
        # Try to detect from origin/HEAD
        base_branch, rc = run_command(
            "git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||'"
        )
        if rc != 0 or not base_branch:
            base_branch = "main"
    
    # Fetch latest
    run_command(f"git fetch origin {base_branch} --quiet")
    
    # Get diff
    diff_output, _ = run_command(f"git diff origin/{base_branch}")
    
    if not diff_output:
        diff_output = "No changes detected"
    
    return diff_output, branch, base_branch


def call_relayfreellm(prompt: str, system: str | None = None) -> str:
    """Call RelayFreeLLM API."""
    client = OpenAI(
        base_url=os.environ.get("RELAYFREE_URL", "http://localhost:8000/v1"),
        api_key=os.environ.get("RELAYFREE_KEY", "relay-free"),
    )
    
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    
    response = client.chat.completions.create(
        model=os.environ.get("RELAYFREE_MODEL", "meta-model"),
        messages=messages,  # type: ignore
        temperature=0.3,
    )
    
    content = response.choices[0].message.content
    return content if content else ""


def run_review(branch: str | None = None, base_branch: str | None = None):
    """Run the code review."""
    print("🔍 Gathering diff...")
    diff_output, branch, base_branch = get_diff(branch, base_branch)
    
    print(f"📋 Branch: {branch} → {base_branch}")
    
    if diff_output == "No changes detected":
        print("✅ Nothing to review - no changes detected")
        return
    
    # Show diff stats
    stats, _ = run_command(f"git diff origin/{base_branch} --stat")
    print(f"\nChanged files:\n{stats}\n")
    
    # Build prompt
    user_prompt = get_user_prompt(diff_output, branch, base_branch)
    full_prompt = f"{CORE_REVIEW_PROMPT}\n\n{user_prompt}"
    
    print("🤖 Running AI code review...")
    try:
        result = call_relayfreellm(full_prompt, SYSTEM_PROMPT)
        print("\n" + "="*50)
        print("REVIEW RESULTS")
        print("="*50)
        print(result)
    except Exception as e:
        print(f"❌ Error calling RelayFreeLLM: {e}")
        print("\n📝 Manual Review Required")
        print("-" * 50)
        # Show the diff for manual review
        print(diff_output[:5000])
        if len(diff_output) > 5000:
            print(f"\n... (truncated, full diff is {len(diff_output)} chars)")


def main():
    parser = argparse.ArgumentParser(description="GStack-style code review with RelayFreeLLM")
    parser.add_argument("--branch", help="Branch to review")
    parser.add_argument("--base", help="Base branch to compare against")
    args = parser.parse_args()
    
    run_review(branch=args.branch, base_branch=args.base)


if __name__ == "__main__":
    main()
