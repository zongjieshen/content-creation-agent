import httpx
import asyncio
import random
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from ..utils.db_client import get_db_context

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InstagramPostsScraper:
    def __init__(self):
        """
        Initialize the Instagram Posts Scraper with SQLite database.
        
        """
        
        # Instagram API configuration
        self.base_url = "https://i.instagram.com/api/v1/feed/user/{user_id}/"
        self.profile_info_url = "https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
        
        # HTTP client with Instagram-like headers
        self.client = httpx.AsyncClient(
            headers={
                "x-ig-app-id": "936619743392459",  # Instagram's public app ID
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Referer": "https://www.instagram.com/",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=30.0
        )
    
    async def check_stop_event(self, stop_event=None):
        """Check if stop_event is set and raise CancelledError if it is
        
        Args:
            stop_event (asyncio.Event, optional): Event to check for cancellation
            
        Raises:
            asyncio.CancelledError: If stop_event is set
        """
        if stop_event and stop_event.is_set():
            logger.info("Scraping operation cancelled")
            raise asyncio.CancelledError("Scraping operation cancelled")

    def should_scrape_user(self, username: str) -> bool:
        """
        Check if a user should be scraped based on last scrape date.
        Skip if scraped within the last week.
        
        Args:
            username (str): Instagram username
            
        Returns:
            bool: True if user should be scraped, False otherwise
        """
        try:
            with get_db_context() as (conn, cursor):
                # Get last scrape date for username
                cursor.execute("SELECT last_scraped FROM scraped_users WHERE username = ?", (username,))
                result = cursor.fetchone()
                
                if not result:
                    # User has never been scraped
                    return True
                
                last_scraped = datetime.strptime(result[0], "%Y-%m-%d")
                current_date = datetime.now()
                
                # Skip if scraped within the last week
                if current_date - last_scraped < timedelta(days=7):
                    logger.info(f"Skipping {username} - scraped recently on {last_scraped.strftime('%Y-%m-%d')}")
                    return False
                
                return True
                
        except Exception as e:
            logger.error(f"Error checking scrape status for {username}: {str(e)}")
            return True  # Default to scraping if there's an error
    
    def update_tracking(self, username: str):
        """
        Update tracking data for a username in the database.
        
        Args:
            username (str): Instagram username that was processed
        """
        try:
            with get_db_context() as (conn, cursor):
                # Insert or replace user tracking data
                cursor.execute(
                    "INSERT OR REPLACE INTO scraped_users (username, last_scraped) VALUES (?, ?)",
                    (username, datetime.now().strftime("%Y-%m-%d"))
                )
                
                logger.info(f"Updated tracking for {username}")
                
        except Exception as e:
            logger.error(f"Error updating tracking data: {str(e)}")

    async def get_user_id_from_username(self, username: str) -> Optional[str]:
        """
        Get user ID from Instagram username.
        
        Args:
            username (str): Instagram username
            force (bool): If True, bypass the should_scrape_user check
        
        Returns:
            str: User ID if found, None otherwise
        """
        # Check if we should scrape this user unless force is True
        if not self.should_scrape_user(username):
            logger.info(f"Skipping user ID retrieval for {username} - scraped recently")
            return None
            
        try:
            url = self.profile_info_url.format(username=username)
            response = await self.client.get(url)
            
            if response.status_code == 200:
                data = response.json()
                user_data = data.get("data", {}).get("user", {})
                user_id = user_data.get("id")
                
                if user_id:
                    logger.info(f"Found user ID {user_id} for username {username}")
                    return user_id
                else:
                    logger.error(f"No user ID found for username {username}")
                    return None
            else:
                logger.error(f"Failed to get user info for {username}: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting user ID for {username}: {str(e)}")
            return None
    
    async def add_random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """
        Add random delay to simulate human behavior.
        
        Args:
            min_seconds (float): Minimum delay in seconds
            max_seconds (float): Maximum delay in seconds
        """
        delay = random.uniform(min_seconds, max_seconds)
        logger.info(f"Adding random delay of {delay:.2f} seconds")
        await asyncio.sleep(delay)
    
    async def scrape_user_posts(self, username: str, max_limit: int = 50, stop_event: Optional[asyncio.Event] = None) -> List[Dict[str, Any]]:
        """Scrape posts from an Instagram user.
        
        Args:
            username (str): Instagram username
            max_limit (int): Maximum number of posts to scrape
            stop_event (asyncio.Event, optional): Event to check for cancellation
            
        Returns:
            List[Dict]: List of post data
        """
        # Get user ID first
        user_id = await self.get_user_id_from_username(username)
        if not user_id:
            logger.error(f"Could not find user ID for username: {username}")
            return []
        
        all_posts = []
        max_id = None
        posts_scraped = 0
        page = 1
        
        logger.info(f"Starting to scrape posts for user {username} (ID: {user_id})")
        
        while posts_scraped < max_limit:
            try:
                # Check for cancellation
                await self.check_stop_event(stop_event)
                
                # Build URL with pagination
                url = self.base_url.format(user_id=user_id)
                params = {}
                
                if max_id:
                    params["max_id"] = max_id
                
                logger.info(f"Fetching page {page} for user {username}")
                
                # Make request
                response = await self.client.get(url, params=params)
                
                if response.status_code != 200:
                    logger.error(f"Request failed with status {response.status_code}: {response.text}")
                    break
                
                data = response.json()
                
                # Extract posts from response
                items = data.get("items", [])
                
                if not items:
                    logger.info("No more posts found")
                    break
                
                # Process posts
                for item in items:
                    # Check for cancellation periodically
                    if posts_scraped % 10 == 0:  # Check every 10 posts
                        await self.check_stop_event(stop_event)
                        
                    if posts_scraped >= max_limit:
                        break
                        
                    post_data = self.extract_post_data(item)
                    all_posts.append(post_data)
                    posts_scraped += 1
                
                logger.info(f"Scraped {len(items)} posts from page {page}. Total: {posts_scraped}")
                
                # Check for pagination
                more_available = data.get("more_available", False)
                if not more_available:
                    logger.info("No more pages available")
                    break
                
                # Get next page ID
                max_id = data.get("next_max_id")
                if not max_id:
                    logger.info("No next_max_id found, stopping pagination")
                    break
                
                page += 1
                
                # Add delay between requests
                await self.add_random_delay(2.0, 5.0)
                
            except asyncio.CancelledError:
                logger.info(f"Scraping cancelled for user {username} after {posts_scraped} posts")
                return all_posts
            except Exception as e:
                logger.error(f"Error scraping page {page}: {str(e)}")
                break
        
        logger.info(f"Finished scraping. Total posts collected: {len(all_posts)}")
        return all_posts
    
    def extract_post_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract relevant data from a post item.
        
        Args:
            item (Dict): Raw post data from Instagram API
            
        Returns:
            Dict: Cleaned post data
        """
        try:
            # Basic post information
            post_data = {
                "id": item.get("id", ""),
                "code": item.get("code", ""),
                "taken_at": item.get("taken_at", ""),
                "media_type": item.get("media_type", ""),
                "like_count": item.get("like_count", 0),
                "comment_count": item.get("comment_count", 0),
                "play_count": item.get("play_count", 0),  # For videos
                "video_duration": item.get("video_duration", 0),  # For videos
            }
            
            # Caption
            caption = item.get("caption")
            if caption:
                post_data["caption_text"] = caption.get("text", "")
            else:
                post_data["caption_text"] = ""
            
            # User information
            user = item.get("user", {})
            post_data["username"] = user.get("username", "")
            post_data["full_name"] = user.get("full_name", "")
            post_data["is_verified"] = user.get("is_verified", False)
            
            # Media URLs
            image_versions = item.get("image_versions2", {}).get("candidates", [])
            if image_versions:
                post_data["image_url"] = image_versions[0].get("url", "")
            else:
                post_data["image_url"] = ""
            
            # Video URL (if applicable)
            video_versions = item.get("video_versions", [])
            if video_versions:
                post_data["video_url"] = video_versions[0].get("url", "")
            else:
                post_data["video_url"] = ""
            
            # Location
            location = item.get("location")
            if location:
                post_data["location_name"] = location.get("name", "")
                post_data["location_city"] = location.get("city", "")
            else:
                post_data["location_name"] = ""
                post_data["location_city"] = ""
            
            # Convert timestamp to readable format
            if post_data["taken_at"]:
                try:
                    timestamp = int(post_data["taken_at"])
                    post_data["taken_at_formatted"] = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                except:
                    post_data["taken_at_formatted"] = ""
            else:
                post_data["taken_at_formatted"] = ""
            
            # Post URL
            if post_data["code"]:
                post_data["post_url"] = f"https://www.instagram.com/p/{post_data['code']}/"
            else:
                post_data["post_url"] = ""
            
            # Extract tagged users
            usertags = item.get("usertags", {})
            if usertags and "in" in usertags:
                post_data["tagged_users"] = usertags["in"]
            else:
                post_data["tagged_users"] = []
            
            # Extract coauthors
            coauthor_producers = item.get("coauthor_producers", [])
            if coauthor_producers:
                
                # Remove tagged users that are also coauthors
                if post_data["tagged_users"]:
                    coauthor_ids = [coauthor.get("pk", "") for coauthor in coauthor_producers]
                    post_data["tagged_users"] = [tag for tag in post_data["tagged_users"] 
                                              if tag.get("user", {}).get("pk", "") not in coauthor_ids]
            
            # Extract sponsorship information
            post_data["is_paid_partnership"] = item.get("is_paid_partnership", False)
            post_data["commerciality_status"] = item.get("commerciality_status", "")
            
            # Check for sponsorship keywords in caption
            sponsorship_keywords = ["ad", "sponsored", "partnership", "collab", "#ad", "#sponsored", "#partner", "code", "link","website"]
            post_data["has_sponsorship_keywords"] = any(keyword in post_data["caption_text"].lower() for keyword in sponsorship_keywords)
            
            return post_data
            
        except Exception as e:
            logger.error(f"Error extracting post data: {str(e)}")
            return {}
    
    def save_to_db(self, posts: List[Dict[str, Any]], username: str) -> bool:
        """Save posts data to SQLite database using batch execution."""
        if not posts:
            logger.warning(f"No posts to save for {username}")
            return False
        
        try:
            with get_db_context() as (conn, cursor):
                # Prepare all posts for batch insert
                batch_data = []
                
                for post in posts:
                    # Format tagged users as string
                    if "tagged_users" in post and post["tagged_users"]:
                        formatted_users = []
                        for user in post["tagged_users"]:
                            user_name = user.get("user", {}).get("username", "")
                            full_name = user.get("user", {}).get("full_name", "")
                            if user_name and full_name:
                                formatted_users.append(f"{user_name}:{full_name}")
                        post["tagged_users"] = ";".join(formatted_users)
                    else:
                        post["tagged_users"] = ""
                    
                    # Clean and sanitize text fields
                    for field in ["caption_text", "full_name", "location_name"]:
                        if field in post and post[field]:
                            # Replace any problematic characters or sequences
                            post[field] = str(post[field]).replace('\r', ' ').replace('\n', ' ')
                    
                    # Add scrape metadata
                    post["scrape_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Convert boolean values to integers for SQLite
                    post["is_verified"] = 1 if post.get("is_verified") else 0
                    post["is_paid_partnership"] = 1 if post.get("is_paid_partnership") else 0
                    post["has_sponsorship_keywords"] = 1 if post.get("has_sponsorship_keywords") else 0
                    
                    # Add to batch data
                    batch_data.append((
                        post.get("id", ""),
                        post.get("code", ""),
                        post.get("taken_at", ""),
                        post.get("taken_at_formatted", ""),
                        post.get("media_type", ""),
                        post.get("like_count", 0),
                        post.get("comment_count", 0),
                        post.get("play_count", 0),
                        post.get("video_duration", 0),
                        post.get("caption_text", ""),
                        post.get("username", ""),
                        post.get("full_name", ""),
                        post.get("is_verified", 0),
                        post.get("image_url", ""),
                        post.get("video_url", ""),
                        post.get("location_name", ""),
                        post.get("location_city", ""),
                        post.get("post_url", ""),
                        post.get("is_paid_partnership", 0),
                        post.get("commerciality_status", ""),
                        post.get("has_sponsorship_keywords", 0),
                        post.get("tagged_users", ""),
                        post.get("scrape_date", "")
                    ))
                
                # Execute batch insert
                cursor.executemany("""
                INSERT OR REPLACE INTO instagram_posts (
                    id, code, taken_at, taken_at_formatted, media_type, like_count, 
                    comment_count, play_count, video_duration, caption_text, username, 
                    full_name, is_verified, image_url, video_url, location_name, 
                    location_city, post_url, is_paid_partnership, commerciality_status, 
                    has_sponsorship_keywords, tagged_users, scrape_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch_data)
                
                logger.info(f"Saved {len(posts)} posts for {username} to database using batch execution")
                return True
                    
        except Exception as e:
            logger.error(f"Error saving to database: {str(e)}")
            return False

    async def scrape_and_save_multiple(self, usernames: List[str], max_limit: int = 50, stop_event: Optional[asyncio.Event] = None) -> bool:
        """Scrape posts from multiple Instagram usernames and save to database.
        
        Args:
            usernames (List[str]): List of Instagram usernames
            max_limit (int): Maximum number of posts to scrape per username
            stop_event (Optional[asyncio.Event]): Event to check for cancellation
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info(f"Starting Instagram posts scraping for {len(usernames)} users")
        logger.info(f"Max posts limit per user: {max_limit}")
        
        success = True
        
        try:
            for username in usernames:
                # Check for cancellation before each user
                await self.check_stop_event(stop_event)
                
                logger.info(f"Processing username: {username}")
                
                # Scrape posts
                posts = await self.scrape_user_posts(username, max_limit, stop_event)
                
                if not posts:
                    logger.warning(f"No posts found for user {username}")
                    continue
                
                # Save to database
                if self.save_to_db(posts, username):
                    # Update tracking data
                    self.update_tracking(username)
                    logger.info(f"Successfully scraped {len(posts)} posts for {username}")
                else:
                    logger.error(f"Failed to save posts for {username}")
                    success = False
                
                # Add delay between users
                await self.add_random_delay(3.0, 7.0)
            
            return success
            
        except asyncio.CancelledError:
            logger.info("Scraping operation cancelled")
            return False
        except Exception as e:
            logger.error(f"Error in scrape_and_save_multiple: {str(e)}")
            return False
        
        # In the finally block of scrape_and_save_multiple
        finally:
            await self.client.aclose()

    async def scrape_and_save(self, username: str, max_limit: int = 50) -> bool:
        """
        Main method to scrape posts and save to database (for backward compatibility).
        
        Args:
            username (str): Instagram username
            max_limit (int): Maximum number of posts to scrape
            
        Returns:
            bool: True if successful, False otherwise
        """
        return await self.scrape_and_save_multiple([username], max_limit)
    
    def get_scraped_users(self):
        """Get list of all scraped usernames and their last scraped date."""
        try:
            with get_db_context() as (conn, cursor):
                cursor.execute("SELECT username, last_scraped FROM scraped_users ORDER BY last_scraped DESC")
                rows = cursor.fetchall()
                
                results = []
                for row in rows:
                    results.append({
                        "username": row[0],
                        "last_scraped": row[1]
                    })
                
                return results
                
        except Exception as e:
            logger.error(f"Error getting scraped users: {str(e)}")
            return []

    @staticmethod
    def load_posts_from_db(username=None, limit=None, order_by="taken_at", order="DESC",  since_date=None, captions_only=False):
        """
        Load posts from the database with filtering options.
        
        Args:
            username (str, optional): Filter by specific Instagram username
            limit (int, optional): Maximum number of posts to return (None for no limit)
            order_by (str, optional): Column to order results by (default: taken_at)
            order (str, optional): Sort order, ASC or DESC (default: DESC)
            since_date (str, optional): Filter posts since date (format: YYYY-MM-DD)
            captions_only (bool, optional): If True, only return captions and sponsorship flags
            
        Returns:
            List[Dict]: List of post data dictionaries
        """
        try:
            with get_db_context() as (conn, cursor):
                # Build query with parameters
                if captions_only:
                    # Only select caption and sponsorship fields
                    query = "SELECT caption_text, is_paid_partnership, has_sponsorship_keywords, username, taken_at_formatted FROM instagram_posts WHERE 1=1"
                else:
                    # Select all fields
                    query = "SELECT * FROM instagram_posts WHERE 1=1"
                
                params = []
                
                # Add filters
                if username:
                    query += " AND username = ?"
                    params.append(username)
                
                
                if since_date:
                    query += " AND taken_at_formatted >= ?"
                    params.append(since_date)
                
                # Add ordering
                valid_columns = ["taken_at", "like_count", "comment_count", "scrape_date"]
                if order_by not in valid_columns:
                    order_by = "taken_at"
                    
                valid_orders = ["ASC", "DESC"]
                if order.upper() not in valid_orders:
                    order = "DESC"
                    
                query += f" ORDER BY {order_by} {order.upper()}"
                
                # Add limit only if specified
                if limit is not None:
                    query += " LIMIT ?"
                    params.append(limit)
                
                # Execute query
                cursor.execute(query, params)
                rows = cursor.fetchall()
                
                # Get column names
                column_names = [description[0] for description in cursor.description]
                
                # Convert to list of dictionaries
                results = []
                for row in rows:
                    post_dict = {}
                    for i, value in enumerate(row):
                        # Convert SQLite integer booleans back to Python booleans
                        if column_names[i] in ["is_verified", "is_paid_partnership", "has_sponsorship_keywords"]:
                            post_dict[column_names[i]] = bool(value)
                        else:
                            post_dict[column_names[i]] = value
                    
                    # Only process tagged_users if we're not in captions_only mode and the field exists
                    if not captions_only and "tagged_users" in post_dict and post_dict.get("tagged_users"):
                        tagged_list = []
                        for tag in post_dict["tagged_users"].split(";"):
                            if ":" in tag:
                                username, full_name = tag.split(":", 1)
                                tagged_list.append({"user": {"username": username, "full_name": full_name}})
                        post_dict["tagged_users"] = tagged_list
                    elif not captions_only and "tagged_users" in post_dict:
                        post_dict["tagged_users"] = []
                        
                    results.append(post_dict)
                    
                logger = logging.getLogger(__name__)
                logger.info(f"Loaded {len(results)} posts from database")
                return results
                
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error loading posts from database: {str(e)}")
            return []

    @staticmethod
    def load_tagged_users_from_ads():
        """
        Load tagged users from ad posts and construct Instagram profile URLs.
        
        This method queries the database for posts that are ads (either paid partnerships
        or containing sponsorship keywords), extracts the tagged users from these posts,
        and constructs Instagram profile URLs for each tagged user.
        
        Returns:
            List[Dict]: List of dictionaries containing username and profile_url
        """
        try:
            with get_db_context() as (conn, cursor):
                # Query for posts that are ads (paid partnerships or have sponsorship keywords)
                query = """
                SELECT tagged_users 
                FROM instagram_posts 
                WHERE (is_paid_partnership = 1 OR has_sponsorship_keywords = 1) 
                AND tagged_users IS NOT NULL 
                AND tagged_users != ''
                """
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                # Process tagged users
                tagged_users_set = set()  # Use a set to avoid duplicates
                result = []
                
                for row in rows:
                    tagged_users_str = row[0]
                    
                    # Skip if no tagged users
                    if not tagged_users_str:
                        continue
                    
                    # Split by semicolon to get individual user entries
                    user_entries = tagged_users_str.split(';')
                    
                    for entry in user_entries:
                        # Split by colon to separate username and full name
                        if ':' in entry:
                            username, _ = entry.split(':', 1)  # We only need the username
                            
                            # Skip if already processed
                            if username in tagged_users_set:
                                continue
                            
                            # Add to set to avoid duplicates
                            tagged_users_set.add(username)
                            
                            # Construct Instagram profile URL
                            profile_url = f"https://www.instagram.com/{username}/"
                            
                            # Add to result
                            result.append({
                                'username': username,
                                'profile_url': profile_url
                            })
                
                logger = logging.getLogger(__name__)
                logger.info(f"Loaded {len(result)} unique tagged users from ad posts")
                return result
                
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error loading tagged users from ad posts: {str(e)}")
            return []


# Example usage
async def main():
    """
    Example usage of the Instagram Posts Scraper.
    """
    
    # Normal usage
    scraper = InstagramPostsScraper()
    
    # Example: scrape posts from multiple public accounts
    usernames = ["tika_andhini", "ugcwithkrystle", "ugcbymelody"]  # Replace with desired usernames
    max_limit = 10  # Maximum number of posts to scrape per username
    
    # Normal scraping (respects 1-week interval)
    success = await scraper.scrape_and_save_multiple(usernames, max_limit)
    
    if success:
        print(f"Posts saved to database: {scraper.db_path}")
        
        # Example: Load and display results from database
        print("\nScraped Users:")
        users = scraper.get_scraped_users()
        for user in users:
            print(f"- {user['username']} (Last scraped: {user['last_scraped']})")
        
        print("\nRecent Posts:")
        posts = scraper.load_posts_from_db(limit=5, order_by="taken_at", order="DESC")
        for post in posts:
            print(f"- {post['username']} ({post['taken_at_formatted']}): {post['caption_text'][:50]}...")
        
        # Example: Filter posts with sponsorships
        sponsored_posts = scraper.load_posts_from_db(has_sponsorship=True, limit=3)
        print(f"\nFound {len(sponsored_posts)} sponsored posts")
    else:
        print("Failed to scrape posts")


if __name__ == "__main__":
    asyncio.run(main())