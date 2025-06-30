from typing import List, Optional
from langchain_core.tools import tool
from googleapiclient.discovery import build
import os
from trendspy import Trends
import logging
from datetime import datetime, timedelta

# Initialize the search service at module level
def _init_search_service():
    """Initialize Google Custom Search API service with environment validation"""
    required_vars = ['GOOGLE_API_KEY', 'GOOGLE_CSE_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    api_key = os.getenv('GOOGLE_API_KEY')
    # Build the service object for the Custom Search API
    service = build("customsearch", "v1", developerKey=api_key)
    return service

# Create a singleton instance at module level
try:
    _search_service = _init_search_service()
except Exception as e:
    print(f"Error initializing search service: {str(e)}")
    _search_service = None

# Initialize trends client at module level
try:
    _trends_client = Trends(request_delay=3)
except Exception as e:
    print(f"Error initializing trends client: {str(e)}")
    _trends_client = None

@tool
def get_trending_topics(city_code : str) -> List[str]:
    """Fetches trending topics from Google Trends.
    
    Args:
        city (str): The city to get trends for. Defaults to 'AU'.
    
    Returns:
        List[Dict]: A list of dictionaries containing trend data, where each dictionary has
            'keyword' (str) and 'category' (str) fields.
    """
    try:
        if _trends_client is None:
            return ["Error: Trends client not initialized properly."]
        
        # Get trending topics
        raw = _trends_client.trending_now(geo=city_code, hours=191)
        formatted_results = []
        
        for t in raw:
            cat = t.topic_names[0] if t.topic_names else 'Unknown'
            trend_data = {
                'keyword': t.normalized_keyword,
                'category': cat
            }
            formatted_results.append(trend_data)
        
        #formatted_results = formatted_results[:200]
        return formatted_results if formatted_results else [{'keyword': 'No trending topics found', 'category': 'None'}]
        
    except Exception as e:
        return [f"Error fetching trends: {str(e)}"]

@tool
def google_search(query: str, num_results: Optional[int] = 5) -> List[str]:
    """Performs a Google search and returns relevant results.
    
    Args:
        query (str): The search query string to find relevant content.
                    Should be specific and focused on the target topic.
        num_results (Optional[int]): Number of results to return. Defaults to 5.
    
    Returns:
        List[str]: A list of relevant search results, each containing the title and snippet.
    """
    try:
        if _search_service is None:
            return ["Error: Search service not initialized properly."]
        
        # Get the Custom Search Engine ID
        cse_id = os.getenv('GOOGLE_CSE_ID')
        
        # Execute the search query
        res = _search_service.cse().list(
            q=query,
            cx=cse_id,
            num=num_results
        ).execute()
        
        # Format the results
        formatted_results = []
        
        # Check if there are any search results
        if 'items' not in res:
            return ["No results found for the query."]
            
        for item in res['items']:
            title = item.get("title", "")
            formatted_results.append(title)
        
        return formatted_results
        
    except Exception as e:
        error_message = str(e)
        # Add more detailed error information for debugging
        if "403" in error_message:
            return [f"Error performing search: {error_message}\n\nThis is likely due to API key permissions. Please check that:\n1. The Custom Search API is enabled in your Google Cloud Console\n2. Your API key has the necessary permissions\n3. There are no IP restrictions on your API key"]
        return [f"Error performing search: {error_message}"]


@tool
def get_related_queries(keyword: str) -> List[str]:
    """Fetches related queries for a given keyword from Google Trends.
    
    Args:
        keyword (str): The keyword to get related queries for (e.g., 'nsw flood').
    
    Returns:
        List[str]: A list of related queries for the given keyword.
    """
    try:
        if _trends_client is None:
            return ["Error: Trends client not initialized properly."]
        
        # Maximum number of retry attempts
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries + 1):  # +1 to include the initial attempt
            try:
                # Add significant delay between attempts to avoid hitting rate limits
                if attempt > 0:
                    import time
                    # Longer wait times: 30 seconds, 60 seconds, 120 seconds
                    wait_time = 30 * (2 ** (attempt - 1))
                    print(f"Waiting {wait_time} seconds before retry {attempt}...")
                    time.sleep(wait_time)
                    
                # Use Google referer for all attempts to improve success rate
                related = _trends_client.related_queries(keyword)
                formatted_results = []
                
                # Process and format the results
                if related and hasattr(related, 'top'):
                    for query in related.top:
                        formatted_results.append(query.query)
                        
                return formatted_results if formatted_results else ["No related queries found for the keyword."]
                
            except Exception as e:
                last_error = e
                # Check if it's a quota exceeded error
                if "quota exceeded" in str(e).lower() or "trendsquotaexceedederror" in str(type(e)).lower():
                    # Continue to next retry attempt
                    print(f"Quota exceeded on attempt {attempt}, will retry...")
                    continue
                else:
                    # For other errors, raise immediately
                    raise
        
        # If we've exhausted all retry attempts
        return [f"Error fetching related queries after {max_retries} retry attempts: {str(last_error)}. "
                f"Consider trying again later or with a different keyword."]
        
    except Exception as e:
        return [f"Error fetching related queries: {str(e)}"]


@tool
def enhanced_google_search(keyword: str, source_type: Optional[str] = "all", num_results: Optional[int] = 5) -> List[str]:
    """Discovers why a keyword is trending by searching across news, press releases, and social media.
    
    Args:
        keyword (str): The trending keyword to research.
        source_type (str): Type of sources to search. Options: "news", "press", "social", "all". Defaults to "all".
        num_results (int): Number of results to return per source type. Defaults to 5.
    
    Returns:
        List[str]: A list of search results explaining why the keyword might be trending.
    """
    try:
        if _search_service is None:
            return ["Error: Search service not initialized properly."]
        
        # Get the Custom Search Engine ID
        cse_id = os.getenv('GOOGLE_CSE_ID')
        
        # Calculate date for last 7 days
        seven_days_ago = datetime.now() - timedelta(days=7)
        date_restrict = f"d7" # Restrict to last 7 days
        
        all_results = []
        queries = []
        
        # News sources
        if source_type.lower() in ["news", "all"]:
            news_queries = [
                f'"{keyword}" announcement', 
                f'"{keyword}" update', 
                f'"{keyword}" controversy',
                f'"{keyword}" site:nytimes.com',
                f'"{keyword}" site:cnn.com',
                f'"{keyword}" site:bbc.com'
            ]
            queries.extend([(q, "News") for q in news_queries])
        
        # Press releases
        if source_type.lower() in ["press", "all"]:
            press_queries = [
                f'"{keyword}" site:prnewswire.com', 
                f'"{keyword}" site:businesswire.com'
            ]
            queries.extend([(q, "Press Release") for q in press_queries])
        
        # Social media and forums
        if source_type.lower() in ["social", "all"]:
            social_queries = [
                f'site:reddit.com "{keyword}"',
                f'site:quora.com "{keyword}" why',
                f'site:twitter.com "{keyword}"'
            ]
            queries.extend([(q, "Social Media") for q in social_queries])
        
        # Execute searches
        for query, source in queries:
            try:
                # Add sleep between API calls to avoid rate limiting
                import time
                time.sleep(2.0)  # Sleep for 1.5 seconds between calls
                
                # Use the existing google_search function instead of direct API calls
                search_results = google_search.invoke(query, num_results)
                
                # Process the results
                if search_results and not search_results[0].startswith("Error") and not search_results[0].startswith("No results"):
                    for title in search_results:
                        # Since google_search only returns titles, we'll format with just the title
                        result = f"[{source}] {title}\nSource: Search result for '{query}'"
                        all_results.append(result)
                else:
                    # Add the error or no results message
                    all_results.append(f"[{source}] {search_results[0]}")
            except Exception as e:
                # Continue with other queries if one fails
                all_results.append(f"Error with query '{query}': {str(e)}")
        
        # Return results or error message
        if not all_results:
            return [f"No context found for why '{keyword}' is trending in the last 7 days."]
        
        # Import necessary modules for Gemini integration
        from langchain_google_genai import ChatGoogleGenerativeAI
        from pydantic import BaseModel, Field
        
        # Define structured output model for trend summary
        class TrendSummary(BaseModel):
            """Structured output for trend context summary"""
            main_reason: str = Field(description="The primary reason why this keyword is trending")
            key_points: List[str] = Field(description="3-5 key points extracted from the search results")
            source_analysis: str = Field(description="Brief analysis of the sources (news, press, social) and their perspectives")
        
        # Initialize Gemini model with structured output
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.3
        )
        structured_llm = llm.with_structured_output(TrendSummary)
        
        # Prepare prompt for summarization
        summary_prompt = f"""
        Analyze these search results about why '{keyword}' is trending:
        
        {all_results}
        
        Provide a concise summary explaining why this keyword is trending based on the search results.
        Focus on extracting the main reason, key points, and analyzing the different source perspectives.
        """
        
        try:
            # Get structured summary from Gemini
            summary = structured_llm.invoke(summary_prompt)
            
            # Add summary to the beginning of results
            summary_text = f"""
            ## Summary: Why '{keyword}' is Trending
            
            **Main Reason**: {summary.main_reason}
            
            **Key Points**:
            {chr(10).join([f'- {point}' for point in summary.key_points])}
            
            **Source Analysis**: {summary.source_analysis}
            
            ## Detailed Search Results:
            """
            
            return [summary_text] + all_results
        except Exception as e:
            # If summarization fails, return just the search results
            logging.warning(f"Summarization failed: {str(e)}")
            return all_results
        return all_results
        
    except Exception as e:
        error_message = str(e)
        if "403" in error_message:
            return [f"Error performing trend context search: {error_message}\n\nThis is likely due to API key permissions. Please check that:\n1. The Custom Search API is enabled in your Google Cloud Console\n2. Your API key has the necessary permissions\n3. There are no IP restrictions on your API key"]
        return [f"Error performing trend context search: {error_message}"]


