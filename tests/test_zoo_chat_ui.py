import os


os.environ.setdefault("AGENT_URL", "https://agent.example.com")

from zoo_chat_ui.app import execution_trace


def test_execution_trace_includes_agent_transfers_and_tool_names_only():
    events = [
        {
            "content": {
                "parts": [
                    {
                        "functionCall": {
                            "name": "transfer_to_agent",
                            "args": {"agent_name": "travel_planner_agent"},
                        }
                    }
                ]
            },
            "actions": {"transferToAgent": "travel_planner_agent"},
        },
        {
            "content": {
                "parts": [
                    {
                        "functionCall": {
                            "name": "get_weather_forecast",
                            "args": {"zoo_id": "chicago", "visit_date": "2026-09-03"},
                        }
                    }
                ]
            }
        },
    ]

    assert execution_trace(events) == [
        {"type": "agent", "name": "travel_planner_agent"},
        {"type": "tool", "name": "get_weather_forecast"},
    ]