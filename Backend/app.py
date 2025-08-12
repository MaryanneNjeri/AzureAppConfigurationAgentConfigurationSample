import os
import logging
import atexit
import signal
from flask import Flask, request, jsonify
from flask_cors import CORS
from azure.identity import DefaultAzureCredential
from azure.appconfiguration.provider import load, WatchKey
from featuremanagement import FeatureManager
from azure_open_ai_service import AzureOpenAIService
from llm_configuration import LLMConfiguration, AzureOpenAIConnectionInfo
from models import ChatRequest, ChatbotMessage
from foundry_agent import FoundryAgent
from event_loop_manager import EventLoopManager

app = Flask(__name__)

# Configure CORS
CORS(app, origins=['http://localhost:5173', 'http://127.0.0.1:5173'])

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
configurations = None

credential = DefaultAzureCredential()
app_config_endpoint = os.environ.get("AZURE_APP_CONFIG_ENDPOINT")

# Track configuration state
config_version = 0
foundry_agent = None
foundry_agent_config_version = -1

def on_refresh_success():
    global config_version, foundry_agent, foundry_agent_config_version
    app.config.update(configurations)
    config_version += 1
    logger.info(f"Configuration refreshed, new version: {config_version}")
    
    # If foundry agent exists and config changed, schedule cleanup for next creation
    if foundry_agent and foundry_agent_config_version < config_version:
        logger.info("Configuration changed, foundry agent will be recreated on next request")

# Load configurations
configurations = load(
    app_config_endpoint,
    credential,
    feature_flag_enabled=True,
    feature_flag_refresh_enabled=True,
    refresh_interval=10,
    on_refresh_success=on_refresh_success,
    keyvault_credential=credential,
    refresh_on=[WatchKey("AZURE_OPENAI"), WatchKey("CHAT_LLM"), WatchKey("MyAgent"), WatchKey(".appconfig.featureflag/Beta")],
)
    
app.config.update(configurations)

# Register services
azure_openai_connection_info = AzureOpenAIConnectionInfo(endpoint=app.config["AzureOpenAI:Endpoint"])
llm_configuration = LLMConfiguration(**app.config["ChatLLM"])
openai_service = AzureOpenAIService(azure_openai_connection_info, llm_configuration)
feature_manager = FeatureManager(app.config)

# Initialize event loop manager
loop_manager = EventLoopManager()

async def get_foundry_agent(config):
    """Get or create the foundry agent, recreating if config has changed."""
    global foundry_agent, foundry_agent_config_version, config_version
    
    # Check if we need to recreate the agent due to config changes
    if foundry_agent and foundry_agent_config_version < config_version:
        logger.info("Config changed, cleaning up existing foundry agent")
        try:
            await foundry_agent.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up existing foundry agent: {e}")
        foundry_agent = None
        foundry_agent_config_version = -1
    
    # Create new agent if needed
    if foundry_agent is None:
        logger.info("Creating new foundry agent")
        foundry_agent = await FoundryAgent.create(config, credential=credential, extras={"BingConnectionId": config["BingConnectionId"]})
        foundry_agent_config_version = config_version
        logger.info(f"Foundry agent created with config version: {config_version}")
    
    return foundry_agent

async def cleanup_foundry_agent():
    global foundry_agent
    if foundry_agent:
        await foundry_agent.cleanup()
        foundry_agent = None

def cleanup():
    """Cleanup function called on shutdown."""
    global foundry_agent
    if foundry_agent and loop_manager.is_running:
        try:
            # Run cleanup on the existing event loop
            loop_manager.run_async(cleanup_foundry_agent(), timeout=5)
        except Exception as e:
            print(f"Error during cleanup: {e}")
    loop_manager.stop()

# Register cleanup
atexit.register(cleanup)

@app.route("/api/chat", methods=["POST"])
def chat():
    """Endpoint to handle chat requests."""
    try:
        configurations.refresh()
        data = request.get_json()

        # Convert history from list of dicts to list of ChatbotMessage objects
        if "history" in data:
            data["history"] = [ChatbotMessage(**message) for message in data["history"]]
        
        message = ChatRequest(**data)

        feature_manager = FeatureManager(app.config)

        if not message:
            return jsonify({"error": "Message cannot be empty"}), 400
        
        if feature_manager.is_enabled("Beta"):
            async def get_response():
                agent = await get_foundry_agent(app.config)
                
                return await agent.get_agent_response(message)
            
            response = loop_manager.run_async(get_response(), timeout=60)
            
            return jsonify(response), 200
        else:
            response = openai_service.get_chat_completion(message)
            return jsonify(response), 200

    except Exception as ex:
        logger.error("Error processing chat request: %s", ex)
        return (
            jsonify({"error": "An error occurred while processing your request"}),
            500,
        )

@app.route("/api/chat/model", methods=["GET"])
def get_model_name():
    """Endpoint to get the model name."""
    return jsonify({"model": llm_configuration.model}), 200

@app.route("/api/featureFlag/status", methods=["GET"])
def get_feature_status():
    """Endpoint to get the feature flag status"""
    configurations.refresh()
    feature_manager = FeatureManager(app.config)
    try:
        return jsonify({"isEnabled": feature_manager.is_enabled("Beta")}), 200
    except Exception as ex:
        logger.error("Error checking feature flag: %s", ex)
        return jsonify({"error": "Feature 'Beta' not found"}), 404

def signal_handler(sig, frame):
    print("Received shutdown signal, cleaning up...")
    cleanup()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == "__main__":
    app.run()