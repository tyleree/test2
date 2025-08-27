#!/usr/bin/env python3
"""
Startup script to run both Flask and FastAPI servers concurrently.
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path

def run_server(command, name, port):
    """Run a server with the given command."""
    print(f"Starting {name} server on port {port}...")
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        return process
    except Exception as e:
        print(f"Failed to start {name} server: {e}")
        return None

def main():
    """Main function to start both servers."""
    
    # Ensure we're in the right directory
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    print("🚀 Starting Veterans AI RAG Pipeline Servers")
    print("=" * 50)
    
    # Check if .env file exists
    if not Path(".env").exists():
        print("⚠️  Warning: .env file not found. Please copy .env.example to .env and configure your API keys.")
        print("   The servers may not work properly without proper configuration.")
        print()
    
    processes = []
    
    try:
        # Start FastAPI RAG Pipeline server (port 8000)
        fastapi_cmd = "uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
        fastapi_process = run_server(fastapi_cmd, "FastAPI RAG Pipeline", 8000)
        if fastapi_process:
            processes.append(("FastAPI", fastapi_process))
        
        # Wait a moment for FastAPI to start
        time.sleep(2)
        
        # Start Flask frontend server (port 5000)  
        flask_cmd = "python app.py"
        flask_process = run_server(flask_cmd, "Flask Frontend", 5000)
        if flask_process:
            processes.append(("Flask", flask_process))
        
        if not processes:
            print("❌ Failed to start any servers")
            return 1
        
        print()
        print("✅ Servers started successfully!")
        print(f"📊 FastAPI RAG Pipeline: http://localhost:8000")
        print(f"🌐 Flask Frontend: http://localhost:5000")
        print(f"📚 API Documentation: http://localhost:8000/docs")
        print(f"📈 Admin Analytics: http://localhost:5000/admin/analytics?token=your-admin-token")
        print()
        print("Press Ctrl+C to stop all servers")
        print("=" * 50)
        
        # Monitor processes
        while True:
            time.sleep(1)
            
            # Check if any process has died
            for name, process in processes:
                if process.poll() is not None:
                    print(f"⚠️  {name} server has stopped")
                    return 1
    
    except KeyboardInterrupt:
        print("\n🛑 Shutting down servers...")
        
        # Terminate all processes
        for name, process in processes:
            try:
                print(f"Stopping {name} server...")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"Force killing {name} server...")
                process.kill()
            except Exception as e:
                print(f"Error stopping {name} server: {e}")
        
        print("✅ All servers stopped")
        return 0
    
    except Exception as e:
        print(f"❌ Error running servers: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())



