# Leads Workflow Dashboard - User Guide

This guide explains how to install, launch, and use the Leads Workflow Dashboard application.

## Installation and Setup

No installation is needed! The application comes as a standalone executable file that contains everything you need to run the dashboard.

## Launching the Application

### Using the Executable

1. Navigate to the folder where you downloaded the application
2. Double-click on the `content-create-agent.exe` file
3. The dashboard will automatically:
   - Start the required background services
   - Open the dashboard in your default web browser
   - Initialize the necessary components

**Note**: If the browser doesn't open automatically, you can manually access the dashboard at `http://localhost:8080`

### Alternative Launch Methods

You can also use the provided shortcut batch file:

1. Double-click on the `run.bat` file in the application folder
2. The application will launch automatically

## Dashboard Overview

The Leads Workflow Dashboard provides a modern interface for Instagram collaboration search and messaging, with two main modules:

- **Search Module**: Find Instagram profiles based on niche and location
- **Message Module**: Automate messaging to Instagram profiles

## Using the Search Module

### Starting a Search

1. Click on the "Search" tab in the sidebar
2. Fill in the search form:
   - **Niche** (required): Enter the industry or niche (e.g., "fitness", "beauty", "tech")
   - **Location** (optional): Specify a location (e.g., "New York", "London")
   - **Max Results**: Set the number of profiles to find (default: 50)
   - **Max Pages**: Set the number of pages to search (default: 5)
3. Click "Start Search" to begin

### Working with Search Results

1. After the search completes, results will appear in the table below the form
2. You can:
   - View profile details directly in the table
   - Sort the results by clicking on column headers
   - Download results as a CSV file using the "Download CSV" button
   - Use the results directly for the messaging workflow

## Using the Message Module

### Setting Up the Message Workflow

1. Click on the "Message" tab in the sidebar
2. Choose one of the following options:
   - Use the results from a previous search
   - Upload a CSV file with Instagram profile URLs
   - Enter profile URLs manually

### CSV Upload Requirements

If uploading a CSV file, ensure it includes at least:
- A `profile_url` column with valid Instagram profile URLs

### Automating Messages

1. Start chatting with the AI assistant in the message interface
2. The assistant will guide you through setting up your messaging campaign
3. You can:
   - Define your campaign goals
   - Create message templates
   - Set targeting criteria
   - Monitor progress

### Using Interactive Features

The messaging interface includes:
- **Chat Input**: Type your instructions or questions
- **Interrupt Options**: Use the clickable buttons to quickly modify the workflow
- **Status Updates**: View real-time progress of your messaging campaign
- **Session Management**: Continue from where you left off in previous sessions

## Configuration

Click on the gear icon (⚙️) in the top-right corner to access the configuration editor where you can:
- Adjust application settings
- Set default parameters
- Customize workflows

## Troubleshooting

### Common Issues and Solutions

1. **Application Doesn't Launch**:
   - Ensure your antivirus isn't blocking the application
   - Try running as administrator

2. **Connection Error**:
   - Check that your internet connection is active
   - The application requires internet access for Instagram interactions

3. **Search Not Working**:
   - Ensure the "Niche" field is filled (required)
   - Try using more general keywords

4. **CSV Upload Errors**:
   - Verify your CSV file has the required `profile_url` column
   - Check that the CSV formatting is correct

5. **Session Issues**:
   - Click the refresh button next to "Session" to create a new session
   - If problems persist, restart the application

## Privacy and Security

- The application runs locally on your machine
- Your data and search results are stored only on your computer
- No account information is sent to external servers

## Getting Help

For additional support:
1. Check the README.md file for more detailed information
2. Visit our support portal (link in the About section of the dashboard)
3. Submit issues through our GitHub repository
