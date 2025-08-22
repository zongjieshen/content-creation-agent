import os
import asyncio
import logging
import time
import random
from uuid import uuid4
from typing import List, Dict, Any, Optional
from traceback import print_exc
# Add these imports at the top of the file
import yaml
import httpx
from fastapi import FastAPI, Request, HTTPException, Response, File, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from pydantic import BaseModel, Field, validator
import uvicorn
import bleach

# Import workflow classes
from .instagram_collaboration_workflow import InstagramCollaborationWorkflow
from .instagram_message_workflow import InstagramMessageWorkflow
from ..base_workflow import BaseWorkflow

# With these lines
# Global stop events for different workflow types
messaging_stop_event = None
collaboration_stop_event = None
# Set up logging
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO').upper())
logger = logging.getLogger(__name__)

# Simple in-memory session manager for leads server
class LeadsSessionManager:
    def __init__(self):
        self.sessions = {}
        self.conversations = {}
    
    def create_session(self, session_id: str) -> bool:
        """Create a new session"""
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "created_at": time.time(),
                "last_activity": time.time(),
                "thread_id": session_id
            }
            self.conversations[session_id] = []
            return True
        return False
    
    def is_session(self, session_id: str) -> bool:
        """Check if session exists"""
        return session_id in self.sessions
    
    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """Get session information"""
        return self.sessions.get(session_id)
    
    def update_session_info(self, session_id: str, info: Dict) -> None:
        """Update session information"""
        if session_id in self.sessions:
            self.sessions[session_id].update(info)
            self.sessions[session_id]["last_activity"] = time.time()
    
    def get_conversation(self, session_id: str) -> List[Dict]:
        """Get conversation history"""
        return self.conversations.get(session_id, [])
    
    def save_conversation(self, session_id: str, user_id: str, messages: List[Dict]) -> None:
        """Save conversation messages"""
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        self.conversations[session_id].extend(messages)
        self.update_session_info(session_id, {"user_id": user_id})
    
    def delete_conversation(self, session_id: str) -> None:
        """Delete session and conversation"""
        self.sessions.pop(session_id, None)
        self.conversations.pop(session_id, None)

# Pydantic models
class Message(BaseModel):
    """Definition of the Chat Message type."""
    role: str = Field(description="Role for a message AI, User and System", default="user", max_length=256, pattern=r'[\s\S]*')
    content: str = Field(description="The input query/prompt to the pipeline.", default="Hello what can you do?", max_length=131072, pattern=r'[\s\S]*')

    @validator('role')
    def validate_role(cls, value):
        """Field validator function to validate values of the field role"""
        value = bleach.clean(value, strip=True)
        valid_roles = {'user', 'assistant', 'system'}
        if value.lower() not in valid_roles:
            raise ValueError("Role must be one of 'user', 'assistant', or 'system'")
        return value.lower()

    @validator('content')
    def sanitize_content(cls, v):
        """Field validator function to sanitize user populated fields from HTML"""
        v = bleach.clean(v, strip=True)
        if not v:
            raise ValueError("Message content cannot be empty.")
        return v

class LeadsPrompt(BaseModel):
    """Definition of the Leads Prompt API data type."""
    messages: List[Message] = Field(..., description="A list of messages comprising the conversation so far.", max_items=50000)
    user_id: str = Field(None, description="A unique identifier representing your end-user.")
    session_id: str = Field(..., description="A unique identifier representing the session associated with the response.")
    workflow_type: str = Field(..., description="Type of workflow: 'collaboration' or 'messaging'")
    parameters: Dict[str, Any] = Field(default={}, description="Additional parameters for the workflow")

class LeadsResponseChoices(BaseModel):
    """Definition of Leads response choices"""
    index: int = Field(default=0, ge=0, le=256, format="int64")
    message: Message = Field(default=Message())
    finish_reason: str = Field(default="", max_length=4096, pattern=r'[\s\S]*')
    options: Optional[List[str]] = Field(default=None, description="Options for user interaction")

class LeadsResponse(BaseModel):
    """Definition of Leads APIs response data type"""
    id: str = Field(default="", max_length=100000, pattern=r'[\s\S]*')
    choices: List[LeadsResponseChoices] = Field(default=[], max_items=256)
    session_id: str = Field(None, description="A unique identifier representing the session associated with the response.")
    workflow_status: str = Field(default="", description="Current workflow status")
    interrupt_data: Optional[Dict] = Field(default=None, description="Data for workflow interrupts")

class CreateSessionResponse(BaseModel):
    session_id: str = Field(max_length=4096)

class HealthResponse(BaseModel):
    message: str = Field(max_length=4096, pattern=r'[\s\S]*', default="")

class FileUploadResponse(BaseModel):
    filename: str = Field(max_length=4096, pattern=r'[\s\S]*')
    filepath: str = Field(max_length=4096, pattern=r'[\s\S]*')
    message: str = Field(max_length=4096, pattern=r'[\s\S]*', default="File uploaded successfully")

# FastAPI app setup
tags_metadata = [
    {"name": "Health", "description": "APIs for checking server health."},
    {"name": "Session Management", "description": "APIs for managing sessions."},
    {"name": "Leads Workflows", "description": "APIs for Instagram collaboration and messaging workflows."},
]

app = FastAPI(
    title="Leads Workflow API",
    description="API for Instagram collaboration and messaging workflows",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=tags_metadata,
)

# CORS middleware
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fallback responses
FALLBACK_RESPONSES = [
    "Please try re-phrasing, I am likely having some trouble with that question.",
    "I will get better with time, please try with a different question.",
    "I wasn't able to process your input. Let's try something else.",
    "Something went wrong. Could you try again in a few seconds with a different question?",
    "Oops, that proved a tad difficult for me, can you retry with another question?"
]

@app.on_event("startup")
async def startup_event():
    """Initialize the leads server components"""
    try:
        # Initialize session manager
        app.session_manager = LeadsSessionManager()
        
        # Initialize workflow instances
        app.collaboration_workflow = InstagramCollaborationWorkflow()
        app.messaging_workflow = InstagramMessageWorkflow()
        
        logger.info("Leads server initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize leads server: {str(e)}")
        raise RuntimeError(f"Leads server initialization failed: {str(e)}")

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors(), exclude={"input"})}
    )

# API Endpoints
@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check():
    """Perform a Health Check"""
    return HealthResponse(message="Leads server is up and running.")

@app.get("/create_session", tags=["Session Management"], response_model=CreateSessionResponse)
async def create_session():
    """Create a new session for workflow management"""
    for _ in range(5):
        session_id = str(uuid4())
        
        if not app.session_manager.is_session(session_id):
            app.session_manager.create_session(session_id)
            return CreateSessionResponse(session_id=session_id)
    
    raise HTTPException(status_code=500, detail="Unable to generate session_id")

@app.delete("/delete_session")
async def delete_session(session_id: str):
    """Delete a session and its associated data"""
    if not app.session_manager.is_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    
    app.session_manager.delete_conversation(session_id)
    return {"message": "Session deleted successfully"}

@app.post("/generate", tags=["Leads Workflows"], response_model=LeadsResponse)
async def generate_workflow_response(
    request: Request,
    prompt: LeadsPrompt
) -> JSONResponse:
    """Generate response for leads workflows with LangGraph interrupt/resume support"""
    
    logger.info(f"Input at /generate endpoint: {prompt.dict()}")
    global messaging_stop_event, collaboration_stop_event
    # Select workflow based on type
    if prompt.workflow_type == "collaboration":
        workflow = app.collaboration_workflow
        collaboration_stop_event = asyncio.Event()
        stop_event = collaboration_stop_event
    elif prompt.workflow_type == "messaging":
        workflow = app.messaging_workflow
        messaging_stop_event = asyncio.Event()
        stop_event = messaging_stop_event
    else:
        raise HTTPException(status_code=400, detail="Invalid workflow type")
    
    
    try:
        user_query_timestamp = time.time()
        
        # Validate session
        if not app.session_manager.is_session(prompt.session_id):
            logger.error(f"No session_id created {prompt.session_id}. Please create session id before generate request.")
            return JSONResponse(
                content={
                    "id": str(uuid4()),
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": random.choice(FALLBACK_RESPONSES)
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "session_id": prompt.session_id,
                    "workflow_status": "error"
                }
            )
        
        # Get session info
        session_info = app.session_manager.get_session_info(prompt.session_id)
        
        # Check if there's a cancellation request for this session
        if session_info.get("cancelled_operation") and session_info.get("cancelled_at"):
            # Clear the cancellation flag
            app.session_manager.update_session_info(
                prompt.session_id,
                {"cancelled_operation": None, "cancelled_at": None}
            )
        
        # Get the last user message
        chat_history = prompt.messages
        last_user_message = next(
            (message.content for message in reversed(chat_history) if message.role == 'user'),
            None
        )
        
        if not last_user_message:
            raise HTTPException(status_code=400, detail="No user message found")
        
        resp_id = str(uuid4())
        resp_str = ""
        
        # Configuration for LangGraph
        config = {
            "configurable": {
                "thread_id": prompt.session_id,
                "chat_history": app.session_manager.get_conversation(prompt.session_id)
            }
        }
        

        # Check for existing workflow state (interrupt/resume support)
        if hasattr(workflow, 'app') and workflow.app:
            try:
                # Check for interrupt state
                snapshot = await workflow.app.aget_state(config)
                
                if snapshot.next:  # Workflow is interrupted
                    logger.info(f"Resuming interrupted workflow for session {prompt.session_id}")
                    
                    # Resume workflow with user input
                    task = asyncio.create_task(
                        workflow.resume(last_user_message, prompt.session_id, stop_event)
                    )
                    result = await task
                else:
                    # Start new workflow
                    logger.info(f"Starting new {prompt.workflow_type} workflow for session {prompt.session_id}")
                    # Use asyncio.create_task to run the workflow
                    task = asyncio.create_task(
                        workflow.run(last_user_message, prompt.session_id, stop_event)
                    )
                    result = await task
            
            except Exception as workflow_error:
                logger.error(f"Workflow execution error: {str(workflow_error)}")
                result = {
                    "workflow_status": "error",
                    "error_message": str(workflow_error)
                }
        else:
            # Fallback for workflows without LangGraph app
            logger.warning(f"Workflow {prompt.workflow_type} does not have LangGraph app, using basic execution")
            result = {"workflow_status": "completed", "message": "Workflow executed successfully"}
        
        workflow_status = result.get("status")
            
        # Create response object with the complete result data
        leads_response = LeadsResponse(
            id=resp_id,
            session_id=prompt.session_id,
            workflow_status=workflow_status,
            interrupt_data=result  # Pass the entire result object instead of just interrupt_data
        )
        
        if workflow_status == "awaiting_human_input" and result:  # Use result instead of interrupt_data
            # Handle workflow interrupt
            interrupt_message = result.get("message", "Please provide additional input to continue.")
            resp_str = interrupt_message
            
            # Get options from the result data if available
            options = None
            if "data" in result and "options" in result["data"]:
                options = result["data"]["options"]
            
            response_choice = LeadsResponseChoices(
                index=0,
                message=Message(role="assistant", content=interrupt_message),
                finish_reason="stop",
                options=options  # Add options to the response choice
            )
            
            leads_response.choices.append(response_choice)
            
        elif workflow_status == "error":
            # Handle workflow error
            error_message = result.get("error_message", "An error occurred during workflow execution")
            resp_str = f"Error: {error_message}"
            
            response_choice = LeadsResponseChoices(
                index=0,
                message=Message(role="assistant", content=resp_str),
                finish_reason="stop"
            )
            leads_response.choices.append(response_choice)
            
        else:
            # Handle successful completion
            if "collaboration_result" in result:
                resp_str = f"Collaboration search completed. Found {len(result['collaboration_result'].get('profiles', []))} profiles."
            elif "automation_result" in result:
                automation_result = result["automation_result"]
                resp_str = automation_result.get("message", "Messaging automation completed successfully.")
            else:
                resp_str = "Workflow completed successfully."
            
            response_choice = LeadsResponseChoices(
                index=0,
                message=Message(role="assistant", content=resp_str),
                finish_reason="stop"
            )
            leads_response.choices.append(response_choice)
        
        # Save conversation
        app.session_manager.save_conversation(
            prompt.session_id,
            prompt.user_id or "",
            [
                {"role": "user", "content": last_user_message, "timestamp": f"{user_query_timestamp}"},
                {"role": "assistant", "content": resp_str, "timestamp": f"{time.time()}"},
            ],
        )
        
        return JSONResponse(content=leads_response.dict())
    
    except Exception as e:
        logger.error(f"Unhandled Error from /generate endpoint. Error details: {e}")
        print_exc()
        return JSONResponse(
            content={
                "id": str(uuid4()),
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": random.choice(FALLBACK_RESPONSES)
                        },
                        "finish_reason": "stop"
                    }
                ],
                "session_id": prompt.session_id,
                "workflow_status": "error"
            }
        )

@app.get("/workflows", tags=["Leads Workflows"])
async def list_workflows():
    """List available workflow types"""
    return {
        "workflows": [
            {
                "type": "collaboration",
                "name": "Instagram Collaboration Finder",
                "description": "Find Instagram profiles for collaboration opportunities"
            },
            {
                "type": "messaging",
                "name": "Instagram Messaging Automation",
                "description": "Automate messaging to Instagram profiles"
            }
        ]
    }

@app.get("/session/{session_id}/status", tags=["Session Management"])
async def get_session_status(session_id: str):
    """Get the current status of a session"""
    if not app.session_manager.is_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    
    session_info = app.session_manager.get_session_info(session_id)
    conversation = app.session_manager.get_conversation(session_id)
    
    return {
        "session_id": session_id,
        "session_info": session_info,
        "conversation_length": len(conversation),
        "last_activity": session_info.get("last_activity")
    }

@app.post("/upload_csv", tags=["Leads Workflows"], response_model=FileUploadResponse)
async def upload_csv(file: UploadFile = File(...)):
    """Upload a CSV file for leads workflows"""
    # Validate file type
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    
    try:
        # Create uploads directory if it doesn't exist
        upload_dir = get_resource_path("uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Clear the uploads directory first
        for existing_file in os.listdir(upload_dir):
            existing_file_path = os.path.join(upload_dir, existing_file)
            if os.path.isfile(existing_file_path):
                os.remove(existing_file_path)
        
        # Save the file
        file_path = os.path.join(upload_dir, file.filename)
        contents = await file.read()
        
        # Write the file and ensure it's properly closed
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Make sure the file handle is closed before validation
        await file.close()
        
        # Validate CSV format
        try:
            import pandas as pd
            df = pd.read_csv(file_path)
            
            # Check for required columns
            required_columns = ["profile_url"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                # Remove the invalid file
                os.remove(file_path)
                raise HTTPException(
                    status_code=400, 
                    detail=f"CSV missing required columns: {missing_columns}"
                )
                
        except Exception as e:
            # Remove the invalid file
            os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")
        
        return FileUploadResponse(
            filename=file.filename,
            filepath=file_path
        )
        
    except Exception as e:
        logger.error(f"Error uploading CSV file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

class CancelOperationRequest(BaseModel):
    session_id: str = Field(..., description="Session ID for the operation to cancel")
    operation_type: str = Field(..., description="Type of operation to cancel: 'search', 'message', etc.")

@app.post("/cancel_operation", tags=["Leads Workflows"])
async def cancel_operation(request: CancelOperationRequest):
    """Cancel an ongoing operation for a session"""
    global messaging_stop_event, collaboration_stop_event
    
    if not app.session_manager.is_session(request.session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update session info to indicate cancellation
    app.session_manager.update_session_info(
        request.session_id, 
        {"cancelled_operation": request.operation_type, "cancelled_at": time.time()}
    )
    
    # Set the appropriate stop event based on operation type
    if request.operation_type == "message" and messaging_stop_event is not None:
        messaging_stop_event.set()
        logger.info(f"Messaging workflow abort signal sent for session {request.session_id}")
        return {"message": f"Operation {request.operation_type} cancelled for session {request.session_id}"}
    elif request.operation_type == "collaboration" and collaboration_stop_event is not None:
        collaboration_stop_event.set()
        logger.info(f"Collaboration workflow abort signal sent for session {request.session_id}")
        return {"message": f"Operation {request.operation_type} cancelled for session {request.session_id}"}
    else:
        raise HTTPException(status_code=404, detail=f"No active {request.operation_type} operation found")

@app.post("/save_csv", tags=["Leads Workflows"], response_model=FileUploadResponse)
async def save_csv(request: Request):
    """Save updated CSV data back to the file"""
    try:
        # Get the JSON data from the request
        data = await request.json()
        csv_data = data.get("csv_data", [])
        filename = data.get("filename", "")
        
        if not csv_data or not filename:
            raise HTTPException(status_code=400, detail="Missing CSV data or filename")
        
        # Determine the file path
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
        file_path = os.path.join(upload_dir, filename)
        
        # Check if the file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"File {filename} not found")
        
        # Write the updated CSV data back to the file
        import csv
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            if not csv_data:
                raise HTTPException(status_code=400, detail="Empty CSV data")
            
            # Get the fieldnames from the first row
            fieldnames = list(csv_data[0].keys())
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_data)
        
        return FileUploadResponse(
            filename=filename,
            filepath=file_path
        )
        
    except Exception as e:
        logger.error(f"Error saving CSV file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")



# Add these Pydantic models with the other models
class ConfigResponse(BaseModel):
    config_content: str = Field(max_length=1000000, pattern=r'[\s\S]*')
    message: str = Field(max_length=4096, pattern=r'[\s\S]*', default="Config loaded successfully")

class SaveConfigRequest(BaseModel):
    config_content: str = Field(..., description="The updated config content")

from src.utils.gemini_client import initialize_client
initialize_client()

from src.utils.resource_path import get_resource_path

@app.get("/get_config", tags=["Configuration"], response_model=ConfigResponse)
async def get_config():
    """Get the content of the config.yaml file"""
    try:
        # Get the path to the config file
        config_path = get_resource_path("config.yaml")
        
        # Read the config file with UTF-8 encoding explicitly specified
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()
        
        return ConfigResponse(config_content=config_content)
    except Exception as e:
        logger.error(f"Error reading config file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error reading config file: {str(e)}")

@app.post("/save_config", tags=["Configuration"], response_model=ConfigResponse)
async def save_config(request: SaveConfigRequest):
    """Save updated content to the config.yaml file and notify other services"""
    try:
        # Get the path to the config file
        config_path = get_resource_path("config.yaml")
        
        # Validate YAML format
        try:
            yaml.safe_load(request.config_content)
        except yaml.YAMLError as e:
            raise HTTPException(status_code=400, detail=f"Invalid YAML format: {str(e)}")
        
        # Create a backup of the current config
        backup_path = f"{config_path}.bak"
        with open(config_path, "r", encoding="utf-8") as src, open(backup_path, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        
        # Write the updated config
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(request.config_content)
        
        # Clear the config cache
        from src.utils.config_loader import get_config
        get_config.cache_clear()
            
        initialize_client()
        
        # Notify other services to reload their configuration
        notification_results = await notify_services_config_changed()
        
        return ConfigResponse(
            config_content=request.config_content,
            message=f"Configuration saved successfully and services notified: {notification_results}"
        )
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error saving config file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error saving config file: {str(e)}")


async def notify_services_config_changed():
    """Notify all other services that the configuration has changed"""
    # Get the current hostname from the request context
    hostname = "localhost"  # Default to localhost
    
    # Define the services to notify
    services = [
        {"name": "scraping", "url": f"http://{hostname}:8002/reload_config"},
        {"name": "captions", "url": f"http://{hostname}:8005/reload_config"},
        # GUI server doesn't need notification as it doesn't cache config
    ]
    
    results = {}
    
    # Create an async HTTP client
    async with httpx.AsyncClient(timeout=5.0) as client:
        for service in services:
            try:
                response = await client.post(service["url"])
                if response.status_code == 200:
                    results[service["name"]] = "success"
                else:
                    results[service["name"]] = f"failed: {response.status_code}"
            except Exception as e:
                logger.error(f"Error notifying {service['name']} service: {str(e)}")
                results[service["name"]] = f"error: {str(e)}"
    
    return results

def main():
    """Main function to run the server with Windows ProactorEventLoop"""
    # Set Windows-specific event loop
    if os.name == 'nt':  # Windows
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        logger.info("Using ProactorEventLoop for Windows")
    
    # Get configuration from environment variables
    host = os.environ.get("LEADS_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("LEADS_SERVER_PORT", "8001"))
    
    logger.info(f"Starting Leads server on {host}:{port}")
    
    # Run the server
    uvicorn.run(
        "src.leads.server:app",  # Use the full module path
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()


