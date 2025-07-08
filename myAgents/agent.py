from google.adk.agents import Agent
from google.adk.tools import google_search

root_agent = Agent(
   # A unique name for the agent.
   name="agent",
   # The Large Language Model (LLM) that agent will use.
   # model="gemini-2.0-flash-live-preview-04-09", # if this model does not work, try below
   #model="gemini-2.0-flash-live-001",
   model="gemini-2.0-flash-exp",
   # A short description of the agent's purpose.
   description="Agent to answer questions using Google Search.",
   # Instructions to set the agent's behavior.
   instruction="Answer the question using the Google Search tool.",
   # Add google_search tool to perform grounding with Google search.
#    tools=[google_search],
)