import random
import asyncio
import logging
import numpy as np
import json
import hashlib
import os
from pathlib import Path
from google.genai import types
from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional
# Add this import
from src.utils.env_loader import load_environment
# Update this import
from src.utils.gemini_client import get_client
from src.utils.config_loader import get_config
from src.utils.resource_path import get_app_data_dir  # Add this import


# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_environment()

# Cache directory for analyzed screenshots
CACHE_DIR = Path(get_app_data_dir()) / "screenshot_analysis_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Delay functions
async def add_random_delays(min_seconds, max_seconds, logger=None):
    """
    Add a random delay between actions to simulate human behavior.
    
    Args:
        min_seconds (int): Minimum delay in seconds
        max_seconds (int): Maximum delay in seconds
        logger: Optional logger instance
    """
    delay = random.uniform(min_seconds, max_seconds)
    if logger:
        logger.info(f"Adding random delay of {delay:.2f} seconds")
    await asyncio.sleep(delay)  # Use asyncio.sleep instead of time.sleep


async def add_delay(seconds, logger=None):
    """
    Add a fixed delay between actions.
    
    Args:
        seconds (int): Delay in seconds
        logger: Optional logger instance
    """
    if logger:
        logger.info(f"Adding fixed delay of {seconds} seconds")
    await asyncio.sleep(seconds)  # Use asyncio.sleep instead of time.sleep


# Mouse movement simulation
async def simulate_human_mouse_movement(page, target_x, target_y, current_mouse_x=0, current_mouse_y=0, steps=10):
    """Simulate human-like mouse movement with acceleration and deceleration.
    
    Args:
        page: Playwright page object
        target_x: Target X coordinate
        target_y: Target Y coordinate
        current_mouse_x: Current mouse X position
        current_mouse_y: Current mouse Y position
        steps: Number of steps for the movement
        
    Returns:
        tuple: The new mouse position (x, y)
    """
    # Use provided current position
    start_x, start_y = current_mouse_x, current_mouse_y
    
    # Calculate distance
    distance_x = target_x - start_x
    distance_y = target_y - start_y
    
    # Add slight randomness to the target position
    target_x += random.randint(-5, 5)
    target_y += random.randint(-5, 5)
    
    # Simulate human-like movement with acceleration and deceleration
    for i in range(steps):
        # Non-linear interpolation for more natural movement
        progress = i / steps
        ease_factor = 3 * (progress ** 2) - 2 * (progress ** 3)  # Ease in-out cubic
        
        current_x = start_x + distance_x * ease_factor
        current_y = start_y + distance_y * ease_factor
        
        # Add slight jitter
        jitter_x = random.randint(-2, 2) if i > 0 and i < steps-1 else 0
        jitter_y = random.randint(-2, 2) if i > 0 and i < steps-1 else 0
        
        await page.mouse.move(current_x + jitter_x, current_y + jitter_y)
        await asyncio.sleep(random.uniform(0.01, 0.03))  # Random delay between movements
    
    # Final move to exact target
    await page.mouse.move(target_x, target_y)
    
    # Return the new position
    return target_x, target_y


# Typing functions
async def type_humanlike(page, element, text, min_delay=0.02, max_delay=0.1, logger=None):
    """
    Type text into an element with human-like timing variations.
    
    Args:
        page: Playwright page object
        element: The Playwright element to type into
        text: The text to type
        min_delay: Minimum delay between keystrokes in seconds
        max_delay: Maximum delay between keystrokes in seconds
        logger: Optional logger instance
    """
    # Clear the element first
    await element.fill("")  # Clear any existing text
    
    # Focus on the element
    await element.focus()
    
    # Type each character with a random delay
    for char in text:
        # Type the character
        await page.keyboard.type(char)
        
        # Add a random delay between keystrokes
        typing_delay = random.uniform(min_delay, max_delay)
        
        # Add slightly longer delays for certain characters to simulate thinking
        if char in ['.', ',', '!', '?', ' ']:
            typing_delay *= 1.5  # Longer pause after punctuation or spaces
        
        await asyncio.sleep(typing_delay)
    
    # Log the typing action
    if logger:
        logger.info(f"Typed '{text}' with human-like timing variations")


async def type_and_send_message(page, message_input, text, auto_send=True, min_delay=0.05, max_delay=0.25, logger=None):
    """Type a message with human-like timing and optionally send it.
    
    Args:
        page: Playwright page object
        message_input: The Playwright element to type into
        text: The text to type
        auto_send: Whether to automatically send the message or wait for manual sending
        min_delay: Minimum delay between keystrokes in seconds
        max_delay: Maximum delay between keystrokes in seconds
        logger: Optional logger instance
        
    Returns:
        bool: True if message was sent successfully
    """
    # Type the message with human-like timing
    await type_humanlike(page, message_input, text, min_delay, max_delay, logger)
    
    # Add a natural pause after typing (as if reviewing the message)
    await add_random_delays(0.5, 2.0, logger)
    
    if auto_send:
        # Send the message by pressing Enter
        await page.keyboard.press('Enter')
        if logger:
            logger.info(f"Automatically sent message: '{text}'")
        # Add a delay after sending
        await add_random_delays(1.0, 3.0, logger)
        return True
    else:
        # Prompt for manual confirmation in Python console
        if logger:
            logger.info(f"Message typed: '{text}'. Waiting for confirmation in console...")
        print(f"\n===========================================================")
        print(f"MESSAGE READY: '{text}'")
        print(f"Press Enter in this console to send the message...")
        print(f"==========================================================\n")
        
        # Wait for user input in the console
        input("Press Enter to confirm sending...")
        
        # Send the message programmatically after confirmation
        await page.keyboard.press('Enter')
        if logger:
            logger.info(f"Message sent after manual confirmation: '{text}'")
        
        # Add a delay after sending
        await add_random_delays(1.0, 3.0, logger)
        return True


def get_screenshot_hash(screenshot_path):
    """Generate a hash for the screenshot to use as cache key."""
    with open(screenshot_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

    # Add this model definition after the imports (around line 20)
class InstagramProfileAnalysis(BaseModel):
    """Simple model for Instagram profile analysis"""
    account_niche: str
    account_type: str  # "brand" or "personal"
    noteworthy_elements: List[str]

async def analyze_instagram_screenshot(screenshot_path, logger=None):
    """
    Analyze Instagram screenshot using Gemini to extract post information.
    
    Args:
        screenshot_path: Path to the screenshot image
        logger: Optional logger instance
        
    Returns:
        dict: Analysis results containing posts, captions, and hooks
    """
    # Check cache first
    screenshot_hash = get_screenshot_hash(screenshot_path)
    cache_file = CACHE_DIR / f"{screenshot_hash}_analysis.json"
    
    if cache_file.exists():
        if logger:
            logger.info(f"Using cached analysis for screenshot: {screenshot_path}")
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    try:
        # Read screenshot
        with open(screenshot_path, 'rb') as f:
            image_bytes = f.read()
        
        # Analyze screenshot with Gemini
        analysis_prompt = """
        Analyze this Instagram profile screenshot and extract only the following information:
        
        1. The primary niche or category of the Instagram account
        2. Whether this is a brand account or personal account
        3. Specific noteworthy elements that would be worth mentioning in a personalized message
        
        Return the analysis in this JSON format:
        {
            "account_niche": "brief description of the account's primary category/niche",
            "account_type": "brand" or "personal",
            "noteworthy_elements": ["element1", "element2", "element3"]
        }
        
        For the account_niche, provide a concise description like "fitness", "travel photography", "food blogging", etc.
        
        For account_type, use these specific visual indicators to determine if this is a brand/business account or a personal/individual account:
        
        Brand/Business Account indicators:
        - Presence of a contact button or email address
        - Category label under the profile name (e.g., "Clothing Brand", "Restaurant")
        - Professional logo as profile picture instead of a person
        - Use of branded hashtags
        - Consistent visual style/theme across posts
        - Product-focused content
        - Shopping tags or product links
        - Business metrics mentioned (if visible)
        
        Personal Account indicators:
        - Person's face as profile picture
        - Personal narrative in bio (using "I" or "my")
        - Casual, varied content style
        - Personal life moments/selfies
        - Informal language
        - Fewer structured calls-to-action
        - Friends/family in photos
        - Personal achievements or activities
        
        If multiple indicators from both categories are present, determine the dominant type based on the overall presentation and content focus.
        
        For noteworthy_elements, include 2-3 specific aspects that would make a message sound researched and personalized,
        without identifying exact posts. These could be content themes, visual styles, recurring topics, or unique approaches.
        
        If no clear content is visible, return empty values.
        """
    
        
        # Replace the existing generate_content call (around line 293-302) with this:
        response = get_client().models.generate_content(
            model='gemini-2.0-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type='image/jpeg',
                ),
                analysis_prompt
            ],
            config={
                'response_mime_type': 'application/json',
                'response_schema': InstagramProfileAnalysis,
            }
        )
        
        # Get the structured analysis
        analysis_result = response.parsed
        
        # Parse JSON response
        try:
            analysis_result = json.loads(response.text)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            analysis_result = {
                "posts": [],
                "profile_tone": "casual",
                "main_topics": []
            }
        
        # Cache the result
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_result, f, indent=2)
        
        if logger:
            logger.info(f"Analyzed screenshot and cached result: {len(analysis_result.get('posts', []))} posts found")
        
        return analysis_result
        
    except Exception as e:
        if logger:
            logger.error(f"Error analyzing screenshot with Gemini: {str(e)}")
        # Return empty result on error
        return {
            "posts": [],
            "profile_tone": "casual",
            "main_topics": []
        }

async def generate_personalized_message(analysis_result, logger=None):
    """
    Generate a personalized Instagram message based on screenshot analysis.
    
    Args:
        analysis_result: Result from analyze_instagram_screenshot (InstagramProfileAnalysis)
        profile_url: Optional profile URL for context
        logger: Optional logger instance
        
    Returns:
        str: Generated personalized message
    """
    # Get data from the InstagramProfileAnalysis model
    account_niche = analysis_result["account_niche"]
    noteworthy_elements = analysis_result["noteworthy_elements"]
        
    config = get_config()
    
    # Get the custom template or use the default if not found
    message_template = config.get('instagram_message_workflow', {}).get('message_template', None)
    
    # Format the template with the actual values
    message_template = message_template.format(
        account_niche=account_niche,
        noteworthy_elements=', '.join(noteworthy_elements)
    )
    
    # Create message generation prompt
    message_prompt = message_template
    
    response = get_client().models.generate_content(
        model='gemini-2.0-flash',
        contents=[message_prompt]
    )
    
    generated_message = response.text.strip()
    
    if logger:
        logger.info(f"Generated personalized message: {generated_message[:50]}...")
    
    return generated_message