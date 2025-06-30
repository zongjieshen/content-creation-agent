# Add these imports at the top of the file
from typing import TypedDict, Optional
import logging
import pandas as pd
import asyncio
import argparse
import sys
from src.base_workflow import BaseWorkflow, BaseWorkflowState
from src.video_processing_helper import process_videos_for_analysis, generate_overall_summary
from src.tiktok_topic_trending import get_topic_trending_videos
from langgraph.graph import END

logger = logging.getLogger(__name__)

class VideoAnalysisState(BaseWorkflowState):
    """State for video analysis workflow"""
    user_input: str  # User input from BaseWorkflowState
    keyword: str  # The keyword to analyze
    tiktok_csv_path: Optional[str]  # Path to TikTok CSV file
    final_analysis_csv: Optional[str]  # Path to final analysis CSV
    video_folder_path: Optional[str]  # Path to video folder
    summary_report: Optional[str]  # Generated summary report

class VideoAnalysisWorkflow(BaseWorkflow):
    """Workflow for analyzing TikTok videos for a given keyword"""
    
    def get_state_class(self):
        return VideoAnalysisState
    
    def define_nodes(self):
        return {
            "download_tiktok_videos": self.download_tiktok_videos,
            "analyze_videos": self.analyze_videos,
            "generate_summary": self.generate_summary
        }
    
    def define_edges(self, workflow):
        workflow.add_edge("download_tiktok_videos", "analyze_videos")
        workflow.add_edge("analyze_videos", "generate_summary")
        workflow.add_edge("generate_summary", END)
    
    def get_entry_point(self) -> str:
        return "download_tiktok_videos"
    
    async def download_tiktok_videos(self, state: VideoAnalysisState):
        """Download TikTok videos based on the keyword."""
        state = self.update_step(state, "tiktok_download")
        
        keyword = state["user_input"].strip().lstrip('#')
        state["keyword"] = keyword
        
        if not keyword:
            state["error_message"] = "No keyword provided for video analysis"
            state["workflow_status"] = "error"
            return state
        
        try:
            logger.info(f"Starting TikTok video download for keyword: {keyword}")
            
            # Get the result with DataFrame
            result = await get_topic_trending_videos(
                topic=keyword,
                limit=100,
                download_top=10
            )
            
            if 'error' in result:
                logger.error(f"Failed to download TikTok videos: {result['error']}")
                state["error_message"] = f"Failed to download TikTok videos: {result['error']}"
                state["workflow_status"] = "error"
                return state
            
            logger.info(f"Successfully analyzed {result['total_videos']} videos for #{keyword}")
            
            # Store paths for next steps
            state["tiktok_csv_path"] = result['csv_path']
            state["video_folder_path"] = result['hashtag_dir']
            state["workflow_status"] = "downloaded"
            
        except Exception as e:
            logger.error(f"Error downloading TikTok videos: {e}")
            state["error_message"] = f"Error downloading TikTok videos: {str(e)}"
            state["workflow_status"] = "error"
        
        return state
    
    async def analyze_videos(self, state: VideoAnalysisState):
        """Analyze downloaded TikTok videos using video_processing_helper."""
        state = self.update_step(state, "video_analysis")
        
        keyword = state.get("keyword", "")
        csv_path = state.get("tiktok_csv_path", "")
        video_folder_path = state.get("video_folder_path", "")
        
        if not csv_path or not keyword:
            logger.error("Missing required data for video analysis")
            state["error_message"] = "Missing required data for video analysis"
            state["workflow_status"] = "error"
            return state
        
        try:
            logger.info(f"Starting video analysis for keyword: {keyword}")
            if video_folder_path:
                logger.info(f"Using video folder: {video_folder_path}")
            
            # Read the TikTok CSV file
            df = pd.read_csv(csv_path)
            
            if df.empty:
                logger.warning("Empty CSV file for analysis")
                state["error_message"] = "No videos found for analysis"
                state["workflow_status"] = "error"
                return state
            
            # Process videos for analysis with reduced concurrency to prevent API overload
            analyzed_df = process_videos_for_analysis(
                df=df,
                max_workers=2,  # Reduced to prevent API overload
                output_path=csv_path,  # Overwrite the original CSV with analysis results
                video_folder_path=video_folder_path
            )
            
            logger.info(f"Video analysis complete. Analyzed {len(analyzed_df)} videos with detailed performance insights.")
            
            state["final_analysis_csv"] = csv_path
            state["workflow_status"] = "analyzed"
            
        except Exception as e:
            error_msg = f"Video analysis failed: {str(e)}"
            logger.error(f"Error in video analysis: {error_msg}")
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state
    
    async def generate_summary(self, state: VideoAnalysisState):
        """Generate overall summary report from analyzed videos."""
        state = self.update_step(state, "summary_generation")
        
        csv_path = state.get("final_analysis_csv", "")
        keyword = state.get("keyword", "")
        
        if not csv_path or not keyword:
            logger.error("Missing required data for summary generation")
            state["error_message"] = "Missing required data for summary generation"
            state["workflow_status"] = "error"
            return state
        
        try:
            logger.info(f"Generating performance summary for keyword: {keyword}")
            
            # Read the analyzed CSV file
            df = pd.read_csv(csv_path)
            
            if df.empty:
                logger.warning("Empty analysis file for summary generation")
                state["error_message"] = "No analysis data available for summary"
                state["workflow_status"] = "error"
                return state
            
            # Generate the overall summary using the helper function
            summary_report = generate_overall_summary(df)
            
            # Save summary to file
            from pathlib import Path
            summary_path = Path(csv_path).parent / f"{keyword}_performance_summary.md"
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(summary_report)
            
            logger.info(f"Performance summary generated and saved to: {summary_path}")
            logger.info(f"Summary preview:\n{summary_report[:500]}...")
            
            state["summary_report"] = summary_report
            state["workflow_status"] = "completed"
            
        except Exception as e:
            error_msg = f"Summary generation failed: {str(e)}"
            logger.error(f"Error in summary generation: {error_msg}")
            state["error_message"] = error_msg
            state["workflow_status"] = "error"
        
        return state

# Create workflow instance
video_analysis_workflow = VideoAnalysisWorkflow()

# Add this at the end of the file
async def run_workflow(keyword: str):
    """Run the video analysis workflow with the given keyword"""
    # Initialize state with user input
    
    # Run the workflow
    result = await video_analysis_workflow.run(keyword)
    
    if result.get("error_message"):
        print(f"\nError: {result['error_message']}")
        return False
    
    # Print summary report
    if result.get("summary_report"):
        print("\n===== ANALYSIS SUMMARY =====\n")
        print(result["summary_report"])
        print(f"\nSummary saved to: {result.get('final_analysis_csv', '').replace('.csv', '_performance_summary.md')}")
    
    return True

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("video_analysis.log")
        ]
    )

def main():
    """Main function to run the script"""
    # Set up logging
    setup_logging()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Analyze TikTok videos for a given keyword")
    parser.add_argument("keyword", help="Keyword or hashtag to analyze (without the # symbol)")
    
    # Get the keyword from arguments
    keyword = 'collagendrink'
    
    if not keyword:
        print("Error: No keyword provided")
        return 1
    
    print(f"Starting video analysis for keyword: {keyword}")
    
    # Run the workflow
    try:
        result = asyncio.run(run_workflow(keyword))
        return 0 if result else 1
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        return 130
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
