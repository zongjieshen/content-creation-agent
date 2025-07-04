from TikTokApi import TikTokApi
from yt_dlp import YoutubeDL
import asyncio
import os
from pathlib import Path
import csv
import json
from datetime import datetime
import pandas as pd

# Get ms_token from environment variable or set to None
ms_token = os.environ.get("ms_token", None)  # You'll need to set this from your TikTok cookies

# Configure yt-dlp options - remove the hardcoded output_dir
ydl_opts = {
    'outtmpl': '',  # This will be set dynamically per download
    'format': 'best',
    'quiet': False,
    'no_warnings': True,
    'continuedl': True,
    'concurrent_fragment_downloads': 3,  # Download fragments of each video concurrently
    'throttledratelimit': 100000,  # Rate limit in bytes/sec per download
    'retries': 10,  # Number of retries for each fragment
    'fragment_retries': 10,  # Number of retries for each fragment
    'file_access_retries': 10,  # Number of retries due to file access issues
}

def save_to_csv(videos_data, topic, performance_category=None):
    """Save video metadata to CSV file and return as DataFrame"""
    # Create a timestamp for the filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Use the hashtag directory structure for CSV files - one level above src directory
    base_output_dir = Path(__file__).parent.parent / "temp_video"
    hashtag_name = topic.replace('#', '')
    hashtag_dir = base_output_dir / hashtag_name
    hashtag_dir.mkdir(parents=True, exist_ok=True)
    
    # Save CSV in the hashtag directory (not in topic_trending subdirectory)
    csv_filename = hashtag_dir / f"{hashtag_name}_metadata_{timestamp}.csv"
    
    # Extract all fields from the first video to get column headers
    if not videos_data:
        print("No data to save to CSV")
        return pd.DataFrame(), None
    
    # Create DataFrame data
    df_data = []
    
    # Get all metadata fields from the first video
    first_video = videos_data[0]['video']
    video_dict = first_video.as_dict
    
    # Flatten nested dictionaries for CSV
    flattened_fields = {}
    
    # Basic video fields
    flattened_fields['id'] = video_dict.get('id', '')
    flattened_fields['desc'] = video_dict.get('desc', '')
    flattened_fields['createTime'] = video_dict.get('createTime', '')
    flattened_fields['video_url'] = f"https://www.tiktok.com/@{video_dict.get('author', {}).get('uniqueId', '')}/video/{video_dict.get('id', '')}"
    
    # Author information
    author = video_dict.get('author', {})
    flattened_fields['author_id'] = author.get('id', '')
    flattened_fields['author_uniqueId'] = author.get('uniqueId', '')
    flattened_fields['author_nickname'] = author.get('nickname', '')
    flattened_fields['author_verified'] = author.get('verified', False)
    flattened_fields['author_signature'] = author.get('signature', '')
    flattened_fields['author_followerCount'] = author.get('followerCount', 0)
    flattened_fields['author_followingCount'] = author.get('followingCount', 0)
    
    # Music information
    music = video_dict.get('music', {})
    flattened_fields['music_id'] = music.get('id', '')
    flattened_fields['music_title'] = music.get('title', '')
    flattened_fields['music_authorName'] = music.get('authorName', '')
    flattened_fields['music_original'] = music.get('original', False)
    flattened_fields['music_playUrl'] = music.get('playUrl', '')
    
    # Stats information
    stats = video_dict.get('stats', {})
    flattened_fields['diggCount'] = stats.get('diggCount', 0)
    flattened_fields['shareCount'] = stats.get('shareCount', 0)
    flattened_fields['commentCount'] = stats.get('commentCount', 0)
    flattened_fields['playCount'] = stats.get('playCount', 0)
    
    # Video details
    flattened_fields['duration'] = video_dict.get('video', {}).get('duration', 0)
    flattened_fields['ratio'] = video_dict.get('video', {}).get('ratio', '')
    flattened_fields['height'] = video_dict.get('video', {}).get('height', 0)
    flattened_fields['width'] = video_dict.get('video', {}).get('width', 0)
    
    # Hashtags
    challenges = video_dict.get('challenges', [])
    hashtags = []
    for challenge in challenges:
        hashtags.append(challenge.get('title', ''))
    flattened_fields['hashtags'] = ','.join(hashtags)
    
    # Add performance metrics to fieldnames
    flattened_fields['likes_views_ratio'] = 0
    flattened_fields['performance_category'] = ''
    
    # Get all field names from the flattened dictionary
    fieldnames = list(flattened_fields.keys())
    
    # Write to CSV
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # Process each video for both CSV and DataFrame
        for video_data in videos_data:
            video = video_data['video']
            video_dict = video.as_dict
            
            row = {}
            # Basic video fields
            row['id'] = video_dict.get('id', '')
            row['desc'] = video_dict.get('desc', '')
            row['createTime'] = video_dict.get('createTime', '')
            row['video_url'] = f"https://www.tiktok.com/@{video_dict.get('author', {}).get('uniqueId', '')}/video/{video_dict.get('id', '')}"
            
            # Author information
            author = video_dict.get('author', {})
            row['author_id'] = author.get('id', '')
            row['author_uniqueId'] = author.get('uniqueId', '')
            row['author_nickname'] = author.get('nickname', '')
            row['author_verified'] = author.get('verified', False)
            row['author_signature'] = author.get('signature', '')
            row['author_followerCount'] = author.get('followerCount', 0)
            row['author_followingCount'] = author.get('followingCount', 0)
            
            # Music information
            music = video_dict.get('music', {})
            row['music_id'] = music.get('id', '')
            row['music_title'] = music.get('title', '')
            row['music_authorName'] = music.get('authorName', '')
            row['music_original'] = music.get('original', False)
            row['music_playUrl'] = music.get('playUrl', '')
            
            # Stats information
            stats = video_dict.get('stats', {})
            row['diggCount'] = stats.get('diggCount', 0)
            row['shareCount'] = stats.get('shareCount', 0)
            row['commentCount'] = stats.get('commentCount', 0)
            row['playCount'] = stats.get('playCount', 0)
            
            # Video details
            row['duration'] = video_dict.get('video', {}).get('duration', 0)
            row['ratio'] = video_dict.get('video', {}).get('ratio', '')
            row['height'] = video_dict.get('video', {}).get('height', 0)
            row['width'] = video_dict.get('video', {}).get('width', 0)
            
            # Hashtags
            challenges = video_dict.get('challenges', [])
            hashtags = []
            for challenge in challenges:
                hashtags.append(challenge.get('title', ''))
            row['hashtags'] = ','.join(hashtags)
            
            # Performance metrics
            row['likes_views_ratio'] = video_data.get('likes_views_ratio', 0)
            row['performance_category'] = video_data.get('performance_category', '')
            
            # Add to both CSV and DataFrame data
            writer.writerow(row)
            df_data.append(row)
    
    # Create DataFrame from the same data
    df = pd.DataFrame(df_data)
    
    # Also save the full raw JSON data for reference in the same directory
    json_filename = hashtag_dir / f"{hashtag_name}_full_data_{timestamp}.json"
    with open(json_filename, 'w', encoding='utf-8') as jsonfile:
        # Convert video objects to dictionaries
        serializable_data = []
        for video_data in videos_data:
            video_dict = video_data['video'].as_dict
            serializable_data.append(video_dict)
        json.dump(serializable_data, jsonfile, indent=2, ensure_ascii=False)
    
    print(f"\nMetadata saved to CSV: {csv_filename}")
    print(f"DataFrame created with shape: {df.shape}")
    return df, csv_filename

async def get_topic_trending_videos(topic, limit=10, download_top=1):
    """Find trending videos related to a specific topic and return analysis DataFrame"""
    if not ms_token:
        print("Warning: ms_token not set. You may encounter issues with TikTok's bot detection.")
        print("To get your ms_token, log into TikTok, open developer tools, go to Application tab,")
        print("then look in Cookies for the 'msToken' value.")
    
    print(f"Searching for videos related to topic: {topic}...")
    videos_data = []
    
    # Create hashtag directory - one level above src directory
    # Create hashtag directory in system temp folder
    import tempfile
    base_output_dir = Path(tempfile.gettempdir()) / "content_creation_agent" / "temp_video"
    hashtag_name = topic.replace('#', '')
    hashtag_dir = base_output_dir / hashtag_name
    hashtag_dir.mkdir(parents=True, exist_ok=True)
    
    # Create performance directories
    best_dir = hashtag_dir / "bestperform"
    worst_dir = hashtag_dir / "worstperform"
    best_dir.mkdir(parents=True, exist_ok=True)
    worst_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        async with TikTokApi() as api:
            # Create a session with the ms_token if available
            await api.create_sessions(
                ms_tokens=[ms_token] if ms_token else None,
                num_sessions=1,
                sleep_after=3,
                browser="chromium",
                headless=False
            )
            
            # Search for videos by hashtag
            hashtag_name = topic.replace('#', '')
            print(f"Searching for videos with hashtag: #{hashtag_name}...")
            
            # Get hashtag object
            hashtag = api.hashtag(name=hashtag_name)
            
            count = 0
            async for video in hashtag.videos(count=limit):
                # Check if the video language is English
                video_dict = video.as_dict
                if video_dict.get('textLanguage') != 'en':
                    print(f"Skipping non-English video: {video.id} (language: {video_dict.get('textLanguage', 'unknown')})")
                    continue
                    
                count += 1
                print(f"Found video {count}/{limit}: {video.id} by @{video.author.username}")
                if count == 1:
                    video_data1 = video.as_dict
                    print(f"Video data: {video_data1}")
                # Store video data with popularity metrics
                videos_data.append({
                    'video': video,
                    'author': video.author.username,
                    'id': video.id,
                    'likes': int(video.stats.get('diggCount', 0)),
                    'shares': int(video.stats.get('shareCount', 0)),
                    'views': int(video.stats.get('playCount', 0)),
                    'comments': int(video.stats.get('commentCount', 0))
                })
            
            if not videos_data:
                print(f"No videos found for topic: {topic}")
                return
            
            # Sort videos by popularity (using likes as the metric)
            videos_data.sort(key=lambda x: x['likes'], reverse=True)
            
            print(f"\nTop {len(videos_data)} videos for topic '{topic}' (sorted by likes):")
            for i, video_data in enumerate(videos_data):
                print(f"{i+1}. @{video_data['author']} - {video_data['id']} - "
                      f"Likes: {video_data['likes']}, Views: {video_data['views']}")
            
            # Calculate likes/views ratio for each video
            for video_data in videos_data:
                views = video_data['views']
                likes = video_data['likes']
                # Avoid division by zero
                if views > 0:
                    video_data['likes_views_ratio'] = likes / views
                else:
                    video_data['likes_views_ratio'] = 0
            
            # Sort by likes/views ratio
            videos_data.sort(key=lambda x: x['likes_views_ratio'], reverse=True)
            
            # After calculating likes/views ratio and sorting videos
            
            # Calculate the number of videos for top and bottom 20%
            total_videos = len(videos_data)
            top_count = max(1, int(total_videos * 0.2))
            bottom_count = max(1, int(total_videos * 0.2))
            
            # Get top and bottom videos by likes/views ratio
            top_ratio_videos = videos_data[:top_count]
            bottom_ratio_videos = videos_data[-bottom_count:]
            
            # Sort bottom videos by likes/views ratio ascending (worst first)
            bottom_ratio_videos.sort(key=lambda x: x['likes_views_ratio'])
            
            # Add performance category to each video
            for video in top_ratio_videos:
                video['performance_category'] = 'bestperform'
            
            for video in bottom_ratio_videos:
                video['performance_category'] = 'worstperform'
            
            # Combine videos for a single CSV with performance indicator
            combined_videos = top_ratio_videos + bottom_ratio_videos
            
            # Print information about the videos
            print(f"\nTop {top_count} videos by likes/views ratio:")
            for i, video_data in enumerate(top_ratio_videos):
                ratio = video_data['likes_views_ratio']
                print(f"{i+1}. @{video_data['author']} - {video_data['id']} - "
                      f"Ratio: {ratio:.4f} (Likes: {video_data['likes']}, Views: {video_data['views']})")
            
            print(f"\nBottom {bottom_count} videos by likes/views ratio (worst first):")
            for i, video_data in enumerate(bottom_ratio_videos):
                ratio = video_data['likes_views_ratio']
                print(f"{i+1}. @{video_data['author']} - {video_data['id']} - "
                      f"Ratio: {ratio:.4f} (Likes: {video_data['likes']}, Views: {video_data['views']})")
            
            # Save only the combined CSV with performance_category column
            combined_df, csv_filename = save_to_csv(combined_videos, topic)
            
            # Download videos to separate folders based on performance
            top_urls = []
            bottom_urls = []
            
            # Collect top performing video URLs
            for i in range(min(download_top, len(top_ratio_videos))):
                video_data = top_ratio_videos[i]
                video_url = f"https://www.tiktok.com/@{video_data['author']}/video/{video_data['id']}"
                top_urls.append(video_url)
                print(f"Queuing top performing video {i+1}/{min(download_top, len(top_ratio_videos))}: {video_url}")
            
            # Collect bottom performing video URLs
            for i in range(min(download_top, len(bottom_ratio_videos))):
                video_data = bottom_ratio_videos[i]
                video_url = f"https://www.tiktok.com/@{video_data['author']}/video/{video_data['id']}"
                bottom_urls.append(video_url)
                print(f"Queuing bottom performing video {i+1}/{min(download_top, len(bottom_ratio_videos))}: {video_url}")
            
            # Download top performing videos in batch to bestperform folder
            if top_urls:
                print("\nDownloading top performing videos in parallel...")
                ydl_opts['outtmpl'] = str(best_dir / '%(uploader)s_%(id)s.%(ext)s')
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download(top_urls)
            
            # Download bottom performing videos in batch to worstperform folder
            if bottom_urls:
                print("\nDownloading bottom performing videos in parallel...")
                ydl_opts['outtmpl'] = str(worst_dir / '%(uploader)s_%(id)s.%(ext)s')
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.download(bottom_urls)
            
            print(f"\nVideos downloaded to: {hashtag_dir}")
            print(f"Best performing videos in: {best_dir}")
            print(f"Worst performing videos in: {worst_dir}")
            print(f"Analysis complete. DataFrame shape: {combined_df.shape}")
            print(f"Combined metadata saved to: {csv_filename}")
            
            # Return both the DataFrame and metadata
            return {
                'dataframe': combined_df,
                'csv_path': csv_filename,
                'hashtag_dir': str(hashtag_dir),
                'total_videos': len(videos_data),
                'top_performers': len(top_ratio_videos),
                'bottom_performers': len(bottom_ratio_videos)
            }
        
    except Exception as e:
        print(f"Error: {e}")
        return {
            'error': str(e),
            'dataframe': pd.DataFrame(),  # Empty DataFrame on error
            'csv_path': None,
            'hashtag_dir': None,
            'total_videos': 0,
            'top_performers': 0,
            'bottom_performers': 0
        }

def main():
    """Main function to run the script"""
    print("TikTok Topic Trending Video Finder")
    print("==================================")
    
    # Get topic from command line argument or use default
    topic = sys.argv[1] if len(sys.argv) > 1 else "popmart"
    
    # Run the async function
    asyncio.run(get_topic_trending_videos(topic=topic, limit=60, download_top=10))

if __name__ == "__main__":
    import sys
    main()