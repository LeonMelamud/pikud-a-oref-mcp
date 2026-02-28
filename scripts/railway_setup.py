#!/usr/bin/env python3
"""Configure Railway services via GraphQL API"""
import json
import urllib.request
import sys

TOKEN = json.load(open("/Users/leon.melamud/.railway/config.json"))["user"]["token"]
ENV_ID = "a78db729-d730-465c-9390-c1b83450ed4c"

SERVICES = {
    "mcp-tools": {
        "id": "6e98deae-8c33-4c76-b65f-c4e3ba2f5477",
        "dockerfilePath": "docker/mcp.Dockerfile",
        "healthcheckPath": "/mcp",
        "healthcheckTimeout": 15,
    },
    "sse-relay": {
        "id": "5be9926a-ed21-4225-879b-32284d1f6d7e",
        "dockerfilePath": "docker/sse.Dockerfile",
        "healthcheckPath": "/health",
        "healthcheckTimeout": 10,
    },
}

def graphql(query, variables=None):
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://backboard.railway.com/graphql/v2",
        data=data,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  HTTP {e.code}: {body[:200]}")
        return {"errors": [{"message": f"HTTP {e.code}"}]}

def update_service(name, config):
    service_id = config.pop("id")
    query = """mutation($serviceId: String!, $environmentId: String!, $input: ServiceInstanceUpdateInput!) {
        serviceInstanceUpdate(serviceId: $serviceId, environmentId: $environmentId, input: $input)
    }"""
    result = graphql(query, {
        "serviceId": service_id,
        "environmentId": ENV_ID,
        "input": config,
    })
    if "errors" in result:
        print(f"  ERROR: {result['errors'][0]['message']}")
        return False
    print(f"  OK: {result['data']}")
    return True

def generate_domain(service_id):
    query = """mutation($input: CustomDomainCreateInput!) {
        customDomainCreate(input: $input) { id domain { domain } }
    }"""
    # Try service domain instead
    query2 = """mutation($serviceId: String!, $environmentId: String!) {
        serviceDomainCreate(serviceId: $serviceId, environmentId: $environmentId) { domain }
    }"""
    result = graphql(query2, {"serviceId": service_id, "environmentId": ENV_ID})
    if "errors" in result:
        print(f"  Domain error: {result['errors'][0]['message']}")
        return None
    domain = result["data"]["serviceDomainCreate"]["domain"]
    print(f"  Domain: https://{domain}")
    return domain

if __name__ == "__main__":
    for name, config in SERVICES.items():
        sid = config["id"]
        print(f"\n=== Configuring {name} ===")
        update_service(name, dict(config))
        print(f"  Generating domain...")
        generate_domain(sid)
    
    print("\n=== Done! ===")
    print("Now redeploy each service with: railway service link <id> && railway up --detach")
