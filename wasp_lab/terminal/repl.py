import cmd
import sys
import json
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8001"

def api_post(endpoint, data=None):
    try:
        req = urllib.request.Request(f"{API_URL}{endpoint}", method="POST")
        if data:
            req.add_header('Content-Type', 'application/json')
            req.data = json.dumps(data).encode('utf-8')
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"[Error] API POST request to {endpoint} failed: {e}\n(Make sure the server is running via 'wasp server')")
        return None

def api_get(endpoint):
    try:
        req = urllib.request.Request(f"{API_URL}{endpoint}")
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"[Error] API GET request to {endpoint} failed: {e}\n(Make sure the server is running via 'wasp server')")
        return None

class WaspREPL(cmd.Cmd):
    intro = (
        "===========================================================\n"
        "       WASP Network Lab - Interactive Terminal Client\n"
        "===========================================================\n"
        "Commands:\n"
        "  status, start, stop, pause, resume, step, toggle, topology\n"
        "  router <id>, node <id>, inject <name>, events, report, help, exit\n"
    )
    prompt = "wasp/network> "
    
    def __init__(self):
        super().__init__()
        self.mode = "network"
        self.router_id = None
        
    def update_prompt(self):
        if self.mode == "network":
            self.prompt = "wasp/network> "
        else:
            self.prompt = f"wasp/router/{self.router_id}> "
            
    def do_status(self, arg):
        """Get simulation status and elapsed clock: status"""
        data = api_get("/status")
        if data:
            print(f"Engine Status : {data.get('status')}\nSimulated Time: {data.get('time', 0):.2f}s\nWorld Mode    : {data.get('world_mode', 'ON')}")
            
    def do_start(self, arg):
        """Start simulation: start"""
        res = api_post("/start")
        if res:
            print("[Engine] Simulation started.")
        
    def do_stop(self, arg):
        """Stop simulation: stop"""
        res = api_post("/stop")
        if res:
            print("[Engine] Simulation stopped.")

    def do_pause(self, arg):
        """Pause simulation: pause"""
        res = api_post("/pause")
        if res:
            print("[Engine] Simulation paused.")

    def do_resume(self, arg):
        """Resume simulation: resume"""
        res = api_post("/resume")
        if res:
            print("[Engine] Simulation resumed.")

    def do_step(self, arg):
        """Step simulation by 1 tick: step"""
        res = api_post("/step")
        if res:
            print(f"[Engine] Stepped. Time: {res.get('time', 0):.2f}s")
            
    def do_toggle(self, arg):
        """Toggle WASP shield ON/OFF: toggle"""
        res = api_post("/network/toggle_wasp")
        if res:
            print(f"[Engine] WASP Toggled: Enabled = {res.get('wasp_enabled')}, Mode = {res.get('world_mode')}")

    def do_topology(self, arg):
        """Display current network topology: topology"""
        data = api_get("/network/topology")
        if data:
            print("+----------------+------------------------------------------------+")
            print("| Node ID       | Type       | Details                            |")
            print("+----------------+------------------------------------------------+")
            for n in data.get("nodes", []):
                nid = n.get("id")
                ntype = n.get("type")
                details = f"Compromised={n.get('compromised', False)}" if ntype == "router" else ""
                print(f"| {nid:<14} | {ntype:<10} | {details:<34} |")
            print("+----------------+------------------------------------------------+")

    def do_node(self, arg):
        """Inspect state of a node or attacker: node <node_id> (e.g. node r0 or node ATTACKER)"""
        target = arg.strip() if arg.strip() else (self.router_id or "r0")
        data = api_get(f"/node/{target}")
        if data:
            print(json.dumps(data, indent=2))

    def do_inject(self, arg):
        """Inject an Interest packet: inject [content_name] [consumer_id] (default: /c/1 s0)"""
        parts = arg.strip().split()
        name = parts[0] if len(parts) > 0 and parts[0] else "/c/1"
        consumer_id = parts[1] if len(parts) > 1 else "s0"
        res = api_post("/inject", {"consumer_id": consumer_id, "name": name})
        if res:
            trace = res.get("trace", {})
            print(f"[Injected] {name} from {consumer_id}\nOutcome : {trace.get('outcome')}\nHops    : {trace.get('hops')}\nShield  : {trace.get('shielded')}\nLatency : {trace.get('latency_ms', 0):.2f} ms")

    def do_events(self, arg):
        """Show recent simulation events: events"""
        data = api_get("/events")
        if data:
            events = data.get("events", [])[-10:]
            for ev in events:
                print(f"[{ev.get('time', 0):.2f}s] {ev.get('type')} {ev.get('name')}: {ev.get('outcome')} ({ev.get('latency_ms', 0):.1f}ms)")

    def do_report(self, arg):
        """Display simulation metrics report: report"""
        req = urllib.request.Request(f"{API_URL}/api/report")
        try:
            with urllib.request.urlopen(req) as resp:
                print(resp.read().decode())
        except Exception as e:
            print(f"[Error] Failed to fetch report: {e}")

    def do_router(self, arg):
        """Switch to router inspection mode: router <id> (e.g. router r0)"""
        if arg:
            self.mode = "router"
            self.router_id = arg.strip()
            self.update_prompt()
            print(f"Switched to router {self.router_id} inspection mode.")
            self.do_node(self.router_id)
        else:
            print("Usage: router <id>  (e.g., router r0)")

    def do_network(self, arg):
        """Switch back to network control mode: network"""
        self.mode = "network"
        self.router_id = None
        self.update_prompt()
        print("Switched to network mode.")
        
    def do_exit(self, arg):
        """Exit the interactive REPL: exit"""
        print("Exiting WASP Terminal.")
        return True
        
    def do_quit(self, arg):
        """Exit the interactive REPL: quit"""
        return self.do_exit(arg)

def run_terminal():
    WaspREPL().cmdloop()

if __name__ == "__main__":
    run_terminal()
