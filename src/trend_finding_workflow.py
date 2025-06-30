from typing import TypedDict, List, Optional, Dict, Any, Literal
from .base_workflow import BaseWorkflow, BaseWorkflowState,InterruptConfig
from langgraph.graph import END
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from .tool import get_trending_topics
from collections import defaultdict
from difflib import SequenceMatcher
from pydantic import BaseModel, Field
import json
import yaml
import os
from google import genai

class TrendFindingState(BaseWorkflowState):
    """Unified state for trend finding workflow"""
    user_input: str  # User input from BaseWorkflowState
    trend_data: Optional[List]  # Collected trend data
    location: Optional[str]  # Selected location
    categories: Optional[List[str]]  # Available categories
    selected_categories: Optional[List[str]]  # User selected categories
    raw_location_input: Optional[str]  # Raw location input for validation
    is_satisfied: Optional[bool]  # Track if user is satisfied
    trends_summary: Optional[str]  # Summary of trends

def load_user_profile():
    """Load user profile from YAML file"""
    try:
        with open('user_interests.yaml', 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading user profile: {str(e)}")
        return {
            "interests": ["technology", "news", "entertainment"],
            "expertise_areas": ["content creation", "trend analysis"]
        }

def load_country_mapping():
    """Load country code mapping from JSON file"""
    try:
        with open('src/country_code_mapping.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "united states": "US", "usa": "US", "america": "US",
            "united kingdom": "GB", "uk": "GB", "britain": "GB",
            "canada": "CA", "australia": "AU", "germany": "DE",
            "france": "FR", "japan": "JP", "china": "CN",
            "india": "IN", "brazil": "BR", "global": "global",
            "worldwide": "global"
        }

COUNTRY_MAPPING = load_country_mapping()

def find_closest_countries(input_location: str, top_n: int = 3) -> List[str]:
    """Find closest matching countries using fuzzy matching"""
    input_lower = input_location.lower()
    
    if input_lower in COUNTRY_MAPPING:
        return [input_lower]
    
    matches = []
    for country in COUNTRY_MAPPING.keys():
        similarity = SequenceMatcher(None, input_lower, country).ratio()
        if similarity > 0.6:
            matches.append((country, similarity))
    
    matches.sort(key=lambda x: x[1], reverse=True)
    return [match[0] for match in matches[:top_n]]

def extract_location_from_message(message: str) -> Optional[str]:
    """Extract and normalize location from direct user input"""
    if not message:
        return None
    
    # Clean and normalize the input
    location = message.strip().lower()
    
    # Remove common prefixes that users might add
    prefixes_to_remove = [
        "in ", "for ", "from ", "location:", "country:", 
        "trending in", "trends in", "i want", "show me", "get"
    ]
    
    for prefix in prefixes_to_remove:
        if location.startswith(prefix):
            location = location[len(prefix):].strip()
    
    # Remove quotes if user wrapped the location
    location = location.strip('\'"')
    
    # Handle common variations and abbreviations
    location_aliases = {
        "usa": "united states",
        "america": "united states", 
        "us": "united states",
        "uk": "united kingdom",
        "britain": "united kingdom",
        "england": "united kingdom",
        "korea": "south korea",
        "uae": "united arab emirates",
        "emirates": "united arab emirates",
        "russia": "russia",
        "deutschland": "germany",
        "nippon": "japan",
        "中国": "china",
        "日本": "japan"
    }
    
    # Check for alias first
    if location in location_aliases:
        location = location_aliases[location]
    
    # Handle multi-word locations (remove extra spaces)
    location = " ".join(location.split())
    
    # Return the cleaned location if it's reasonable
    if len(location) > 0 and len(location) <= 50:  # Reasonable length check
        return location
    
    return None

class LocationPrediction(BaseModel):
    """Structured output model for location prediction"""
    country: str = Field(description="The predicted country name from the provided list")
    confidence: float = Field(description="Confidence score between 0 and 1")

def interpret_location_with_gemini(location_input: str, country_mapping: dict) -> Optional[str]:
    """Use Gemini to interpret ambiguous location inputs"""
    try:
        # Configure Gemini client
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        
        # Create prompt with available country options
        country_options = ", ".join(country_mapping.keys())
        prompt = f"""
        I need to map this location input: "{location_input}" to the closest match in this list:
        {country_options}
        
        Return a structured response with the predicted country name and your confidence level.
        Only use country names from the provided list. If you're not confident, set a low confidence score.
        """
        
        # Call Gemini API with structured output
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': LocationPrediction,
            }
        )
        
        # Get the structured prediction
        prediction = response.parsed
        
        # Only accept prediction if confidence is reasonable
        if prediction.confidence >= 0.6:
            # Find the correctly cased key
            for key in country_mapping.keys():
                if key.lower() == prediction.country.lower():
                    return key
        
        return None
    except Exception as e:
        print(f"Error calling Gemini: {str(e)}")
        return None

def validate_category_selection(user_input: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Validate user's category selection against available categories
    
    Args:
        user_input: The user's input string
        context: Dictionary containing available_categories
        
    Returns:
        Dict with validation results
    """
    available_categories = context.get("available_categories", [])
    
    # Handle special "all" case
    if user_input.lower() == "all":
        return {
            "valid": True,
            "selected_categories": available_categories
        }
        
    # Process comma-separated list of categories
    if "," in user_input:
        selected = [cat.strip() for cat in user_input.split(",")]
    else:
        selected = [user_input]
    
    # Validate selections against available categories
    valid_selections = []
    for selection in selected:
        # Try to find a matching category (case-insensitive)
        matching_category = next(
            (cat for cat in available_categories if cat.lower() == selection.lower()),
            None
        )
        
        if matching_category:
            valid_selections.append(matching_category)
    
    # If we have valid selections, return them
    if valid_selections:
        return {
            "valid": True,
            "selected_categories": valid_selections
        }
    
    # Return invalid result with guidance
    return {
        "valid": False,
        "error_message": f"Sorry, couldn't find categories matching '{user_input}'. Please select from the available options."
    }

def validate_satisfaction_response(user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
    """Validate user's satisfaction response
    
    Args:
        user_input: The user's input string
        context: Dictionary containing additional context (optional)
        
    Returns:
        Dict with validation results
    """
    # Convert to lowercase for case-insensitive matching
    user_input_lower = user_input.lower()
    
    # Check if user is satisfied
    if user_input_lower in ["yes", "y", "satisfied", "ok", "okay", "good", "done"]:
        return {
            "valid": True,
            "satisfied": True
        }
    
    # Check if user wants to try different categories
    if user_input_lower in ["no", "n", "not satisfied", "change", "different", "try again"]:
        return {
            "valid": True,
            "satisfied": False
        }
    
    # Invalid input
    return {
        "valid": False,
        "error_message": "Please respond with 'yes' if you're satisfied or 'no' to try different categories."
    }

class TrendFindingWorkflow(BaseWorkflow):
    """Simplified workflow for finding trending keywords"""
    
    def _register_interrupt_configs(self) -> Dict[str, InterruptConfig]:
        """Register interrupt configurations for trend finding workflow"""
        return {
            "category_selection": InterruptConfig(
                interrupt_type="category_selection",
                message="Please select categories from the available options:",
                instructions="You can select multiple categories separated by commas, or type 'all' to select all categories.",
                options=[],  # Will be populated dynamically
                step_name="category_selection",
                validation_fn=validate_category_selection,
                state_update_fn=self._update_category_selection_state
            ),
            "satisfaction_review": InterruptConfig(
                interrupt_type="satisfaction_review",
                message="Are you satisfied with these trending topics?",
                instructions="Type 'yes' if you're satisfied, or 'no' to try different categories.",
                options=["yes", "no"],
                step_name="satisfaction_review",
                validation_fn=validate_satisfaction_response,
                state_update_fn=self._update_satisfaction_state
            )
        }
    
    def _build_custom_interrupt_data(self, state: Dict, config: InterruptConfig) -> Dict[str, Any]:
        """Add trend-specific data to interrupts"""
        if config.interrupt_type == "category_selection":
            categories = state.get("categories", [])
            return {
                "available_categories": categories,
                "options": categories
            }
        elif config.interrupt_type == "satisfaction_review":
            return {
                "trends_summary": state.get("trends_summary", ""),
                "selected_categories": state.get("selected_categories", [])
            }
        return {}
    
    def _build_validation_context(self, state: Dict, config: InterruptConfig) -> Dict[str, Any]:
        """Build validation context for trend finding"""
        if config.interrupt_type == "category_selection":
            return {"available_categories": state.get("categories", [])}
        return {}
    
    def _validate_preconditions(self, state: Dict, config: InterruptConfig) -> Optional[Dict]:
        """Validate preconditions for trend finding interrupts"""
        if config.interrupt_type == "category_selection":
            categories = state.get("categories", [])
            if not categories:
                state["error_message"] = "No categories available for selection."
                state["workflow_status"] = "error"
                return state
        return None
    
    def _update_category_selection_state(self, state: Dict, result: Dict[str, Any]) -> Dict:
        """Update state after category selection"""
        state["selected_categories"] = result["selected_categories"]
        return state
    
    def _update_satisfaction_state(self, state: Dict, result: Dict[str, Any]) -> Dict:
        """Update state after satisfaction review"""
        state["is_satisfied"] = result["satisfied"]
        if result["satisfied"]:
            state["workflow_status"] = "completed"
        return state
    
    def define_nodes(self):
        return {
            "validate_location": self.validate_location,
            "fetch_trends": self.fetch_trends,
            "analyze_categories": self.analyze_categories,
            "process_category_selection": self.create_human_interaction_node("category_selection"),
            "show_results": self.show_results,
            "human_satisfaction_review": self.create_human_interaction_node("satisfaction_review")
        }
    
    def get_state_class(self):
        return TrendFindingState
    

    def define_edges(self, workflow):
        # Updated workflow with human-in-the-loop
        workflow.add_conditional_edges(
            "validate_location",
            self.route_after_location,
            {"fetch_trends": "fetch_trends", "END": END}
        )
        workflow.add_edge("fetch_trends", "analyze_categories")
        workflow.add_conditional_edges(
            "analyze_categories", 
            self.route_after_categories,
            {"process_category_selection": "process_category_selection", "END": END}
        )
        workflow.add_conditional_edges(
            "process_category_selection",
            self.route_after_selection,
            {"show_results": "show_results", "analyze_categories": "analyze_categories", "END": END}
        )
        # New: Route to satisfaction review after showing results
        workflow.add_edge("show_results", "human_satisfaction_review")
        workflow.add_conditional_edges(
            "human_satisfaction_review",
            self.route_after_satisfaction,
            {"analyze_categories": "analyze_categories", "END": END}
        )


    def get_entry_point(self) -> str:
        return "validate_location"
    
    def route_after_location(self, state: TrendFindingState) -> str:
        """Route after location validation"""
        if state.get("error_message"):
            return "END"
        return "fetch_trends"
    
    def route_after_categories(self, state: TrendFindingState) -> str:
        """Route after category analysis"""
        if state.get("error_message") or not state.get("categories"):
            return "END"
        return "process_category_selection"
    
    def route_after_selection(self, state: TrendFindingState) -> str:
        """Route after processing user's category selection"""
        if state.get("error_message"):
            return "END"
            
        # If user is satisfied with results, end the workflow
        if state.get("is_satisfied", False):
            return "END"
            
        # If categories were successfully selected, proceed to results
        if state.get("selected_categories"):
            return "show_results"
        
        # If no valid selection was made, go back to category analysis
        return "analyze_categories"
    
    def route_after_satisfaction(self, state: TrendFindingState) -> str:
        """Route after satisfaction review"""
        if state.get("error_message"):
            return "END"
            
        # If user is satisfied, end the workflow
        if state.get("is_satisfied", False):
            return "END"
            
        # If not satisfied, go back to category selection
        return "analyze_categories"
        
    def validate_location(self, state: TrendFindingState):
        """Validate and set location from user input"""
        state = self.update_step(state, "location_validation")
        
        user_input = state["user_input"]
        
        # Extract location from user input - now expects direct location input
        location_to_check = extract_location_from_message(user_input)
        if not location_to_check:
            # Default to global if no location provided or empty input
            location_to_check = "global"
        
        location_lower = location_to_check.lower()
        
        # Valid location - proceed to fetch trends
        if location_lower in COUNTRY_MAPPING:
            state["location"] = COUNTRY_MAPPING[location_lower]
            return state
        
        # Try using Gemini to interpret the location
        gemini_location = interpret_location_with_gemini(location_to_check, COUNTRY_MAPPING)
        if gemini_location:
            state["location"] = COUNTRY_MAPPING[gemini_location]
            state["raw_location_input"] = location_to_check
            state["interpreted_location"] = gemini_location
            return state
        
        # If Gemini can't interpret, fall back to fuzzy matching
        suggested_countries = find_closest_countries(location_to_check)
        location_options = suggested_countries + ["Global", "United States", "United Kingdom"]
        seen = set()
        location_options = [x for x in location_options if not (x in seen or seen.add(x))]
        
        # Set error message with suggested countries and end workflow
        state["error_message"] = f"Location '{location_to_check}' not found. Did you mean one of these?\n\n" + \
                                 "\n".join([f"• {option}" for option in location_options[:5]]) + \
                                 f"\n\nPlease try again with: `/trends <location>`"
        state["workflow_status"] = "error"
        
        return state
    
    def fetch_trends(self, state: TrendFindingState):
        """Fetch trending topics using the tool directly"""
        state = self.update_step(state, "trend_fetching")
        
        location = state.get("location", "global")
        
        try:
            trend_results = get_trending_topics.invoke({"city_code": location})
            
            # Store trend data
            if isinstance(trend_results, list):
                state["trend_data"] = trend_results
            elif isinstance(trend_results, dict):
                state["trend_data"] = [trend_results]
            else:
                state["trend_data"] = []
        
            return state
            
        except Exception as e:
            state["error_message"] = f"Error fetching trends: {str(e)}"
            state["workflow_status"] = "error"
            return state
    
    
    
    def analyze_categories(self, state: TrendFindingState):
        """Analyze trend data and populate categories"""
        state = self.update_step(state, "category_analysis")
        
        trend_data = state.get("trend_data", [])
        
        if not trend_data:
            state["error_message"] = "No trending data found. Please try a different location."
            state["workflow_status"] = "error"
            return state
        
        # Get distinct categories
        all_categories = set()
        for item in trend_data:
            if isinstance(item, dict) and 'category' in item and item['category']:
                all_categories.add(item['category'])
        
        distinct_categories = sorted(list(all_categories))
        
        if not distinct_categories:
            state["error_message"] = "No categories found in trending data."
            state["workflow_status"] = "error"
            return state
        
        state["categories"] = distinct_categories
        
        # Note: We no longer create an interrupt here as that's handled by process_category_selection
        return state
    
    def show_results(self, state: TrendFindingState):
        """Show filtered results based on selected categories"""
        state = self.update_step(state, "result_display")
        
        # Get selected categories from resumed input
        # This will be populated when the workflow is resumed
        trend_data = state.get("trend_data", [])
        selected_categories = state.get("selected_categories", [])
        
        # If we don't have selected categories yet, try to get them from the resume input
        if not selected_categories:
            # This happens when the workflow is resumed after category selection
            # The selected category will be in the user_input or we use all categories
            user_selection = state.get("user_input", "")
            if user_selection and user_selection != "all":
                selected_categories = [user_selection]
            else:
                # Use all categories as fallback
                selected_categories = state.get("categories", [])
        
        if selected_categories:
            # Filter trends by selected categories
            filtered_trends = [
                item for item in trend_data
                if item.get("category") in selected_categories
            ]
        else:
            filtered_trends = trend_data
        
        if not filtered_trends:
            state["error_message"] = "No trending topics found for your selected categories."
            state["workflow_status"] = "error"
            return state
        
        # Group by category for better presentation
        trends_by_category = defaultdict(list)
        for item in filtered_trends:
            trends_by_category[item.get("category", "Unknown")].append(item)
        
        # Format results for display
        trend_sections = []
        for category, items in trends_by_category.items():
            top_items = items[:10]  # Limit per category
            item_list = "\n".join([f"  • {item.get('keyword', 'Unknown')}" for item in top_items])
            trend_sections.append(f"**{category}** ({len(items)} topics):\n{item_list}")
        
        trends_content = "\n\n".join(trend_sections)
        
        state["trends_summary"] = trends_content
        
        return state
    
    def get_interrupt_config(self, interrupt_type: str) -> Dict[str, Any]:
        """Return UI configuration for trend finding workflow interrupt types"""
        configs = {
            "location_selection": {
                "emoji": "🌍",
                "title": "Location Selection",
                "button_emoji": "📍",
                "max_per_row": 2,
                "utility_buttons": [
                    {"text": "✏️ Type Custom Location", "data": "custom_location"},
                    {"text": "❌ Cancel", "data": "cancel"}
                ]
            },
            "category_selection": {
                "emoji": "📊", 
                "title": "Category Selection",
                "button_emoji": "",
                "max_per_row": 2,
                "utility_buttons": [
                    {"text": "🔄 All Categories", "data": "all"},
                    {"text": "❌ Cancel", "data": "cancel"}
                ]
            },
            "satisfaction_review": {
                "emoji": "✅",
                "title": "Trending Topics Found",
                "button_emoji": "",
                "max_per_row": 1,
                "utility_buttons": [
                    {"text": "❌ Cancel", "data": "cancel"}
                ],
                "content_fields": ["trends_summary"]  # Specify which fields to include in the message
            }
        }
        return configs.get(interrupt_type, super().get_interrupt_config(interrupt_type))

# Create workflow instance
trend_workflow = TrendFindingWorkflow()


