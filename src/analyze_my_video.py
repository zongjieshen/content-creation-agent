import os
import pandas as pd
import asyncio
import logging
from pathlib import Path
from src.video_processing_helper import analyze_video, generate_overall_summary
from src.tiktok_topic_trending import get_topic_trending_videos

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def analyze_my_video(my_video_path, hashtag="IndoorPlayground"):
    """
    Analyze a user's video, compare it with top-performing videos from a specific hashtag,
    and provide insights on why it's not performing well.
    
    Args:
        my_video_path (str): Path to the user's video file
        hashtag (str): Hashtag to search for on TikTok (without the # symbol)
    
    Returns:
        str: Analysis report comparing the user's video with top-performing videos
    """
    try:
        # Step 1: Validate the user's video file
        video_path = Path(my_video_path)
        if not video_path.exists():
            return f"Error: Video file not found at {my_video_path}"
        
        logger.info(f"Analyzing user's video: {video_path}")
        
        # Step 2: Analyze the user's video
        my_video_analysis = analyze_video(str(video_path), performance_category="worstperform")
        if not my_video_analysis:
            return "Error: Failed to analyze your video. Please check the file format."
        
        logger.info("Successfully analyzed user's video")
        
        # Step 3: Search TikTok for videos with the specified hashtag
        logger.info(f"Searching TikTok for videos with hashtag #{hashtag}...")
        tiktok_results = await get_topic_trending_videos(
            topic=hashtag,
            limit=60,  # Get a good sample size
            download_top=5  # Download top 5 videos for analysis
        )
        
        if 'error' in tiktok_results:
            return f"Error searching TikTok: {tiktok_results['error']}"
        
        logger.info(f"Found {tiktok_results['total_videos']} videos with hashtag #{hashtag}")
        logger.info(f"Downloaded {tiktok_results['top_performers']} top-performing videos")
        
        # Step 4: Create a DataFrame with the user's video analysis
        my_video_df = pd.DataFrame([
            {
                'id': 'my_video',
                'author': 'me',
                'performance_category': 'worstperform',
                'video_path': str(video_path),
                'hook_score': my_video_analysis.hook_score,
                'hook_type': my_video_analysis.hook_type,
                'hook_works': my_video_analysis.hook_works,
                'filming_score': my_video_analysis.filming_score,
                'filming_style': my_video_analysis.filming_style,
                'filming_notes': my_video_analysis.filming_notes,
                'location_score': my_video_analysis.location_score,
                'location_type': my_video_analysis.location_type,
                'location_impact': my_video_analysis.location_impact,
                'collaboration_score': my_video_analysis.collaboration_score,
                'who_involved': my_video_analysis.who_involved,
                'collaboration_effect': my_video_analysis.collaboration_effect,
                'overall_score': my_video_analysis.overall_score,
                'biggest_win': my_video_analysis.biggest_win,
                'biggest_fail': my_video_analysis.biggest_fail
            }
        ])
        
        # Step 5: Load the TikTok videos DataFrame
        tiktok_df = pd.read_csv(tiktok_results['csv_path'])
        
        # Step 6: Process the downloaded TikTok videos to get their analysis
        # The videos are already downloaded and analyzed by get_topic_trending_videos
        # We just need to load the analysis results
        
        # Step 7: Combine the user's video with the TikTok videos for comparison
        # We'll add the user's video to the worst performers for comparison
        combined_df = pd.concat([tiktok_df, my_video_df], ignore_index=True)
        
        # Step 8: Generate a comparison summary
        logger.info("Generating comparison summary...")
        summary = generate_overall_summary(combined_df)
        
        # Step 9: Add a personalized introduction to the summary
        personalized_summary = f"""# Your TikTok Video Performance Analysis

## Your Video vs. Top Performing #{hashtag} Videos

### Your Video Analysis:
- **Hook Score:** {my_video_analysis.hook_score}/10 - {my_video_analysis.hook_type} - {my_video_analysis.hook_works}
- **Filming Score:** {my_video_analysis.filming_score}/10 - {my_video_analysis.filming_style} - {my_video_analysis.filming_notes}
- **Location Score:** {my_video_analysis.location_score}/10 - {my_video_analysis.location_type} - {my_video_analysis.location_impact}
- **Collaboration Score:** {my_video_analysis.collaboration_score}/10 - {my_video_analysis.who_involved} - {my_video_analysis.collaboration_effect}
- **Overall Score:** {my_video_analysis.overall_score}/10
- **Biggest Win:** {my_video_analysis.biggest_win}
- **Biggest Fail:** {my_video_analysis.biggest_fail}

## Comparison with Top Performers

{summary}
"""
        
        return personalized_summary
        
    except Exception as e:
        logger.error(f"Error in analyze_my_video: {str(e)}")
        return f"An error occurred during analysis: {str(e)}"

async def main():
    # Get the video path from command line arguments or use a default
    import sys
    if len(sys.argv) > 1:
        my_video_path = sys.argv[1]
    else:
        print("Please provide the path to your TikTok video as a command line argument.")
        print("Example: python analyze_my_video.py path/to/your/video.mp4")
        return
    
    # Get the hashtag from command line arguments or use the default
    hashtag = "IndoorPlayground"
    if len(sys.argv) > 2:
        hashtag = sys.argv[2].lstrip('#')  # Remove # if present
    
    # Run the analysis
    result = await analyze_my_video(my_video_path, hashtag)
    
    # Print the result
    print(result)

if __name__ == "__main__":
    asyncio.run(main())