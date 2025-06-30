import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

def main():
    # Serve files from the current directory
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, SimpleHTTPRequestHandler)
    print(f"GUI server started at http://localhost:8080")
    
    # Open the browser
    webbrowser.open('http://localhost:8080')
    
    # Start the server
    httpd.serve_forever()

if __name__ == "__main__":
    # Change to the directory containing this script
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()