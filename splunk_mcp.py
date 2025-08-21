#!/usr/bin/env python3
import sys
import json
import asyncio
import aiohttp
from dotenv import load_dotenv
import os

# --- Load secrets from .env file ---
load_dotenv()
SPLUNK_URL = os.getenv("SPLUNK_URL", "https://splunk.example.com:8089")
SPLUNK_TOKEN = os.getenv("SPLUNK_TOKEN", "")

# --- Global cache of Splunk state ---
SPLUNK_STATE = {
    "indexes": [],
    "datamodels": {},
    "apps": []
}


# --- SPLUNK METADATA LOADER ---
async def load_splunk_metadata():
    headers = {"Authorization": f"Bearer {SPLUNK_TOKEN}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        # Indexes
        async with session.get(f"{SPLUNK_URL}/services/data/indexes?output_mode=json", ssl=False) as resp:
            data = await resp.json()
            SPLUNK_STATE["indexes"] = [e["name"] for e in data.get("entry", [])]

        # Datamodels
        async with session.get(f"{SPLUNK_URL}/services/datamodel?output_mode=json", ssl=False) as resp:
            dmdata = await resp.json()
            for entry in dmdata.get("entry", []):
                name = entry["name"]
                SPLUNK_STATE["datamodels"][name] = entry["content"]["objects"]

        # Installed Apps
        async with session.get(f"{SPLUNK_URL}/services/apps/local?output_mode=json", ssl=False) as resp:
            appdata = await resp.json()
            SPLUNK_STATE["apps"] = [e["name"] for e in appdata.get("entry", [])]

    sys.stderr.write(f"[MCP] Loaded indexes: {SPLUNK_STATE['indexes']}\n")
    sys.stderr.write(f"[MCP] Loaded datamodels: {list(SPLUNK_STATE['datamodels'].keys())}\n")
    sys.stderr.write(f"[MCP] Loaded apps: {SPLUNK_STATE['apps']}\n")


# --- SPLUNK SEARCH RUNNER ---
async def splunk_search(query, earliest="-24h", latest="now"):
    headers = {"Authorization": f"Bearer {SPLUNK_TOKEN}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. Create search job
        async with session.post(
            f"{SPLUNK_URL}/services/search/jobs?output_mode=json",
            data={"search": query, "earliest_time": earliest, "latest_time": latest},
            ssl=False
        ) as resp:
            job = await resp.json()
            sid = job["sid"]

        # 2. Poll until results ready
        while True:
            async with session.get(
                f"{SPLUNK_URL}/services/search/jobs/{sid}/results?output_mode=json&count=20",
                ssl=False
            ) as r:
                data = await r.json()
                if "results" in data:
                    return data["results"]
            await asyncio.sleep(1)


# --- ENGLISH → SPL TRANSLATION (basic demo) ---
def english_to_spl(question: str) -> str:
    q = question.lower()

    # If failed login question
    if "failed login" in q or "login failure" in q:
        if "Authentication" in SPLUNK_STATE["datamodels"]:
            return '| tstats count from datamodel=Authentication.Authentication ' \
                   'where Authentication.action="failure" earliest=-24h ' \
                   'by Authentication.user'
        else:
            auth_indexes = [i for i in SPLUNK_STATE["indexes"] if "auth" in i.lower() or "winevent" in i.lower()]
            if auth_indexes:
                return f'search index=({" OR ".join(auth_indexes)}) "failed login" earliest=-24h | stats count by user'
            return 'search index=_internal "failed login" | stats count'

    # If process question
    if "process" in q:
        if "Endpoint" in SPLUNK_STATE["datamodels"]:
            return '| tstats count from datamodel=Endpoint.Processes by Processes.process_name'
        return 'search index=endpoint process_name=* | stats count by process_name'

    # Default fallback
    return 'search index=_internal | head 10'


# --- MCP HANDLER ---
async def handle_message(msg):
    method = msg.get("method")

    if method == "initialize":
        return {"name": "SplunkMCP", "version": "0.1.0"}

    elif method == "listResources":
        return {"resources": [
            {"uri": "splunk://metadata", "name": "Splunk Metadata"}
        ]}

    elif method == "readResource":
        if msg["params"]["uri"] == "splunk://metadata":
            return {"contents": [{"type": "json", "json": SPLUNK_STATE}]}

    elif method == "listTools":
        return {"tools": [
            {
                "name": "askSplunk",
                "description": "Ask a question in English, runs translated SPL in Splunk",
                "inputSchema": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"]
                }
            },
            {
                "name": "describeEnvironment",
                "description": "Summarize Splunk environment (indexes, apps, datamodels)",
                "inputSchema": {"type": "object", "properties": {}}
            }
        ]}

    elif method == "callTool":
        if msg["params"]["name"] == "askSplunk":
            question = msg["params"]["arguments"]["question"]
            spl = english_to_spl(question)
            results = await splunk_search(spl)
            return {"content": [
                {"type": "text", "text": f"Translated SPL: {spl}"},
                {"type": "json", "json": results}
            ]}

        elif msg["params"]["name"] == "describeEnvironment":
            return {"content": [{"type": "json", "json": SPLUNK_STATE}]}


# --- JSON-RPC LOOP ---
async def main():
    await load_splunk_metadata()

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    while True:
        line = await reader.readline()
        if not line:
            break
        msg = json.loads(line.decode())
        result = await handle_message(msg)
        response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
        writer.write((json.dumps(response) + "\n").encode())
        await writer.drain()


if __name__ == "__main__":
    asyncio.run(main())
