Memory: Long-Term Knowledge with MemoryService¶

python_only

We've seen how Session tracks the history (events) and temporary data (state) for a single, ongoing conversation. But what if an agent needs to recall information from past conversations or access external knowledge bases? This is where the concept of Long-Term Knowledge and the MemoryService come into play.

Think of it this way:

    Session / State: Like your short-term memory during one specific chat.
    Long-Term Knowledge (MemoryService): Like a searchable archive or knowledge library the agent can consult, potentially containing information from many past chats or other sources.

The MemoryService Role¶

The BaseMemoryService defines the interface for managing this searchable, long-term knowledge store. Its primary responsibilities are:

    Ingesting Information (add_session_to_memory): Taking the contents of a (usually completed) Session and adding relevant information to the long-term knowledge store.
    Searching Information (search_memory): Allowing an agent (typically via a Tool) to query the knowledge store and retrieve relevant snippets or context based on a search query.

Choosing the Right Memory Service¶

The ADK offers two distinct MemoryService implementations, each tailored to different use cases. Use the table below to decide which is the best fit for your agent.
Feature 	InMemoryMemoryService 	[NEW!] VertexAiMemoryBankService
Persistence 	None (data is lost on restart) 	Yes (Managed by Vertex AI)
Primary Use Case 	Prototyping, local development, and simple testing. 	Building meaningful, evolving memories from user conversations.
Memory Extraction 	Stores full conversation 	Extracts meaningful information from conversations and consolidates it with existing memories (powered by LLM)
Search Capability 	Basic keyword matching. 	Advanced semantic search.
Setup Complexity 	None. It's the default. 	Low. Requires an Agent Engine in Vertex AI.
Dependencies 	None. 	Google Cloud Project, Vertex AI API
When to use it 	When you want to search across multiple sessions’ chat histories for prototyping. 	When you want your agent to remember and learn from past interactions.
In-Memory Memory¶

The InMemoryMemoryService stores session information in the application's memory and performs basic keyword matching for searches. It requires no setup and is best for prototyping and simple testing scenarios where persistence isn't required.

from google.adk.memory import InMemoryMemoryService
memory_service = InMemoryMemoryService()

Example: Adding and Searching Memory

This example demonstrates the basic flow using the InMemoryMemoryService for simplicity.
Full Code

Vertex AI Memory Bank¶

The VertexAiMemoryBankService connects your agent to Vertex AI Memory Bank, a fully managed Google Cloud service that provides sophisticated, persistent memory capabilities for conversational agents.
How It Works¶

The service automatically handles two key operations:

    Generating Memories: At the end of a conversation, the ADK sends the session's events to the Memory Bank, which intelligently processes and stores the information as "memories."
    Retrieving Memories: Your agent code can issue a search query against the Memory Bank to retrieve relevant memories from past conversations.

Prerequisites¶

Before you can use this feature, you must have:

    A Google Cloud Project: With the Vertex AI API enabled.
    An Agent Engine: You need to create an Agent Engine in Vertex AI. This will provide you with the Agent Engine ID required for configuration.
    Authentication: Ensure your local environment is authenticated to access Google Cloud services. The simplest way is to run:

gcloud auth application-default login

Environment Variables: The service requires your Google Cloud Project ID and Location. Set them as environment variables:

    export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
    export GOOGLE_CLOUD_LOCATION="your-gcp-location"

Configuration¶

To connect your agent to the Memory Bank, you use the --memory_service_uri flag when starting the ADK server (adk web or adk api_server). The URI must be in the format agentengine://<agent_engine_id>.
bash

adk web path/to/your/agents_dir --memory_service_uri="agentengine://1234567890"

Or, you can configure your agent to use the Memory Bank by manually instantiating the VertexAiMemoryBankService and passing it to the Runner.

from google.adk.memory import VertexAiMemoryBankService

agent_engine_id = agent_engine.api_resource.name.split("/")[-1]

memory_service = VertexAiMemoryBankService(
    project="PROJECT_ID",
    location="LOCATION",
    agent_engine_id=agent_engine_id
)

runner = adk.Runner(
    ...
    memory_service=memory_service
)

Using Memory in Your Agent¶

With the service configured, the ADK automatically saves session data to the Memory Bank. To make your agent use this memory, you need to call the search_memory method from your agent's code.

This is typically done at the beginning of a turn to fetch relevant context before generating a response.

Example:

from google.adk.agents import Agent
from google.genai import types

class MyAgent(Agent):
    async def run(self, request: types.Content, **kwargs) -> types.Content:
        # Get the user's latest message
        user_query = request.parts[0].text

        # Search the memory for context related to the user's query
        search_result = await self.search_memory(query=user_query)

        # Create a prompt that includes the retrieved memories
        prompt = f"Based on my memory, here's what I recall about your query: {search_result.memories}\n\nNow, please respond to: {user_query}"

        # Call the LLM with the enhanced prompt
        return await self.llm.generate_content_async(prompt)

Advanced Concepts¶
How Memory Works in Practice¶

The memory workflow internally involves these steps:

    Session Interaction: A user interacts with an agent via a Session, managed by a SessionService. Events are added, and state might be updated.
    Ingestion into Memory: At some point (often when a session is considered complete or has yielded significant information), your application calls memory_service.add_session_to_memory(session). This extracts relevant information from the session's events and adds it to the long-term knowledge store (in-memory dictionary or RAG Corpus).
    Later Query: In a different (or the same) session, the user might ask a question requiring past context (e.g., "What did we discuss about project X last week?").
    Agent Uses Memory Tool: An agent equipped with a memory-retrieval tool (like the built-in load_memory tool) recognizes the need for past context. It calls the tool, providing a search query (e.g., "discussion project X last week").
    Search Execution: The tool internally calls memory_service.search_memory(app_name, user_id, query).
    Results Returned: The MemoryService searches its store (using keyword matching or semantic search) and returns relevant snippets as a SearchMemoryResponse containing a list of MemoryResult objects (each potentially holding events from a relevant past session).
    Agent Uses Results: The tool returns these results to the agent, usually as part of the context or function response. The agent can then use this retrieved information to formulate its final answer to the user.

Can an agent have access to more than one memory service?¶

    Through Standard Configuration: No. The framework (adk web, adk api_server) is designed to be configured with one single memory service at a time via the --memory_service_uri flag. This single service is then provided to the agent and accessed through the built-in self.search_memory() method. From a configuration standpoint, you can only choose one backend (InMemory, VertexAiMemoryBankService) for all agents served by that process.

    Within Your Agent's Code: Yes, absolutely. There is nothing preventing you from manually importing and instantiating another memory service directly inside your agent's code. This allows you to access multiple memory sources within a single agent turn.

For example, your agent could use the framework-configured VertexAiMemoryBankService to recall conversational history, and also manually instantiate a InMemoryMemoryService to look up information in a technical manual.
Example: Using Two Memory Services¶

Here’s how you could implement that in your agent's code:

from google.adk.agents import Agent
from google.adk.memory import InMemoryMemoryService, VertexAiMemoryBankService
from google.genai import types

class MultiMemoryAgent(Agent):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.memory_service = InMemoryMemoryService()
        # Manually instantiate a second memory service for document lookups
        self.vertexai_memorybank_service = VertexAiMemoryBankService(
            project="PROJECT_ID",
            location="LOCATION",
            agent_engine_id="AGENT_ENGINE_ID"
        )

    async def run(self, request: types.Content, **kwargs) -> types.Content:
        user_query = request.parts[0].text

        # 1. Search conversational history using the framework-provided memory
        #    (This would be InMemoryMemoryService if configured)
        conversation_context = await self.search_memory(query=user_query)

        # 2. Search the document knowledge base using the manually created service
        document_context = await self.vertexai_memorybank_service.search_memory(query=user_query)

        # Combine the context from both sources to generate a better response
        prompt = "From our past conversations, I remember:\n"
        prompt += f"{conversation_context.memories}\n\n"
        prompt += "From the technical manuals, I found:\n"
        prompt += f"{document_context.memories}\n\n"
        prompt += f"Based on all this, here is my answer to '{user_query}':"

        return await self.llm.generate_content_async(prompt)
