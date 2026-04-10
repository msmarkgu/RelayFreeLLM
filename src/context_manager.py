"""
Context Manager — handles selecting and managing conversation history for API calls.

Responsible for deciding what portion of conversation history to send to providers
on every request, based on configuration and current conversation state.
"""

import re
from collections import Counter
from typing import List, Optional
from .models import ChatMessage
from .config import settings


class ContextManager:
    """Manages conversation history selection for API calls to providers."""
    
    def __init__(self):
        self.logger = None  # Will be set by dispatcher if needed
        
        # Load configuration
        self.context_management_mode = getattr(settings, 'CONTEXT_MANAGEMENT_MODE', 'static')
        self.static_recent_keep = getattr(settings, 'CONTEXT_STATIC_RECENT_KEEP', 10)
        self.dynamic_utilization_target = getattr(settings, 'CONTEXT_DYNAMIC_UTILIZATION_TARGET', 0.8)
        self.dynamic_min_utilization = getattr(settings, 'CONTEXT_DYNAMIC_MIN_UTILIZATION', 0.3)
        self.dynamic_max_boost = getattr(settings, 'CONTEXT_DYNAMIC_MAX_BOOST', 1.5)
        self.reservoir_recent_keep = getattr(settings, 'CONTEXT_RESERVOIR_RECENT_KEEP', 15)
        self.reservoir_summary_budget = getattr(settings, 'CONTEXT_RESERVOIR_SUMMARY_BUDGET', 400)

        # Summarization settings
        self.summarization_max_tokens = getattr(settings, 'SUMMARIZATION_MAX_TOKENS', 200)

        # For dynamic mode tracking
        self._usage_history: dict[str, List[int]] = {}  # session_id -> list of recent token usages
    
    def select_context_for_request(
        self, 
        full_history: List[ChatMessage], 
        session_id: str,
        target_context_tokens: int
    ) -> List[ChatMessage]:
        """
        Select what portion of conversation history to send in the API call.
        
        Args:
            full_history: Complete conversation history for this session
            session_id: Identifier for the user session
            target_context_tokens: Maximum tokens we want to use for context
            
        Returns:
            List of ChatMessage objects to include in the API call
        """
        if not full_history:
            return []
            
        if self.context_management_mode == "disabled":
            return []
        elif self.context_management_mode == "static":
            return self._select_static(full_history, target_context_tokens)
        elif self.context_management_mode == "dynamic":
            return self._select_dynamic(full_history, session_id, target_context_tokens)
        elif self.context_management_mode == "reservoir":
            return self._select_reservoir(full_history, target_context_tokens)
        elif self.context_management_mode == "adaptive":
            return self._select_adaptive(full_history, target_context_tokens)
        else:
            # Default to static if unknown mode
            return self._select_static(full_history, target_context_tokens)
    
    def _select_static(self, full_history: List[ChatMessage], target_context_tokens: int) -> List[ChatMessage]:
        """
        Static mode: Keep last N messages verbatim.
        
        Simple and safe - always returns the same number of recent messages.
        """
        # For now, we'll use a fixed number of messages
        # In a more sophisticated version, we'd count tokens and adjust N
        return full_history[-self.static_recent_keep:] if len(full_history) > self.static_recent_keep else full_history
    
    def _select_dynamic(
        self, 
        full_history: List[ChatMessage], 
        session_id: str,
        target_context_tokens: int
    ) -> List[ChatMessage]:
        """
        Dynamic mode: Adjust context amount based on actual usage.
        
        If we've been using less than our target, we can use more (up to a limit).
        If we've been using more, we use less.
        """
        # Get recent usage for this session
        recent_usages = self._usage_history.get(session_id, [])
        
        # Calculate average recent usage
        if recent_usages:
            avg_usage = sum(recent_usages) / len(recent_usages)
            # If we've been using less than target, we can boost up
            if avg_usage < target_context_tokens * self.dynamic_utilization_target:
                boost_factor = min(
                    self.dynamic_max_boost,
                    (target_context_tokens * self.dynamic_utilization_target) / max(avg_usage, 1)
                )
                adjusted_target = int(target_context_tokens * boost_factor)
            else:
                # We've been using enough or more, use target or slightly less
                adjusted_target = int(target_context_tokens * self.dynamic_utilization_target)
        else:
            # No history, use target utilization
            adjusted_target = int(target_context_tokens * self.dynamic_utilization_target)
        
        # But don't go below a minimum or above our hard limit
        adjusted_target = max(
            int(target_context_tokens * self.dynamic_min_utilization),
            min(adjusted_target, target_context_tokens)
        )
        
        # For now, use static selection with adjusted target as message count
        # In a full implementation, we'd count actual tokens
        estimated_messages = max(1, int(adjusted_target / 50))  # Rough estimate: 50 tokens per message
        return full_history[-estimated_messages:] if len(full_history) > estimated_messages else full_history
    
    def _select_reservoir(
        self, 
        full_history: List[ChatMessage], 
        target_context_tokens: int
    ) -> List[ChatMessage]:
        """
        Reservoir mode: Keep recent N verbatim, summarize older content.

        The older portion of the conversation is condensed into a compact
        extractive summary and prepended as a system message, giving the
        model awareness of earlier context without spending tokens on the
        full verbatim history.
        """
        if len(full_history) <= self.reservoir_recent_keep:
            return full_history

        recent_messages = full_history[-self.reservoir_recent_keep:]
        older_messages = full_history[:-self.reservoir_recent_keep]

        summary_text = self._extractive_summarize(
            older_messages, token_budget=self.reservoir_summary_budget
        )

        if summary_text:
            summary_msg = ChatMessage(
                role="system",
                content=f"[Earlier conversation summary]\n{summary_text}",
            )
            return [summary_msg] + recent_messages

        # Summary came back empty (e.g. older_messages had no text) — fall back
        return recent_messages
    
    def _select_adaptive(
        self, 
        full_history: List[ChatMessage], 
        target_context_tokens: int
    ) -> List[ChatMessage]:
        """
        Adaptive mode: Different strategies based on detected task type.

        Code-heavy conversations get reservoir mode so older code context is
        summarized but not lost. General chat uses static (last N messages).
        """
        combined_text = " ".join(msg.content.lower() for msg in full_history)
        code_indicators = [
            "def ", "class ", "import ", "function", "var ", "const ", "let ",
            "=>", "```", "();" 
        ]
        is_code_heavy = any(indicator in combined_text for indicator in code_indicators)

        if is_code_heavy:
            return self._select_reservoir(full_history, target_context_tokens)
        else:
            return self._select_static(full_history, target_context_tokens)

    # ── Extractive Summarization ────────────────────────────────────

    # Stop-words to ignore when scoring sentence importance
    _STOP_WORDS = frozenset({
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "i", "you", "he", "she", "it", "we", "they",
        "my", "your", "his", "her", "its", "our", "their", "that", "this",
        "what", "which", "who", "how", "when", "where", "why", "not", "no",
        "can",
    })

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: 1 word ≈ 1.3 tokens."""
        return int(len(text.split()) * 1.3)

    def _extractive_summarize(
        self, messages: List[ChatMessage], token_budget: int
    ) -> str:
        """
        Build a compact extractive summary of a list of messages.

        Algorithm:
          1. Split each message into sentences.
          2. Score each sentence by the TF (term frequency) of its
             non-stop-word tokens across the whole corpus.
          3. Apply a mild position bias so earlier sentences of each
             message score slightly higher (they tend to be topical).
          4. Greedily pick highest-scoring sentences until the token
             budget is exhausted, preserving their original order.

        Returns a single string ready to embed into a system message.
        """
        if not messages:
            return ""

        # ── Step 1: collect all sentences with metadata ──────────────
        all_sentences: List[dict] = []
        for msg_idx, msg in enumerate(messages):
            role_prefix = "User" if msg.role == "user" else "Assistant"
            raw_sentences = re.split(r"(?<=[.!?])\s+", msg.content.strip())
            for sent_idx, sent in enumerate(raw_sentences):
                sent = sent.strip()
                if sent:
                    all_sentences.append({
                        "text": f"{role_prefix}: {sent}" if sent_idx == 0 else sent,
                        "raw": sent,
                        "msg_idx": msg_idx,
                        "sent_idx": sent_idx,
                        "global_idx": len(all_sentences),
                    })

        if not all_sentences:
            return ""

        # ── Step 2: build term-frequency table ───────────────────────
        def tokenize(text: str) -> List[str]:
            return [
                w.lower()
                for w in re.findall(r"[\w']+", text)
                if w.lower() not in self._STOP_WORDS and len(w) > 2
            ]

        corpus_tokens: List[str] = []
        for s in all_sentences:
            corpus_tokens.extend(tokenize(s["raw"]))

        total = len(corpus_tokens) or 1
        tf = Counter(corpus_tokens)
        # Normalised TF
        tf_norm = {word: count / total for word, count in tf.items()}

        # ── Step 3: score each sentence ──────────────────────────────
        n_sentences = len(all_sentences)
        for s in all_sentences:
            words = tokenize(s["raw"])
            if not words:
                s["score"] = 0.0
                continue
            tf_score = sum(tf_norm.get(w, 0) for w in words) / len(words)
            # Position bias: first sentence of each message +20 %
            position_boost = 0.2 if s["sent_idx"] == 0 else 0.0
            # Mild length penalty for very short or very long sentences
            length_factor = min(1.0, len(words) / 8)  # reward up to 8 words
            s["score"] = (tf_score + position_boost) * length_factor

        # ── Step 4: greedy selection within token budget ──────────────
        ranked = sorted(all_sentences, key=lambda s: s["score"], reverse=True)
        selected_indices: set[int] = set()
        tokens_used = 0

        for s in ranked:
            cost = self._estimate_tokens(s["text"])
            if tokens_used + cost > token_budget:
                continue
            selected_indices.add(s["global_idx"])
            tokens_used += cost
            if tokens_used >= token_budget:
                break

        # Restore original order
        selected = [
            s for s in all_sentences if s["global_idx"] in selected_indices
        ]
        selected.sort(key=lambda s: s["global_idx"])

        return " ".join(s["text"] for s in selected)

    # ── Usage tracking (dynamic mode) ──────────────────────────────

    def update_usage(self, session_id: str, tokens_used: int):
        """
        Update usage tracking for dynamic mode.

        Args:
            session_id: Identifier for the user session
            tokens_used: Number of context tokens used in the last request
        """
        if session_id not in self._usage_history:
            self._usage_history[session_id] = []
        
        self._usage_history[session_id].append(tokens_used)
        
        # Keep only the last 10 samples
        if len(self._usage_history[session_id]) > 10:
            self._usage_history[session_id] = self._usage_history[session_id][-10:]
    
    def get_usage_stats(self, session_id: str) -> dict:
        """Get usage statistics for a session."""
        usages = self._usage_history.get(session_id, [])
        if not usages:
            return {"count": 0, "average": 0, "recent": 0}
        
        return {
            "count": len(usages),
            "average": sum(usages) / len(usages),
            "recent": usages[-1] if usages else 0,
            "min": min(usages),
            "max": max(usages),
        }