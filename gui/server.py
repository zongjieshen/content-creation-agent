import os
import sys
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler

class NoCacheHTTPRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Add no-cache headers
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

def main():
    # Serve files from the current directory
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, NoCacheHTTPRequestHandler)
    print(f"GUI server started at http://localhost:8080")
    
    # Open the browser
    webbrowser.open('http://localhost:8080')
    
    # Start the server
    httpd.serve_forever()

if __name__ == "__main__":
    # Change to the directory containing this script
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    main()
