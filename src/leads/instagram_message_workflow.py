from typing import TypedDict, Optional, Dict, Any, List, Callable
import csv
import asyncio
import logging
import os
from pathlib import Path
from src.utils.env_loader import load_environment
from datetime import datetime
from src.utils.db_client import get_db_context
from src.utils.config_loader import get_config

# Use only load_environment()
load_environment()
from playwright.async_api import async_playwright
from src.base_workflow import BaseWorkflow, BaseWorkflowState, InterruptConfig, check_cancellation
from langgraph.graph import END
import hashlib
import yaml
from src.leads.instagram_automator_helpers import CACHE_DIR
CACHE_DIR.mkdir(exist_ok=True)

# Import helper functions
from src.leads.instagram_automator_helpers import (
    add_random_delays, add_delay, simulate_human_mouse_movement,
    detect_message_button, type_humanlike, analyze_instagram_screenshot,
    generate_personalized_message
)


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def validate_login_confirmation(user_input: str, context: Dict) -> Dict[str, Any]:
    """Validate login confirmation input"""
    if user_input.lower() in ["yes", "y", "yes, i've logged in"]:
        return {"valid": True, "confirmed": True}
    elif user_input.lower() in ["no", "n", "cancel"]:
        return {"valid": True, "confirmed": False}
    else:
        return {
            "valid": False,
            "error_message": "Please confirm with 'Yes' or cancel with 'No'"
        }

class InstagramMessageState(BaseWorkflowState):
    """State for Instagram messaging workflow"""
    user_input: str  # User input from BaseWorkflowState
    csv_path: Optional[str]  # Path to CSV file with profiles
    delay: Optional[int]  # Delay between messages
    max_profiles: Optional[int]  # Maximum profiles to message
    automation_result: Optional[dict]  # Result from automation
    screenshot_path: Optional[str]  # Path to current screenshot
    current_profile_url: Optional[str]  # Current profile being processed
    message_text: Optional[str]  # Message to be sent
    message_confirmed: Optional[bool] = None  # Confirmation status for message
    message_sent: Optional[bool] = None  # Sent status for message
    processed: int = 0  # Number of profiles processed
    successful: int = 0  # Number of profiles successfully messaged

class InstagramMessageAutomator:
    def __init__(self, csv_path, headless=False, workflow_instance=None):
        """
        Initialize the Instagram Message Automator.
        
        Args:
            csv_path (str): Path to the CSV file containing Instagram profiles
            headless (bool): Run browser in headless mode
            workflow_instance: Reference to the workflow for interrupts
        """
        self.csv_path = Path(csv_path)
        self.headless = headless
        self.profiles = []
        self.browser = None
        self.page = None
        self.logger = logger  # Initialize logger attribute
        self.current_mouse_x = 0
        self.current_mouse_y = 0
        self.workflow = workflow_instance  # Store workflow reference
        
    async def setup(self, playwright):
        """Set up the Playwright browser instance with a persistent context."""
        # Use the provided playwright instance
        self.playwright = playwright
        
        # Use a persistent context to maintain cookies and session data
        user_data_dir = Path.home() / ".playwright-instagram-data"
        self.browser = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-infobars',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--hide-scrollbars',
                '--mute-audio'
            ],
            viewport={'width': 600, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
            color_scheme='light',
            device_scale_factor=0.3,
            is_mobile=False
        )
        
        self.page = await self.browser.new_page()
        
        # Add additional headers
        await self.page.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br'
        })
        
    async def login(self, state):
        """Log in to Instagram manually with user interaction via LangGraph interrupt."""
        try:
            # Navigate to Instagram login page
            await self.page.goto("https://www.instagram.com/accounts/login/")
            
            # Take a screenshot for the UI
            screenshot_path = "temp_screenshot.png"
            await self.page.screenshot(path=screenshot_path)
            state["screenshot_path"] = screenshot_path
            
            self.logger.info("Please log in to Instagram manually in the browser window.")
            
            # Return state to be used by the login_confirmation node
            return state
                
        except Exception as e:
            self.logger.error(f"Failed to log in to Instagram: {str(e)}")
            state["error_message"] = f"Failed to log in to Instagram: {str(e)}"
            state["workflow_status"] = "error"
            return state
            
    def load_profiles(self):
        """Load Instagram profiles from the CSV file."""
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                # Filter out profiles that have skip=true or skip=True
                self.profiles = [row for row in reader if row.get('profile_url') and 
                                not (row.get('skip') == 'true' or row.get('skip') == 'True' or row.get('skip') is True)]
                
            self.logger.info(f"Loaded {len(self.profiles)} profiles from {self.csv_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load profiles from CSV: {str(e)}")
            return False
            
    async def find_message_button_visual(self):
        # Capture screenshot of the current page
        screenshot_path = "temp_screenshot.png"
        await self.page.screenshot(path=screenshot_path)
        
        # Process the screenshot to find the message button
        message_button_coords = detect_message_button(screenshot_path)
        
        if message_button_coords:
            # Click at the detected coordinates
            await self.page.mouse.click(message_button_coords[0], message_button_coords[1])
            return True
        return False
            
    async def analyze_profile(self, profile_url, state):
        """Analyze an Instagram profile and determine if it's suitable for messaging."""
        try:
            # Check if this profile has been messaged before
            already_messaged = await check_if_profile_messaged(profile_url)
            if already_messaged:
                self.logger.info(f"Skipping {profile_url} as it has been messaged before")
                state["current_profile_url"] = None
                return False, state
                
            # Navigate to the profile
            await self.page.goto(profile_url)
            await add_random_delays(1, 3, self.logger)
            
            # Store current profile URL in state
            state["current_profile_url"] = profile_url
            
            # Create a URL-based filename for the screenshot
            url_hash = hashlib.md5(profile_url.encode()).hexdigest()
            screenshot_path = os.path.join(CACHE_DIR, f"{url_hash}_screenshot.png")
            
            await self.page.screenshot(path=screenshot_path)

            # Step 1: Analyze screenshot
            analysis_result = await analyze_instagram_screenshot(screenshot_path, self.logger)
            
            # Check if this is a personal account and skip if it is
            if analysis_result.get("account_type", "").lower() == "personal":
                self.logger.info("Skipping personal account")
                state["current_profile_url"] = None
                return False, state
                
            # Step 2: Generate personalized message only for brand accounts
            personalized_message = await generate_personalized_message(analysis_result, self.logger)
            
            # Store the generated message in state
            state["message_text"] = personalized_message
            state["analysis_result"] = analysis_result
            state["screenshot_path"] = screenshot_path
            
            return True, state
            
        except Exception as e:
            self.logger.error(f"Error in analyze_profile: {str(e)}")
            return False, state
    
    async def prepare_and_type_message(self, state):
        """Find message button and type the personalized message."""
        try:
            if not state.get("message_text") or not state.get("current_profile_url"):
                self.logger.error("Missing required state information for messaging")
                return False, state
                
            personalized_message = state["message_text"]
            
            # Try DOM-based approach first
            selectors = [
                "div[role='button'][tabindex='0']:has-text('Message')",
                "button:has-text('Message')",
                "a[role='button']:has-text('Message')",
            ]
            
            message_button = None
            for selector in selectors:
                try:
                    message_button = await self.page.query_selector(selector)
                    if message_button:
                        break
                except Exception:
                    continue
            
            # If DOM-based approach fails, try vision-based approach
            if not message_button:
                success = await self.find_message_button_visual()
                if not success:
                    self.logger.error("Could not find message button using either method")
                    return False, state
            else:
                # Get button position and move mouse
                bounding_box = await message_button.bounding_box()
                if bounding_box:
                    target_x = bounding_box['x'] + bounding_box['width'] / 2
                    target_y = bounding_box['y'] + bounding_box['height'] / 2
                    
                    # Use helper function directly
                    self.current_mouse_x, self.current_mouse_y = await simulate_human_mouse_movement(
                        self.page, target_x, target_y, self.current_mouse_x, self.current_mouse_y
                    )
                    await self.page.mouse.click(target_x, target_y)
            
            # Wait for message textarea to appear
            try:
                # Try multiple selectors with fallback logic
                message_input = None
                selectors = [
                    "div[contenteditable='true'][aria-label*='Message']",
                    "input[placeholder*='Message']",
                    "[role='textbox']",
                    "[contenteditable='true']"
                ]
                
                for selector in selectors:
                    try:
                        self.logger.info(f"Trying to find message input with selector: {selector}")
                        message_input = await self.page.wait_for_selector(selector, timeout=5000)
                        if message_input:
                            self.logger.info(f"Found message input with selector: {selector}")
                            break
                    except Exception as e:
                        self.logger.info(f"Selector {selector} failed: {str(e)}")
                        continue
                
                if not message_input:                    
                    raise Exception("All selectors failed to find message input")
                    
                self.logger.info("Successfully opened message dialog")
                # Reduce the delay to prevent timeout issues
                await add_delay(2, self.logger)
                
                # Take a screenshot for the UI
                screenshot_path = "temp_screenshot.png"
                await self.page.screenshot(path=screenshot_path)
                state["screenshot_path"] = screenshot_path
                
                # Re-check if the element is still attached before interacting
                try:
                    # Alternative way to check if element is attached
                    bounding_box = await message_input.is_visible()
                    is_visible = bounding_box is not None
                    self.logger.info(f"Message input visibility (via bounding box): {is_visible}")
                    
                    await type_humanlike(self.page, message_input, personalized_message, 0.05, 0.25, self.logger)
                    
                    # Add a natural pause after typing (as if reviewing the message)
                    await add_random_delays(0.5, 2.0, self.logger)
                    
                    # Take a screenshot after typing the message
                    screenshot_path = "temp_screenshot.png"
                    await self.page.screenshot(path=screenshot_path)
                    state["screenshot_path"] = screenshot_path
                    
                    # Return state for message confirmation interrupt
                    return True, state
                    
                except Exception as e:
                    self.logger.error(f"Element interaction failed: {str(e)}")
                    state["error_message"] = f"Element interaction failed: {str(e)}"
                    return False, state

            except Exception as e:
                self.logger.error(f"Failed to find message textarea: {str(e)}")
                await self.page.go_back()
                return False, state
        except Exception as e:
            self.logger.error(f"Error in prepare_and_type_message: {str(e)}")
            return False, state
            
    
    async def send_message(self, state):
        """Send the message after confirmation"""
        try:
            # Send the message programmatically after confirmation
            await self.page.keyboard.press('Enter')
            self.logger.info(f"Message sent after confirmation: '{state.get('message_text')}'")
            
            # Record the sent message in the database
            profile_url = state.get("current_profile_url")
            message_text = state.get("message_text")
            if profile_url and message_text:
                await record_sent_message(profile_url, message_text)
                
            # Add a delay after sending
            await add_random_delays(1.0, 3.0, self.logger)            
            await add_delay(2, self.logger)  # Final delay before going back
            await self.page.go_back()
            return True
        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}")
            return False
            
    async def run(self, state, delay=5, max_profiles=None):
        """Run the automation process."""
        async with async_playwright() as playwright:
            try:
                if not self.load_profiles():
                    state["error_message"] = "Failed to load profiles from CSV"
                    state["workflow_status"] = "error"
                    return state
                    
                await self.setup(playwright)
                
                # Login with interrupt for confirmation
                state = await self.login(state)
                if state.get("error_message"):
                    return state
                
                # Process will continue after login confirmation in the workflow
                        
                # Process profiles
                processed = 0
                successful = 0
                
                profiles_to_process = self.profiles
                if max_profiles:
                    profiles_to_process = self.profiles[:max_profiles]
                    
                for profile in profiles_to_process:
                    processed += 1
                    
                    # Process each profile with interrupts for confirmation
                    success, updated_state = await self.analyze_profile(profile['profile_url'], state)
                    state.update(updated_state)  # Update state with any changes
                    
                    if success:
                        # The message is ready to be sent, but we need confirmation
                        # This will be handled by the message_confirmation node
                        # After confirmation, send_message will be called
                        return state
                    
                    # If we reach here, there was an error with this profile
                    continue
                        
                self.logger.info(f"Completed processing {processed} profiles. Successfully messaged: {successful}")
                state["automation_result"] = {
                    "success": True,
                    "processed": processed,
                    "successful": successful,
                    "message": f"Successfully processed {processed} profiles. Successfully messaged: {successful}"
                }
                state["workflow_status"] = "completed"
                return state
            except Exception as e:
                error_msg = f"Error in Instagram messaging: {str(e)}"
                self.logger.error(error_msg)
                state["error_message"] = error_msg
                state["workflow_status"] = "error"
                return state
            finally:
                # Ensure browser is properly closed even if exceptions occur
                if self.browser:
                    await self.browser.close()
                # The playwright instance is stopped by the context manager

class InstagramMessageWorkflow(BaseWorkflow):
    """Workflow for sending Instagram messages"""
    
    def _register_interrupt_configs(self) -> Dict[str, InterruptConfig]:
        """Register interrupt configurations for this workflow"""
        return {
            "login_confirmation": InterruptConfig(
                interrupt_type="login_confirmation",
                message="Please confirm Instagram login",
                instructions="Please log in to Instagram in the browser window, then confirm when ready",
                options=["Yes, I've logged in", "Cancel"],
                step_name="login_confirmation",
                validation_fn=validate_login_confirmation,  # Updated to use the standalone function
                state_update_fn=self._update_state_after_login
            ),
            "message_confirmation": InterruptConfig(
                interrupt_type="message_confirmation",
                message="Confirm or edit message",
                instructions="Review the message and confirm when ready to send, or edit it",
                options=["Send message", "Skip this profile", "Edit", "Cancel"],
                step_name="message_confirmation",
                validation_fn=self._validate_message_confirmation,
                state_update_fn=self._update_state_after_message_confirmation
            )
            # Removed edit_confirmation as it's merged with message_confirmation
        }
    
    def _build_custom_interrupt_data(self, state: Dict, config: InterruptConfig) -> Dict[str, Any]:
        """Add custom data to interrupt based on type"""
        if config.interrupt_type == "login_confirmation":
            return {
                "screenshot": state.get("screenshot_path")
            }
        elif config.interrupt_type == "message_confirmation":
            return {
                "screenshot": state.get("screenshot_path"),
                "profile_url": state.get("current_profile_url"),
                "message_text": state.get("message_text")
            }
        return {}
    
    def _validate_login_confirmation(self, user_input: str, context: Dict) -> Dict[str, Any]:
        """Validate login confirmation input"""
        if user_input.lower() in ["yes", "y", "yes, i've logged in"]:
            return {"valid": True, "confirmed": True}
        elif user_input.lower() in ["no", "n", "cancel"]:
            return {"valid": True, "confirmed": False}
        else:
            return {
                "valid": False,
                "error_message": "Please confirm with 'Yes' or cancel with 'No'"
            }
    
    def _build_validation_context(self, state: Dict, config: InterruptConfig) -> Dict[str, Any]:
      """Build validation context for Instagram message workflow"""
      # Include user_input in the validation context
      return {"user_input": state.get("user_input", "")}

    def _update_state_after_login(self, state: Dict, validation_result: Dict) -> Dict:
        """Update state after login confirmation"""
        if validation_result.get("confirmed", False):
            # Continue with the workflow
            return state
        else:
            # User cancelled
            state["error_message"] = "Login cancelled by user"
            state["workflow_status"] = "cancelled"
            return state
    
    def _validate_message_confirmation(self, user_input: str, context: Dict) -> Dict[str, Any]:
        """Validate message confirmation input"""
        if user_input.lower() in ["yes", "y", "send", "send message"]:
            return {"valid": True, "action": "send"}
        elif user_input.lower() in ["no", "n", "skip", "skip this profile"]:
            return {"valid": True, "action": "skip"}
        elif user_input.lower() in ["cancel", "end", "quit", "exit"]:
            return {"valid": True, "action": "cancel"}
        else:
            # Treat any other input as an edited message that needs confirmation
            return {
                "valid": True,
                "action": "edit",  # Changed from "send" to "edit"
                "edited_message": user_input
            }
    
    def _update_state_after_message_confirmation(self, state: Dict, validation_result: Dict) -> Dict:
        """Update state after message confirmation"""
        state["message_confirmed"] = validation_result.get("action")
        
        # Update message_text if an edited message was provided
        if "edited_message" in validation_result:
            state["message_text"] = validation_result["edited_message"]
        
        return state
    
    def get_state_class(self):
        return InstagramMessageState
    
    def define_nodes(self):
        return {
            "extract_parameters": self.extract_parameters,
            "validate_csv": self.validate_csv,
            "initialize_automation": self.initialize_automation,
            "login_confirmation": self.create_human_interaction_node("login_confirmation"),
            "process_profiles": self.process_profiles,
            "message_confirmation": self.create_human_interaction_node("message_confirmation"),
            "prepare_message": self.prepare_message,
            "send_message": self.send_message,
            "skip_profile": self.skip_profile,
            "cancel_workflow": self.cancel_workflow,
            "finalize_automation": self.finalize_automation
        }
    
    def define_edges(self, workflow):
        workflow.add_conditional_edges(
            "extract_parameters",
            self.route_after_extraction,
            {"validate_csv": "validate_csv", "END": END}
        )
        workflow.add_conditional_edges(
            "validate_csv",
            self.route_after_validation,
            {"initialize_automation": "initialize_automation", "END": END}
        )
        workflow.add_edge("initialize_automation", "login_confirmation")
        workflow.add_conditional_edges(
            "login_confirmation",
            self.route_after_login,
            {"process_profiles": "process_profiles", "END": END}
        )
        workflow.add_conditional_edges(
            "process_profiles",
            self.route_after_processing,
            {"message_confirmation": "message_confirmation", "finalize_automation": "finalize_automation", "END": END}
        )
        # Removed edit_confirmation from the workflow
        workflow.add_edge("prepare_message", "send_message")  # Changed to go straight to send_message
        workflow.add_conditional_edges(
            "message_confirmation",
            self.route_after_message_confirmation,
            {"prepare_message": "prepare_message", "cancel_workflow": "cancel_workflow", "skip_profile": "skip_profile","message_confirmation":"message_confirmation"}
        )
        workflow.add_edge("skip_profile", "process_profiles")
        workflow.add_edge("cancel_workflow", "finalize_automation")
        workflow.add_edge("send_message", "process_profiles")
        workflow.add_edge("finalize_automation", END)
    
    def get_entry_point(self) -> str:
        return "extract_parameters"
    
    def extract_parameters(self, state: InstagramMessageState):
        """Extract parameters from config.yaml"""
        state = self.update_step(state, "parameter_extraction")
        
        # Use the CSV file path from the uploads directory
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
        csv_files = []
        
        if os.path.exists(upload_dir):
            csv_files = [os.path.join(upload_dir, f) for f in os.listdir(upload_dir) if f.endswith(".csv")]
        
        if csv_files:
            # Use the most recent CSV file from uploads directory
            csv_path = max(csv_files, key=os.path.getctime)
        else:
            # No uploaded CSV file found
            csv_path = None
            state["error_message"] = "No uploaded CSV file found. Please upload a CSV file with Instagram profiles."
        
        try:
            config = get_config()
                
            # Get default values from config
            instagram_config = config.get('instagram_message_workflow', {})
            delay = instagram_config.get('default_delay', 5)
            max_profiles = instagram_config.get('default_max_profiles', 10)
        except Exception as e:
            logger.error(f"Error loading configuration: {str(e)}")
            # Fallback to default values if config loading fails
            delay = 5
            max_profiles = 10
        
        state["csv_path"] = csv_path
        state["delay"] = delay
        state["max_profiles"] = max_profiles
        
        logger.info(f"Extracted CSV: {csv_path}, delay: {delay}, max: {max_profiles}")
        
        return state
    
    def route_after_extraction(self, state: InstagramMessageState) -> str:
        """Route after parameter extraction"""
        if state.get("csv_path"):
            return "validate_csv"
        else:
            state["error_message"] = "No CSV file found. Please upload a CSV file with Instagram profiles."
            state["workflow_status"] = "error"
            return "END"
    
    def validate_csv(self, state: InstagramMessageState):
        """Validate the CSV file exists and has required columns"""
        state = self.update_step(state, "csv_validation")
        
        csv_path = state.get("csv_path")
        
        try:
            import pandas as pd
            df = pd.read_csv(csv_path)
            
            # Check for required columns
            required_columns = ["profile_url"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                state["error_message"] = f"CSV missing required columns: {missing_columns}"
                state["workflow_status"] = "error"
            else:
                logger.info(f"CSV validated successfully with {len(df)} profiles")
                
        except Exception as e:
            state["error_message"] = f"Error validating CSV: {str(e)}"
            state["workflow_status"] = "error"
        
        return state
    
    def route_after_validation(self, state: InstagramMessageState) -> str:
        """Route after CSV validation"""
        if state.get("error_message"):
            return "END"
        else:
            return "initialize_automation"
    
    async def initialize_automation(self, state: InstagramMessageState):
        """Initialize the Instagram message automator"""
        state = self.update_step(state, "automation_initialization")
        
        try:
            # Store the playwright instance at the class level so it stays alive
            self.playwright = await async_playwright().start()
            
            # Create automator instance with reference to this workflow
            self.automator = InstagramMessageAutomator(
                csv_path=state.get("csv_path"),
                headless=False,  # Keep visible for Instagram
                workflow_instance=self
            )
            
            # Load profiles
            if not self.automator.load_profiles():
                state["error_message"] = "Failed to load profiles from CSV"
                state["workflow_status"] = "error"
                return state
            
            # Setup browser without using a context manager
            await self.automator.setup(self.playwright)
            
            # Navigate to Instagram login page
            await self.automator.page.goto("https://www.instagram.com/accounts/login/")
            
            # Take a screenshot for the UI
            screenshot_path = "temp_screenshot.png"
            await self.automator.page.screenshot(path=screenshot_path)
            state["screenshot_path"] = screenshot_path
            
            self.automator.logger.info("Please log in to Instagram manually in the browser window.")
            
            return state
        
        except Exception as e:
            error_msg = f"Error initializing automation: {str(e)}"
            logger.error(error_msg)
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
            
            # Clean up resources if there's an error
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
            
            return state
    
    def route_after_login(self, state: InstagramMessageState) -> str:
        """Route after login confirmation"""
        if state.get("error_message") or state.get("workflow_status") == "cancelled":
            return "END"
        else:
            return "process_profiles"
    
    async def process_profiles(self, state: InstagramMessageState):
        """Process the next profile or finalize if done"""
        state = self.update_step(state, "profile_processing")
        
        # Check if we're continuing after sending a message
        if state.get("message_sent"):
            # Clear the flag and continue with the next profile
            state["message_sent"] = None  # Changed from state.pop("message_sent", None)
            
            # Update counters
            processed = state.get("processed", 0) + 1
            successful = state.get("successful", 0) + 1
            state["processed"] = processed
            state["successful"] = successful
            
            # Check if we've processed all profiles
            max_profiles = state.get("max_profiles", 10)
            if processed >= max_profiles:
                # We're done
                return state
        
        # If we have a current profile, return the state as is
        if state.get("current_profile_url") is not None:
            return state
    
        # Process the next profile
        profiles_to_process = self.automator.profiles
        max_profiles = state.get("max_profiles", 10)
        processed = state.get("processed", 0)
        
        # Check if there are more profiles to process
        if processed < len(profiles_to_process) and processed < max_profiles:
            profile = profiles_to_process[processed]
            
            # Process the profile with interrupts for confirmation
            success, updated_state = await self.automator.analyze_profile(profile['profile_url'], state)
            state.update(updated_state)  # Update state with any changes
            
            if success:
                # The message is ready to be sent, but we need confirmation
                # This will be handled by the message_confirmation node
                return state
            else:
                # If there was an error with this profile, increment processed count and try next one
                state["processed"] = processed + 1
                return await self.process_profiles(state)  # Recursively process next profile
        else:
            # We're done or there was an error
            state["automation_result"] = {
                "success": True,
                "processed": state.get("processed", 0),
                "successful": state.get("successful", 0),
                "message": f"Successfully processed {state.get('processed', 0)} profiles. Successfully messaged: {state.get('successful', 0)}"
            }
            state["workflow_status"] = "completed"
            return state
    
    def route_after_processing(self, state: InstagramMessageState) -> str:
        """Route after processing a profile"""
        if state.get("error_message"):
            return "END"
        elif state.get("current_profile_url") is not None and state.get("message_text") is not None:
            # We have a message ready for confirmation
            return "message_confirmation"
        else:
            # We're done with all profiles
            return "finalize_automation"
    
    async def cancel_workflow(self, state: InstagramMessageState):
        """Handle workflow cancellation"""
        state = self.update_step(state, "workflow_cancellation")
        
        # Set cancellation state
        state["workflow_status"] = "cancelled"
        state["automation_result"] = {
            "success": False,
            "processed": state.get("processed", 0),
            "successful": state.get("successful", 0),
            "message": "Workflow cancelled by user"
        }
        
        return state

    async def skip_profile(self, state: InstagramMessageState):
        """Skip the current profile and prepare for the next one"""
        state = self.update_step(state, "profile_skipping")
        
        # Skip this profile and continue
        state["current_profile_url"] = None
        state["message_text"] = None
        state["processed"] = state.get("processed", 0) + 1
        
        return state
    
    def route_after_message_confirmation(self, state: InstagramMessageState) -> str:
        """Route after message confirmation"""
        # Check the action based on message_confirmed value
        if state.get("message_confirmed") == "cancel":
            return "cancel_workflow"  # Route to the new cancel_workflow node
        elif state.get("message_confirmed") == "send":
            return "prepare_message"
        elif state.get("message_confirmed") == "edit":
            # For edited messages, loop back to message_confirmation
            return "message_confirmation"
        else:  # "skip" or any other value
            return "skip_profile"
    

    async def prepare_message(self, state: InstagramMessageState):
        """Prepare and type the message into Instagram DM."""
        state = self.update_step(state, "message_preparation")
        
        # Call the existing prepare_and_type_message method
        success, updated_state = await self.automator.prepare_and_type_message(state)
        state.update(updated_state)  # Update state with any changes
        
        if not success:
            state["error_message"] = "Failed to prepare and type message"
        
        return state
    
    @check_cancellation
    async def send_message(self, state: InstagramMessageState):
        """Send the message after confirmation"""
        state = self.update_step(state, "message_sending")
        
        try:
            # Send the mess
            success = await self.automator.send_message(state)
            
            if success:
                # Mark as sent and clear for next profile
                state["message_sent"] = True
                state["current_profile_url"] = None 
                state["message_text"] = None  
            else:
                # There was an error sending
                state["error_message"] = "Failed to send message"
            
            return state
            
        except Exception as e:
            error_msg = f"Error sending message: {str(e)}"
            logger.error(error_msg)
            state["error_message"] = error_msg
            return state
    
    async def finalize_automation(self, state: InstagramMessageState):
        """Finalize the automation process"""
        state = self.update_step(state, "automation_finalization")
        
        # Ensure we have a result
        if not state.get("automation_result"):
            state["automation_result"] = {
                "success": True,
                "processed": state.get("processed", 0),
                "successful": state.get("successful", 0),
                "message": f"Successfully processed {state.get('processed', 0)} profiles. Successfully messaged: {state.get('successful', 0)}"
            }
        
        # Clean up resources
        try:
            if hasattr(self, 'automator') and self.automator and self.automator.browser:
                await self.automator.browser.close()
            
            if hasattr(self, 'playwright'):
                await self.playwright.stop()
        except Exception as e:
            logger.error(f"Error cleaning up resources: {str(e)}")
        
        state["workflow_status"] = "completed"
        return state


# helper function
async def check_if_profile_messaged(profile_url):
    """Check if a profile has already been messaged"""
    try:
        with get_db_context() as (conn, cursor):
            # Extract username from profile URL
            username = profile_url.split('/')[-2] if profile_url.endswith('/') else profile_url.split('/')[-1]
            
            # Check by both profile URL and username for robustness
            cursor.execute(
                "SELECT * FROM sent_messages WHERE profile_url = ? OR username = ?", 
                (profile_url, username)
            )
            result = cursor.fetchone()
            
            if result:
                return True
            return False
    except Exception as e:
        return False

async def record_sent_message(profile_url, message_text, success=True):
    """Record a sent message in the database"""
    try:
        # Extract username from profile URL
        username = profile_url.split('/')[-2] if profile_url.endswith('/') else profile_url.split('/')[-1]
        
        with get_db_context() as (conn, cursor):
            cursor.execute(
                "INSERT OR REPLACE INTO sent_messages (profile_url, username, message_text, sent_date, success) VALUES (?, ?, ?, ?, ?)",
                (profile_url, username, message_text, datetime.now().isoformat(), 1 if success else 0)
            )
            return True
    except Exception as e:
        return False

async def main():
    # Path to the CSV file
    csv_path = r"c:\Users\Zongjie\Documents\GitHub\content-create-agent\collaboration_opportunities\fitness_instagram_collaborations_20250616_201553.csv"
    
    try:
        # Create the workflow
        workflow = InstagramMessageWorkflow()
        
        # Run the workflow
        result = await workflow.run(f"Send messages using {csv_path} with delay 5 and max 10")
        
        # Handle interrupts and resume workflow
        while result.get("status") == "awaiting_human_input":
            print("\n" + "-"*50)
            print(f"Workflow interrupted: {result.get('message')}")
            print("Data:", result.get("data", {}))
            print("-"*50 + "\n")
            
            # Get user input
            user_input = input("Enter your response (or 'cancel' to stop): ")
            
            # Resume the workflow with user input
            thread_id = result.get("thread_id")
            result = await workflow.resume(user_input, thread_id)
        
        # Print final result
        print("\nWorkflow completed with status:", result.get("status"))
        print(result)
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")


if __name__ == "__main__":
    # Use standard asyncio.run for direct execution
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")