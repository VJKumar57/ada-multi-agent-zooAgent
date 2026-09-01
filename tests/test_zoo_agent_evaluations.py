"""Offline evaluation cases for deterministic Zoo Tour Guide business rules."""

import importlib
import sys
from types import SimpleNamespace

import google.cloud.logging
import pytest


@pytest.fixture
def agent_module(monkeypatch):
    monkeypatch.setenv("MODEL", "test-model")
    monkeypatch.setenv("MCP_SERVER_URL", "https://zoo-mcp.example.com/mcp")
    monkeypatch.setenv(
        "TRAVEL_MCP_SERVER_URL", "https://zoo-travel-mcp.example.com/mcp"
    )
    monkeypatch.setenv(
        "KNOWLEDGE_MCP_SERVER_URL", "https://zoo-knowledge-mcp.example.com/mcp"
    )
    monkeypatch.setenv("MCP_SERVER_AUTHENTICATED", "FALSE")
    monkeypatch.setattr(
        google.cloud.logging,
        "Client",
        lambda: SimpleNamespace(setup_logging=lambda: None),
    )
    sys.modules.pop("multi_tool_agent.agent", None)
    return importlib.import_module("multi_tool_agent.agent")


@pytest.mark.parametrize(
    ("role", "expected_price", "expected_rate"),
    [
        ("guest", "$28.00", 0.0),
        ("member", "$26.60", 0.05),
        ("employee", "$25.20", 0.10),
    ],
)
def test_ticket_evaluation_applies_only_server_owned_role_discounts(
    agent_module, role, expected_price, expected_rate
):
    result = agent_module.get_ticket_details(
        SimpleNamespace(state={"USER_ROLE": role}), "day_pass"
    )

    assert result["status"] == "success"
    assert result["discount"] == {"role": role, "rate": expected_rate}
    assert result["details"]["resident"]["adult"] == expected_price


def test_cafe_evaluation_applies_role_discount_before_food_credit(agent_module):
    result = agent_module.calculate_meal_order(
        SimpleNamespace(state={"USER_ROLE": "member"}),
        ["fruit_bowl", "water"],
        full_day_pass_with_food=True,
    )

    assert result["status"] == "success"
    assert result["subtotal"] == "$10.00"
    assert result["role_discount"] == "$0.50"
    assert result["discounted_subtotal"] == "$9.50"
    assert result["food_credit"] == "$9.50"
    assert result["amount_due"] == "$0.00"


def test_cafe_evaluation_does_not_apply_credit_without_confirmed_pass(agent_module):
    result = agent_module.calculate_meal_order(
        SimpleNamespace(state={"USER_ROLE": "guest"}),
        ["fruit_bowl", "water"],
    )

    assert result["food_credit"] == "$0.00"
    assert result["amount_due"] == "$10.00"