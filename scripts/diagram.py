from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.network import Haproxy
from diagrams.onprem.client import User
from diagrams.programming.language import Python
from diagrams.generic.network import Subnet
from diagrams.onprem.compute import Server
from diagrams.aws.general import Client
from diagrams.generic.storage import Storage
from diagrams.programming.framework import React

with Diagram("Pikud Haoref Real-Time Alert System - Pub/Sub Architecture", show=False, filename="poha_sse_architecture"):

    # External Data Source
    poha_api = Haproxy("Pikud Haoref API\n(oref.org.il)")

    # Client applications
    web_client = User("Web Clients")
    vscode_extension = React("VS Code Extension\n(pikud-haoref-alerts)")
    ai_client = Client("AI Assistants\n(MCP)")

    # The FastAPI Middleware Service (Publisher)
    with Cluster("FastAPI Middleware (Publisher)"):
        # The single poller that queries the API
        poller = Python("Single API Poller\n(polling.py)")
        
        # SSE endpoints with authentication
        client_sse = Subnet("Client SSE Endpoint\n/api/alerts-stream\n🔐 Authenticated")
        webhook_sse = Storage("Webhook SSE Endpoint\n/api/webhook/alerts\n🔐 Authenticated")
        
        # Poller publishes to both endpoints
        poller >> Edge(label="Publishes alerts", style="bold", color="orange") >> client_sse
        poller >> Edge(label="Publishes alerts", style="bold", color="orange") >> webhook_sse

    # The MCP Server (Subscriber)
    with Cluster("MCP Server (Subscriber)"):
        mcp_server = Server("SSE Client + Tools\n(mcp_server.py)")

    # Define the primary data flow
    # 1. Single polling source
    poha_api >> Edge(label="1. API Response\n(JSON data)", style="dashed", color="blue") >> poller
    poller >> Edge(label="1. Polling Request\n(every 2s)", style="dashed", color="darkblue") >> poha_api
    
    # 2. Pub-sub connections with authentication
    client_sse >> Edge(label="2a. SSE Stream\n🔐 API Key", color="firebrick", style="bold") >> web_client
    client_sse >> Edge(label="2b. SSE Stream\n🔐 API Key", color="orange", style="bold") >> vscode_extension
    webhook_sse >> Edge(label="2c. SSE Stream\n🔐 API Key", color="purple", style="bold") >> mcp_server
    mcp_server >> Edge(label="2d. MCP Tools\n(real-time data)", color="green", style="bold") >> ai_client
    
    # Client authentication connections
    web_client >> Edge(label="Authenticates +\nSubscribes", style="dotted", color="red") >> client_sse
    vscode_extension >> Edge(label="Authenticates +\nSubscribes", style="dotted", color="orange") >> client_sse
    mcp_server >> Edge(label="Authenticates +\nSubscribes", style="dotted", color="purple") >> webhook_sse
    ai_client >> Edge(label="Calls MCP\nTools", style="dotted", color="green") >> mcp_server 