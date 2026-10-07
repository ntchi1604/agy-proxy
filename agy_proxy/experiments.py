"""
Antigravity Experimental Features & Flags Manager.

Manages experimental features and Google CloudCode / Antigravity internal flags.
Safely activates high-value capabilities (e.g. /deepagent, multi-agent teams,
swarms, Mixture of Agents, Model Context Protocol, interactive diff views,
local/remote RAG, sidecars, and skills) while strictly blocking harmful or
restrictive flags (e.g. Free Tier downgrades, disablers, telemetry blocks,
and history wiping).
"""

import copy
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("agy_proxy.experiments")

# Configuration path for user overrides
EXPERIMENTS_CONFIG_FILE = Path.home() / ".config" / "agy-proxy" / "experiments.json"
DEFAULT_EXPERIMENTS_FILE = Path(__file__).parent / "default_experiments.json"

# =============================================================================
# 1. Toxic / Restrictive Flags Blocklist (Must NEVER be True)
# Turning any of these to True downgrades features, disables tools, or breaks the IDE
# =============================================================================
BLOCKLIST_FLAGS: set[str] = {
    # Free tier downgrade (forces quota limits and disables advanced features)
    "GeminiFreeTier__enable_free_tier",
    "GCAUpgradeToPaid__enable_upgrade_from_free_tier",
    "GCAUpgradeToPaid__enable_g1_upgrade_flow",

    # Tool and assessor disablers
    "disable-search-tools",
    "disable-command-assessor",
    "disable-system-message-merging",
    "disable-system-message-tag",
    "disable-teamwork-forced-flash-model",
    "disable-tool-hook-notices",

    # Destructive or broken flags
    "remove-conversation-history",
    "collect-x20-quotas-on-checkin",
    "show-trajectory-labeling-ad",
    "GCAFeedbackBlock__enable_feedback_block",
    "GcaTelemetryBlock__enable_telemetry_block",
    "GcaEventsPipeline__enable_events_pipeline_polling",
    "GcaCitationBlock__enable_citation_block",
    "enable-gemini-next-opt-out-switch",
    "enable-vscode-injection-removal",
    "ApigeeCloudCode__enable_mock_server",
    "DuetAiGeneration__codeGeneration_use_transform_api",
    "allow-pss-experimental-monitors",
    "allow-experimental-monitors",
    "shadow-call-aicode-mendel",
}

DISABLER_PATTERN = re.compile(r"^disable-(?!loop-detection)")

# =============================================================================
# 2. Curated High-Value Experimental Features
# Organized by category with human-readable descriptions
# =============================================================================

EXPERIMENT_CATEGORIES = {
    "agents": "Autonomous Agents, Teams & Swarm Coordination",
    "mcp": "Model Context Protocol (MCP) & Stdio Tools",
    "ui_editor": "UI, Diff View, Thought Steering & Editor UX",
    "rag_context": "RAG, Codebase Awareness & Large Context Windows",
    "tools_plugins": "Tools, Customizations, Skills & Sidecars",
    "sdlc_models": "SDLC Model Connections & Generation Enhancements",
}

CURATED_SAFE_FLAGS: dict[str, dict[str, Any]] = {
    # --- Autonomous Agents & Swarm Coordination ---
    "enable-deepagent": {
        "value": True,
        "category": "agents",
        "desc": "Enables DeepAgent autonomous subagent workflows (/deepagent)",
    },
    "enable-agent-team": {
        "value": True,
        "category": "agents",
        "desc": "Enables autonomous agent team collaboration",
    },
    "enable-swarm": {
        "value": True,
        "category": "agents",
        "desc": "Enables multi-agent swarm task execution",
    },
    "enable-native-swarm": {
        "value": True,
        "category": "agents",
        "desc": "Enables native swarm orchestration engine",
    },
    "enable-subagent-hub": {
        "value": True,
        "category": "agents",
        "desc": "Enables Subagent Hub UI and manager",
    },
    "enable-subagent-user-messaging": {
        "value": True,
        "category": "agents",
        "desc": "Allows subagents to communicate directly with user",
    },
    "enable-teamwork-subagent": {
        "value": True,
        "category": "agents",
        "desc": "Enables specialized teamwork subagents",
    },
    "enable-battle-mode": {
        "value": True,
        "category": "agents",
        "desc": "Enables battle mode for comparative multi-agent testing",
    },
    "enable-battle-contrib-variants": {
        "value": True,
        "category": "agents",
        "desc": "Enables battle mode contribution variants",
    },
    "enable-battle-mode-custom-agents": {
        "value": True,
        "category": "agents",
        "desc": "Allows custom agents in battle mode",
    },
    "enable-trajectory-debug-in-battle-mode": {
        "value": True,
        "category": "agents",
        "desc": "Trajectory debugging in battle mode",
    },
    "jetski-autonomous-mode": {
        "value": True,
        "category": "agents",
        "desc": "Enables autonomous mode in Jetski engine",
    },
    "jetski-unified-customizations-panel-enabled": {
        "value": True,
        "category": "agents",
        "desc": "Enables unified customizations panel",
    },
    "convenient-multi-agent-coordination": {
        "value": True,
        "category": "agents",
        "desc": "Enables streamlined multi-agent coordination protocol",
    },
    "Chat__enable_chat_moa": {
        "value": True,
        "category": "agents",
        "desc": "Enables Mixture of Agents (MoA) synthesis in chat",
    },
    "Chat__enable_chat_crescendo_agents": {
        "value": True,
        "category": "agents",
        "desc": "Enables crescendo multi-turn agent workflows",
    },
    "Chat__enable_agent_mode_slash_commands": {
        "value": True,
        "category": "agents",
        "desc": "Enables slash commands in agent mode",
    },
    "Chat__enable_agentic_chat_ij": {
        "value": True,
        "category": "agents",
        "desc": "Enables agentic chat in JetBrains & IDE extensions",
    },
    "enable-markdown-agents": {
        "value": True,
        "category": "agents",
        "desc": "Enables markdown-specified agent prompts and roles",
    },
    "enable-autonomous-mode-critic": {
        "value": True,
        "category": "agents",
        "desc": "Enables critic evaluation in autonomous mode",
    },
    "enable-concierge-agent": {
        "value": True,
        "category": "agents",
        "desc": "Enables concierge routing subagent",
    },
    "enable-browser-subagent-v2": {
        "value": True,
        "category": "agents",
        "desc": "Enables browser subagent v2 for web exploration",
    },
    "enable-image-generator-subagent": {
        "value": True,
        "category": "agents",
        "desc": "Enables image generator subagent",
    },

    # --- Model Context Protocol (MCP) ---
    "Chat__enable_chat_agentic_mcp_chat": {
        "value": True,
        "category": "mcp",
        "desc": "Enables agentic Model Context Protocol (MCP) chat integration",
    },
    "Chat__enable_mcp_server": {
        "value": True,
        "category": "mcp",
        "desc": "Enables MCP server connectivity in Antigravity",
    },
    "Chat__enable_mcp_server_ij": {
        "value": True,
        "category": "mcp",
        "desc": "Enables MCP server integration in IDE extensions",
    },
    "DatacloudMcp__enable_stdio_mcp_proxy": {
        "value": True,
        "category": "mcp",
        "desc": "Enables stdio MCP server proxy",
    },
    "enable-mcp-apps": {
        "value": True,
        "category": "mcp",
        "desc": "Enables MCP application integration",
    },
    "enable-mcp-non-blocking-turn-load": {
        "value": True,
        "category": "mcp",
        "desc": "Enables non-blocking turn loading during MCP tool calls",
    },

    # --- UI, Diff Views & Editor UX ---
    "DuetAiGeneration__codeGeneration_enable_diff_view": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables rich inline diff view for generated code",
    },
    "DuetAiGeneration__codeGeneration_enable_pane_view": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables side-by-side pane view for code generation",
    },
    "enable-split-view": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables split editor view in chat/editor panels",
    },
    "enable-file-diff-accumulator": {
        "value": True,
        "category": "ui_editor",
        "desc": "Accumulates multi-file diffs across agent turns",
    },
    "enable-thought-editing": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables inspecting and steering reasoning thought streams",
    },
    "enable-thought-steering-from-selection": {
        "value": True,
        "category": "ui_editor",
        "desc": "Steers model thoughts using current editor selection",
    },
    "enable-conversation-forking": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables conversation branching and forking",
    },
    "enable-conversation-groups": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables logical conversation groups",
    },
    "enable-conversation-search-v2": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables full conversation history search v2",
    },
    "enable-conversation-selection-quoting": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables quoting selected code directly into chat prompt",
    },
    "enable-file-explorer-tab": {
        "value": True,
        "category": "ui_editor",
        "desc": "Adds file explorer tab directly in agent workspace view",
    },
    "enable-file-viewer-keyboard-navigation": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables smooth keyboard navigation in file viewer",
    },
    "enable-notebook-rendering": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables native Jupyter notebook rendering in Antigravity",
    },
    "enable-pdf-viewer": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables built-in PDF viewer",
    },
    "enable-tasks": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables interactive task tracking panel",
    },
    "enable-compact-slash-command": {
        "value": True,
        "category": "ui_editor",
        "desc": "Compact slash command list formatting",
    },
    "enable-input-autocomplete": {
        "value": True,
        "category": "ui_editor",
        "desc": "Autocomplete in chat prompt input",
    },
    "enable-input-draft-persistence": {
        "value": True,
        "category": "ui_editor",
        "desc": "Persists prompt drafts across window and tab switches",
    },
    "DuetAiGeneration__codeGeneration_enable_quickpick_chat": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables quickpick model and action selection in chat",
    },
    "Chat__enable_code_customization_webview": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables webview panel for codebase customizations",
    },
    "Chat__enable_custom_prompts": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables reusable custom prompts library",
    },
    "Chat__delete_chat_request_button": {
        "value": True,
        "category": "ui_editor",
        "desc": "Allows deleting and editing previous user prompts",
    },
    "Chat__edit_chat_request_button": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables editing previous chat turns",
    },
    "Chat__stop_chat_request_button": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables clean stop button during generation",
    },
    "Chat__enable_chat_checkpoints": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables conversation restore checkpoints",
    },
    "Chat__enable_chat_streaming": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables realtime SSE token streaming",
    },
    "enable-run-command-semantic-rendering": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables semantic terminal execution rendering",
    },
    "markdown-table-v2": {
        "value": True,
        "category": "ui_editor",
        "desc": "Enables enhanced markdown table formatting v2",
    },

    # --- RAG, Codebase Awareness & Context Windows ---
    "Chat__enable_chat_folder_context_selection": {
        "value": True,
        "category": "rag_context",
        "desc": "Allows selecting entire folders as context in chat",
    },
    "Chat__enable_full_codebase_awareness_chat": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables comprehensive full-codebase context indexing",
    },
    "Chat__enable_local_codebase_awareness_chat_ij": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables local codebase awareness in IDEs",
    },
    "DuetAiLocalRag__enable_local_rag_completion_snippets": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables local RAG context snippets for completions",
    },
    "DuetAiLocalRag__enable_local_rag_completion_snippets_with_pruning": {
        "value": True,
        "category": "rag_context",
        "desc": "Local RAG snippet extraction with intelligent pruning",
    },
    "DuetAiLocalRag__enable_local_rag_completion_snippets_with_pruning_bm25_scoring": {
        "value": True,
        "category": "rag_context",
        "desc": "BM25 snippet scoring for local RAG completions",
    },
    "DuetAiLocalRag__enable_local_rag_completion_snippets_with_pruning_colocated_files": {
        "value": True,
        "category": "rag_context",
        "desc": "Includes colocated workspace files in RAG snippets",
    },
    "DuetAiLocalRag__include_currently_open_files": {
        "value": True,
        "category": "rag_context",
        "desc": "Automatically includes open editor tabs in RAG context",
    },
    "DuetAiLocalRag__include_doc_files": {
        "value": True,
        "category": "rag_context",
        "desc": "Includes documentation files (*.md, *.rst) in RAG context",
    },
    "DuetAiLocalRag__enable_wald_file_selection": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables Wald file selection heuristics for RAG",
    },
    "DuetAiRemoteRag__enable_remote_rag": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables remote codebase RAG queries",
    },
    "DuetAiRemoteRag__enable_remote_rag_chat": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables remote RAG retrieval within chat",
    },
    "DuetAiRemoteRag__enable_hyde_for_generation": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables Hypothetical Document Embeddings (HyDE) for generation",
    },
    "enable-ripgrep-path-search": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables ripgrep-powered ultra-fast path search",
    },
    "enable-code-search-palette": {
        "value": True,
        "category": "rag_context",
        "desc": "Enables code search command palette",
    },

    # --- Tools, Customizations, Skills & Sidecars ---
    "enable-hub-builtin-browser": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables built-in Chromium browser in Antigravity Hub",
    },
    "enable-programmatic-tools": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables programmatic tool execution",
    },
    "enable-run-workflow-tool": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables running custom automation workflows",
    },
    "enable-ask-question-tool": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables interactive ask_question modal tool",
    },
    "enable-ask-permission-tool": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables granular permission prompt tool",
    },
    "enable-wait-tool": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables asynchronous wait tool for long-running tasks",
    },
    "enable-persistent-terminals": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables persistent shell terminal sessions",
    },
    "enable-pty": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables PTY terminal emulation support",
    },
    "enable-plugins": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables Antigravity plugin system",
    },
    "enable-plugin-bundles": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables bundled plugin installation",
    },
    "enable-plugin-themes": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables custom UI plugin themes",
    },
    "enable-plugin-auth": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables authentication manager for plugins",
    },
    "enable-marketplace-search-tool": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables searching the extension & tool marketplace",
    },
    "enable-customization-skills": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables Antigravity custom skills framework (SKILL.md)",
    },
    "enable-sidecar-sdk": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables Sidecar SDK integration",
    },
    "enable-ui-sidecars": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables UI sidecars inside editor panels",
    },
    "enable-sidecars": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables background sidecar services",
    },
    "enable-developer-mode": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables Antigravity developer mode & diagnostics",
    },
    "enable-directory-local-discovery": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables directory-local discovery for skills and rules",
    },
    "enable-trustedcli-config-files": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables trusted CLI configuration files",
    },
    "enable-generative-hooks": {
        "value": True,
        "category": "tools_plugins",
        "desc": "Enables generative hook listeners",
    },

    # --- SDLC Model Connections & Completions ---
    "SDLCAgents__enable_anthropic_model_connection": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables direct Anthropic Claude backend connection",
    },
    "SDLCAgents__enable_azure_model_connection": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables Azure OpenAI model connection",
    },
    "SDLCAgents__enable_gemini_model_connection": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables Google Gemini model connection",
    },
    "SDLCAgents__enable_rest_model_connection": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables standard REST LLM model endpoints",
    },
    "DuetAICodeTransform__enable_m2": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables M2 code transformation pipeline",
    },
    "DuetAICodeTransformIj__enable_ij": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables JetBrains IDE code transformation support",
    },
    "CliComplexityBasedRouting__enabled": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables complexity-based automatic model routing",
    },
    "DuetAiCompletion__codeCompletion_enablePrefetchNextSuggestions": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Prefetches next code completion suggestions in background",
    },
    "DuetAiCompletion__codeCompletion_enableAdaptingCache": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables adaptive completion cache",
    },
    "DuetAiCompletion__codeCompletion_enableInfixCache": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Enables infix completion cache",
    },
    "enable-model-capacity-exhausted-retries": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Automatically retries alternative models on capacity exhaustion",
    },
    "disable-loop-detection": {
        "value": True,
        "category": "sdlc_models",
        "desc": "Prevents false-positive agent loop interrupts on long workflows",
    },
}

# Optimized non-bool flag overrides
NON_BOOL_OPTIMIZATIONS: dict[str, dict[str, Any]] = {
    "Chat__fca_chat_context_window_size": {
        "intValue": "3500000",
        "desc": "Expanded 3.5M token full codebase context window",
    },
    "DuetAiGeneration__codeGeneration_context_window_size": {
        "intValue": "64000",
        "desc": "Expanded 64k token code generation window",
    },
}

# =============================================================================
# 3. Verified Upstream Experiment IDs
# Extracted from traffic dumps. Includes 106544526 (Claude 5.5 & Vertex preview)
# =============================================================================
CURATED_EXPERIMENT_IDS: list[int] = [
    101551624, 101868197, 103012592, 103012598, 103118069, 103118072, 104638459,
    104638466, 104673683, 104817729, 104913210, 104913215, 104922082, 104922093,
    105011762, 105620012, 105620019, 105658064, 105658067, 105658068, 105658071,
    105695344, 105695346, 105721268, 105721273, 105723762, 105746178, 105746180,
    105746181, 105746183, 105785683, 105785684, 105821928, 105821930, 105822881,
    105822884, 105822886, 105856899, 105867469, 105867471, 105887311, 105887313,
    105906495, 105943694, 105943702, 105979517, 105979530, 105979531, 105979552,
    105979553, 105979574, 106015328, 106015351, 106032301, 106032303, 106064028,
    106064030, 106100625, 106100654, 106106760, 106113877, 106113900, 106121399,
    106121401, 106121604, 106121607, 106143956, 106221097, 106221101, 106228452,
    106264150, 106264162, 106264532, 106281951, 106283614, 106283618, 106392106,
    106392108, 106392113, 106392115, 106392120, 106392122, 106413417, 106413419,
    106428370, 106428372, 106458967, 106458969, 106474625, 106474627, 106511968,
    106544526, 106555564, 106555566, 106568390, 106568772, 106588527, 106597020,
    106617388, 106617390, 106621675, 106640124, 106640126, 106643242, 106659335,
    106659337, 106659338, 106659344, 106659346, 106659347, 106670811, 106676368,
    106701431, 106701435, 106711598, 106713377, 106713379, 106713380, 106713382,
    106724030, 106754391
]


# =============================================================================
# 4. Configuration Management
# =============================================================================

def load_experiment_config() -> dict[str, Any]:
    """Loads user experimental feature settings from disk."""
    default_config = {
        "enabled": True,
        "mode": "curated",  # Options: "curated" (safe & rich), "all_safe", "passthrough"
        "custom_overrides": {},
    }
    if not EXPERIMENTS_CONFIG_FILE.exists():
        return default_config
    try:
        with open(EXPERIMENTS_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                default_config.update(data)
    except Exception as e:
        logger.warning("Could not read experiment config from %s: %s", EXPERIMENTS_CONFIG_FILE, e)
    return default_config


def save_experiment_config(config: dict[str, Any]) -> bool:
    """Saves user experimental feature settings to disk."""
    try:
        EXPERIMENTS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(EXPERIMENTS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error("Failed to write experiment config to %s: %s", EXPERIMENTS_CONFIG_FILE, e)
        return False


def get_default_experiments_payload() -> dict[str, Any]:
    """
    Returns full default listExperiments response payload with all 121 IDs
    and 446 curated flags. Used for offline fallback or cold boot.
    """
    if DEFAULT_EXPERIMENTS_FILE.exists():
        try:
            with open(DEFAULT_EXPERIMENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return enhance_list_experiments(data)
        except Exception as e:
            logger.warning("Could not load default_experiments.json: %s", e)

    # Fallback structure if file is missing
    flags_list = []
    for name, meta in CURATED_SAFE_FLAGS.items():
        flags_list.append({"name": name, "boolValue": meta["value"]})
    for name in BLOCKLIST_FLAGS:
        flags_list.append({"name": name, "boolValue": False})

    return {
        "experimentIds": copy.deepcopy(CURATED_EXPERIMENT_IDS),
        "flags": flags_list,
    }


# =============================================================================
# 5. Core Enhancement & Safety Transformers
# =============================================================================

def enhance_list_experiments(
    data: dict[str, Any],
    config_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Transforms /v1internal:listExperiments response:
    1. Injects and deduplicates 121 rich experiment IDs (including 106544526 for Claude 5.5).
    2. Strictly disables toxic/disabling flags in BLOCKLIST_FLAGS and ^disable-*.
    3. Safely activates CURATED_SAFE_FLAGS (deepagent, swarm, MOA, MCP, diff-view, RAG, etc.).
    4. Applies user custom overrides from ~/.config/agy-proxy/experiments.json.
    5. Optimizes non-bool parameters (e.g. 3.5M token context window).
    """
    if not isinstance(data, dict):
        return data

    cfg = config_override or load_experiment_config()
    if not cfg.get("enabled", True) or cfg.get("mode") == "passthrough":
        return data

    mode = cfg.get("mode", "curated")
    user_overrides = cfg.get("custom_overrides", {})

    # --- 1. Merge & deduplicate experimentIds ---
    existing_ids = data.get("experimentIds", [])
    seen_ids = set()
    merged_ids: list[Any] = []

    # Preserve upstream IDs first
    if isinstance(existing_ids, list):
        for eid in existing_ids:
            s_eid = str(eid)
            if s_eid not in seen_ids:
                seen_ids.add(s_eid)
                merged_ids.append(eid)

    # Add curated IDs
    for cid in CURATED_EXPERIMENT_IDS:
        s_cid = str(cid)
        if s_cid not in seen_ids:
            seen_ids.add(s_cid)
            merged_ids.append(cid)

    data["experimentIds"] = merged_ids

    # --- 2. Process Flags ---
    existing_flags = data.get("flags", [])
    flag_map: dict[str, dict[str, Any]] = {}

    if isinstance(existing_flags, list):
        for fl in existing_flags:
            if isinstance(fl, dict) and "name" in fl:
                flag_map[fl["name"]] = fl

    # Helper to update or append flag
    def _apply_flag(name: str, value: bool):
        if name in flag_map:
            flag_map[name]["boolValue"] = value
        else:
            new_fl = {"name": name, "boolValue": value}
            flag_map[name] = new_fl

    # Process all existing flags according to rules
    for name, fl in list(flag_map.items()):
        # Rule A: User explicit override has highest priority
        if name in user_overrides:
            fl["boolValue"] = bool(user_overrides[name])
            continue

        # Rule B: Strict Blocklist & disablers must ALWAYS be False
        if name in BLOCKLIST_FLAGS or DISABLER_PATTERN.match(name):
            fl["boolValue"] = False
            continue

        # Rule C: Curated safe flags
        if name in CURATED_SAFE_FLAGS:
            fl["boolValue"] = CURATED_SAFE_FLAGS[name]["value"]
            continue

        # Rule D: In "all_safe" mode, enable remaining bool flags (except blocklisted ones)
        if mode == "all_safe" and "boolValue" in fl:
            fl["boolValue"] = True

    # Rule E: Ensure all curated safe flags exist even if missing from upstream response
    for name, meta in CURATED_SAFE_FLAGS.items():
        if name not in flag_map:
            # Check user override first
            val = user_overrides[name] if name in user_overrides else meta["value"]
            _apply_flag(name, val)

    # Rule F: Ensure all blocklist flags are present and False
    for name in BLOCKLIST_FLAGS:
        if name in flag_map:
            if name not in user_overrides:
                flag_map[name]["boolValue"] = False

    # Rule G: Optimize non-bool flags (context window etc.)
    for name, opt in NON_BOOL_OPTIMIZATIONS.items():
        if name in flag_map:
            fl = flag_map[name]
            for k, v in opt.items():
                if k != "desc":
                    fl[k] = v
        else:
            new_fl = {"name": name}
            for k, v in opt.items():
                if k != "desc":
                    new_fl[k] = v
            flag_map[name] = new_fl

    data["flags"] = list(flag_map.values())
    return data


def enhance_available_models(data: dict[str, Any]) -> dict[str, Any]:
    """
    Safely unlocks model capabilities and experiments in /v1internal:fetchAvailableModels.
    Protected against None capabilities and missing keys.
    """
    if not isinstance(data, dict):
        return data

    models = data.get("models")
    if not isinstance(models, dict):
        return data

    for model_id, model_data in models.items():
        if not isinstance(model_data, dict):
            continue

        # 1. Capabilities (chat, code, streaming, toolCalling)
        caps = model_data.get("capabilities")
        if isinstance(caps, dict):
            for section in caps.values():
                if isinstance(section, dict):
                    if "boolValue" in section:
                        section["boolValue"] = True
                    for k, v in section.items():
                        if isinstance(v, dict) and "boolValue" in v:
                            v["boolValue"] = True
                elif isinstance(section, bool):
                    pass

        # 2. ModelExperiments (extended context, reasoning, deep research)
        model_exp = model_data.get("modelExperiments")
        if isinstance(model_exp, dict):
            experiments = model_exp.get("experiments")
            if isinstance(experiments, dict):
                for exp_name, exp_val in experiments.items():
                    if isinstance(exp_val, dict) and "boolValue" in exp_val:
                        exp_val["boolValue"] = True

    return data


# =============================================================================
# 6. Status & Query API Helpers
# =============================================================================

def get_experiments_status() -> dict[str, Any]:
    """Returns detailed status of all experimental flags and configuration."""
    cfg = load_experiment_config()
    overrides = cfg.get("custom_overrides", {})
    mode = cfg.get("mode", "curated")

    flags_info = []
    for name, meta in CURATED_SAFE_FLAGS.items():
        eff_value = overrides.get(name, meta["value"])
        flags_info.append({
            "name": name,
            "category": meta.get("category", "other"),
            "category_label": EXPERIMENT_CATEGORIES.get(meta.get("category", "other"), "Other"),
            "enabled": eff_value,
            "default": meta["value"],
            "is_overridden": name in overrides,
            "description": meta.get("desc", ""),
        })

    blocked_info = []
    for name in sorted(list(BLOCKLIST_FLAGS)):
        blocked_info.append({
            "name": name,
            "blocked": True,
            "reason": "Security, stability or free-tier restriction protection",
        })

    return {
        "active": cfg.get("enabled", True),
        "mode": mode,
        "total_curated_flags": len(CURATED_SAFE_FLAGS),
        "total_experiment_ids": len(CURATED_EXPERIMENT_IDS),
        "total_blocked_flags": len(BLOCKLIST_FLAGS),
        "overrides_count": len(overrides),
        "categories": EXPERIMENT_CATEGORIES,
        "flags": flags_info,
        "blocked": blocked_info,
    }


def set_experiment_override(flag_name: str, value: bool) -> bool:
    """Sets a custom override for a specific experimental flag."""
    cfg = load_experiment_config()
    if "custom_overrides" not in cfg or not isinstance(cfg["custom_overrides"], dict):
        cfg["custom_overrides"] = {}
    cfg["custom_overrides"][flag_name] = bool(value)
    return save_experiment_config(cfg)


def remove_experiment_override(flag_name: str) -> bool:
    """Removes a custom override for a specific experimental flag."""
    cfg = load_experiment_config()
    if "custom_overrides" in cfg and flag_name in cfg["custom_overrides"]:
        del cfg["custom_overrides"][flag_name]
        return save_experiment_config(cfg)
    return True


def reset_experiment_overrides() -> bool:
    """Resets all custom overrides back to curated defaults."""
    cfg = load_experiment_config()
    cfg["custom_overrides"] = {}
    return save_experiment_config(cfg)


def set_experiment_mode(mode: str) -> bool:
    """Sets the experiment operating mode ('curated', 'all_safe', 'passthrough')."""
    if mode not in ("curated", "all_safe", "passthrough"):
        raise ValueError(f"Invalid mode '{mode}'. Choose from: curated, all_safe, passthrough")
    cfg = load_experiment_config()
    cfg["mode"] = mode
    return save_experiment_config(cfg)
