import os
from semantic_kernel.agents import AgentRegistry, AzureAIAgent, AzureAIAgentSettings
from azure.ai.projects import AIProjectClient
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from models import ChatRequest, ChatResponse
from semantic_kernel.agents import AgentResponseItem
from typing import List, Optional

class FoundryAgent:
    """
    Azure AI Agent
    """
    def __init__(self):
        self.agent: AzureAIAgent = None
        self.client: AIProjectClient = None

    @classmethod
    async def create(
        cls, config, credential, extras
    ):
        if not config:
            raise ValueError("configuration cannot be null")

        instance = cls()
        
        # Set environment variables that AzureAIAgentSettings expects
        os.environ["AZURE_AI_AGENT_ENDPOINT"] = config["MyAgent:ProjectEndpoint"]
        os.environ["AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME"] = config["MyAgent:ModelDeploymentName"]
        os.environ["AZURE_AI_AGENT_API_VERSION"] = config["MyAgent:ApiVersion"]

        agentSpec = config["MyAgent"]

        settings = AzureAIAgentSettings()
        instance.client = AzureAIAgent.create_client(credential=credential)
        
        instance.agent = await AgentRegistry.create_from_yaml(
            yaml_str=agentSpec,
            client = instance.client,
            settings=settings,
            extras=extras
        )
        
        return instance
        
    
    async def get_agent_response(self, request: ChatRequest) -> ChatResponse:
        if not self.agent:
            raise ValueError("Agent not intialize")
        try:
            thread_id:Optional[str] = request.thread_id
            

            agent_response: AgentResponseItem = None

            if thread_id:
                async for response in self.agent.invoke(messages=request.message, thread_id=thread_id):
                    agent_response = response
            else:
                async for response in self.agent.invoke(messages=request.message):
                    agent_response = response
                
            if agent_response is None:
                return ChatResponse(message="No response received from agent")
            
            # Get thread_id from the response to use in subsequent requests
            response_thread_id = agent_response.thread.id if agent_response.thread else None

            # Safely extract text from content
            content_obj = agent_response.content
            if isinstance(content_obj, ChatMessageContent):
                message_text = content_obj.content or ""
            else:
                message_text = str(content_obj) if content_obj is not None else ""

            return ChatResponse(message=message_text, thread_id=response_thread_id)
        except Exception as e:
            print(e)
            return ChatResponse(message=f"Error getting agent response: {str(e)}")
        
    async def cleanup(self):
        """Clean up resources"""
        if self.agent is not None and self.client:
            try:
                print(f"Deleting agent with ID: {self.agent.id}")
                # Delete agent if the method exists
                if hasattr(self.client, 'agents') and hasattr(self.client.agents, 'delete_agent'):
                    # Don't await here - just call it synchronously to avoid loop issues
                    await self.client.agents.delete_agent(self.agent.id)
                    print("Agent deleted successfully")
                else:
                    print("Warning: client.agents.delete_agent not available")
            except Exception as e:
                print(f"Error deleting agent: {e}")
        
        if self.client:
            try:
                await self.client.close()
                print("Client closed successfully")
            except Exception as e:
                print(f"Error closing client: {e}")
            finally:
                self.client = None