import os
import re
import csv
import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
import random
from typing import TypedDict, Optional
from ..base_workflow import BaseWorkflow, BaseWorkflowState
from langgraph.graph import END

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InstagramCollaborationState(BaseWorkflowState):
    """State for Instagram collaboration workflow"""
    user_input: str  # User input from BaseWorkflowState
    niche: Optional[str]  # Extracted niche
    location: Optional[str]  # Extracted location
    collaboration_result: Optional[dict]  # Result from collaboration finder
    number_search_result: Optional[int]  # Number of search results
    max_results: Optional[int] = 10  # Maximum number of results per page
    max_pages: Optional[int] = 10  # Maximum number of pages to search


class InstagramCollaborationFinder:
    def __init__(self, niche="", location="", output_dir=None):
        """
        Initialize the Instagram Collaboration Finder.
        
        Args:
            niche (str): Your content niche (e.g., fitness, beauty, travel)
            location (str): Your location for region-specific collaborations
            output_dir (str): Directory to save results (default: project root)
        """
        self.niche = niche
        self.location = location
        
        # Set default output directory if not provided
        if output_dir is None:
            self.output_dir = Path(__file__).parent.parent / "collaboration_opportunities"
        else:
            self.output_dir = Path(output_dir)
            
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # User agent to mimic browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # List to store collaboration opportunities
        self.opportunities = []
    
    def generate_search_queries(self):
        """
        Generate a list of search queries to find collaboration opportunities.
        
        Returns:
            list: List of search queries
        """
        queries = [
            # Brand-focused queries with niche and location
            f"site:instagram.com \"{self.niche}\" \"www.\" \"{self.location}\" -inurl:/reel/ -inurl:/p/",
            f"site:instagram.com \"official account\" \"{self.niche}\" \"{self.location}\" -inurl:/reel/ -inurl:/p/",
        ]
        
        return queries
    
    async def search_google(self, query, num_results=10, max_pages=10):
        """
        Perform a Google search with the given query, supporting multiple pages of results.
        
        Args:
            query (str): Search query
            num_results (int): Number of results per page
            max_pages (int): Maximum number of pages to retrieve (default: 10)
            
        Returns:
            list: List of search result dictionaries
        """
        try:
            # Get the search client from gemini_client.py
            from src.utils.gemini_client import get_search_client
            
            search_service = get_search_client()
            if search_service is None:
                logger.error("Error: Search service not initialized properly.")
                return []
            
            # Get the Custom Search Engine ID
            cse_id = os.getenv('GOOGLE_CSE_ID')
                        
            logger.info(f"Searching Google for: {query}")
            
            all_results = []
            
            # Fetch multiple pages of results (maximum 10 pages)
            actual_max_pages = min(max_pages, 10)  # Ensure we don't exceed 10 pages
            
            for page in range(actual_max_pages):
                start_index = (page * num_results) + 1  # Google's API uses 1-based indexing
                
                logger.info(f"Fetching page {page+1}/{actual_max_pages} with start_index {start_index}")
                
                # Execute the search query for this page
                res = search_service.cse().list(
                    q=query,
                    cx=cse_id,
                    num=num_results,
                    start=start_index
                ).execute()
                
                # Check if there are any search results
                if 'items' not in res:
                    logger.warning(f"No results found for page {page+1}")
                    break  # No more results available
                
                # Format the results for this page
                for item in res['items']:
                    result = {
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "")
                    }
                    all_results.append(result)
                
                # If we got fewer results than requested, there are no more pages
                if len(res.get('items', [])) < num_results:
                    logger.info(f"Received fewer results than requested, stopping pagination")
                    break
                
                # Add a delay between requests to avoid rate limiting
                if page < actual_max_pages - 1:
                    sleep_time = random.uniform(2.0, 5.0)  # Random sleep between 2-5 seconds
                    logger.info(f"Sleeping for {sleep_time:.2f} seconds before next request")
                    await asyncio.sleep(sleep_time)
            
            logger.info(f"Total results found: {len(all_results)}")
            
            # Save raw search results to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_csv_filename = f"{self.niche}_raw_search_results_{timestamp}.csv"
            raw_csv_path = self.output_dir / raw_csv_filename
            
            with open(raw_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ["title", "link", "snippet"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for result in all_results:
                    writer.writerow(result)
            
            logger.info(f"Saved {len(all_results)} raw search results to {raw_csv_path}")
            return all_results
            
        except Exception as e:
            error_message = str(e)
            # Add more detailed error information for debugging
            if "403" in error_message:
                logger.error(f"Error performing search: {error_message}\n\nThis is likely due to API key permissions. Please check that:\n1. The Custom Search API is enabled in your Google Cloud Console\n2. Your API key has the necessary permissions\n3. There are no IP restrictions on your API key")
            else:
                logger.error(f"Error searching Google: {error_message}")
            return []
    
    def extract_instagram_handles(self, results):
        """
        Extract Instagram handles from search results.
        
        Args:
            results (list): List of search result dictionaries
            
        Returns:
            list: List of dictionaries with Instagram handle information
        """
        handles = []
        
        for result in results:
            # Extract Instagram handles from URLs
            instagram_pattern = r'instagram\.com/([\w\.]+)'
            matches = re.findall(instagram_pattern, result.get("link", ""))
            
            if matches:
                for handle in matches:
                    # Skip Instagram's own handle
                    if handle in ["instagram", "explore", "p"]:
                        continue
                        
                    # Create opportunity dictionary
                    opportunity = {
                        "handle": handle,
                        "profile_url": f"https://instagram.com/{handle}",
                        "source": result.get("title", ""),
                        "description": result.get("snippet", ""),
                        "contact_info": self.extract_contact_info(result.get("snippet", ""))
                    }
                    
                    handles.append(opportunity)
        
        return handles
    
    
    def extract_contact_info(self, text):
        """
        Extract contact information from text.
        
        Args:
            text (str): Text to analyze
            
        Returns:
            dict: Dictionary with contact information
        """
        contact_info = {}
        
        # Extract email addresses
        email_pattern = r'[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}'
        email_matches = re.findall(email_pattern, text)
        if email_matches:
            contact_info["email"] = email_matches[0]
        
        # Extract instructions for contact
        if "dm" in text.lower() or "direct message" in text.lower():
            contact_info["method"] = "DM on Instagram"
        elif "email" in text.lower():
            contact_info["method"] = "Email"
        elif "link in bio" in text.lower():
            contact_info["method"] = "Link in bio"
        
        return contact_info
    
    async def find_collaboration_opportunities(self, max_results, max_pages):
        """
        Find collaboration opportunities on Instagram.
        
        Returns:
            list: List of collaboration opportunities
        """
        # Generate search queries
        queries = self.generate_search_queries()
        
        # Search Google for each query
        all_results = []
        for query in queries:
            results = await self.search_google(query, max_results, max_pages)
            all_results.extend(results)
        
        # Extract Instagram handles from search results
        opportunities = self.extract_instagram_handles(all_results)
        
        # Remove duplicates based on handle
        unique_opportunities = []
        seen_handles = set()
        
        for opportunity in opportunities:
            if opportunity["handle"] not in seen_handles:
                unique_opportunities.append(opportunity)
                seen_handles.add(opportunity["handle"])
        
        self.opportunities = unique_opportunities
        return unique_opportunities
    
    def save_to_csv(self):
        """
        Save collaboration opportunities to a CSV file.
        
        Returns:
            str: Path to the saved CSV file
        """
        if not self.opportunities:
            logger.warning("No opportunities to save")
            return None
        
        # Create timestamp for filename
        timestamp = datetime.now().strftime("%Y%m%d")
        
        # Create filename with niche
        niche_str = self.niche.replace(" ", "_") if self.niche else "all"
        filename = f"{niche_str}_leads_{timestamp}.csv"
        
        # Full path to CSV file
        csv_path = self.output_dir / filename
        
        # Write to CSV
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                "handle", "profile_url", "source", "description", 
                "collaboration_type", "contact_info"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for opportunity in self.opportunities:
                # Convert contact_info dictionary to string for CSV
                opportunity["contact_info"] = json.dumps(opportunity["contact_info"])
                writer.writerow(opportunity)
        
        logger.info(f"Saved {len(self.opportunities)} opportunities to {csv_path}")
        return str(csv_path)
    

class InstagramCollaborationWorkflow(BaseWorkflow):
    """Workflow for finding Instagram collaboration opportunities"""
    
    def get_state_class(self):
        return InstagramCollaborationState
    
    def define_nodes(self):
        return {
            "extract_parameters": self.extract_parameters,
            "find_collaborations": self.find_collaborations
        }
    
    def define_edges(self, workflow):
        workflow.add_edge("extract_parameters", "find_collaborations")
        workflow.add_edge("find_collaborations", END)
    
    def get_entry_point(self) -> str:
        return "extract_parameters"
    
    def extract_parameters(self, state: InstagramCollaborationState):
        """Extract parameters using structured command syntax"""
        state = self.update_step(state, "parameter_extraction")
        
        user_input = state["user_input"]
        
        # Define parameter keys
        param_keys = {
            "niche:": "niche",
            "location:": "location",
            "max_results:": "max_results",
            "max_pages:": "max_pages"
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
        
        # Set extracted parameters in state
        if "niche" in extracted_params:
            state["niche"] = extracted_params["niche"]
        else:
            raise ValueError("Niche is required")
            
        if "location" in extracted_params:
            state["location"] = extracted_params["location"]
        else:
            state["location"] = ""
            
        # Handle numeric parameters
        if "max_results" in extracted_params:
            try:
                state["max_results"] = int(extracted_params["max_results"])
            except ValueError:
                state["max_results"] = 10  # Default value
                
        if "max_pages" in extracted_params:
            try:
                state["max_pages"] = int(extracted_params["max_pages"])
            except ValueError:
                state["max_pages"] = 10  # Default value
        
        logger.info(f"Extracted parameters: {extracted_params}")
        
        return state
    
    async def find_collaborations(self, state: InstagramCollaborationState):
        """Find Instagram collaboration opportunities"""
        state = self.update_step(state, "collaboration_search")
        
        niche = state.get("niche", "")
        location = state.get("location", "")
        max_results = state.get("max_results", 10)
        max_pages = state.get("max_pages", 10)
        
        try:
            # Create finder instance directly
            finder = InstagramCollaborationFinder(niche=niche, location=location)
            
            # Find collaboration opportunities
            opportunities = await finder.find_collaboration_opportunities(max_results=max_results, max_pages=max_pages)

            # Save results to CSV
            csv_path = finder.save_to_csv()
            
            # Create result dictionary
            result = {
                "success": True,
                "profiles": opportunities,  # Change from opportunities to profiles
                "csv_path": csv_path
            }
            
            state["collaboration_result"] = result
            state["workflow_status"] = "completed"
            logger.info(f"Found {len(opportunities)} collaboration opportunities")
        except Exception as e:
            error_msg = f"Error finding collaborations: {str(e)}"
            logger.error(error_msg)
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state