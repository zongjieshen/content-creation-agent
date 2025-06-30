# Leads Workflow Dashboard

A modern web interface for Instagram collaboration and messaging workflows.

## Features

- **Search Module**: Find Instagram profiles for collaboration opportunities
  - Form-based search with niche, location, max results, and max pages parameters
  - Results display in a table format
  - CSV download functionality
  - Direct integration with messaging workflow

- **Message Module**: Automate messaging to Instagram profiles
  - Chat-based interface for natural conversation
  - CSV file upload support
  - Integration with search results
  - Interrupt handling with clickable options
  - Session persistence

## Setup and Running

### Prerequisites

1. Python 3.7+ installed
2. Required Python packages (install from the main project directory):
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

1. **Start the Leads API Server** (from the main project directory):
   ```bash
   cd c:\Users\Zongjie\Documents\GitHub\content-create-agent
   python -m src.leads.leads_server
   ```
   
   The API server will start on `http://localhost:8001`

2. **Start the GUI Server** (from the gui directory):
   ```bash
   cd c:\Users\Zongjie\Documents\GitHub\content-create-agent\gui
   python server.py
   ```
   
   The GUI will be available at `http://localhost:8080` and should open automatically in your browser.

## Usage

### Search Workflow

1. Click on the "Search" tab in the sidebar
2. Fill in the search form:
   - **Niche**: Required field (e.g., "fitness", "beauty", "tech")
   - **Location**: Optional (e.g., "New York", "London")
   - **Max Results**: Number of profiles to find (default: 50)
   - **Max Pages**: Number of pages to search (default: 5)
3. Click "Start Search" to begin the collaboration search
4. View results in the table below
5. Download results as CSV or use directly for messaging

### Messaging Workflow

1. Click on the "Message" tab in the sidebar
2. Upload a CSV file with profile URLs or use search results
3. Start chatting with the AI to set up your messaging campaign
4. Use interrupt options (buttons) for quick responses
5. Monitor the conversation and provide input as needed

## API Endpoints Used

- `GET /create_session` - Create a new session
- `POST /generate` - Send messages to workflows
- `POST /upload_csv` - Upload CSV files
- `GET /session/{session_id}/status` - Check session status

## File Structure

```
gui/
├── index.html          # Main HTML file
├── styles.css          # CSS styling
├── app.js             # JavaScript functionality
├── server.py          # Simple HTTP server
└── README.md          # This file
```

## Features

- **Modern UI**: Clean, responsive design similar to calendar applications
- **Session Management**: Persistent sessions that don't reset
- **Tab-based Navigation**: Switch between Search and Message modules
- **Real-time Updates**: Live status updates and messaging
- **CSV Integration**: Upload, download, and process CSV files
- **Interrupt Handling**: Interactive workflow management
- **Mobile Responsive**: Works on desktop and mobile devices

## Troubleshooting

1. **Connection Error**: Make sure the leads server is running on port 8002
2. **Session Issues**: Refresh the page to create a new session
3. **CSV Upload Errors**: Ensure CSV has required columns (especially 'profile_url')
4. **Search Not Working**: Check that all required fields are filled

## Development

To modify the interface:

1. Edit `index.html` for structure changes
2. Edit `styles.css` for styling changes
3. Edit `app.js` for functionality changes
4. Refresh the browser to see changes

The interface communicates with the FastAPI backend using REST API calls and maintains session state for workflow continuity.