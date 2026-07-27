import logging
import re
from typing import Any

from .graphify import load_graphify_summary
from .personas import (
    get_claude_opus_persona_summary,
    get_default_best_persona,
    get_fable5_mythos_persona_summary,
    get_gemini_36_persona_summary,
    get_gpt56_thinking_persona_summary,
    get_gstack_workflow_summary,
)



from .skills_matcher import format_skills_and_roles_context, match_and_get_skills_context
from .local_reasoner import predict_intent_and_skills_with_smollm2, predict_intent_with_smollm2
from .adr_generator import should_generate_adr
from .debt_scanner import scan_workspace_for_debt
from .indexer import ensure_workspace_indexed, link_monorepo_context
from .pattern_memory import search_patterns
from .prompt_tuner import tune_system_prompt_for_intent
from .obsidian_vault import get_obsidian_vault_summary
from .query_optimizer import get_query_optimization_context
from .infra_terraform import get_infra_terraform_context
from .api_contract import get_api_contract_context
from .strix_auditor import get_strix_security_audit_context
from .asset_generator import get_web_asset_generator_context
from .typeui_designer import get_typeui_design_context
from .opus_reasoner import generate_opus_pass1_plan
from .gemini_graph import query_gemini_workspace_graph












logger = logging.getLogger("opencode-proxy.orchestrator")

INTENT_PATTERNS = {
    "refactor": re.compile(r"\b(refactor|feature|build|implement|add|create|rewrite|worktree|tdd)\b", re.I),
    "debugging": re.compile(r"\b(bug|fix|error|trace|debug|crash|fail|exception|leak|memory|issue)\b", re.I),
    "docs": re.compile(r"\b(doc|documentation|library|sdk|api|help|usage|how to|upstash|context7)\b", re.I),
    "security": re.compile(r"\b(security|secret|vulnerability|cve|auth|jwt|password|token|xss|csrf)\b", re.I),
    "qa": re.compile(r"\b(test|qa|unittest|pytest|jest|coverage|mock|assert|playwright|e2e)\b", re.I),
    "frontend": re.compile(r"\b(ui|ux|design|css|frontend|style|theme|color|bento|glassmorphism|tailwind|shadcn)\b", re.I),
    "planning": re.compile(r"\b(plan|roadmap|architecture|design|spec|prd|cto|architect)\b", re.I),

}


def classify_intent(payload: dict[str, Any]) -> str:
    """Classify the incoming prompt payload into a primary task category.

    Tries SmolLM2-135M local reasoning model first (< 15ms). Falls back to pattern heuristics.
    """
    if not isinstance(payload, dict):
        return "general"

    messages = payload.get("messages", [])
    if not messages:
        return "general"

    user_text = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_text += " " + content.lower()
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        user_text += " " + block.get("text", "").lower()
            break

    if not user_text.strip():
        return "general"

    # Try local SmolLM2-135M reasoning model first
    smollm2_intent = predict_intent_with_smollm2(user_text)
    if smollm2_intent:
        return smollm2_intent

    # Fallback to fast pattern heuristics
    for category, pattern in INTENT_PATTERNS.items():
        if pattern.search(user_text):
            return category

    return "general"



def orchestrate_payload(payload: dict[str, Any], workspace_path: str | None = None) -> str:
    """Smart Middle-Layer Orchestrator: Dynamically classifies intent and synthesizes optimal skills/plugins.

    Selects the minimal, best-fit set of skills per request to maximize reasoning accuracy while avoiding prompt bloat.
    """
    if workspace_path:
        ensure_workspace_indexed(workspace_path)
        observe_payload(payload, workspace_path=workspace_path)

    intent = classify_intent(payload)
    logger.info("Smart Orchestrator classified request intent: %s for workspace: %s", intent, workspace_path)

    sections: list[str] = []

    # Extract last user message text for cross-cutting checks
    user_text = ""
    for msg in reversed(payload.get("messages", [])):
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                user_text = content
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        user_text += block.get("text", "")
            break

    # 1. Base Principal Architect & Staff Engineer Persona Baseline
    default_persona = get_default_best_persona()
    if default_persona:
        sections.append(default_persona.strip())

    # 2. Workspace Persistent SQLite Memory & AST Graph (if workspace available)
    if workspace_path:
        memory_summary = get_workspace_memory_summary(workspace_path=workspace_path)
        if memory_summary:
            sections.append(memory_summary.strip())

        graph_summary = load_graphify_summary(workspace_path=workspace_path)
        if graph_summary:
            sections.append(graph_summary.strip())

    # 2a. Cross-Session Pattern Memory Recall (BM25 FTS5 semantic search)
    if user_text.strip():
        recalled = search_patterns(user_text[:128], limit=3)
        if recalled:
            recall_lines = [f"  - [{r['category']}] {r['description']}" for r in recalled]
            sections.append(
                "\n--- CODEBASE PATTERN MEMORY (Institutional Knowledge Recall) ---\n"
                + "\n".join(recall_lines)
                + "\n--- END PATTERN MEMORY ---"
            )

    # 2b. Proactive Technical Debt Report (AST scan)
    if workspace_path:
        debt_issues = scan_workspace_for_debt(workspace_path, max_files=20)
        high_debt = [d for d in debt_issues if d.severity == "high"]
        if high_debt:
            debt_lines = [f"  - [{d.issue_type}] {d.file.split('/')[-1]}:{d.line} {d.detail}" for d in high_debt[:5]]
            sections.append(
                "\n--- TECHNICAL DEBT ALERT (Proactive DE Scan) ---\n"
                + "\n".join(debt_lines)
                + "\n--- END DEBT ALERT ---"
            )

    # 2d. Cross-Repo Monorepo Symbol Linker & Specialized Coding Skills
    if user_text.strip():
        monorepo_ctx = link_monorepo_context(user_text)
        if monorepo_ctx:
            sections.append(monorepo_ctx.strip())

        obsidian_ctx = get_obsidian_vault_summary()
        if obsidian_ctx:
            sections.append(obsidian_ctx.strip())

        sql_ctx = get_query_optimization_context(user_text)
        if sql_ctx:
            sections.append(sql_ctx.strip())

        iac_ctx = get_infra_terraform_context(user_text)
        if iac_ctx:
            sections.append(iac_ctx.strip())

        contract_ctx = get_api_contract_context(user_text)
        if contract_ctx:
            sections.append(contract_ctx.strip())

        strix_ctx = get_strix_security_audit_context(user_text)
        if strix_ctx:
            sections.append(strix_ctx.strip())

        asset_ctx = get_web_asset_generator_context(user_text)
        if asset_ctx:
            sections.append(asset_ctx.strip())

        typeui_ctx = get_typeui_design_context(user_text)
        if typeui_ctx:
            sections.append(typeui_ctx.strip())




        opus_plan = generate_opus_pass1_plan(user_text)
        if opus_plan:
            sections.append(opus_plan.strip())




    # 3. Dynamic Intent-Based Plugin & Skill Synthesis
    if intent == "refactor":
        sections.append(
            "\n--- ORCHESTRATED TOOL: OBRA/SUPERPOWERS (TDD & WORKTREE REFRACTORING) ---\n"
            "- Practice Test-Driven Development (TDD): Write or specify failing tests before writing logic.\n"
            "- Worktree Isolation: Keep changes modular and avoid breaking active code paths.\n"
            "- High Architecture Standards: Simplify complex logic and reduce technical debt.\n"
            "--- END SUPERPOWERS TOOL ---"
        )
        sections.append(get_gstack_workflow_summary().strip())

    elif intent == "debugging":
        sections.append(
            "\n--- ORCHESTRATED TOOL: SEQUENTIAL THINKING MCP (STEP-BY-STEP REASONING SCRATCHPAD) ---\n"
            "- Step-by-Step Analysis: Break down complex bug behavior into sequential hypotheses.\n"
            "- Revision & Branching: Revise earlier assumptions if empirical log/test evidence contradicts them.\n"
            "- Root Cause Verification: Verify underlying contracts before declaring bug resolution.\n"
            "--- END SEQUENTIAL THINKING TOOL ---"
        )

    elif intent == "docs":
        sections.append(
            "\n--- ORCHESTRATED TOOL: UPSTASH CONTEXT7 (REAL-TIME DOCUMENTATION RETRIEVAL) ---\n"
            "- Retrieve latest version-specific API signatures and documentation snippets.\n"
            "- Avoid deprecated methods or obsolete syntax.\n"
            "--- END CONTEXT7 TOOL ---"
        )

    elif intent == "security":
        sections.append(
            "\n--- ORCHESTRATED TOOL: OFFICIAL SECURITY AUDITOR & GSTACK REVIEW ---\n"
            "- Audit for hardcoded secrets, plain-text tokens, and unvalidated user inputs.\n"
            "- Enforce safe defaults, strict access controls, and sanitized error responses.\n"
            "--- END SECURITY TOOL ---"
        )

    elif intent == "qa":
        sections.append(
            "\n--- ORCHESTRATED TOOL: QA ARCHITECT & AUTOMATED TEST SUITE ---\n"
            "- Formulate complete test coverage spanning unit, integration, and E2E scenarios.\n"
            "- Handle edge cases, boundary failures, and race conditions with zero test flakiness.\n"
            "--- END QA TOOL ---"
        )

    elif intent == "frontend":
        sections.append(
            "\n--- ORCHESTRATED TOOL: NEXTLEVELBUILDER UI/UX PRO MAX DESIGN INTELLIGENCE ---\n"
            "- UI Style Architecture: Apply modern Glassmorphism, Bento Grid, Neumorphism, or Claymorphism design system.\n"
            "- Color & Typography: Use curated industry-specific color palettes, HSL variables, and Google Fonts font pairings.\n"
            "- Accessibility & Responsiveness: Enforce ARIA labels, 4.5:1 contrast ratios, focus states, and mobile layout validation.\n"
            "--- END UI/UX PRO MAX TOOL ---"
        )

    elif intent == "planning":
        sections.append(
            "\n--- ORCHESTRATED TOOL: PRINCIPAL ARCHITECT PLANNING MODE ---\n"
            "- System Design First: Define components, data flows, and contracts before writing code.\n"
            "- Document Decisions: Every architectural choice must include rationale and trade-offs.\n"
            "- Estimate Blast Radius: Evaluate downstream impact on all consumers before committing to a design.\n"
            "- Review Non-Functional Requirements: Consider scalability, security, observability, and cost.\n"
            "--- END PLANNING TOOL ---"
        )
        sections.append(get_gstack_workflow_summary().strip())

    # 3. Dynamic Flagship Persona Selection
    if intent in ("refactor", "planning"):
        sections.append(get_claude_opus_persona_summary().strip())
        sections.append(get_fable5_mythos_persona_summary().strip())
    elif intent == "debugging":
        sections.append(get_gpt56_thinking_persona_summary().strip())
    elif intent in ("qa", "frontend"):
        sections.append(get_gemini_36_persona_summary().strip())
    else:
        # General / Baseline: Inject Universal Flagship Baseline
        sections.append(get_default_best_persona().strip())
        sections.append(get_gpt56_thinking_persona_summary().strip())
        sections.append(get_gemini_36_persona_summary().strip())

    sections.append(get_gstack_workflow_summary().strip())




    # 4. Intent Keyword Matcher & SmolLM2 Skill Predictor
    smollm2_prediction = predict_intent_and_skills_with_smollm2(user_text) if user_text else None
    if smollm2_prediction and (smollm2_prediction.get("skills") or smollm2_prediction.get("role")):
        predicted_items = list(smollm2_prediction.get("skills", []))
        if smollm2_prediction.get("role"):
            predicted_items.append(smollm2_prediction["role"])
        smollm2_ctx = format_skills_and_roles_context(predicted_items)
        if smollm2_ctx:
            sections.append(smollm2_ctx.strip())

    matched_skills = match_and_get_skills_context(payload)
    if matched_skills:
        sections.append(matched_skills.strip())

    combined_system = "\n\n".join(sections)
    return tune_system_prompt_for_intent(combined_system, intent, user_prompt=user_text)



