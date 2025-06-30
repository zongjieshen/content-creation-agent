import asyncio
import aiohttp
import json
import time
import os
from typing import Dict, Any

# Configuration
SERVER_URL = "http://localhost:8001"  # Adjust port as needed

class LeadsServerDebugger:
    def __init__(self, base_url: str = SERVER_URL):
        self.base_url = base_url
        self.session_id = None
    
    async def create_session(self) -> str:
        """Create a new session for testing"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/create_session") as response:
                if response.status == 200:
                    data = await response.json()
                    self.session_id = data["session_id"]
                    print(f"✅ Created session: {self.session_id}")
                    return self.session_id
                else:
                    raise Exception(f"Failed to create session: {response.status}")
    
    async def send_message(self, message: str, workflow_type: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a message to the leads server and stream the response"""
        if not self.session_id:
            await self.create_session()
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": message
                }
            ],
            "user_id": "debug_user",
            "session_id": self.session_id,
            "workflow_type": workflow_type,
            "parameters": parameters or {}
        }
        
        print(f"\n🚀 Sending message: {message}")
        print(f"📋 Workflow type: {workflow_type}")
        print(f"⚙️ Parameters: {parameters}")
        print("\n📡 Streaming response:")
        print("-" * 50)
        
        interrupt_data = None
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/generate",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    # Read the entire response as JSON
                    response_json = await response.json()
                    
                    # Extract message content
                    if response_json.get('choices') and len(response_json['choices']) > 0:
                        choice = response_json['choices'][0]
                        message_content = choice.get('message', {}).get('content', '')
                        finish_reason = choice.get('finish_reason', '')
                        options = choice.get('options', [])
                        
                        if message_content.strip():
                            print(f"💬 {message_content}", flush=True)
                        
                        if options:
                            print(f"🔘 Options: {options}", flush=True)
                    
                    # Show workflow status and interrupt data
                    workflow_status = response_json.get('workflow_status')
                    interrupt_data = response_json.get('interrupt_data')
                    
                    if workflow_status:
                        print(f"📊 Workflow Status: {workflow_status}")
                    
                    if interrupt_data:
                        print(f"⏸️ Interrupt Data: {interrupt_data}")
                        
                        # Display options from interrupt_data if available
                        if 'data' in interrupt_data and 'options' in interrupt_data['data']:
                            options = interrupt_data['data']['options']
                            print(f"🔘 Available options: {options}")
                            
                            # Automatically handle options if needed
                            # For example, you could implement auto-selection logic here
                    
                    return interrupt_data
                    
                else:
                    error_text = await response.text()
                    print(f"❌ Error {response.status}: {error_text}")
        
        return {"interrupt_data": interrupt_data}
    
    async def get_session_status(self) -> Dict[str, Any]:
        """Get current session status"""
        if not self.session_id:
            return {"error": "No session created"}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/session/{self.session_id}/status") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Status {response.status}"}
    
    async def list_workflows(self) -> Dict[str, Any]:
        """List available workflows"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/workflows") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Status {response.status}"}
    
    async def health_check(self) -> Dict[str, Any]:
        """Check server health"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/health") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    return {"error": f"Status {response.status}"}

async def test_csv_upload_and_message():
    """Test CSV upload and messaging workflow with automatic interrupt handling"""
    debugger = LeadsServerDebugger()
    
    print("\n📤 Testing CSV Upload and Messaging with Automatic Interrupt Handling")
    print("=" * 60)
    
    # Path to the CSV file
    csv_path = "c:\\Users\\Zongjie\\Documents\\GitHub\\content-create-agent\\uploads\\instagram_sample.csv"
    
    # Upload the CSV file
    # Create a temporary copy of the file
    import shutil
    temp_csv_path = csv_path + ".temp"
    shutil.copy2(csv_path, temp_csv_path)
    
    async with aiohttp.ClientSession() as session:
        # Create a form with the temporary file
        with open(temp_csv_path, 'rb') as f:
            form_data = aiohttp.FormData()
            form_data.add_field('file', 
                               f,
                               filename=os.path.basename(csv_path),
                               content_type='text/csv')
            
            # Send the upload request
            async with session.post(
                f"{debugger.base_url}/upload_csv",
                data=form_data
            ) as response:
                if response.status == 200:
                    upload_result = await response.json()
                    print(f"✅ CSV uploaded successfully: {upload_result['filename']}")
                    print(f"� File saved at: {upload_result['filepath']}")
                    
                    # Now use the uploaded file for messaging
                    result = await debugger.send_message(
                        message=f"Send messages to Instagram profiles from the uploaded CSV file {upload_result['filepath']}",
                        workflow_type="messaging",
                        parameters={
                            "csv_path": upload_result['filepath'],
                            "message_template": "Hi! I'd love to collaborate with you on fitness content.",
                            "delay_between_messages": 5,
                            "max_profiles": 3
                        }
                    )
                    
                    # Handle interrupts that require human input
                    while result.get("status") == "awaiting_human_input" and result.get("data"):
                        interrupt_type = result["data"].get("type")
                        options = result["data"].get("options", [])
                        response_message = options[0] if options else "Continue"
                        
                        if interrupt_type == "login_confirmation":
                            print("\n🔐 Detected login confirmation interrupt, automatically responding...")
                            await asyncio.sleep(2)  # Small delay for readability
                            
                            # Send confirmation to proceed with login
                            result = await debugger.send_message(
                                message=response_message,
                                workflow_type="messaging"
                            )
                        elif interrupt_type == "message_confirmation":
                            print("\n📨 Detected message confirmation interrupt, automatically responding...")
                            await asyncio.sleep(2)  # Small delay for readability
                            
                            # Send confirmation to send the message
                            result = await debugger.send_message(
                                message=options[1],
                                workflow_type="messaging"
                            )
                        elif interrupt_type == "edit_confirmation":
                            print("\n📨 Detected edit message confirmation interrupt, automatically responding...")
                            await asyncio.sleep(2)  # Small delay for readability
                            
                            # Send confirmation to send the message
                            result = await debugger.send_message(
                                message=options[0],
                                workflow_type="messaging"
                            )
                        else:
                            print(f"\n⚠️ Unknown interrupt type: {interrupt_type}, breaking loop")
                            break
                else:
                    error_text = await response.text()
                    print(f"❌ Error uploading CSV: {response.status} - {error_text}")
    
    # Clean up the temporary file
    try:
        os.remove(temp_csv_path)
    except Exception as e:
        print(f"Warning: Could not remove temporary file: {e}")
    
    # Check session status
    status = await debugger.get_session_status()
    print(f"\n📊 Session Status: {json.dumps(status, indent=2)}")

async def test_collaboration_workflow():
    """Test Instagram collaboration workflow"""
    debugger = LeadsServerDebugger()
    
    print("\n📊 Testing Instagram Collaboration Workflow")
    print("=" * 60)
    
    # Test parameters
    niche = "fresh food"
    location = "sydney"
    max_results = 5
    max_pages = 3
    
    # Send message to trigger collaboration workflow
    message = f"Find Instagram collaboration opportunities\nniche: {niche}\nlocation: {location}\nmax_results: {max_results}\nmax_pages: {max_pages}"
    
    result = await debugger.send_message(
        message=message,
        workflow_type="collaboration",
        parameters={
            "niche": niche,
            "location": location,
            "max_results": max_results,
            "max_pages": max_pages
        }
    )
    
    # Handle any interrupts if needed
    while result and isinstance(result, dict) and result.get("status") == "awaiting_human_input" and result.get("data"):
        interrupt_type = result["data"].get("type")
        options = result["data"].get("options", [])
        response_message = options[0] if options else "Continue"
        
        print(f"\n⏸️ Detected interrupt: {interrupt_type}")
        print(f"🔘 Automatically responding with: {response_message}")
        await asyncio.sleep(1)  # Small delay for readability
        
        # Send response to continue workflow
        result = await debugger.send_message(
            message=response_message,
            workflow_type="collaboration"
        )
    
    # Check session status
    status = await debugger.get_session_status()
    print(f"\n📊 Session Status: {json.dumps(status, indent=2)}")
    
    return result

async def main():
    """Main debug function"""
    debugger = LeadsServerDebugger()
    
    try:
        # Health check
        print("🏥 Health Check")
        health = await debugger.health_check()
        print(f"Health: {health}")
        
        # List workflows
        print("\n📋 Available Workflows")
        workflows = await debugger.list_workflows()
        print(f"Workflows: {json.dumps(workflows, indent=2)}")
        
        # Test collaboration workflow
        await test_collaboration_workflow()
        
        # Test messaging workflow
        #await test_messaging_workflow()
        
        # Test interrupt/resume
        #await test_interrupt_resume()
        
        # Test CSV upload and messaging
        #await test_csv_upload_and_message()
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Set Windows event loop if needed
    import os
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    print("🚀 Starting Leads Server Debug Session")
    print(f"🌐 Server URL: {SERVER_URL}")
    print("\nMake sure your leads server is running first!")
    print("To start the server, run: python -m src.leads.leads_server")
    print("\n" + "=" * 60)
    
    asyncio.run(main())

