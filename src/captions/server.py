import os
import logging
import asyncio
import tabnanny
from uuid import uuid4
from typing import Dict, Any
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

# Import the video workflow
from .video_gemini_workflow import VideoGeminiWorkflow
from ..utils.resource_path import get_resource_path

# Set up logging
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO').upper())
logger = logging.getLogger(__name__)

# Global variable to store the stop event
video_analysis_stop_event = None

# Pydantic models
class FileUploadResponse(BaseModel):
    filename: str = Field(max_length=4096, pattern=r'[\s\S]*')
    filepath: str = Field(max_length=4096, pattern=r'[\s\S]*')
    video_url: str = Field(max_length=4096, pattern=r'[\s\S]*')
    message: str = Field(max_length=4096, pattern=r'[\s\S]*', default="Video uploaded successfully")

class VideoAnalysisRequest(BaseModel):
    location: str = Field(default="", description="Optional location context for video analysis")
    target_label: str = Field(default="ad", description="Target style label (ad or non-ad)")

class VideoAnalysisResponse(BaseModel):
    id: str = Field(max_length=100000, pattern=r'[\s\S]*')
    status: str = Field(description="Analysis status")
    message: str = Field(description="Response message")
    error_message: str = Field(default="", description="Error message if any")
    report: str = Field(default="", description="Analysis report in markdown format")

class HealthResponse(BaseModel):
    message: str = Field(max_length=4096, pattern=r'[\s\S]*', default="")

# Add this new Pydantic model for the cancel request
class CancelOperationRequest(BaseModel):
    operation_type: str = Field(..., description="Type of operation to cancel: 'video_analysis', etc.")

# FastAPI app setup
tags_metadata = [
    {"name": "Health", "description": "APIs for checking server health."},
    {"name": "Video Upload", "description": "APIs for video file uploads."},
    {"name": "Video Analysis", "description": "APIs for video analysis using Gemini."},
]

app = FastAPI(
    title="Video Analysis API",
    description="API for video upload and analysis using Gemini",
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

@app.on_event("startup")
async def startup_event():
    """Initialize the video analysis server components"""
    try:
        # Initialize workflow instance
        app.video_workflow = VideoGeminiWorkflow()
        
        # Mount the uploads directory
        uploads_path = get_resource_path("uploads")
        os.makedirs(uploads_path, exist_ok=True)
        app.mount("/videos", StaticFiles(directory=uploads_path), name="videos")
        
        logger.info("Video analysis server initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize video analysis server: {str(e)}")
        raise RuntimeError(f"Video analysis server initialization failed: {str(e)}")

@app.get("/video/{filename}", tags=["Video Streaming"])
async def get_video(filename: str):
    """Stream a video file"""
    try:
        video_path = get_resource_path(os.path.join("uploads", filename))
        
        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Video not found")
            
        return FileResponse(
            video_path,
            media_type="video/mp4",
            filename=filename
        )
        
    except Exception as e:
        logger.error(f"Error streaming video: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API Endpoints
@app.get("/health", tags=["Health"], response_model=HealthResponse)
async def health_check():
    """Perform a Health Check"""
    return HealthResponse(message="Video analysis server is up and running.")

@app.post("/upload_video", tags=["Video Upload"], response_model=FileUploadResponse)
async def upload_video(file: UploadFile = File(...)):
    """Upload a video file for analysis"""
    # Validate file type
    allowed_video_types = ["video/mp4", "video/quicktime", "video/avi", "video/x-matroska", "video/webm"]
    if file.content_type not in allowed_video_types:
        raise HTTPException(status_code=400, detail="Only video files (mp4, mov, avi, mkv, webm) are allowed")
    
    try:
        # Create uploads directory if it doesn't exist
        upload_dir = get_resource_path("uploads")
        os.makedirs(upload_dir, exist_ok=True)
        
        # Clear the uploads directory first (optional, based on your requirement)
        for existing_file in os.listdir(upload_dir):
            existing_file_path = os.path.join(upload_dir, existing_file)
            if os.path.isfile(existing_file_path):
                os.remove(existing_file_path)
        
        # Save the file
        file_path = os.path.join(upload_dir, file.filename)
        contents = await file.read()
        
        with open(file_path, "wb") as f:
            f.write(contents)
        
        await file.close()
        
        logger.info(f"Video uploaded successfully: {file_path}")
        
        # Create video URL based on the filename
        video_url = f"/videos/{file.filename}"
        
        return FileUploadResponse(
            filename=file.filename,
            filepath=file_path,
            video_url=video_url,
            message="Video uploaded successfully"
        )
        
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload video: {e}")

@app.post("/analyze_video", tags=["Video Analysis"], response_model=VideoAnalysisResponse)
async def analyze_video(request: VideoAnalysisRequest):
    """Analyze the uploaded video using Gemini"""
    global video_analysis_stop_event
    video_analysis_stop_event = asyncio.Event()
    
    try:
        resp_id = str(uuid4())
        
        # Construct user input with target label
        user_input = f"{request.location}\n{request.target_label}"
        logger.info(f"Starting video analysis with input: {user_input}")
        
        task = asyncio.create_task(
                app.video_workflow.run(user_input, thread_id=resp_id, stop_event=video_analysis_stop_event)
            )
        result = await task
        
        if not result:
            return VideoAnalysisResponse(
                id=resp_id,
                status="error",
                message="Video analysis failed",
                error_message="Workflow execution failed"
            )
        
        # Check if the workflow was cancelled
        if result.get("status") == "cancelled":
            return VideoAnalysisResponse(
                id=resp_id,
                status="cancelled",
                message="Video analysis was cancelled",
                error_message="Operation cancelled by user"
            )
        
        if result.get("error_message"):
            return VideoAnalysisResponse(
                id=resp_id,
                status="error",
                message="Video analysis failed",
                error_message=result["error_message"]
            )
        

        message = f"Video analysis completed successfully."
    
        return VideoAnalysisResponse(
            id=resp_id,
            status="completed",
            message=message,
            report=result.get("report")
        )
        
    except Exception as e:
        logger.error(f"Error in video analysis: {str(e)}")
        return VideoAnalysisResponse(
            id=str(uuid4()),
            status="error",
            message="Video analysis failed",
            error_message=str(e)
        )

@app.post("/cancel_operation", tags=["Video Analysis"])
async def cancel_operation(request: CancelOperationRequest):
    """Cancel an ongoing operation"""
    global video_analysis_stop_event
    if request.operation_type == 'video_analysis' and video_analysis_stop_event is not None:
        video_analysis_stop_event.set()
        return {"message": "Video analysis operation cancelled"}
    else:
        raise HTTPException(status_code=404, detail="No active video analysis operation found")

def main():
    """Main function to run the server"""
    # Get configuration from environment variables
    host = os.environ.get("SCRAPING_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SCRAPING_SERVER_PORT", "8005"))
    
    logger.info(f"Starting captions server on {host}:{port}")
    
    # Run the server
    uvicorn.run(
        "src.captions.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()