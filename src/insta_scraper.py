import json
import httpx
import csv
from datetime import datetime
from pathlib import Path
import logging
import time
import random

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InstaScraper:
    def __init__(self, output_dir=None):
        """
        Initialize the Instagram scraper using direct API calls.
        
        Args:
            output_dir (str): Directory to save results
        """
        # Set default output directory
        if output_dir is None:
            self.output_dir = Path("scraped_posts")
        else:
            self.output_dir = Path(output_dir)
            
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create an HTTP client with browser-like headers
        self.client = httpx.Client(
            headers={
                # Instagram app ID (doesn't change often)
                "x-ig-app-id": "936619743392459",
                # Browser-like user agent
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
            },
            timeout=30.0  # Increased timeout for reliability
        )
    
    def scrape_profile(self, username, max_posts=10):
        """
        Scrape posts from an Instagram profile using the public API.
        
        Args:
            username (str): Instagram username (without @)
            max_posts (int): Maximum number of posts to scrape
            
        Returns:
            list: List of post data dictionaries
        """
        logger.info(f"Scraping profile: {username}")
        
        try:
            # Get user profile info
            profile_info = self._get_profile_info(username)
            if not profile_info:
                logger.error(f"Could not retrieve profile info for {username}")
                return []
            
            # Get user ID
            user_id = profile_info.get('id')
            if not user_id:
                logger.error(f"Could not retrieve user ID for {username}")
                return []
            
            # Get user posts
            posts = self._get_user_posts(user_id, username, max_posts)
            
            # Save data
            self._save_data(profile_info, posts, f"{username}_profile")
            
            return posts
            
        except Exception as e:
            logger.error(f"Error scraping profile {username}: {str(e)}")
            return []
    
    def _get_profile_info(self, username):
        """
        Get profile information using Instagram's public API.
        
        Args:
            username (str): Instagram username
            
        Returns:
            dict: Profile information
        """
        try:
            url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
            response = self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                user_data = data.get('data', {}).get('user', {})
                
                # Extract relevant profile info
                profile_info = {
                    'username': user_data.get('username'),
                    'full_name': user_data.get('full_name'),
                    'biography': user_data.get('biography'),
                    'followers': user_data.get('edge_followed_by', {}).get('count'),
                    'followees': user_data.get('edge_follow', {}).get('count'),
                    'posts_count': user_data.get('edge_owner_to_timeline_media', {}).get('count'),
                    'id': user_data.get('id'),
                    'scrape_time': datetime.now().isoformat()
                }
                
                return profile_info
            else:
                logger.error(f"Failed to get profile info: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting profile info: {str(e)}")
            return None
    
    def _get_user_posts(self, user_id, username, max_posts):
        """
        Get user posts using Instagram's public API with pagination.
        
        Args:
            user_id (str): Instagram user ID
            username (str): Instagram username
            max_posts (int): Maximum number of posts to retrieve
            
        Returns:
            list: List of post data
        """
        posts = []
        max_id = None
        
        try:
            # Continue fetching until we have enough posts or no more are available
            while len(posts) < max_posts:
                # Use the more reliable user feed API endpoint instead of GraphQL
                url = f"https://i.instagram.com/api/v1/feed/user/{user_id}/"
                
                # Add pagination parameter if we have a max_id
                params = {}
                if max_id:
                    params['max_id'] = max_id
                
                # Add random delay to avoid rate limiting
                time.sleep(random.uniform(1.5, 3.0))
                
                # Make the request
                response = self.client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Failed to get posts: {response.status_code} - {response.text}")
                    break
                
                data = response.json()
                items = data.get('items', [])
                
                # Break if no items returned
                if not items:
                    break
                
                # Process each post
                for item in items:
                    # Extract post data using modified extraction method
                    post_data = self._extract_post_data_from_feed(item, username)
                    posts.append(post_data)
                    
                    logger.info(f"Scraped post {len(posts)}/{max_posts}")
                    
                    # Break if we have enough posts
                    if len(posts) >= max_posts:
                        break
                    
                    # Add small delay between processing posts
                    time.sleep(random.uniform(0.5, 1.0))
                
                # Get pagination info for next request
                more_available = data.get('more_available', False)
                if not more_available:
                    break
                    
                # Update max_id for next page
                max_id = data.get('next_max_id')
                if not max_id:
                    break
                time.sleep(random.uniform(0.5, 1.0))
                logger.info(f"Fetching next page with max_id: {max_id}")
                    
        except Exception as e:
            logger.error(f"Error getting posts: {str(e)}")
        
        return posts[:max_posts]
    
    def _extract_post_data_from_feed(self, item, username):
        """
        Extract all available data from a post item from the feed API.
        
        Args:
            item: Instagram post item from feed API
            username: Instagram username
            
        Returns:
            dict: Post data with all available fields
        """
        # Extract caption
        caption = ""
        caption_obj = item.get('caption', {})
        if caption_obj:
            caption = caption_obj.get('text', '')
        
        # Extract hashtags from caption
        hashtags = [tag.strip("#") for tag in caption.split() if tag.startswith("#")]
        
        # Create post data dictionary with all available fields
        code = item.get('code', '')
        post_data = {
            # Basic post information
            'id': item.get('id', ''),
            'code': code,
            'shortcode': code,
            'url': f"https://www.instagram.com/p/{code}/",
            'title': caption[:50] + "..." if caption and len(caption) > 50 else caption,
            'text': caption,
            
            # Timestamps
            'taken_at': item.get('taken_at', 0),
            'timestamp': datetime.fromtimestamp(item.get('taken_at', 0)).isoformat(),
            'device_timestamp': item.get('device_timestamp', 0),
            
            # Engagement metrics
            'likes': item.get('like_count', 0),
            'comments': item.get('comment_count', 0),
            'has_liked': item.get('has_liked', False),
            'has_more_comments': item.get('has_more_comments', False),
            
            # Media information
            'media_type': item.get('media_type', ''),
            'product_type': item.get('product_type', ''),
            'is_video': item.get('is_video', False),
            'video_duration': item.get('video_duration', 0),
            'view_count': item.get('view_count', 0),
            'play_count': item.get('play_count', 0),
            
            # Location information
            'location': json.dumps(item.get('location', {})) if item.get('location') else '',
            
            # User information
            'owner_username': username,
            'owner_id': item.get('user', {}).get('pk', '') if item.get('user') else '',
            
            # Image information
            'original_width': item.get('original_width', 0),
            'original_height': item.get('original_height', 0),
            
            # Carousel/album information
            'carousel_media_count': item.get('carousel_media_count', 0),
            
            # Hashtags and mentions
            'hashtags': ','.join(hashtags),
            
            # Sponsorship information
            'sponsor_tags': json.dumps(item.get('sponsor_tags', [])) if item.get('sponsor_tags') else '',
            'is_paid_partnership': item.get('is_paid_partnership', False),
            'is_sponsored': item.get('is_sponsored', False),
            'sponsor_id': item.get('sponsor', {}).get('id', '') if item.get('sponsor') else '',
            'sponsor_username': item.get('sponsor', {}).get('username', '') if item.get('sponsor') else '',
            
            # Status
            'success': True
        }
        
        return post_data
    
    
    def _save_data(self, info, posts, prefix):
        """
        Save data to files.
        
        Args:
            info (dict): Profile or hashtag information
            posts (list): List of post data
            prefix (str): Prefix for filenames
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save posts to CSV with all available fields
        csv_path = self.output_dir / f"post_texts_{timestamp}.csv"
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            # Use all fields from the post data
            if posts:
                fieldnames = list(posts[0].keys())  # Get all field names from the first post
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for post in posts:
                    # Write the entire post data dictionary
                    writer.writerow(post)
            else:
                logger.warning("No posts to save to CSV")
        
        logger.info(f"Saved {len(posts)} posts to {csv_path}")
        
        # Save captions to text file
        txt_path = self.output_dir / f"{prefix}_captions_{timestamp}.txt"
        
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"📥 Captions from {prefix}\n\n")
            
            for i, post in enumerate(posts):
                caption = post['text'] or "[No caption]"
                f.write(f"Post {i+1}:\n{caption}\n{'-'*40}\n")
        
        logger.info(f"Saved captions to {txt_path}")


def main():
    # Example usage
    scraper = InstaScraper()
    
    # Target username (public profile)
    username = "anniesbucketlist"
    
    # Set how many posts you want to scrape
    max_posts = 50
    
    print(f"📥 Downloading captions from @{username}...\n")
    
    # Scrape profile
    posts = scraper.scrape_profile(username, max_posts)
    
    print(f"\n✅ Scraped {len(posts)} posts from @{username}")


if __name__ == "__main__":
    main()