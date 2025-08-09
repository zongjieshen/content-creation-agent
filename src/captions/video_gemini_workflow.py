import os
import logging
import time
import httpx
import re
from typing import TypedDict, Optional, Dict, Any, List
from pydantic import BaseModel
from pathlib import Path

from src.base_workflow import BaseWorkflow, BaseWorkflowState, check_cancellation
from src.utils.gemini_client import get_client
from src.utils.config_loader import get_config
from langgraph.graph import END

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load config
config = get_config()

# Define Pydantic models for structured output
class Hashtag(BaseModel):
    tag: str
    relevance: Optional[str] = None

class VideoAnalysis(BaseModel):
    title: str
    summary: str
    hashtags: List[Hashtag]
    key_topics: Optional[List[str]] = None

class VideoGeminiState(BaseWorkflowState):
    """State for video analysis workflow using Gemini"""
    user_input: str  # User input from BaseWorkflowState
    video_path: Optional[str] = None  # Path to the video file
    target_label: str = "ad"  # Target style label ("ad" or "non-ad")
    location: Optional[str] = None  # Location for video analysis
    video_file: Optional[Any] = None  # Uploaded video file object
    analysis_result: Optional[VideoAnalysis] = None  # Result of video analysis
    report: str

class VideoGeminiWorkflow(BaseWorkflow):
    """Workflow for analyzing videos using Gemini API"""
    
    def __init__(self):
        
        # HTTP client for API calls
        self.http_client = httpx.Client(timeout=120.0)  # Increased from 30.0 to 120.0 seconds
        
        # Call the parent constructor
        super().__init__()
    
    def get_state_class(self):
        return VideoGeminiState
    
    def define_nodes(self):
        return {
            "extract_parameters": self.extract_parameters,
            "upload_video": self.upload_video,
            "analyze_with_gemini": self.analyze_with_gemini,
            "apply_style": self.apply_style,
            "format_results": self.format_results
        }
    
    def define_edges(self, workflow):
        # Define the flow of the workflow with individual edges for each step
        workflow.add_edge("extract_parameters", "upload_video")
        workflow.add_edge("upload_video", "analyze_with_gemini")
        workflow.add_edge("analyze_with_gemini", "apply_style")
        workflow.add_edge("apply_style", "format_results")
        workflow.add_edge("format_results", END)
    
    def get_entry_point(self) -> str:
        return "extract_parameters"
    
    def extract_parameters(self, state: VideoGeminiState):
        """Extract parameters from user input and find video file"""
        state = self.update_step(state, "parameter_extraction")
        
        # Extract parameters from user input
        user_input = state.get("user_input", "")
        lines = [line.strip() for line in user_input.split("\n") if line.strip()]
        
        # Extract location and target_label from the input
        if len(lines) > 2:
            state["location"] = lines[0]
            state["target_label"] = lines[1]
        else:
            state["target_label"] = lines[0]
        
        # Log extracted parameters
        logger.info(f"Extracted location: {state.get('location')}")
        logger.info(f"Extracted target_label: {state.get('target_label')}")
        
        # Find the video file in the uploads directory
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
        video_files = []
        
        if os.path.exists(upload_dir):
            # Look for common video file extensions
            video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
            video_files = [
                os.path.join(upload_dir, f) for f in os.listdir(upload_dir) 
                if any(f.lower().endswith(ext) for ext in video_extensions)
            ]
        
        if video_files:
            # Use the most recent video file from uploads directory
            video_path = max(video_files, key=os.path.getctime)
            state["video_path"] = video_path
            logger.info(f"Found video file: {video_path}")
        else:
            # No uploaded video file found
            state["error_message"] = "No video file found in uploads directory. Please upload a video file."
            state["workflow_status"] = "error"
        
        logger.info(f"Extracted parameters: target_label={state['target_label']}, video_path={state.get('video_path')}")
        
        return state
    
    async def upload_video(self, state: VideoGeminiState):
        """Upload a video file to Gemini and wait for it to be processed"""
        state = self.update_step(state, "video_upload")
        client = get_client()
        video_path = state.get("video_path")
        
        if not video_path:
            state["error_message"] = "No video path provided for upload"
            state["workflow_status"] = "error"
            return state
        
        try:
            if not os.path.exists(video_path):
                logger.error(f"Video file not found: {video_path}")
                state["error_message"] = f"Video file not found: {video_path}"
                state["workflow_status"] = "error"
                return state
            
            logger.info(f"Uploading video file: {video_path}...")
            # Use the filename as the display name
            display_name = os.path.basename(video_path)
            video_file = client.files.upload(
                file=video_path,
                config={
                    "display_name": display_name,
                    "mime_type": "video/mp4"  # Assuming mp4, adjust if needed
                }
            )
            logger.info(f"Uploaded file '{video_file.display_name}' as: {video_file.name} (URI: {video_file.uri})")
            logger.info(f"Initial state: {video_file.state.name}")

            # Wait for the file to be processed and become ACTIVE
            logger.info("Waiting for file to become ACTIVE...")
            while video_file.state.name == "PROCESSING":
                logger.info("File is still PROCESSING. Waiting 10 seconds...")
                time.sleep(10)  # Wait for 10 seconds
                video_file = client.files.get(name=video_file.name)  # Fetch the latest file state
                logger.info(f"Current state: {video_file.state.name}")

            if video_file.state.name == "ACTIVE":
                logger.info(f"File '{video_file.name}' is now ACTIVE and ready for use.")
                state["video_file"] = video_file
                state["workflow_status"] = "uploaded"
            elif video_file.state.name == "FAILED":
                error_message = f"File '{video_file.name}' processing FAILED."
                if hasattr(video_file, 'state_reason') and video_file.state_reason:
                    error_message += f" Reason: {video_file.state_reason}"
                logger.error(error_message)
                state["error_message"] = error_message
                state["workflow_status"] = "error"
            else:
                error_message = f"File '{video_file.name}' is in an unexpected state: {video_file.state.name}"
                logger.error(error_message)
                state["error_message"] = error_message
                state["workflow_status"] = "error"
                
        except Exception as e:
            error_msg = f"Video upload failed: {str(e)}"
            logger.error(f"Error in video upload: {error_msg}")
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state
    
    @check_cancellation
    async def analyze_with_gemini(self, state: VideoGeminiState):
        """Analyze a video using Gemini model"""
        state = self.update_step(state, "gemini_analysis")
        client = get_client()
        video_file = state.get("video_file")
        
        if not video_file:
            state["error_message"] = "No video file available for analysis"
            state["workflow_status"] = "error"
            return state
        
        try:
            # Get prompt from config
            base_prompt = config.get('video_analysis', {}).get('analysis_prompt', '')
            
            # Add location context if provided
            if state.get("location") and state["location"].strip():
                prompt = f"{base_prompt}\nLocation context: {state['location']}"
            else:
                prompt = base_prompt
            
            # Create the prompt parts
            prompt_parts = [
                prompt,
                video_file  # Pass the File object directly
            ]

            logger.info("Generating content with structured output...")
            
            # Request structured output using the VideoAnalysis schema
            response = client.models.generate_content(
                model = 'gemini-2.0-flash',
                contents=prompt_parts,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': VideoAnalysis,
                }
            )
            
            # Parse the response into a VideoAnalysis object
            analysis = response.parsed
            logger.info(f"Generated analysis with {len(analysis.hashtags)} hashtags")
            
            # Store the analysis result
            state["analysis_result"] = analysis
            state["workflow_status"] = "analyzed"
            
        except Exception as e:
            error_msg = f"Gemini analysis failed: {str(e)}"
            logger.error(f"Error in Gemini analysis: {error_msg}")
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state
    
    
    @check_cancellation
    async def apply_style(self, state: VideoGeminiState):
        """Apply style to the analysis title and summary"""
        def get_scraping_service_url():
            """Get the correct scraping service URL based on environment"""
            if os.environ.get('DOCKER_ENV') == 'true':
                # In Docker, use service names from docker-compose.yml
                return "http://scraping-service:8002/apply_style"
            else:
                # Local development
                return "http://localhost:8002/apply_style"
            
        state = self.update_step(state, "style_application")
        
        analysis = state.get("analysis_result")
        target_label = state.get("target_label")
        
        if not analysis:
            state["error_message"] = "No analysis result available for styling"
            state["workflow_status"] = "error"
            return state
        
        try:
            logger.info("Applying style to title and summary...")
            scraping_url = get_scraping_service_url()
            # Call the API endpoint to style the title
            response = self.http_client.post(
                scraping_url,
                json={
                    "content": analysis.title,
                    "target_label": target_label,
                    "num_examples": 3
                }
            )
            
            if response.status_code == 200:
                styled_data = response.json()
                analysis.title = styled_data["styled_content"]
                
                # Remove any hashtags from the title
                analysis.title = re.sub(r'\s*#\w+', '', analysis.title).strip()
                
                # Add common UGC hashtags from config
                hashtag_list = config.get('hashtags', {}).get(f'{target_label}_hashtags', [])
                common_hashtags = [Hashtag(tag=tag) for tag in hashtag_list]
                analysis.hashtags.extend(common_hashtags)
                
                logger.info("Style applied successfully")
                state["analysis_result"] = analysis
                state["workflow_status"] = "styled"
            else:
                logger.error(f"Error applying style: {response.text}")
                state["error_message"] = f"Error applying style: {response.text}"
                state["workflow_status"] = "error"
                
        except Exception as e:
            error_msg = f"Style application failed: {str(e)}"
            logger.error(f"Error in style application: {error_msg}")
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state
    
    @check_cancellation
    async def format_results(self, state: VideoGeminiState):
        """Format the analysis results for presentation"""
        state = self.update_step(state, "results_formatting")
        
        analysis = state.get("analysis_result")
        
        if not analysis:
            state["error_message"] = "No analysis results available"
            state["workflow_status"] = "error"
            return state
        
        try:
            # Format the results as a markdown report
            report = f"{analysis.title}\n\n"
            
            for hashtag in analysis.hashtags:
                report += f"- {hashtag.tag}\n"
            
            
            # Add the report and path to the state
            state["report"] = report
            state["workflow_status"] = "completed"
            
        except Exception as e:
            error_msg = f"Error formatting results: {str(e)}"
            logger.error(error_msg)
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state
    

# Create workflow instance
video_gemini_workflow = VideoGeminiWorkflow()

# Helper function to run the workflow
async def run_workflow(user_input: str):
    """Run the video analysis workflow with the given input"""
    result = await video_gemini_workflow.run(user_input)
    
    if result.get("error_message"):
        print(f"\nError: {result['error_message']}")
        return False
    
    return result

# For command-line usage
if __name__ == "__main__":
    import asyncio
    import sys
    
    # Get user input from command line
    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "analyze video"
    
    # Run the workflow
    result = asyncio.run(run_workflow(user_input))
    
    # Print the report if available
    if result and result.get("report"):
        print("\n" + result["report"])