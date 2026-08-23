"""Phase 23D-B — ComfyUI Client Foundation.

No live ComfyUI server or GPU required: httpx is monkeypatched at the
call site, matching how the rest of the suite keeps LLM behavior
deterministic via FakeLLMService rather than a real Ollama server.
"""
from unittest.mock import patch

import httpx
import pytest

from app.core.config import Settings
from app.game.visual.comfyui_client import (
    ComfyUIClientError,
    build_comfyui_client,
)


def _settings(**overrides) -> Settings:
    return Settings(**overrides)


def test_disabled_integration_returns_unavailable_without_any_network_call():
    client = build_comfyui_client(_settings(comfyui_enabled=False))

    with patch("httpx.get") as mocked_get:
        assert client.is_available() is False
    mocked_get.assert_not_called()


def test_enabled_but_offline_comfyui_does_not_crash_and_reports_unavailable():
    client = build_comfyui_client(_settings(comfyui_enabled=True))

    with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
        assert client.is_available() is False


def test_health_check_success_can_be_mocked():
    client = build_comfyui_client(_settings(comfyui_enabled=True))

    fake_response = httpx.Response(
        200, json={"system": {}, "devices": []}, request=httpx.Request("GET", "http://x/system_stats")
    )
    with patch("httpx.get", return_value=fake_response):
        assert client.is_available() is True


def test_timeout_produces_a_typed_integration_failure_from_system_stats():
    client = build_comfyui_client(_settings(comfyui_enabled=True))

    with patch("httpx.get", side_effect=httpx.TimeoutException("too slow")):
        with pytest.raises(ComfyUIClientError):
            client.system_stats()


def test_disabled_integration_raises_typed_error_from_system_stats():
    client = build_comfyui_client(_settings(comfyui_enabled=False))

    with pytest.raises(ComfyUIClientError):
        client.system_stats()


def test_base_url_comes_from_configuration():
    client = build_comfyui_client(
        _settings(comfyui_enabled=True, comfyui_base_url="http://127.0.0.1:9999")
    )

    with patch("httpx.get") as mocked_get:
        mocked_get.return_value = httpx.Response(200, json={})
        client.is_available()

    called_url = mocked_get.call_args.args[0]
    assert called_url == "http://127.0.0.1:9999/system_stats"


def test_system_stats_success_returns_the_parsed_payload():
    client = build_comfyui_client(_settings(comfyui_enabled=True))
    fake_response = httpx.Response(
        200,
        json={"system": {"os": "win32"}, "devices": []},
        request=httpx.Request("GET", "http://x/system_stats"),
    )

    with patch("httpx.get", return_value=fake_response):
        stats = client.system_stats()

    assert stats["system"]["os"] == "win32"


def _json_response(payload, url="http://x/prompt") -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("POST", url))


def test_submit_workflow_returns_prompt_id():
    client = build_comfyui_client(_settings(comfyui_enabled=True))

    with patch("httpx.post", return_value=_json_response({"prompt_id": "abc123", "number": 1})):
        prompt_id = client.submit_workflow({"1": {"class_type": "SaveImage"}}, client_id="test-client")

    assert prompt_id == "abc123"


def test_submit_workflow_raises_on_comfyui_rejection():
    client = build_comfyui_client(_settings(comfyui_enabled=True))

    with patch("httpx.post", return_value=_json_response({"error": "invalid prompt: bad node"})):
        with pytest.raises(ComfyUIClientError):
            client.submit_workflow({}, client_id="test-client")


def test_submit_workflow_disabled_raises_without_network_call():
    client = build_comfyui_client(_settings(comfyui_enabled=False))

    with patch("httpx.post") as mocked_post:
        with pytest.raises(ComfyUIClientError):
            client.submit_workflow({}, client_id="test-client")
    mocked_post.assert_not_called()


def test_get_history_returns_none_when_prompt_not_present():
    client = build_comfyui_client(_settings(comfyui_enabled=True))

    with patch("httpx.get", return_value=_json_response({}, url="http://x/history/xyz")):
        assert client.get_history("xyz") is None


def test_get_history_returns_the_entry_when_present():
    client = build_comfyui_client(_settings(comfyui_enabled=True))
    payload = {"xyz": {"status": {"status_str": "success"}, "outputs": {}}}

    with patch("httpx.get", return_value=_json_response(payload, url="http://x/history/xyz")):
        entry = client.get_history("xyz")

    assert entry == payload["xyz"]


def test_wait_for_completion_polls_until_present():
    client = build_comfyui_client(_settings(comfyui_enabled=True))
    responses = [
        _json_response({}, url="http://x/history/xyz"),
        _json_response({"xyz": {"status": {"status_str": "success"}}}, url="http://x/history/xyz"),
    ]

    with patch("httpx.get", side_effect=responses), patch("time.sleep"):
        entry = client.wait_for_completion("xyz", timeout_seconds=10)

    assert entry["status"]["status_str"] == "success"


def test_wait_for_completion_times_out():
    client = build_comfyui_client(_settings(comfyui_enabled=True))

    with patch("httpx.get", return_value=_json_response({}, url="http://x/history/xyz")):
        with patch("time.monotonic", side_effect=[0.0, 0.0, 999.0]):
            with pytest.raises(ComfyUIClientError):
                client.wait_for_completion("xyz", timeout_seconds=10)


def test_resolve_output_path_joins_root_subfolder_and_filename(tmp_path):
    client = build_comfyui_client(
        _settings(comfyui_enabled=True, comfyui_raw_output_root=str(tmp_path))
    )

    resolved = client.resolve_output_path("everreach_tests/npcs", "portrait_00001_.png")

    assert resolved == (tmp_path / "everreach_tests/npcs" / "portrait_00001_.png").resolve()


def test_resolve_output_path_rejects_path_traversal(tmp_path):
    client = build_comfyui_client(
        _settings(comfyui_enabled=True, comfyui_raw_output_root=str(tmp_path))
    )

    with pytest.raises(ComfyUIClientError):
        client.resolve_output_path("../../etc", "passwd")


def test_resolve_output_path_requires_configured_root():
    client = build_comfyui_client(_settings(comfyui_enabled=True, comfyui_raw_output_root=""))

    with pytest.raises(ComfyUIClientError):
        client.resolve_output_path("sub", "file.png")
