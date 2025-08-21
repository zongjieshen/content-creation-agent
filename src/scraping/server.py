import os
import asyncio
import logging
from uuid import uuid4
from typing import List, Dict, Any, Optional
from traceback import print_exc

from fastapi import FastAPI, Request, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY
from pydantic import BaseModel, Field, validator
import uvicorn

# Import scraping components
from .instagram_posts_scraper import InstagramPostsScraper
from .scraping_workflow import InstagramScrapingWorkflow
from .caption_embeddings import apply_style_to_content, LABELS, initialize_caption_utils

# Set up logging
logging.basicConfig(level=os.environ.get('LOGLEVEL', 'INFO').upper())
logger = logging.getLogger(__name__)

initialize_caption_utils()
# Pydantic models
class ScrapeProfileRequest(BaseModel):
    """Request model for scraping Instagram profiles"""
    usernames: List[str] = Field(..., description="List of Instagram usernames to scrape")
    max_posts: int = Field(50, description="Maximum number of posts to scrape per username")
    force_reset: bool = Field(False, description="Whether to force scrape even if recently scraped")

class ScrapeProfileResponse(BaseModel):
    """Response model for scraping Instagram profiles"""
    request_id: str = Field(..., description="Unique identifier for this request")
    usernames: List[str] = Field(..., description="List of Instagram usernames that were scraped")
    posts_scraped: Dict[str, int] = Field(..., description="Number of posts scraped for each username")
    status: str = Field(..., description="Status of the scraping operation")
    message: str = Field(..., description="Message describing the result")

class GetScrapedUsersResponse(BaseModel):
    """Response model for getting scraped users"""
    users: List[Dict[str, Any]] = Field(..., description="List of scraped users with metadata")

class GetPostsRequest(BaseModel):
    """Request model for getting posts from the database"""
    username: Optional[str] = Field(None, description="Filter posts by username")
    limit: int = Field(50, description="Maximum number of posts to return")
    offset: int = Field(0, description="Offset for pagination")
    order_by: str = Field("taken_at", description="Field to order results by")
    order_dir: str = Field("desc", description="Order direction (asc or desc)")
    is_ad_only: bool = Field(False, description="Whether to return only ads")

class GetPostsResponse(BaseModel):
    """Response model for getting posts from the database"""
    posts: List[Dict[str, Any]] = Field(..., description="List of posts")
    total: int = Field(..., description="Total number of posts matching the criteria")
    has_more: bool = Field(..., description="Whether there are more posts to fetch")

class GetTaggedUsersFromAdsResponse(BaseModel):
    """Response model for getting tagged users from ad posts"""
    users: List[Dict[str, Any]] = Field(..., description="List of tagged users from ad posts")

# New models for style application
class ApplyStyleRequest(BaseModel):
    """Request model for applying style to content"""
    content: str = Field(..., description="Content to be styled")
    embedding_type: str = Field(..., description="Embedding type to use, caption or transcript")
    num_examples: int = Field(3, description="Number of similar examples to use")
    filter_tags: Optional[Dict[str, Any]] = Field(None, description="Filter tags for content retrieval")


class ApplyStyleResponse(BaseModel):
    """Response model for applying style to content"""
    request_id: str = Field(..., description="Unique identifier for this request")
    original_content: str = Field(..., description="Original content")
    styled_content: str = Field(..., description="Styled content")
    embedding_type: str = Field(..., description="Embedding type used")
    status: str = Field(..., description="Status of the operation")

# Fallback responses
FALLBACK_RESPONSES = [
    "An error occurred during the scraping process. Please try again.",
    "Unable to complete the scraping operation. Please check the usernames and try again.",
    "The scraping service is currently experiencing issues. Please try again later."
]

# FastAPI app setup
tags_metadata = [
    {"name": "Health", "description": "APIs for checking server health."},
    {"name": "Instagram Scraping", "description": "APIs for scraping Instagram profiles and retrieving data."},
    {"name": "Content Styling", "description": "APIs for applying style to content using FAISS indices."},
]

app = FastAPI(
    title="Instagram Scraping API",
    description="API for scraping Instagram profiles and retrieving data",
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

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(exc.errors(), exclude={"input"})}
    )

# API Endpoints
@app.get("/health", tags=["Health"])
async def health_check():
    """Perform a Health Check"""
    return {"message": "Instagram Scraping server is up and running."}


@app.get("/scraped_users", tags=["Instagram Scraping"], response_model=GetScrapedUsersResponse)
async def get_scraped_users():
    """Get list of scraped users"""
    try:
        # Initialize scraper
        scraper = InstagramPostsScraper()
        
        # Get scraped users
        users = scraper.get_scraped_users()
        
        return GetScrapedUsersResponse(users=users)
    
    except Exception as e:
        logger.error(f"Error getting scraped users: {str(e)}")
        print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error getting scraped users: {str(e)}"
        )

@app.post("/posts", tags=["Instagram Scraping"], response_model=GetPostsResponse)
async def get_posts(request: GetPostsRequest):
    """Get posts from the database"""
    try:
        # Initialize scraper
        scraper = InstagramPostsScraper()
        
        # Get posts
        posts = scraper.load_posts_from_db(
            username=request.username,
            limit=request.limit,
            offset=request.offset,
            order_by=request.order_by,
            order_dir=request.order_dir,
            is_ad_only=request.is_ad_only
        )
        
        # Check if there are more posts
        total_count = len(posts)
        if request.username:
            # If filtering by username, get total count
            all_posts = scraper.load_posts_from_db(username=request.username, limit=1000000)
            total_count = len(all_posts)
        
        has_more = (request.offset + request.limit) < total_count
        
        return GetPostsResponse(
            posts=posts,
            total=total_count,
            has_more=has_more
        )
    
    except Exception as e:
        logger.error(f"Error getting posts: {str(e)}")
        print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error getting posts: {str(e)}"
        )


# Replace active_workflows with a single global stop_event
scraping_stop_event = None

@app.post("/run_workflow", tags=["Instagram Scraping"])
async def run_scraping_workflow(request: ScrapeProfileRequest):
    """Run the Instagram scraping workflow"""
    global scraping_stop_event
    scraping_stop_event = asyncio.Event()
    try:
        # Generate a workflow ID (still useful for response tracking)
        session_id = str(uuid4())
        
        # Initialize workflow
        workflow = InstagramScrapingWorkflow()
        
        # Prepare input for workflow
        user_input = f"usernames: {', '.join(request.usernames)}\nmax_posts: {request.max_posts}\nforce_reset: {request.force_reset}"
        
        # Run workflow in a task that checks for cancellation
        try:
            task = asyncio.create_task(
                workflow.run(user_input, session_id, scraping_stop_event)
            )
            result = await task
                
        except Exception as workflow_error:
            logger.error(f"Workflow execution error: {str(workflow_error)}")
            result = {
                "workflow_status": "error",
                "error_message": str(workflow_error)
            }
        
        return {
            "session_id": session_id,
            "status": result.get("status", "unknown"),
            "result": result
        }
    
    except Exception as e:
        logger.error(f"Error running workflow: {str(e)}")
        print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error running workflow: {str(e)}"
        )

# New endpoint for applying style to content
@app.post("/apply_style", tags=["Content Styling"], response_model=ApplyStyleResponse)
async def apply_style(request: ApplyStyleRequest):
    """Apply style to content using FAISS indices"""
    try:
        # Generate a unique request ID
        request_id = str(uuid4())
                
        # Apply style to content using the static function
        styled_content = apply_style_to_content(
            content=request.content,
            embedding_type=request.embedding_type,
            num_examples=request.num_examples,
            filter_tags=request.filter_tags
        )
        
        return ApplyStyleResponse(
            request_id=request_id,
            original_content=request.content,
            styled_content=styled_content,
            embedding_type= request.embedding_type,
            status="success"
        )
    
    except Exception as e:
        logger.error(f"Error applying style: {str(e)}")
        print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error applying style: {str(e)}"
        )

@app.get("/get_brands", tags=["Instagram Scraping"], response_model=GetTaggedUsersFromAdsResponse)
async def get_brands():
    """Get tagged users from ad posts"""
    try:
        # Get tagged users from ads using the static method
        tagged_users = InstagramPostsScraper.load_tagged_users_from_ads()
        
        return GetTaggedUsersFromAdsResponse(users=tagged_users)
    
    except Exception as e:
        logger.error(f"Error getting tagged users from ads: {str(e)}")
        print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error getting tagged users from ads: {str(e)}"
        )

# Add this new Pydantic model for the cancel request
class CancelOperationRequest(BaseModel):
    operation_type: str = Field(..., description="Type of operation to cancel: 'scraping', etc.")

@app.post("/cancel_operation", tags=["Instagram Scraping"])
async def cancel_operation(request: CancelOperationRequest):
    global scraping_stop_event
    if request.operation_type == 'scraping' and scraping_stop_event is not None:
        scraping_stop_event.set()
        return {"message": "Scraping operation cancelled"}
    else:
        raise HTTPException(status_code=404, detail="No active scraping operation found")

def main():
    """Main function to run the server"""
    # Get configuration from environment variables
    host = os.environ.get("SCRAPING_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("SCRAPING_SERVER_PORT", "8002"))
    
    logger.info(f"Starting Instagram Scraping server on {host}:{port}")
    
    # Run the server
    uvicorn.run(
        "src.scraping.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()