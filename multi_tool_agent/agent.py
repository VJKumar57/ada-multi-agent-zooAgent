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


root_agent = Agent(
    name="greeter",
    model=model_name,
    description="The entry point for the Zoo Tour Guide.",
    instruction="""Let the user know you will help them learn about animals at the zoo.
When the user responds, use add_prompt_to_state to save their response, then
transfer control to the tour_guide_workflow agent.""",
    tools=[add_prompt_to_state],
    sub_agents=[tour_guide_workflow],
)