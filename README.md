# Splunk MCP Server

A **Model Context Protocol (MCP) server** for Splunk that lets you query Splunk in plain English.  
It automatically discovers indexes, datamodels, and installed apps, and makes them available as MCP resources and tools.  
Works with ChatGPT Desktop, Claude Desktop, and any MCP-compatible client.

---

## Features

- Query Splunk using **plain English**
- Auto-discovers **indexes, datamodels, and apps** at startup
- Exposes metadata as an MCP resource
- Tools provided:
  - `askSplunk` – ask in English, get translated SPL + results
  - `describeEnvironment` – summarize indexes, apps, datamodels
  - `splunk://metadata` – raw environment metadata

---

## Setup

### 1) Clone the repo
```
git clone https://github.com/gaurdiansphere/splunk-mcp.git
cd splunk-mcp
```

### 2) Create virtual environment & install dependencies
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3) Configure Splunk connection
Create a `.env` file in the project root:
```
SPLUNK_URL=https://splunk.example.com:8089
SPLUNK_TOKEN=YOUR_SPLUNK_TOKEN
```

- Use a Splunk service account with **read/search only** permissions
- Do **not** commit `.env` to GitHub

---

## Running the server
```
python3 splunk_mcp.py
```

If successful, you’ll see logs like:
```
[MCP] Loaded indexes: ['wineventlog', 'auth', 'okta']
[MCP] Loaded datamodels: ['Authentication', 'Endpoint']
[MCP] Loaded apps: ['Splunk_TA_windows', 'Splunk_TA_okta']
```

---

## MCP integration

Add this server to your MCP client config (e.g. `~/.config/openai/mcp.json`):
```
{
  "servers": {
    "splunk": {
      "command": "python3",
      "args": ["/absolute/path/to/splunk_mcp.py"]
    }
  }
}
```

Restart your MCP client (ChatGPT Desktop, Claude Desktop, etc.) after updating.

---

## Example usage

### Describe environment
```
/tool splunk.describeEnvironment {}
```
Example response:
```
{
  "applications": ["Splunk_TA_windows", "Splunk_TA_okta"],
  "indexes": ["wineventlog", "auth", "okta"],
  "datamodels": ["Authentication", "Endpoint"]
}
```

### Ask in English
```
/tool splunk.askSplunk {"question": "Show me failed logins in the last 24 hours"}
```
Example response:
```
{
  "Translated SPL": "| tstats count from datamodel=Authentication.Authentication where Authentication.action=\"failure\" earliest=-24h by Authentication.user",
  "results": [
    {"Authentication.user": "bob", "count": "12"},
    {"Authentication.user": "alice", "count": "7"}
  ]
}
```

---

## Security notes

- Keep credentials in `.env`; never commit secrets
- Limit tokens to **read-only** permissions
- Rotate credentials regularly

---

## Roadmap

- Better English → SPL translation using discovered metadata
- Support for saved searches and alerts
- Streaming for large result sets


