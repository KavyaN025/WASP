import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="WASP Network Lab CLI")
    parser.add_argument("command", choices=["server", "terminal", "doctor"], help="Command to run (server, terminal, doctor)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind server (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind server (default 8001)")
    
    args = parser.parse_args()
    
    if args.command == "doctor":
        from .doctor import run_doctor
        run_doctor()
    elif args.command == "terminal":
        from .terminal.repl import run_terminal
        run_terminal()
    elif args.command == "server":
        import uvicorn
        uvicorn.run("wasp_lab.server.app:app", host=args.host, port=args.port)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
