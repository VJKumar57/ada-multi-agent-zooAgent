import logging
import os

import google.auth
import google.auth.transport.requests
import google.cloud.logging
import google.oauth2.id_token
from dotenv import load_dotenv
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools.langchain_tool import LangchainTool
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.tool_context import ToolContext
from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper


load_dotenv()
google.cloud.logging.Client().setup_logging()

model_name = os.environ["MODEL"]
mcp_server_url = os.environ["MCP_SERVER_URL"]
mcp_server_authenticated = os.getenv("MCP_SERVER_AUTHENTICATED", "FALSE").upper() == "TRUE"



def add_prompt_to_state(tool_context: ToolContext, prompt: str) -> dict[str, str]:
    """Save the user's initial question for the research workflow."""
    tool_context.state["PROMPT"] = prompt
    logging.info("Saved user prompt to workflow state.")
    return {"status": "success"}


TICKET_OPTIONS = {
    "day_pass": {
        "name": "Day Pass",
        "hours": "9:00 AM to 5:00 PM",
        "resident": {"adult": "$28", "child": "$18", "senior": "$22"},
        "non_resident": {"adult": "$34", "child": "$22", "senior": "$27"},
        "family": {"resident": "$82", "non_resident": "$102"},
    },
    "night_pass": {
        "name": "Night Pass",
        "hours": "6:00 PM to 10:00 PM",
        "resident": {"adult": "$20", "child": "$13", "senior": "$16"},
        "non_resident": {"adult": "$25", "child": "$16", "senior": "$20"},
        "family": {"resident": "$58", "non_resident": "$72"},
    },
    "half_day_pass": {
        "name": "Half-Day Pass",
        "hours": "9:00 AM to 1:00 PM or 1:00 PM to 5:00 PM",
        "resident": {"adult": "$17", "child": "$11", "senior": "$14"},
        "non_resident": {"adult": "$21", "child": "$14", "senior": "$17"},
        "family": {"resident": "$50", "non_resident": "$62"},
    },
    "half_night_pass": {
        "name": "Half-Night Pass",
        "hours": "6:00 PM to 8:00 PM or 8:00 PM to 10:00 PM",
        "resident": {"adult": "$12", "child": "$8", "senior": "$10"},
        "non_resident": {"adult": "$15", "child": "$10", "senior": "$12"},
        "family": {"resident": "$36", "non_resident": "$45"},
    },
    "weekly_pass": {
        "name": "Weekly Pass",
        "hours": "Daytime admission for seven consecutive days",
        "resident": {"adult": "$90", "child": "$58", "senior": "$72"},
        "non_resident": {"adult": "$110", "child": "$70", "senior": "$88"},
        "family": {"resident": "$260", "non_resident": "$320"},
    },
    "monthly_pass": {
        "name": "Monthly Pass",
        "hours": "Daytime admission for one calendar month",
        "resident": {"adult": "$180", "child": "$115", "senior": "$145"},
        "non_resident": {"adult": "$220", "child": "$140", "senior": "$175"},
        "family": {"resident": "$520", "non_resident": "$640"},
    },
    "yearly_pass": {
        "name": "Yearly Membership",
        "hours": "Unlimited daytime admission for one year",
        "resident": {"adult": "$260", "child": "$165", "senior": "$210"},
        "non_resident": {"adult": "$315", "child": "$200", "senior": "$250"},
        "family": {"resident": "$720", "non_resident": "$875"},
    },
}


def get_ticket_details(pass_type: str = "all") -> dict:
    """Return ticket prices, eligibility, and visiting hours for Zoo passes."""
    normalized_pass_type = pass_type.lower().replace("-", "_").replace(" ", "_")
    if normalized_pass_type in {"all", "passes", "tickets", "ticket"}:
        return {
            "status": "success",
            "details": TICKET_OPTIONS,
            "notes": [
                "Child pricing applies to guests ages 3 to 12; children under 3 enter free.",
                "Senior pricing applies to guests age 65 and older.",
                "Family passes cover two adults and up to three children living at the same address.",
                "Resident pricing requires a valid local address at entry.",
                "Passes exclude separately ticketed special events and parking.",
            ],
        }
    if normalized_pass_type in TICKET_OPTIONS:
        return {"status": "success", "details": TICKET_OPTIONS[normalized_pass_type]}
    return {
        "status": "error",
        "error_message": f"Ticket type '{pass_type}' is not available.",
    }


def get_id_token() -> str:
    """Get a Cloud Run identity token for the Zoo MCP server."""
    audience = mcp_server_url.split("/mcp/")[0]
    request = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(request, audience)


mcp_connection_params = StreamableHTTPConnectionParams(url=mcp_server_url)
if mcp_server_authenticated:
    mcp_connection_params = StreamableHTTPConnectionParams(
        url=mcp_server_url,
        headers={"Authorization": f"Bearer {get_id_token()}"},
    )

mcp_tools = MCPToolset(connection_params=mcp_connection_params)
wikipedia_tool = LangchainTool(
    tool=WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper())
)

comprehensive_researcher = Agent(
    name="comprehensive_researcher",
    model=model_name,
    description="Researches zoo animals using internal data and Wikipedia.",
    instruction="""You are a helpful research assistant. Fully answer the user's PROMPT.

You can retrieve data about animals at our zoo, including names, ages, and
locations, and search Wikipedia for general knowledge, including facts,
lifespan, diet, and habitat.

Analyze the PROMPT first. Use one tool when one source is enough. When the
request needs both internal zoo data and general knowledge, use both tools.
Synthesize the findings into preliminary research data.

For every question that mentions "our zoo", "the zoo", or Zoo Animal Directory,
your first action MUST be the MCP tool find_animals. Use the animal species from
the PROMPT as its query, using the singular form when needed, such as "elephant"
for "elephants". Do not answer until find_animals returns. Do not say that
zoo-specific information is unavailable unless find_animals returns no matching
data. If the question asks about general facts, diet, habitat, or lifespan, call
the wikipedia tool after find_animals and combine both results.

PROMPT: {{ PROMPT }}""",
    tools=[mcp_tools, wikipedia_tool],
    output_key="RESEARCH_DATA",
)

response_formatter = Agent(
    name="response_formatter",
    model=model_name,
    description="Formats research into a friendly Zoo Tour Guide response.",
    instruction="""You are the friendly voice of the Zoo Tour Guide. Turn the
RESEARCH_DATA into a complete, helpful response. Present zoo-specific details
such as names, ages, and locations first. Then add useful general facts. If
information is missing, present only what is available.

RESEARCH_DATA: {{ RESEARCH_DATA }}""",
)

tour_guide_workflow = SequentialAgent(
    name="tour_guide_workflow",
    description="Researches and answers animal questions.",
    sub_agents=[comprehensive_researcher, response_formatter],
)

ticket_information_agent = Agent(
    name="ticket_information_agent",
    model=model_name,
    description="Answers questions about Zoo admission passes and pricing.",
    instruction="""You help visitors choose Zoo admission passes. Always use
get_ticket_details before answering questions about tickets, prices, admission,
passes, resident rates, family rates, or visiting hours. Give the relevant pass
price, distinguish resident and non-resident eligibility, and mention applicable
age or family requirements. Treat all quoted prices as the Zoo's current sample
pricing and advise visitors to confirm special-event availability before booking.""",
    tools=[get_ticket_details],
)


root_agent = Agent(
    name="greeter",
    model=model_name,
    description="The entry point for the Zoo Tour Guide.",
    instruction="""You are the Zoo Tour Guide entry point. Help visitors learn about
animals and Zoo admission. For questions about tickets, passes, prices, resident
rates, family rates, or visiting hours, transfer control to ticket_information_agent.
For animal questions, use add_prompt_to_state to save the user's response, then
transfer control to tour_guide_workflow.""",
    tools=[add_prompt_to_state],
    sub_agents=[tour_guide_workflow, ticket_information_agent],
)