import logging
from typing import TypedDict, Optional, Dict, Any, List
import asyncio

from src.base_workflow import BaseWorkflow, BaseWorkflowState, check_cancellation
from src.scraping import caption_embeddings
from src.scraping.instagram_posts_scraper import InstagramPostsScraper
from src.scraping.caption_embeddings import process_captions
from langgraph.graph import END

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class InstagramScrapingState(BaseWorkflowState):
    """State for Instagram scraping workflow"""
    user_input: str  # User input from BaseWorkflowState
    usernames: List[str] = []  # List of Instagram usernames to scrape
    max_posts: int = 50  # Maximum number of posts to scrape per username
    force_reset: bool = False  # Whether to force scrape even if recently scraped
    scraping_result: Optional[Dict[str, Any]] = None  # Result of Instagram scraping
    clustering_result: Optional[Dict[str, Any]] = None  # Result of caption clustering

class InstagramScrapingWorkflow(BaseWorkflow):
    """Workflow for scraping Instagram posts and building caption embeddings"""
    
    def get_state_class(self):
        return InstagramScrapingState
    
    def define_nodes(self):
        return {
            "extract_parameters": self.extract_parameters,
            "scrape_instagram": self.scrape_instagram,
            "build_embeddings": self.build_embeddings
        }
    
    def define_edges(self, workflow):
        # Define the flow of the workflow
        workflow.add_edge("extract_parameters", "scrape_instagram")
        workflow.add_edge("scrape_instagram", "build_embeddings")
        workflow.add_edge("build_embeddings", END)
    
    def get_entry_point(self) -> str:
        return "extract_parameters"
    
    def extract_parameters(self, state: InstagramScrapingState):
        """Extract parameters using structured command syntax"""
        state = self.update_step(state, "parameter_extraction")
        
        user_input = state["user_input"]
        
        # Define parameter keys
        param_keys = {
            "usernames:": "usernames",
            "accounts:": "usernames",
            "max_posts:": "max_posts",
            "force_reset:": "force_reset"
        }
        
        # Extract parameters using structured syntax
        extracted_params = {}
        
        # Split by lines or semicolons to handle multiple parameters
        lines = user_input.replace(";", "\n").split("\n")
        
        for line in lines:
            line = line.strip()
            for key_prefix, param_name in param_keys.items():
                if line.lower().startswith(key_prefix.lower()):
                    # Extract the value after the prefix
                    value = line[len(key_prefix):].strip()
                    if value:  # Only set if value is not empty
                        extracted_params[param_name] = value
        
        # Process usernames
        if "usernames" in extracted_params:
            # Split by commas or spaces
            username_str = extracted_params["usernames"]
            usernames = [u.strip('@') for u in username_str.replace(',', ' ').split() if u.strip('@')]
            state["usernames"] = usernames
        
        # Process max_posts
        if "max_posts" in extracted_params:
            try:
                max_posts = int(extracted_params["max_posts"])
                state["max_posts"] = max_posts
            except ValueError:
                # Keep default if parsing fails
                pass
        
        if "force_reset" in extracted_params:
            force_value = extracted_params["force_reset"].lower()
            state["force_reset"] = force_value in ["true", "yes", "1"]
        
        # Validate usernames
        if not state["usernames"]:
            state["error_message"] = "No Instagram usernames found in input. Please provide usernames using 'usernames: username1, username2' format."
            state["workflow_status"] = "error"        
        return state
    
    async def scrape_instagram(self, state: InstagramScrapingState):
        """Scrape Instagram posts using InstagramPostsScraper"""
        state = self.update_step(state, "instagram_scraping")
        
        # Handle force_rebuild first
        self.handle_force_rebuild(state)
        
        usernames = state.get("usernames", [])
        max_posts = state.get("max_posts", 50)
        
        if not usernames:
            state["error_message"] = "No usernames provided for scraping"
            state["workflow_status"] = "error"
            return state
        
        try:
            logger.info(f"Starting Instagram scraping for: {usernames} with max_posts: {max_posts}")
            
            scraper = InstagramPostsScraper()
            
                    
            # Scrape posts for each username
            result = await scraper.scrape_and_save_multiple(
                usernames=usernames,
                max_limit=max_posts,
                stop_event=self.stop_event  # Pass the stop_event from the workflow
            )
            

            logger.info(f"Instagram scraping completed")
            
            # Store the scraping result
            state["scraping_result"] = result
            state["workflow_status"] = "scraped"
            
        except Exception as e:
            error_msg = f"Instagram scraping failed: {str(e)}"
            logger.error(f"Error in Instagram scraping: {error_msg}")
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state
    
    
    # And update the build_embeddings function
    @check_cancellation
    async def build_embeddings(self, state: InstagramScrapingState):
        """Build embeddings database using caption processing"""
        state = self.update_step(state, "embedding_building")
        
        try:
            scraper = InstagramPostsScraper()
            posts = scraper.load_posts_from_db()
            
            if not posts:
                state["error_message"] = "No posts available for embedding"
                state["workflow_status"] = "error"
                return state
            
            logger.info(f"Starting caption and transcript processing with {len(posts)} posts")
            
            # Create a dictionary with post_url as keys
            posts_dict = {}
            
            for post in posts:
                post_url = post.get('post_url', '')
                caption = post.get('caption_text', '')
                is_ad = post.get("is_paid_partnership", False) or post.get("has_sponsorship_keywords", False)
                transcript = post.get("video_transcript", "")
                
                # Create tags dictionary with post metadata
                tags = {
                    "post_url": post_url,
                    "username": post.get("username", ""),
                    "media_type": post.get("media_type", ""),
                    "category": post.get("category", ""),
                    "label": "ad" if is_ad else "non-ad",

                }
                
                # Add to posts dictionary
                posts_dict[post_url] = {
                    'caption': caption,
                    'transcript': transcript,
                    'tags': tags
                }
            
            result = process_captions(posts_dict)

            
            # Update state with results
            state["embedding_result"] = result
            state["workflow_status"] = "completed"
            
            return state
            
        except Exception as e:
            logger.error(f"Error building embeddings: {str(e)}", exc_info=True)
            state["error_message"] = f"Error building embeddings: {str(e)}"
            state["workflow_status"] = "error"
            return state
    
    def handle_force_rebuild(self, state: InstagramScrapingState):
        """Handle force_rebuild by clearing database tables and FAISS indices"""
        if state.get("force_reset", False):
            logger.info("Force rebuild requested. Clearing database tables and FAISS indices...")
            
            # 1. Clear database tables
            from src.utils.db_client import ensure_db_initialized
            from src.utils.embedding_client import ensure_embedding_initialized
            ensure_db_initialized(force_reset=True)
            ensure_embedding_initialized(force_reset=True)
            
            
            logger.info("Database tables and embedding db cleared successfully.")

# Create workflow instance
instagram_scraping_workflow = InstagramScrapingWorkflow()

# Helper function to run the workflow
async def run_workflow(user_input: str, stop_event: Optional[asyncio.Event] = None):
    """Run the Instagram scraping workflow with the given input"""
    result = await instagram_scraping_workflow.run(user_input, stop_event=stop_event)
    
    if result.get("error_message"):
        print(f"\nError: {result['error_message']}")
        return False
    
    return result

# For command-line usage
if __name__ == "__main__":
    import asyncio
    
    caption_embeddings.initialize_caption_utils()
    # Get user input from command line
    user_input = "usernames: tika_andhini, ugcwithkrystle, ugcbymelody; max_posts: 10;force_reset: false"
    
    # Run the workflow
    result = asyncio.run(run_workflow(user_input))
    
    # Print the report if available
    if result and result.get("report"):
        print("\n" + result["report"])