# Codex Web Relay

Codex Web Relay is a local FastAPI relay and web console for routing Codex-style requests to OpenAI-compatible model providers. It exposes a single local endpoint for Codex, converts Responses API style payloads into chat-completions payloads, and forwards streaming responses, reasoning content, and tool calls to the selected upstream model.

The project is intentionally compact: the backend, API adapter, and Vue-based control panel all live in `codex_web_relay.py`, with Docker files included for Windows Docker Desktop and Linux/VPS deployment.

The web console now ships with local copies of its frontend assets, so it does not depend on external CDNs at runtime. The interface is bilingual, with Traditional Chinese and English available from the settings panel.

## What It Does

- Provides a browser control panel at `http://127.0.0.1:4446`.
- Lets you create, edit, reorder, import, and export provider profiles.
- Supports OpenAI official API plus OpenAI-compatible providers such as DeepSeek, SiliconFlow, OpenRouter, Kimi, Qwen, Hunyuan, Baidu Qianfan, Nvidia NIM, Groq, Together AI, Mistral, xAI, GitHub Models, Ollama, LM Studio, and vLLM.
- Fetches model lists from the selected provider through `/relay/v1/models`.
- Exposes Codex-facing endpoints under `/relay/v1`.
- Converts Codex/Responses-style requests into upstream `/chat/completions` requests.
- Preserves streaming output through Server-Sent Events.
- Adapts function/tool call shapes for OpenAI-compatible chat-completions providers.
- Stores active provider state in server memory and profile data in the browser's local storage.
- Lets users decide whether API keys are remembered locally, included in exported backups, and whether upstream TLS is verified.

## Project Layout

```text
.
├── codex_web_relay.py                  # FastAPI server, Vue control panel, relay logic
├── Dockerfile                          # Python 3.11 container image
├── docker-compose.yml                  # Windows Docker Desktop friendly compose file
├── vendor/                              # Local frontend assets for Vue, Tailwind, and marked
└── Codex_Web_Relay_Deployment_Guide.pdf # Original deployment guide
```

## Requirements

For local Python usage:

- Python 3.11+
- `fastapi`
- `uvicorn`
- `httpx`
- `pydantic`

For Docker usage:

- Docker Desktop on Windows, or Docker Engine / Docker Compose on Linux

## Quick Start With Python

Install dependencies:

```bash
pip install fastapi uvicorn httpx pydantic
```

Start the relay:

```bash
python codex_web_relay.py
```

Open the web console:

```text
http://127.0.0.1:4446
```

## Quick Start With Docker

Build and run:

```bash
docker-compose build --no-cache
docker-compose up -d
```

Open:

```text
http://127.0.0.1:4446
```

View logs:

```bash
docker logs -f codex_relay
```

Stop:

```bash
docker-compose down
```

## Configure Codex

In the web console, hover the status area and copy the generated Codex config snippet, or add this provider manually to your Codex `config.toml`:

```toml
model = "relay-auto"

model_provider = "local-relay"

[model_providers.local-relay]
name = "Local Relay"
base_url = "http://127.0.0.1:4446/relay/v1"
wire_api = "responses"
```

After this, select and enable a provider profile in the web console. Codex requests sent to the local relay will use the currently active profile.

## Provider Profiles

Each profile contains:

- Provider name
- Base URL
- API key
- Optional OpenAI Organization and Project IDs for OpenAI official API profiles
- Model ID
- Icon and display metadata

The web console includes presets for common OpenAI-compatible services, but you can also use any custom provider that exposes compatible `/models` and `/chat/completions` endpoints.

For OpenAI official API:

- Use the `OpenAI API` preset.
- Base URL defaults to `https://api.openai.com/v1`.
- Authentication uses an OpenAI API key through `Authorization: Bearer ...`.
- If your account requires them, fill in `OpenAI-Organization` and `OpenAI-Project` in the optional fields.
- Account login is intentionally not proxied; keep Codex Desktop account login in Codex Desktop and use API keys for relay traffic.

For local providers:

- `Ollama`: `http://127.0.0.1:11434/v1`, for direct local access.
- `Ollama (Docker)`: `http://host.docker.internal:11434/v1`, for Docker Desktop access to Ollama running on the Windows host.
- LM Studio: `http://localhost:1234/v1`
- vLLM: `http://localhost:8000/v1`

## API Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Web control panel |
| `POST /relay/v1/internal/sync` | Sync the active profile from the browser to the relay process |
| `GET /relay/v1/models` | Proxy model-list requests to the selected upstream provider |
| `POST /relay/v1/responses` | Codex-facing Responses-style relay endpoint |
| `POST /relay/v1/chat/completions` | Chat-completions relay endpoint |
| `POST /v1/responses` | Compatibility alias |
| `POST /v1/chat/completions` | Compatibility alias |

## How The Relay Works

When a request comes from the web console, the upstream base URL and authorization header are provided directly by the browser request.

When a request comes from Codex or another local client, the relay uses the active profile stored in `ACTIVE_PROFILE_STATE`. The browser updates that active profile through `/relay/v1/internal/sync`.

For Codex-facing traffic, the relay:

1. Reads `instructions`, `messages`, and `input` from a Responses-style payload.
2. Converts them into a chat-completions `messages` array.
3. Converts supported tool definitions into OpenAI-compatible function tools.
4. Removes request fields that many chat-completions providers do not accept.
5. Sends the request to the active upstream provider's `/chat/completions` endpoint.
6. Converts streamed chat-completions chunks back into Responses-style SSE events when needed.

## Windows Docker Notes

Docker Desktop on Windows runs containers inside a VM, so `127.0.0.1` inside the container is not the Windows host.

Use this Base URL when connecting from the container to Ollama running on Windows:

```text
http://host.docker.internal:11434/v1
```

The included `docker-compose.yml` maps port `4446` from the container to the host:

```yaml
ports:
  - "4446:4446"
```

## Linux / VPS Notes

For Linux servers, the deployment guide recommends using Docker host networking:

```yaml
network_mode: "host"
```

With host networking, a local Ollama service on the same VPS can usually be reached at:

```text
http://127.0.0.1:11434/v1
```

The current repository's `docker-compose.yml` is the Windows-friendly version. If you deploy on Linux and want host networking, replace the `ports` section with `network_mode: "host"`.

## Nginx Reverse Proxy

For public deployment, do not expose port `4446` directly without access control. Put the service behind HTTPS and authentication.

For smooth streaming output, disable proxy buffering:

```nginx
location / {
    proxy_pass http://127.0.0.1:4446;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
}
```

## Security Notes

- The web console stores profiles in browser `localStorage`.
- The active API key is also held in the relay process memory after profile sync.
- The relay does not currently implement login, authentication, or multi-user isolation.
- Avoid exposing the relay directly to the public internet.
- Treat the web console as a trusted local/admin tool.
- Do not commit exported profile backup files if they contain API keys.

## Troubleshooting

### Port 4446 is already in use

Stop the previous process or container:

```bash
docker-compose down
```

On Windows, also check Task Manager for stray `python.exe` processes if you previously launched the script directly.

### Docker cannot find `codex_web_relay.py`

Make sure the file is named exactly `codex_web_relay.py`. On Windows, enable file extensions in Explorer so the file has not accidentally become `codex_web_relay.py.py`.

Then rebuild:

```bash
docker-compose build --no-cache
```

### Model list is empty

Check:

- Base URL
- API key
- Whether the provider exposes `/models`
- Whether the provider requires a different OpenAI-compatible path

### Context length exceeded

Clear the Codex conversation history or switch to a model with a larger context window.

### 401 or user-not-found errors

Recheck the API key in the profile editor. Use the "show full key" control in the web console and regenerate the key if needed.

## License

No license file is currently included. Add one before publishing or redistributing this project broadly.
