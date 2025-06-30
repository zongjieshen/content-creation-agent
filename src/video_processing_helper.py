import requests
import os
import time
import json
import pandas as pd
import logging
import concurrent.futures
from functools import partial
from google import genai
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import asyncio
import threading

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global semaphore to limit concurrent Gemini API calls
GEMINI_SEMAPHORE = threading.Semaphore(2)  # Allow max 2 concurrent API calls
LAST_API_CALL_TIME = 0
MIN_API_INTERVAL = 1.0  # Minimum 1 second between API calls

# Define simplified Pydantic models for structured output
class VideoAnalysis(BaseModel):
    """Simplified video analysis model focusing on 4 key areas"""
    # Hook analysis
    hook_score: int = Field(description="Hook effectiveness score 1-10")
    hook_type: str = Field(description="Hook technique: question/shock/story/visual")
    hook_works: str = Field(description="Why this hook works/fails in 1 sentence")
    
    # Filming technique
    filming_score: int = Field(description="Filming quality score 1-10") 
    filming_style: str = Field(description="Camera style: closeup/wide/POV/handheld")
    filming_notes: str = Field(description="What filming technique works/fails in 1 sentence")
    
    # Location analysis
    location_score: int = Field(description="Location choice score 1-10")
    location_type: str = Field(description="Location: home/outdoors/studio/car/bedroom")
    location_impact: str = Field(description="Why this location works/fails in 1 sentence")
    
    # Collaboration
    collaboration_score: int = Field(description="Subject presentation score 1-10")
    who_involved: str = Field(description="Who: solo/friends/family/strangers/pets")
    collaboration_effect: str = Field(description="Why this collaboration works/fails in 1 sentence")
    
    # Overall
    overall_score: int = Field(description="Overall performance prediction 1-10")
    biggest_win: str = Field(description="Single biggest success factor")
    biggest_fail: str = Field(description="Single biggest failure factor")

def download_video(url, output_path):
    """Download video from URL to a local file."""
    try:
        #logger.info(f"Attempting to download video from {url} to {output_path}") # <-- Add logging
        response = requests.get(url, stream=True, timeout=60) # <-- Add timeout
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Video downloaded successfully to {output_path}") # <-- Change print to logger.info
        return True
    except requests.exceptions.RequestException as e: # <-- More specific exception
        logger.error(f"Error downloading video from {url}: {str(e)}") # <-- Change print to logger.error
        return False
    except Exception as e:
        logger.error(f"Unexpected error downloading video {url}: {str(e)}", exc_info=True) # <-- Log other errors
        return False

def analyze_video(video_path, performance_category=None):
    """Analyse video using Google Gemini API with performance-aware prompting."""
    global LAST_API_CALL_TIME
    
    try:
        logger.info(f"Analyzing video: {video_path}")
        
        # Acquire semaphore to limit concurrent API calls
        GEMINI_SEMAPHORE.acquire()
        
        try:
            # Rate limiting: ensure minimum interval between API calls
            current_time = time.time()
            time_since_last_call = current_time - LAST_API_CALL_TIME
            if time_since_last_call < MIN_API_INTERVAL:
                sleep_time = MIN_API_INTERVAL - time_since_last_call
                logger.info(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
            
            LAST_API_CALL_TIME = time.time()
            
            # Initialize Gemini client
            client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
            
            # Upload the video file
            logger.info(f"Uploading video file: {video_path}...")
            display_name = os.path.basename(video_path)
            video_file = client.files.upload(
                file=video_path,
                config={
                    "display_name": display_name,
                    "mime_type": "video/mp4"  # Assuming mp4, adjust if needed
                }
            )
            logger.info(f"Uploaded file '{video_file.display_name}' as: {video_file.name}")
            
            # Wait for the file to be processed and become ACTIVE
            logger.info("Waiting for file to become ACTIVE...")
            max_wait_time = 300  # 5 minutes max wait
            start_wait = time.time()
            
            while video_file.state.name == "PROCESSING":
                if time.time() - start_wait > max_wait_time:
                    logger.error(f"File processing timeout after {max_wait_time} seconds")
                    return None
                    
                logger.info("File is still PROCESSING. Waiting 5 seconds...")
                time.sleep(5)  # Wait for 5 seconds
                video_file = client.files.get(name=video_file.name)  # Fetch the latest file state
                logger.info(f"Current state: {video_file.state.name}")
            
            if video_file.state.name == "ACTIVE":
                logger.info(f"File '{video_file.name}' is now ACTIVE and ready for use.")
                
                # Create simplified performance-specific prompt
                if performance_category == "bestperform":
                    context = "🔥 HIGH-PERFORMER: Why does this work?"
                elif performance_category == "worstperform":
                    context = "⚠️ LOW-PERFORMER: Why does this fail?"
                else:
                    context = "📊 ANALYZE: Rate this video's potential"

                # Simplified prompt focusing on 4 key areas
                prompt_parts = [
                    f"""{context}

**ANALYZE 4 KEY AREAS (be brief):**

1. **HOOK (0-3 seconds):** What hook type? (question/shock/story/visual) Score 1-10. Why it works/fails in 1 sentence.

2. **FILMING:** What camera style? (closeup/wide/POV/handheld) Score 1-10. What technique works/fails in 1 sentence.

3. **LOCATION:** Where filmed? (home/outdoors/studio/car/bedroom) Score 1-10. Why this location works/fails in 1 sentence.

4. **WHO:** Who's involved? (solo/friends/family/strangers/pets) Score 1-10. Why this collaboration works/fails in 1 sentence.

**OVERALL:** Performance prediction 1-10. Biggest win + biggest fail.

**BE CONCISE:** One sentence explanations only.
""",
                    video_file
                ]
                
                # Generate content with structured output and retry logic
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        response = client.models.generate_content(
                            model="gemini-1.5-flash",
                            contents=prompt_parts,
                            config={
                                'response_mime_type': 'application/json',
                                'response_schema': VideoAnalysis,
                            }
                        )
                        
                        # Get the structured analysis
                        analysis = response.parsed
                        logger.info(f"Analysis successful for {video_path}")
                        return analysis
                        
                    except Exception as api_error:
                        logger.warning(f"API call attempt {attempt + 1} failed: {str(api_error)}")
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # Exponential backoff
                            logger.info(f"Retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"All API retry attempts failed for {video_path}")
                            return None
                
            elif video_file.state.name == "FAILED":
                error_message = f"File '{video_file.name}' processing FAILED."
                if hasattr(video_file, 'state_reason') and video_file.state_reason:
                    error_message += f" Reason: {video_file.state_reason}"
                logger.error(error_message)
                return None
            else:
                error_message = f"File '{video_file.name}' is in an unexpected state: {video_file.state.name}"
                logger.error(error_message)
                return None
                
        finally:
            # Always release the semaphore
            GEMINI_SEMAPHORE.release()
            
    except Exception as e:
        logger.error(f"Error analysing video {video_path}: {str(e)}", exc_info=True)
        return None

def process_single_video(row, i, total_videos, temp_dir):
    """Process a single video - download and analyze."""
    processed = False
    failed_reason = None
    analysis = None
    
    # Check if analysis already exists and is valid
    if not pd.isna(row.get('analysis')) and row['analysis'] not in ["Analysis failed"]:
        logger.info(f"Video {i+1}/{total_videos}: Skipping - analysis already exists")
        return {
            'index': i,
            'processed': False,
            'skipped_existing': True,
            'skipped_invalid': False,
            'failed_download': False,
            'failed_analysis': False,
            'analysis': row.get('analysis')
        }

    video_url = row.get('video_url')  # Use .get for safety

    # Skip if not a valid URL
    if pd.isna(video_url) or not isinstance(video_url, str) or not video_url.startswith("http"):
        logger.warning(f"Video {i+1}/{total_videos}: Skipping - invalid or missing video URL.")
        return {
            'index': i,
            'processed': False,
            'skipped_existing': False,
            'skipped_invalid': True,
            'failed_download': False,
            'failed_analysis': False,
            'analysis': "Invalid URL"
        }

    logger.info(f"Video {i+1}/{total_videos}: Processing {video_url}")

    # Look for existing video files in the video folder structure
    video_filename = f"video_{row.get('id', i)}.mp4"
    video_path = os.path.join(temp_dir, video_filename)
    
    # Check performance category and look in appropriate subfolder
    performance_category = row.get('performance_category', None)
    if performance_category == 'bestperform':
        subfolder_path = os.path.join(temp_dir, 'bestperform')
    elif performance_category == 'worstperform':
        subfolder_path = os.path.join(temp_dir, 'worstperform')
    else:
        subfolder_path = temp_dir
    
    # Look for existing downloaded video files with various naming patterns
    existing_video = None
    video_id = str(row.get('id', ''))
    author_id = str(row.get('author_uniqueId', ''))
    
    if os.path.exists(subfolder_path):
        for filename in os.listdir(subfolder_path):
            # Check if filename contains the video ID or author info
            if (video_id in filename or 
                (author_id and author_id in filename)):
                existing_video = os.path.join(subfolder_path, filename)
                logger.info(f"Found existing video file: {existing_video}")
                break
    
    # Use existing video if found, otherwise download
    if existing_video and os.path.exists(existing_video):
        video_path = existing_video
        logger.info(f"Video {i+1}/{total_videos}: Using existing video file: {video_path}")
        
        # Analyze the existing video
        logger.info(f"Video {i+1}/{total_videos}: Attempting analysis...")
        analysis = analyze_video(video_path, performance_category)

        if analysis:
            logger.info(f"Video {i+1}/{total_videos}: Analysis successful.")
            processed = True
        else:
            analysis = "Analysis failed"
            logger.warning(f"Video {i+1}/{total_videos}: Analysis failed.")
            failed_reason = "analysis"
        
        return {
            'index': i,
            'processed': processed,
            'skipped_existing': False,
            'skipped_invalid': False,
            'failed_download': False,
            'failed_analysis': failed_reason == "analysis",
            'analysis': analysis,
            'video_path': video_path
        }
    else:
        logger.error(f"Video {i+1}/{total_videos}: Download failed: {video_url}")
        analysis = "Download failed"
        failed_reason = "download"
    
    logger.info(f"Video {i+1}/{total_videos}: Finished processing.")
    
    # Return a dictionary with all the results
    return {
        'index': i,
        'processed': processed,
        'skipped_existing': False,
        'skipped_invalid': False,
        'failed_download': failed_reason == "download",
        'failed_analysis': failed_reason == "analysis",
        'analysis': analysis
    }

def process_videos_for_analysis(df, max_workers=2, output_path=None, video_folder_path=None):
    """Process all videos from DataFrame concurrently and analyze them."""
    # Reduce max_workers to prevent API overload
    max_workers = min(max_workers, 2)  # Cap at 2 to work with semaphore
    logger.info(f"Using {max_workers} workers for video processing")
    
    # Use provided video folder path or default to temp_videos
    if video_folder_path:
        temp_dir = video_folder_path
        logger.info(f"Using provided video folder: {temp_dir}")
    else:
        temp_dir = "temp_videos"
        logger.info(f"Using default temp directory: {temp_dir}")
        
    # Add video_path column to store paths to downloaded videos
    if 'video_path' not in df.columns:
        df['video_path'] = None
    # Add analysis columns if they don't exist
    if 'analysis' not in df.columns:
        df['analysis'] = None
    
    # Simplified analysis component columns
    analysis_columns = [
        'hook_score', 'hook_type', 'hook_works',
        'filming_score', 'filming_style', 'filming_notes',
        'location_score', 'location_type', 'location_impact',
        'collaboration_score', 'who_involved', 'collaboration_effect',
        'overall_score', 'biggest_win', 'biggest_fail'
    ]
    for col in analysis_columns:
        if col not in df.columns:
            df[col] = None
    
    # Process each video
    total_videos = len(df)
    processed_count = 0
    skipped_existing = 0
    skipped_invalid = 0
    failed_download = 0
    failed_analysis = 0

    # Create a partial function with fixed parameters
    process_func = partial(process_single_video, total_videos=total_videos, temp_dir=temp_dir)
    
    # Process videos concurrently using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks = [(row, i) for i, row in df.iterrows()]
        results = list(executor.map(lambda args: process_func(*args), tasks))
        
    # Process results and update DataFrame
    for result in results:
        i = result['index']
        
        # Update DataFrame with results
        analysis = result['analysis']
        if isinstance(analysis, VideoAnalysis):
            # Store simplified analysis data
            df.at[i, 'analysis'] = analysis.json()
            
            # Hook fields
            df.at[i, 'hook_score'] = analysis.hook_score
            df.at[i, 'hook_type'] = analysis.hook_type
            df.at[i, 'hook_works'] = analysis.hook_works
            
            # Filming fields
            df.at[i, 'filming_score'] = analysis.filming_score
            df.at[i, 'filming_style'] = analysis.filming_style
            df.at[i, 'filming_notes'] = analysis.filming_notes
            
            # Location fields
            df.at[i, 'location_score'] = analysis.location_score
            df.at[i, 'location_type'] = analysis.location_type
            df.at[i, 'location_impact'] = analysis.location_impact
            
            # Collaboration fields
            df.at[i, 'collaboration_score'] = analysis.collaboration_score
            df.at[i, 'who_involved'] = analysis.who_involved
            df.at[i, 'collaboration_effect'] = analysis.collaboration_effect
            
            # Overall fields
            df.at[i, 'overall_score'] = analysis.overall_score
            df.at[i, 'biggest_win'] = analysis.biggest_win
            df.at[i, 'biggest_fail'] = analysis.biggest_fail

            # Store the video path if available
            if 'video_path' in result:
                df.at[i, 'video_path'] = result['video_path']
        else:
            # Handle error cases
            df.at[i, 'analysis'] = str(analysis)
            for col in analysis_columns:
                df.at[i, col] = None
        
        # Update counters
        if result['processed']:
            processed_count += 1
        if result['skipped_existing']:
            skipped_existing += 1
        if result['skipped_invalid']:
            skipped_invalid += 1
        if result['failed_download']:
            failed_download += 1
        if result['failed_analysis']:
            failed_analysis += 1

    logger.info(f"Video processing summary: Total={total_videos}, Newly Processed={processed_count}, "
                f"Skipped (Existing)={skipped_existing}, Skipped (Invalid URL)={skipped_invalid}, "
                f"Failed Downloads={failed_download}, Failed Analyses={failed_analysis}")
    
    # Save to CSV with proper encoding
    try:
        if output_path is None:
            output_path = "video_analysis_results.csv"
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        logger.info(f"Successfully saved analysis results to {output_path}")
    except Exception as e:
        logger.error(f"Failed to save results to CSV: {str(e)}")
    
    return df

def generate_overall_summary(df):
    """Generate a focused analysis of top vs worst performing videos."""
    
    try:
        # Check for required columns
        required_columns = ['hook_score', 'filming_score', 'location_score', 'collaboration_score', 'overall_score']
        if not all(col in df.columns for col in required_columns):
            return "Missing required analysis columns for performance comparison."

        # Filter out rows with no analysis, failed analysis, or download failures
        valid_analyses = df[
            ~df[required_columns].isna().all(axis=1) &
            (df['analysis'] != 'Download failed') &
            (df['analysis'] != 'Analysis failed') &
            df['analysis'].notna()
        ]
        
        if len(valid_analyses) == 0:
            return "No valid analysis data available for summary generation."
        
        # Separate top and worst performers
        top_performers = valid_analyses[valid_analyses['performance_category'] == 'bestperform']
        worst_performers = valid_analyses[valid_analyses['performance_category'] == 'worstperform']
        
        if len(top_performers) == 0 or len(worst_performers) == 0:
            return "Need both top and worst performing videos for comparison analysis."
        
        # Calculate average scores for each category
        top_avg_scores = {
            'hook': top_performers['hook_score'].mean(),
            'filming': top_performers['filming_score'].mean(),
            'location': top_performers['location_score'].mean(),
            'collaboration': top_performers['collaboration_score'].mean(),
            'overall': top_performers['overall_score'].mean()
        }
        
        worst_avg_scores = {
            'hook': worst_performers['hook_score'].mean(),
            'filming': worst_performers['filming_score'].mean(),
            'location': worst_performers['location_score'].mean(),
            'collaboration': worst_performers['collaboration_score'].mean(),
            'overall': worst_performers['overall_score'].mean()
        }
        
        # Calculate performance gaps
        gaps = {
            'hook': top_avg_scores['hook'] - worst_avg_scores['hook'],
            'filming': top_avg_scores['filming'] - worst_avg_scores['filming'],
            'location': top_avg_scores['location'] - worst_avg_scores['location'],
            'collaboration': top_avg_scores['collaboration'] - worst_avg_scores['collaboration']
        }
        
        # Sort gaps by size to focus on biggest differences
        sorted_gaps = sorted(gaps.items(), key=lambda x: x[1], reverse=True)
        significant_gaps = [(k, v) for k, v in sorted_gaps if v >= 1.5]  # Only show gaps >= 1.5 points
        
        # Enhanced prompt for practical content creation guidance
        prompt = f"""
Analyze {len(top_performers)} TOP vs {len(worst_performers)} WORST TikTok videos for actionable content creation advice.

**PERFORMANCE GAPS (focus on largest gaps only):**
{', '.join([f'{k}: {v:.1f}' for k, v in significant_gaps])}

**TOP PERFORMER DATA:**
Hook types: {json.dumps(top_performers['hook_type'].tolist()[:8])}
Hook reasons: {json.dumps(top_performers['hook_works'].tolist()[:5])}
Filming styles: {json.dumps(top_performers['filming_style'].tolist()[:8])}
Filming notes: {json.dumps(top_performers['filming_notes'].tolist()[:5])}
Locations: {json.dumps(top_performers['location_type'].tolist()[:8])}
Location impacts: {json.dumps(top_performers['location_impact'].tolist()[:5])}
Who involved: {json.dumps(top_performers['who_involved'].tolist()[:8])}
Collaboration effects: {json.dumps(top_performers['collaboration_effect'].tolist()[:5])}

**WORST PERFORMER DATA:**
Hook types: {json.dumps(worst_performers['hook_type'].tolist()[:8])}
Hook reasons: {json.dumps(worst_performers['hook_works'].tolist()[:5])}
Filming styles: {json.dumps(worst_performers['filming_style'].tolist()[:8])}
Filming notes: {json.dumps(worst_performers['filming_notes'].tolist()[:5])}
Locations: {json.dumps(worst_performers['location_type'].tolist()[:8])}
Location impacts: {json.dumps(worst_performers['location_impact'].tolist()[:5])}
Who involved: {json.dumps(worst_performers['who_involved'].tolist()[:8])}
Collaboration effects: {json.dumps(worst_performers['collaboration_effect'].tolist()[:5])}

**REQUIREMENTS:**
1. Only focus on categories with gaps ≥1.5 points (ignore small differences)
2. Give SPECIFIC, ACTIONABLE examples for content creators
3. Use real data patterns from the analysis above
4. Include exact phrases, setups, or techniques to copy
5. Explain WHY these work based on the data

**OUTPUT FORMAT:**

# Critical Performance Gaps
[List only the 2-3 biggest gaps with specific point differences]

# Winning Formulas (COPY THESE)
[For each significant gap category, provide:]

## [Category with biggest gap]:
**Copy This:** [2-3 specific examples from top performers with exact execution details]
**Why It Works:** [Data-backed reason from the analysis]
**Avoid This:** [1-2 specific examples from worst performers]

[Repeat for other significant gaps only]

# Action Plan
1. [Most critical change based on biggest gap - specific technique to implement]
2. [Second biggest gap - specific technique to implement] 
3. [Third biggest gap - specific technique to implement]

Focus on practical execution. Give content creators exact things to do tomorrow.
"""

        # Call Gemini with rate limiting for summary generation
        GEMINI_SEMAPHORE.acquire()
        try:
            # Rate limiting
            global LAST_API_CALL_TIME
            current_time = time.time()
            time_since_last_call = current_time - LAST_API_CALL_TIME
            if time_since_last_call < MIN_API_INTERVAL:
                sleep_time = MIN_API_INTERVAL - time_since_last_call
                time.sleep(sleep_time)
            
            LAST_API_CALL_TIME = time.time()
            
            client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
            )
            
            summary = response.text
            
        finally:
            GEMINI_SEMAPHORE.release()
        
        # Simplified final summary
        final_summary = f"""# TikTok Performance Analysis

**{len(top_performers)} Top vs {len(worst_performers)} Worst Videos**
**Performance Gap:** {top_avg_scores['overall']:.1f}/10 vs {worst_avg_scores['overall']:.1f}/10

{summary}
"""
        
        return final_summary

    except Exception as e:
        logger.error(f"Error generating performance comparison: {str(e)}")
        return f"Performance analysis failed: {str(e)}"

