import copy
import json
import pytest
from starlette.testclient import TestClient

from agy_proxy.experiments import (
    BLOCKLIST_FLAGS,
    CURATED_EXPERIMENT_IDS,
    CURATED_SAFE_FLAGS,
    NON_BOOL_OPTIMIZATIONS,
    enhance_list_experiments,
    enhance_available_models,
    get_default_experiments_payload,
    get_experiments_status,
    set_experiment_override,
    remove_experiment_override,
    reset_experiment_overrides,
    set_experiment_mode,
    load_experiment_config,
    save_experiment_config,
)
from agy_proxy.server import create_app
from agy_proxy.auth.pool import AccountPool


def test_get_default_experiments_payload():
    payload = get_default_experiments_payload()
    assert isinstance(payload, dict)
    assert "experimentIds" in payload
    assert "flags" in payload

    exp_ids = payload["experimentIds"]
    assert len(exp_ids) >= 121
    assert 106544526 in exp_ids

    flags_dict = {f["name"]: f.get("boolValue") for f in payload["flags"] if "name" in f}
    assert flags_dict.get("enable-deepagent") is True
    assert flags_dict.get("enable-agent-team") is True
    assert flags_dict.get("enable-swarm") is True
    assert flags_dict.get("Chat__enable_chat_moa") is True
    assert flags_dict.get("Chat__enable_chat_agentic_mcp_chat") is True
    assert flags_dict.get("DuetAiGeneration__codeGeneration_enable_diff_view") is True

    # Blocklist verification
    for b_flag in BLOCKLIST_FLAGS:
        assert flags_dict.get(b_flag) is False or flags_dict.get(b_flag) is None


def test_enhance_list_experiments_blocklist_enforcement():
    # Simulate an upstream response where toxic flags were accidentally True
    mock_upstream = {
        "experimentIds": [12345],
        "flags": [
            {"name": "GeminiFreeTier__enable_free_tier", "boolValue": True},
            {"name": "disable-search-tools", "boolValue": True},
            {"name": "disable-command-assessor", "boolValue": True},
            {"name": "remove-conversation-history", "boolValue": True},
            {"name": "GCAFeedbackBlock__enable_feedback_block", "boolValue": True},
            {"name": "disable-loop-detection", "boolValue": True},
            {"name": "enable-deepagent", "boolValue": False},
        ],
    }

    enhanced = enhance_list_experiments(mock_upstream, config_override={"enabled": True, "mode": "curated", "custom_overrides": {}})
    flags_dict = {f["name"]: f.get("boolValue") for f in enhanced["flags"]}

    # Critical blocklist must be forced to False
    assert flags_dict["GeminiFreeTier__enable_free_tier"] is False
    assert flags_dict["disable-search-tools"] is False
    assert flags_dict["disable-command-assessor"] is False
    assert flags_dict["remove-conversation-history"] is False
    assert flags_dict["GCAFeedbackBlock__enable_feedback_block"] is False

    # disable-loop-detection should remain True
    assert flags_dict["disable-loop-detection"] is True

    # Curated safe flag must be enabled
    assert flags_dict["enable-deepagent"] is True

    # Experiment IDs must be merged and contain Claude 5.5 preview ID 106544526
    assert 12345 in enhanced["experimentIds"]
    assert 106544526 in enhanced["experimentIds"]


def test_enhance_list_experiments_non_bool_optimizations():
    mock_upstream = {
        "experimentIds": [],
        "flags": [
            {"name": "Chat__fca_chat_context_window_size", "intValue": "1000"},
            {"name": "DuetAiGeneration__codeGeneration_context_window_size", "intValue": "2000"},
        ],
    }
    enhanced = enhance_list_experiments(mock_upstream, config_override={"enabled": True, "mode": "curated", "custom_overrides": {}})
    flags_dict = {f["name"]: f.get("intValue") for f in enhanced["flags"]}

    assert flags_dict["Chat__fca_chat_context_window_size"] == "3500000"
    assert flags_dict["DuetAiGeneration__codeGeneration_context_window_size"] == "64000"


def test_enhance_list_experiments_modes():
    mock_upstream = {
        "experimentIds": [100],
        "flags": [
            {"name": "some_random_feature", "boolValue": False},
            {"name": "enable-deepagent", "boolValue": False},
            {"name": "disable-search-tools", "boolValue": False},
        ],
    }

    # 1. Mode "passthrough"
    pass_res = enhance_list_experiments(copy.deepcopy(mock_upstream), config_override={"enabled": True, "mode": "passthrough"})
    pass_map = {f["name"]: f.get("boolValue") for f in pass_res["flags"]}
    assert pass_map["enable-deepagent"] is False
    assert pass_map["some_random_feature"] is False

    # 2. Mode "all_safe"
    safe_res = enhance_list_experiments(copy.deepcopy(mock_upstream), config_override={"enabled": True, "mode": "all_safe", "custom_overrides": {}})
    safe_map = {f["name"]: f.get("boolValue") for f in safe_res["flags"]}
    assert safe_map["enable-deepagent"] is True
    assert safe_map["some_random_feature"] is True
    assert safe_map["disable-search-tools"] is False  # Blocklist still enforced!


def test_enhance_available_models_resilience():
    # Test with None capabilities and nested None structures
    mock_models_data = {
        "models": {
            "gemini-3.1-pro-high": {
                "capabilities": None,
                "modelExperiments": None,
            },
            "claude-opus-4-6-thinking": {
                "capabilities": None,
                "modelExperiments": {
                    "experiments": {
                        "reasoning": {"boolValue": False},
                        "extended_context": {"boolValue": False},
                    }
                },
            },
            "gemini-3.8-flash-high": {
                "capabilities": {
                    "chat": {"boolValue": False},
                    "code": {"boolValue": False},
                },
                "modelExperiments": {
                    "experiments": {
                        "deep_research": {"boolValue": False},
                    }
                },
            },
        }
    }

    enhanced = enhance_available_models(mock_models_data)
    assert enhanced["models"]["gemini-3.1-pro-high"]["capabilities"] is None

    claude_exp = enhanced["models"]["claude-opus-4-6-thinking"]["modelExperiments"]["experiments"]
    assert claude_exp["reasoning"]["boolValue"] is True
    assert claude_exp["extended_context"]["boolValue"] is True

    flash_caps = enhanced["models"]["gemini-3.8-flash-high"]["capabilities"]
    assert flash_caps["chat"]["boolValue"] is True
    assert flash_caps["code"]["boolValue"] is True


def test_experiments_status_and_overrides():
    status = get_experiments_status()
    assert "active" in status
    assert "mode" in status
    assert "flags" in status
    assert len(status["flags"]) >= len(CURATED_SAFE_FLAGS)

    # Test override lifecycle
    test_flag = "test_custom_experimental_flag"
    try:
        set_experiment_override(test_flag, True)
        cfg = load_experiment_config()
        assert cfg.get("custom_overrides", {}).get(test_flag) is True

        remove_experiment_override(test_flag)
        cfg = load_experiment_config()
        assert test_flag not in cfg.get("custom_overrides", {})
    finally:
        reset_experiment_overrides()


def test_experiments_api_endpoints():
    pool = AccountPool()
    app = create_app(account_pool=pool)
    client = TestClient(app)

    # GET /api/experiments
    resp = client.get("/api/experiments")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is True
    assert "mode" in data
    assert "flags" in data
    assert data["total_curated_flags"] >= 50

    # POST /api/experiments
    post_resp = client.post("/api/experiments", json={
        "mode": "curated",
        "overrides": {"enable-deepagent": True}
    })
    assert post_resp.status_code == 200
    post_data = post_resp.json()
    assert post_data["status"] == "ok"

    # POST /api/experiments/reset
    reset_resp = client.post("/api/experiments/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "ok"


def test_enhance_list_experiments_strict_oneof_mutual_exclusivity():
    """Verify that every flag in the output has strictly EXACTLY ONE oneof value field."""
    oneof_keys = {"boolValue", "intValue", "floatValue", "stringValue", "stringListValue", "int32ListValue"}

    # 1. Test with default experiments
    payload = get_default_experiments_payload()
    for f in payload.get("flags", []):
        present = set(f.keys()) & oneof_keys
        assert len(present) == 1, f"Flag {f.get('name')} does not have exactly 1 oneof value: {present}"

    # 2. Test with artificially corrupted upstream flags containing multiple oneof fields
    corrupted_upstream = {
        "flags": [
            {
                "name": "enable-deepagent",
                "boolValue": False,
                "stringValue": "corrupted",
                "intValue": "999",
            },
            {
                "name": "GeminiFreeTier__enable_free_tier",
                "boolValue": True,
                "stringValue": "toxic_free_tier",
            },
            {
                "name": "DuetAiLocalRag__cache_co_located",
                "intValue": "20",
                "stringValue": "should_be_float",
            },
            {
                "name": "agy-plugin-marketplaces",
                "stringValue": '{"values": ["old"]}',
            },
            {
                "name": "unknown_flag_with_no_value",
            },
        ]
    }

    enhanced = enhance_list_experiments(corrupted_upstream)
    flags_map = {f["name"]: f for f in enhanced["flags"]}

    for name, f in flags_map.items():
        present = set(f.keys()) & oneof_keys
        assert len(present) == 1, f"Enhanced flag {name} does not have exactly 1 oneof value: {present}"

    # Curated flag should have boolValue True
    assert flags_map["enable-deepagent"]["boolValue"] is True
    assert "stringValue" not in flags_map["enable-deepagent"]
    assert "intValue" not in flags_map["enable-deepagent"]

    # Blocklist flag should have boolValue False
    assert flags_map["GeminiFreeTier__enable_free_tier"]["boolValue"] is False
    assert "stringValue" not in flags_map["GeminiFreeTier__enable_free_tier"]

    # DuetAiLocalRag__cache_co_located should have floatValue
    assert isinstance(flags_map["DuetAiLocalRag__cache_co_located"].get("floatValue"), (int, float))
    assert "intValue" not in flags_map["DuetAiLocalRag__cache_co_located"]

    # agy-plugin-marketplaces should have stringListValue
    assert isinstance(flags_map["agy-plugin-marketplaces"].get("stringListValue"), dict)
    assert "stringValue" not in flags_map["agy-plugin-marketplaces"]

    # Flag with no value should default to boolValue False
    assert flags_map["unknown_flag_with_no_value"]["boolValue"] is False


def test_enhance_list_experiments_input_immutability():
    """Verify that enhance_list_experiments does not mutate its input argument."""
    original_input = {
        "experimentIds": [1001],
        "flags": [
            {"name": "enable-deepagent", "boolValue": False},
            {"name": "GeminiFreeTier__enable_free_tier", "boolValue": True},
        ],
    }
    input_copy = copy.deepcopy(original_input)

    enhanced = enhance_list_experiments(original_input)
    assert original_input == input_copy, "enhance_list_experiments mutated its input argument!"
    assert enhanced["flags"] != original_input["flags"]

