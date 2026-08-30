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


MEAL_MENU = {
    "fruit_bowl": {"name": "Seasonal Fruit Bowl", "price": 7, "calories": 180, "diet": "vegan, gluten-free"},
    "garden_salad": {"name": "Garden Salad", "price": 9, "calories": 240, "diet": "vegan, gluten-free, low-carb"},
    "grilled_chicken_salad": {"name": "Grilled Chicken Salad", "price": 13, "calories": 390, "diet": "non-vegetarian, low-carb"},
    "veggie_burger": {"name": "Veggie Burger", "price": 12, "calories": 480, "diet": "vegetarian"},
    "grilled_chicken_burger": {"name": "Grilled Chicken Burger", "price": 14, "calories": 540, "diet": "non-vegetarian"},
    "vegetable_pizza": {"name": "Vegetable Pizza", "price": 15, "calories": 620, "diet": "vegetarian"},
    "chicken_pizza": {"name": "Chicken Pizza", "price": 17, "calories": 720, "diet": "non-vegetarian"},
    "paneer_tikka": {"name": "Paneer Tikka", "price": 11, "calories": 360, "diet": "vegetarian, gluten-free, low-carb"},
    "chicken_tikka": {"name": "Chicken Tikka", "price": 13, "calories": 410, "diet": "non-vegetarian, gluten-free, low-carb"},
    "bhel_puri": {"name": "Bhel Puri", "price": 7, "calories": 310, "diet": "vegetarian"},
    "pani_puri": {"name": "Pani Puri", "price": 7, "calories": 280, "diet": "vegetarian"},
    "ice_cream": {"name": "Ice Cream", "price": 6, "calories": 260, "diet": "vegetarian"},
    "gulab_jamun": {"name": "Gulab Jamun", "price": 6, "calories": 300, "diet": "vegetarian"},
    "brownie": {"name": "Chocolate Brownie", "price": 6, "calories": 340, "diet": "vegetarian"},
    "water": {"name": "Bottled Water", "price": 3, "calories": 0, "diet": "vegan, gluten-free, low-carb"},
    "fresh_lime_soda": {"name": "Fresh Lime Soda", "price": 5, "calories": 130, "diet": "vegan, gluten-free"},
    "diet_soda": {"name": "Diet Soda", "price": 4, "calories": 0, "diet": "vegan, gluten-free, low-carb"},
}


def get_meal_options(dietary_preference: str = "all") -> dict:
    """Return Zoo Cafe menu items filtered by dietary preference when requested."""
    preference = dietary_preference.lower().replace("_", "-")
    if preference in {"all", "menu", "food"}:
        matching_items = MEAL_MENU
    else:
        matching_items = {
            item_id: item
            for item_id, item in MEAL_MENU.items()
            if preference in item["diet"]
            or (preference == "vegetarian" and "vegan" in item["diet"])
        }
    return {
        "status": "success",
        "items": matching_items,
        "notes": [
            "Menu prices and calorie counts are sample values; confirm current availability with Zoo Cafe staff.",
            "A full-day pass with food included provides a $20 Zoo Cafe credit per pass holder.",
            "Unused food credit has no cash value and does not carry over.",
            "Any amount above the available credit is billed separately.",
            "Tell staff about allergies; the kitchen cannot guarantee an allergen-free environment.",
        ],
    }


def calculate_meal_order(
    item_ids: list[str],
    full_day_pass_with_food: bool = False,
) -> dict:
    """Calculate Zoo Cafe order calories, price, and any eligible day-pass food credit."""
    selected_items = []
    unavailable_items = []
    for item_id in item_ids:
        normalized_item_id = item_id.lower().replace("-", "_").replace(" ", "_")
        menu_item = MEAL_MENU.get(normalized_item_id)
        if menu_item is None:
            menu_item = next(
                (
                    item
                    for item in MEAL_MENU.values()
                    if item["name"].lower() == item_id.lower()
                ),
                None,
            )
        if menu_item:
            selected_items.append(menu_item)
        else:
            unavailable_items.append(item_id)

    subtotal = sum(item["price"] for item in selected_items)
    calories = sum(item["calories"] for item in selected_items)
    food_credit = min(subtotal, 20) if full_day_pass_with_food else 0
    return {
        "status": "success",
        "selected_items": selected_items,
        "unavailable_items": unavailable_items,
        "subtotal": f"${subtotal}",
        "total_calories": calories,
        "food_credit": f"${food_credit}",
        "amount_due": f"${subtotal - food_credit}",
        "message": "The $20 full-day-pass food credit was applied. The remaining balance is billed separately."
        if full_day_pass_with_food
        else "No food credit was applied.",
    }


def get_id_token() -> str:
    """Get a Cloud Run identity token for the Zoo MCP server."""
    audience = mcp_server_url.rstrip("/").removesuffix("/mcp")
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
    instruction="""You are a helpful research assistant. Fully answer the user's latest message.

You can retrieve data about animals at our zoo, including names, ages, and
locations, and search Wikipedia for general knowledge, including facts,
lifespan, diet, and habitat.

Analyze the user's latest message first. Use one tool when one source is enough. When the
request needs both internal zoo data and general knowledge, use both tools.
Synthesize the findings into preliminary research data.

For every question that mentions "our zoo", "the zoo", or Zoo Animal Directory,
your first action MUST be the MCP tool find_animals. Use the animal species from
the PROMPT as its query, using the singular form when needed, such as "elephant"
for "elephants". Do not answer until find_animals returns. Do not say that
zoo-specific information is unavailable unless find_animals returns no matching
data. If the question asks about general facts, diet, habitat, or lifespan, call
the wikipedia tool after find_animals and combine both results.
""",
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

meal_planner_agent = Agent(
    name="meal_planner_agent",
    model=model_name,
    description="Plans Zoo Cafe meals, dietary options, calories, and food-credit totals.",
    instruction="""You are the Zoo Cafe Meal Planner. Help visitors select vegetarian,
non-vegetarian, low-carb, diet, calorie-balanced, fruit, salad, burger, pizza,
dessert, ice cream, sweet, cool drink, chaat, and Indian chaat options. Always
call get_meal_options before recommending menu items. When a visitor selects
items or asks for a total, call calculate_meal_order. For a calorie target,
recommend available selections that stay at or below the target, and calculate
them before responding. Ask whether the visitor has a full-day pass with food
included if they have not said so. Such a pass has a $20 Zoo Cafe credit per
pass holder; apply it only after the visitor confirms it. Clearly state any
amount due, that food credit is not cash or transferable, and that allergies
must be discussed with cafe staff. Explain that menu prices and calorie counts
are sample values and must be confirmed with Zoo Cafe staff.""",
    tools=[get_meal_options, calculate_meal_order],
)


root_agent = Agent(
    name="greeter",
    model=model_name,
    description="The entry point for the Zoo Tour Guide.",
    instruction="""You are the Zoo Tour Guide entry point. Help visitors learn about
animals, Zoo admission, and Zoo Cafe meals. For questions about food, meals,
orders, vegetarian or non-vegetarian options, dietary needs, calories, cafe
items, or food credit, transfer control to meal_planner_agent. For questions
about tickets, passes, prices, resident rates, family rates, or visiting hours,
transfer control to ticket_information_agent.
For animal questions, use add_prompt_to_state to save the user's response, then
transfer control to tour_guide_workflow.""",
    tools=[add_prompt_to_state],
    sub_agents=[tour_guide_workflow, ticket_information_agent, meal_planner_agent],
)