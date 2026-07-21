import os
import re
import io
import shutil
import zipfile
import logging
from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, HTMLResponse, StreamingResponse
from typing import List, Optional, Dict, Any, Literal
import json
from datetime import datetime
from pydantic import BaseModel, Field
import google.generativeai as genai
import asyncio

# Configure logging
from api.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


# Initialize FastAPI app
app = FastAPI(
    title="Streaming API",
    description="API for streaming chat completions"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Helper function to get the (guaranteed-writable) adalflow root path
from api.data_root import get_data_root as get_adalflow_default_root_path
from api import zim_reader
from api import zim_library

# --- Pydantic Models ---
class WikiPage(BaseModel):
    """
    Model for a wiki page.
    """
    id: str
    title: str
    content: str
    filePaths: List[str]
    importance: str # Should ideally be Literal['high', 'medium', 'low']
    relatedPages: List[str]

class ProcessedProjectEntry(BaseModel):
    id: str  # Filename
    owner: str
    repo: str
    name: str  # owner/repo
    repo_type: str # Renamed from type to repo_type for clarity with existing models
    submittedAt: int # Timestamp
    language: str # Extracted from filename

class RepoInfo(BaseModel):
    owner: str
    repo: str
    type: str
    token: Optional[str] = None
    localPath: Optional[str] = None
    repoUrl: Optional[str] = None


class WikiSection(BaseModel):
    """
    Model for the wiki sections.
    """
    id: str
    title: str
    pages: List[str]
    subsections: Optional[List[str]] = None


class WikiStructureModel(BaseModel):
    """
    Model for the overall wiki structure.
    """
    id: str
    title: str
    description: str
    pages: List[WikiPage]
    sections: Optional[List[WikiSection]] = None
    rootSections: Optional[List[str]] = None

class WikiCacheData(BaseModel):
    """
    Model for the data to be stored in the wiki cache.
    """
    wiki_structure: WikiStructureModel
    generated_pages: Dict[str, WikiPage]
    repo_url: Optional[str] = None  #compatible for old cache
    repo: Optional[RepoInfo] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    comprehensive: Optional[bool] = None
    page_count: Optional[int] = None
    # Monotonically increasing release version for this repo/language/type.
    # v1 = first generation, v2 = first update, v3 = second update, ... so an
    # update never overwrites the previous wiki. Legacy caches without a version
    # are treated as v0.
    version: Optional[int] = None

class WikiCacheRequest(BaseModel):
    """
    Model for the request body when saving wiki cache.
    """
    repo: RepoInfo
    language: str
    wiki_structure: WikiStructureModel
    generated_pages: Dict[str, WikiPage]
    provider: str
    model: str
    comprehensive: bool = True
    page_count: int = Field(default=10, ge=1, le=50)
    version: Optional[int] = None

class WikiExportRequest(BaseModel):
    """
    Model for requesting a wiki export.
    """
    repo_url: str = Field(..., description="URL of the repository")
    pages: List[WikiPage] = Field(..., description="List of wiki pages to export")
    format: Literal["markdown", "json", "obsidian"] = Field(..., description="Export format (markdown, json, or obsidian vault zip)")
    title: Optional[str] = Field(None, description="Wiki title (used for the Obsidian vault name/index)")
    version: Optional[int] = Field(None, description="Wiki release version being exported (informational)")

class PageEditRequest(BaseModel):
    """Model for saving a manually or AI-edited wiki page's content."""
    repo: RepoInfo
    language: str
    page_id: str = Field(..., description="Id of the page in generated_pages to update")
    content: str = Field(..., description="New markdown content for the page")
    version: Optional[int] = Field(
        None,
        description="Release version to base the edit on (latest release if omitted)",
    )

class PageEditAIRequest(BaseModel):
    """Model for requesting an AI-assisted rewrite of a wiki page. Streams the
    proposed markdown back -- never persists anything itself."""
    page_title: str
    current_content: str
    instruction: str = Field(..., description="What the user wants changed about the page")
    provider: str = Field("google", description="Model provider (google, openai, openrouter, ollama, bedrock, azure, dashscope)")
    model: Optional[str] = Field(None, description="Model name for the specified provider")
    language: Optional[str] = Field("en", description="Language for the rewritten content")
    api_key: Optional[str] = Field(None, description="Optional custom API key")
    api_endpoint: Optional[str] = Field(None, description="Optional custom API endpoint")

class FileContentRequest(BaseModel):
    """Fetches one file's full content for the in-app code viewer (see
    src/components/CodeViewer.tsx), opened when the user clicks a source
    file a repo chat cited. POST, not GET-with-query-params, since
    `token` (a private repo's access token) must never end up in a URL or
    browser history."""
    repo_url: str = Field(..., description="Repository URL, or local path for type='local'")
    repo_type: str = Field(..., description="Repository type: github, gitlab, bitbucket, or local")
    file_path: str = Field(..., description="Path of the file to read, relative to the repo root")
    token: Optional[str] = Field(None, description="Personal access token for private repositories")

class RepoStructureRequest(BaseModel):
    """File tree + README for a github/gitlab/bitbucket repo, read from a
    local git clone (made fresh if needed) instead of the provider's REST
    API -- see /api/repo/structure and /ws/repo/clone."""
    repo_url: str = Field(..., description="Repository URL")
    repo_type: str = Field(..., description="Repository type: github, gitlab, or bitbucket")
    token: Optional[str] = Field(None, description="Personal access token for private repositories")

# --- Model Configuration Models ---
class Model(BaseModel):
    """
    Model for LLM model configuration
    """
    id: str = Field(..., description="Model identifier")
    name: str = Field(..., description="Display name for the model")

class Provider(BaseModel):
    """
    Model for LLM provider configuration
    """
    id: str = Field(..., description="Provider identifier")
    name: str = Field(..., description="Display name for the provider")
    models: List[Model] = Field(..., description="List of available models for this provider")
    supportsCustomModel: Optional[bool] = Field(False, description="Whether this provider supports custom models")

class ModelConfig(BaseModel):
    """
    Model for the entire model configuration
    """
    providers: List[Provider] = Field(..., description="List of available model providers")
    defaultProvider: str = Field(..., description="ID of the default provider")

class AuthorizationConfig(BaseModel):
    code: str = Field(..., description="Authorization code")

from api.config import configs, WIKI_AUTH_MODE, WIKI_AUTH_CODE
# Aliased: this module already defines its own route handler named
# get_model_config() (GET /models/config, a completely different zero-arg
# "list providers" endpoint) -- importing under the same name would shadow it.
from api.config import get_model_config as get_provider_model_config
from api.provider_streaming import stream_provider_response
from api.prompts import PAGE_EDIT_AI_SYSTEM_PROMPT

@app.get("/lang/config")
async def get_lang_config():
    return configs["lang_config"]

@app.get("/auth/status")
async def get_auth_status():
    """
    Check if authentication is required for the wiki.
    """
    return {"auth_required": WIKI_AUTH_MODE}

@app.post("/auth/validate")
async def validate_auth_code(request: AuthorizationConfig):
    """
    Check authorization code.
    """
    return {"success": WIKI_AUTH_CODE == request.code}

@app.get("/models/config", response_model=ModelConfig)
async def get_model_config():
    """
    Get available model providers and their models.

    This endpoint returns the configuration of available model providers and their
    respective models that can be used throughout the application.

    Returns:
        ModelConfig: A configuration object containing providers and their models
    """
    try:
        logger.info("Fetching model configurations")

        # Create providers from the config file
        providers = []
        default_provider = configs.get("default_provider", "google")

        # Add provider configuration based on config.py
        for provider_id, provider_config in configs["providers"].items():
            models = []
            # Add models from config
            for model_id in provider_config["models"].keys():
                # Get a more user-friendly display name if possible
                models.append(Model(id=model_id, name=model_id))

            # Add provider with its models
            providers.append(
                Provider(
                    id=provider_id,
                    name=f"{provider_id.capitalize()}",
                    supportsCustomModel=provider_config.get("supportsCustomModel", False),
                    models=models
                )
            )

        # Ensure other standard providers exist if not in config
        existing_ids = {p.id for p in providers}
        standard_providers = [
            ("google", "Google Gemini", ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-pro", "gemini-1.5-flash"]),
            ("openai", "OpenAI / Codex", ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]),
            ("claude", "Anthropic Claude", ["claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest", "claude-3-opus-latest", "claude-3-haiku-20240307"]),
            ("openai_custom", "Custom OpenAI-compatible", []),
        ]

        for p_id, p_name, p_models in standard_providers:
            if p_id not in existing_ids:
                providers.append(
                    Provider(
                        id=p_id,
                        name=p_name,
                        supportsCustomModel=True,
                        models=[Model(id=m, name=m) for m in p_models]
                    )
                )

        # Create and return the full configuration
        config = ModelConfig(
            providers=providers,
            defaultProvider=default_provider
        )
        return config

    except Exception as e:
        logger.error(f"Error creating model configuration: {str(e)}")
        # Return some default configuration in case of error
        return ModelConfig(
            providers=[
                Provider(
                    id="google",
                    name="Google",
                    supportsCustomModel=True,
                    models=[
                        Model(id="gemini-2.5-flash", name="Gemini 2.5 Flash")
                    ]
                )
            ],
        )

class ModelProbeRequest(BaseModel):
    endpoint: str = Field(..., description="Base URL of the provider endpoint")
    api_key: Optional[str] = Field(None, description="API key (optional for Ollama)")
    provider_type: str = Field("openai", description="'openai' or 'ollama'")

@app.post("/models/probe")
async def probe_models(request: ModelProbeRequest):
    """
    Probe an OpenAI-compatible or Ollama endpoint and return its model list.
    Used by the frontend to populate the model dropdown for custom providers.
    Tries multiple URL patterns to support various OpenAI-compatible APIs
    (Novita, Together, Groq, vLLM, etc.)
    """
    import httpx
    from urllib.parse import urlparse

    endpoint = request.endpoint.rstrip("/")

    def _is_local_host(url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return (
            host in ("localhost", "0.0.0.0")
            or host.startswith("127.")
            or host.startswith("192.168.")
            or host.startswith("10.")
        )

    # Normalize the scheme. Users often paste "localhost:11434" (no scheme) or
    # "https://localhost:11434"; plain-HTTP servers like Ollama then fail with
    # "[SSL: WRONG_VERSION_NUMBER]". Prefer http:// for local hosts and keep an
    # http:// fallback candidate when https was requested against one.
    if not endpoint.startswith(("http://", "https://")):
        scheme = "http" if _is_local_host(f"http://{endpoint}") else "https"
        endpoint = f"{scheme}://{endpoint}"

    endpoint_candidates = [endpoint]
    if endpoint.startswith("https://") and _is_local_host(endpoint):
        endpoint_candidates.append("http://" + endpoint[len("https://"):])

    headers = {"Accept": "application/json"}
    if request.api_key:
        headers["Authorization"] = f"Bearer {request.api_key}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if request.provider_type == "ollama":
                models = []
                last_error = None
                for base in endpoint_candidates:
                    try:
                        resp = await client.get(f"{base}/api/tags", headers=headers)
                        resp.raise_for_status()
                        data = resp.json()
                        models = [
                            {"id": m["name"], "name": m["name"]}
                            for m in data.get("models", [])
                        ]
                        break
                    except Exception as url_err:
                        last_error = url_err
                        continue
                if not models and last_error:
                    raise last_error
            else:
                # Try multiple URL patterns for OpenAI-compatible endpoints
                # Different providers use different URL structures:
                # - OpenAI: https://api.openai.com/v1/models
                # - Novita: https://api.novita.ai/v3/openai/models
                # - Together: https://api.together.xyz/v1/models
                # - vLLM: http://localhost:8000/v1/models
                models = []
                urls_to_try = []
                for base in endpoint_candidates:
                    urls_to_try.append(f"{base}/models")     # If endpoint already includes /v1 or /v3/openai
                    urls_to_try.append(f"{base}/v1/models")  # Standard OpenAI format
                
                last_error = None
                for url in urls_to_try:
                    try:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            models = [
                                {"id": m["id"], "name": m.get("name", m["id"])}
                                for m in data.get("data", [])
                            ]
                            if models:
                                break
                    except Exception as url_err:
                        last_error = url_err
                        continue
                
                if not models and last_error:
                    return {"models": [], "error": f"Could not fetch models from any URL pattern. Last error: {last_error}"}
                    
        return {"models": models}
    except Exception as e:
        logger.warning(f"Model probe failed for {endpoint}: {e}")
        return {"models": [], "error": str(e)}


@app.post("/export/wiki")
async def export_wiki(request: WikiExportRequest):
    """
    Export wiki content as Markdown or JSON.

    Args:
        request: The export request containing wiki pages and format

    Returns:
        A downloadable file in the requested format
    """
    try:
        logger.info(f"Exporting wiki for {request.repo_url} in {request.format} format")

        # Extract repository name from URL for the filename
        repo_parts = request.repo_url.rstrip('/').split('/')
        repo_name = repo_parts[-1] if len(repo_parts) > 0 else "wiki"

        # Get current timestamp for the filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if request.format == "markdown":
            # Generate Markdown content
            content = generate_markdown_export(request.repo_url, request.pages)
            filename = f"{repo_name}_wiki_{timestamp}.md"
            media_type = "text/markdown"
        elif request.format == "obsidian":
            # Generate a full Obsidian vault (one .md per page with [[wikilinks]])
            # packaged as a downloadable .zip
            content = generate_obsidian_vault_export(
                request.repo_url,
                request.pages,
                title=request.title or f"{repo_name} Wiki",
                version=request.version,
            )
            version_suffix = f"_v{request.version}" if request.version else ""
            filename = f"{repo_name}_wiki{version_suffix}_{timestamp}_obsidian.zip"
            media_type = "application/zip"
        else:  # JSON format
            # Generate JSON content
            content = generate_json_export(request.repo_url, request.pages)
            filename = f"{repo_name}_wiki_{timestamp}.json"
            media_type = "application/json"

        # Create response with appropriate headers for file download
        response = Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

        return response

    except Exception as e:
        error_msg = f"Error exporting wiki: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/local_repo/structure")
async def get_local_repo_structure(path: str = Query(None, description="Path to local repository")):
    """Return the file tree and README content for a local repository."""
    if not path:
        return JSONResponse(
            status_code=400,
            content={"error": "No path provided. Please provide a 'path' query parameter."}
        )

    if not os.path.isdir(path):
        return JSONResponse(
            status_code=404,
            content={"error": f"Directory not found: {path}"}
        )

    try:
        logger.info(f"Processing local repository at: {path}")
        file_tree_lines = []
        readme_content = ""

        for root, dirs, files in os.walk(path):
            # Exclude hidden dirs/files and virtual envs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__' and d != 'node_modules' and d != '.venv']
            for file in files:
                if file.startswith('.') or file == '__init__.py' or file == '.DS_Store':
                    continue
                rel_dir = os.path.relpath(root, path)
                rel_file = os.path.join(rel_dir, file) if rel_dir != '.' else file
                file_tree_lines.append(rel_file)
                # Find README.md (case-insensitive)
                if file.lower() == 'readme.md' and not readme_content:
                    try:
                        with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                            readme_content = f.read()
                    except Exception as e:
                        logger.warning(f"Could not read README.md: {str(e)}")
                        readme_content = ""

        file_tree_str = '\n'.join(sorted(file_tree_lines))
        return {"file_tree": file_tree_str, "readme": readme_content}
    except Exception as e:
        logger.error(f"Error processing local repository: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Error processing local repository: {str(e)}"}
        )

def generate_markdown_export(repo_url: str, pages: List[WikiPage]) -> str:
    """
    Generate Markdown export of wiki pages.

    Args:
        repo_url: The repository URL
        pages: List of wiki pages

    Returns:
        Markdown content as string
    """
    # Start with metadata
    markdown = f"# Wiki Documentation for {repo_url}\n\n"
    markdown += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    # Add table of contents
    markdown += "## Table of Contents\n\n"
    for page in pages:
        markdown += f"- [{page.title}](#{page.id})\n"
    markdown += "\n"

    # Add each page
    for page in pages:
        markdown += f"<a id='{page.id}'></a>\n\n"
        markdown += f"## {page.title}\n\n"



        # Add related pages
        if page.relatedPages and len(page.relatedPages) > 0:
            markdown += "### Related Pages\n\n"
            related_titles = []
            for related_id in page.relatedPages:
                # Find the title of the related page
                related_page = next((p for p in pages if p.id == related_id), None)
                if related_page:
                    related_titles.append(f"[{related_page.title}](#{related_id})")

            if related_titles:
                markdown += "Related topics: " + ", ".join(related_titles) + "\n\n"

        # Add page content
        markdown += f"{page.content}\n\n"
        markdown += "---\n\n"

    return markdown

def generate_json_export(repo_url: str, pages: List[WikiPage]) -> str:
    """
    Generate JSON export of wiki pages.

    Args:
        repo_url: The repository URL
        pages: List of wiki pages

    Returns:
        JSON content as string
    """
    # Create a dictionary with metadata and pages
    export_data = {
        "metadata": {
            "repository": repo_url,
            "generated_at": datetime.now().isoformat(),
            "page_count": len(pages)
        },
        "pages": [page.model_dump() for page in pages]
    }

    # Convert to JSON string with pretty formatting
    return json.dumps(export_data, indent=2)


def _obsidian_safe_filename(title: str) -> str:
    """Turn a page title into a safe Obsidian note filename (no extension).

    Obsidian disallows these characters in note names: * " \\ / < > : | ?
    Also strip control chars and trailing dots/spaces (Windows compatibility,
    important because the vault zip must travel across OSes).
    """
    name = re.sub(r'[*"\\/<>:|?]', '-', title)
    name = re.sub(r'[\x00-\x1f]', '', name)
    name = re.sub(r'-{2,}', '-', name)          # collapse runs of dashes
    name = re.sub(r'\s+-\s*$', '', name)        # drop dangling " -" endings
    name = name.strip().rstrip('.-').strip()
    return name or 'Untitled'


def generate_obsidian_vault_export(
    repo_url: str,
    pages: List[WikiPage],
    title: str = "Wiki",
    version: Optional[int] = None,
) -> bytes:
    """Generate a complete Obsidian vault as a .zip (returned as bytes).

    Layout inside the zip:
        <Vault>/
          Home.md                  – index note linking every page with [[wikilinks]]
          <Page Title>.md          – one note per wiki page, YAML frontmatter +
                                     "Related" section using [[wikilinks]]
          .obsidian/app.json       – minimal config so Obsidian opens the folder
                                     as a vault directly after unzipping

    An Obsidian vault is just a folder of Markdown files, so the zip can be
    unzipped anywhere (Windows/macOS/Linux) and opened with
    "Open folder as vault" — matching this project's portability goal.
    """
    vault_name = _obsidian_safe_filename(title)

    # Map page id -> unique safe filename, deduping title collisions.
    id_to_name: Dict[str, str] = {}
    used_names: Dict[str, int] = {}
    for page in pages:
        base = _obsidian_safe_filename(page.title)
        count = used_names.get(base, 0)
        used_names[base] = count + 1
        id_to_name[page.id] = base if count == 0 else f"{base} ({count + 1})"

    generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Minimal .obsidian config so the unzipped folder is recognized as a vault.
        zf.writestr(f"{vault_name}/.obsidian/app.json", json.dumps({}, indent=2))

        # Home/index note with links to every page.
        home = f"# {title}\n\n"
        home += f"- **Repository:** {repo_url}\n"
        if version:
            home += f"- **Wiki release:** v{version}\n"
        home += f"- **Exported:** {generated_at}\n\n"
        home += "## Pages\n\n"
        for page in pages:
            home += f"- [[{id_to_name[page.id]}]]\n"
        zf.writestr(f"{vault_name}/Home.md", home)

        # One note per page.
        for page in pages:
            note = "---\n"
            note += f"title: {json.dumps(page.title)}\n"
            note += f"page_id: {json.dumps(page.id)}\n"
            note += f"importance: {json.dumps(page.importance)}\n"
            if version:
                note += f"wiki_release: {version}\n"
            if page.filePaths:
                note += "source_files:\n"
                for fp in page.filePaths:
                    note += f"  - {json.dumps(fp)}\n"
            note += "---\n\n"
            note += f"{page.content}\n"
            related_links = [
                f"[[{id_to_name[rid]}]]"
                for rid in (page.relatedPages or [])
                if rid in id_to_name
            ]
            if related_links:
                note += "\n## Related\n\n"
                note += " · ".join(related_links) + "\n"
            zf.writestr(f"{vault_name}/{id_to_name[page.id]}.md", note)

    return buffer.getvalue()

# Import the simplified chat implementation
from api.simple_chat import chat_completions_stream
from api.websocket_wiki import handle_websocket_chat

# Add the chat_completions_stream endpoint to the main app
app.add_api_route("/chat/completions/stream", chat_completions_stream, methods=["POST"])

# Add the WebSocket endpoint
app.add_websocket_route("/ws/chat", handle_websocket_chat)

# --- Wiki Cache Helper Functions ---

WIKI_CACHE_DIR = os.path.join(get_adalflow_default_root_path(), "wikicache")
os.makedirs(WIKI_CACHE_DIR, exist_ok=True)

def _repo_cache_prefix(repo_type: str, owner: str, repo: str, language: str) -> str:
    """Filename prefix shared by every release of one repo/language/type."""
    return f"freedeepwiki_cache_{repo_type}_{owner}_{repo}_{language}"


def _repo_has_any_cache(repo_type: str, owner: str, repo: str) -> bool:
    """Whether any wiki release -- in any language or comprehensive/concise
    variant -- still exists for this repo. Used to decide whether it's
    safe to also delete the repo's cloned-to-disk copy and embeddings db:
    those are shared across every release of a repo (keyed only by
    owner_repo, not by language/version), so they must only be removed
    once literally nothing references them anymore.
    """
    prefix = f"freedeepwiki_cache_{repo_type}_{owner}_{repo}_"
    try:
        return any(
            filename.startswith(prefix) and filename.endswith(".json")
            for filename in os.listdir(WIKI_CACHE_DIR)
        )
    except OSError:
        return True  # can't tell -- err on the side of not deleting shared data


def _delete_local_repo_clone(repo_type: str, owner: str, repo: str) -> None:
    """Removes the local git clone and embeddings db for an owner/repo,
    the same way DatabaseManager._create_repo names them
    (~/.adalflow/repos/{owner}_{repo}, ~/.adalflow/databases/{owner}_{repo}.pkl,
    or FREEDEEPWIKI_DATA_DIR's equivalent). Only ever called once
    _repo_has_any_cache confirms no wiki release still needs them --
    never for repo_type == 'local', where the "clone" is the user's own
    folder on disk, not something FreeDeepWiki created.
    """
    root_path = get_adalflow_default_root_path()
    repo_name = f"{owner}_{repo}"
    clone_dir = os.path.join(root_path, "repos", repo_name)
    db_file = os.path.join(root_path, "databases", f"{repo_name}.pkl")
    if os.path.isdir(clone_dir):
        shutil.rmtree(clone_dir, ignore_errors=True)
        logger.info(f"Deleted local repo clone: {clone_dir}")
    if os.path.isfile(db_file):
        os.remove(db_file)
        logger.info(f"Deleted embeddings db: {db_file}")


def _parse_cache_version(filename: str) -> int:
    """Extract the ``_vN`` release version from a cache filename.

    Returns 0 for legacy caches that predate versioning (no ``_vN`` suffix).
    """
    m = re.search(r"_v(\d+)\.json$", filename)
    return int(m.group(1)) if m else 0


def get_wiki_cache_path(
    owner: str,
    repo: str,
    repo_type: str,
    language: str,
    comprehensive: Optional[bool] = None,
    page_count: Optional[int] = None,
    version: Optional[int] = None,
) -> str:
    """Generates the file path for a given wiki cache.

    When ``version`` is provided the filename carries a ``_v{version}`` suffix so
    each release is stored as its own file and an update never overwrites the
    previous wiki.
    """
    variant = ""
    if comprehensive is not None and page_count is not None:
        mode = "comprehensive" if comprehensive else "concise"
        variant = f"_{mode}_{page_count}"
    version_suffix = f"_v{version}" if version is not None else ""
    filename = (
        f"freedeepwiki_cache_{repo_type}_{owner}_{repo}_{language}{variant}{version_suffix}.json"
    )
    return os.path.join(WIKI_CACHE_DIR, filename)


def _list_repo_cache_files(repo_type: str, owner: str, repo: str, language: str) -> List[str]:
    """Return absolute paths of every cache file for one repo/language/type."""
    prefix = _repo_cache_prefix(repo_type, owner, repo, language)
    try:
        return [
            os.path.join(WIKI_CACHE_DIR, fn)
            for fn in os.listdir(WIKI_CACHE_DIR)
            if fn.startswith(prefix) and fn.endswith(".json")
        ]
    except Exception as e:
        logger.error(f"Error listing cache files for {prefix}: {e}")
        return []


def _next_cache_version(repo_type: str, owner: str, repo: str, language: str) -> int:
    """Next release version number = max existing version + 1 (min 1)."""
    files = _list_repo_cache_files(repo_type, owner, repo, language)
    max_version = 0
    for path in files:
        max_version = max(max_version, _parse_cache_version(os.path.basename(path)))
    return max_version + 1


async def read_wiki_cache(
    owner: str,
    repo: str,
    repo_type: str,
    language: str,
    comprehensive: Optional[bool] = None,
    page_count: Optional[int] = None,
    version: Optional[int] = None,
) -> Optional[WikiCacheData]:
    """Reads wiki cache data from the file system.

    If ``version`` is given, returns that specific release. Otherwise returns the
    latest release (highest ``_vN``; legacy files count as v0, ties broken by
    mtime). An optional ``comprehensive``/``page_count`` preference is honored
    when choosing among same-version variants, but the latest release is always
    preferred over an older exact-variant match so re-entering a wiki restores
    the most recent update instead of regenerating.
    """
    def _load(path: str) -> Optional[WikiCacheData]:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return WikiCacheData(**json.load(f))
        except Exception as e:
            logger.error(f"Error reading wiki cache from {path}: {e}")
            return None

    # Specific release requested -> find the file with that exact version.
    if version is not None:
        files = _list_repo_cache_files(repo_type, owner, repo, language)
        exact = [p for p in files if _parse_cache_version(os.path.basename(p)) == version]
        if exact:
            exact.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            for cache_path in exact:
                cached = _load(cache_path)
                if cached:
                    logger.info(f"Loaded wiki release v{version} from {os.path.basename(cache_path)}")
                    return cached
        logger.info(f"Wiki release v{version} not found for {owner}/{repo}")
        return None

    # No version specified -> pick the latest release.
    files = _list_repo_cache_files(repo_type, owner, repo, language)
    if not files:
        return None

    # Sort by version desc, then mtime desc, so the newest release wins.
    files.sort(
        key=lambda p: (_parse_cache_version(os.path.basename(p)), os.path.getmtime(p)),
        reverse=True,
    )

    # Prefer the latest release whose variant matches the request, but fall back
    # to the latest release regardless of variant.
    def _matches_variant(cached: WikiCacheData) -> bool:
        if page_count is not None and len(cached.wiki_structure.pages) != page_count:
            return False
        if comprehensive is not None and cached.comprehensive is not None and cached.comprehensive != comprehensive:
            return False
        return True

    fallback = None
    for cache_path in files:
        cached = _load(cache_path)
        if not cached:
            continue
        if fallback is None:
            fallback = cached
        if _matches_variant(cached):
            logger.info(f"Using wiki release v{cached.version or 0} from {os.path.basename(cache_path)}")
            return cached

    if fallback:
        logger.info(
            "No exact cache variant match; falling back to %s",
            os.path.basename(files[0]),
        )
        return fallback
    return None

async def save_wiki_cache(data: WikiCacheRequest) -> Optional[int]:
    """Saves wiki cache data to the file system as a NEW versioned release.

    Each save creates a fresh ``_v{N}`` file (N = max existing version + 1) so an
    update never overwrites the previous wiki. Returns the assigned version, or
    None on failure.

    Dedupe guard: if the payload is identical to the newest existing release
    (ignoring the version number), no new file is written and the existing
    version is returned. This makes duplicate POSTs (double-fired frontend
    effects, retries, reloads) idempotent instead of minting v1..vN copies of
    the same wiki.
    """
    try:
        files = _list_repo_cache_files(
            data.repo.type, data.repo.owner, data.repo.repo, data.language
        )
        if files:
            files.sort(
                key=lambda p: (_parse_cache_version(os.path.basename(p)), os.path.getmtime(p)),
                reverse=True,
            )
            newest_path = files[0]
            with open(newest_path, "r", encoding="utf-8") as f:
                newest = WikiCacheData(**json.load(f))
            newest_version = _parse_cache_version(os.path.basename(newest_path))
            same_content = (
                newest.wiki_structure == data.wiki_structure
                and newest.generated_pages == data.generated_pages
                and newest.provider == data.provider
                and newest.model == data.model
            )
            if same_content:
                logger.info(
                    f"Wiki cache save skipped: payload identical to existing release "
                    f"v{newest_version} ({os.path.basename(newest_path)})"
                )
                return newest_version if newest_version > 0 else 0
    except Exception as dedupe_error:
        logger.warning(f"Wiki cache dedupe check failed (saving anyway): {dedupe_error}")

    next_version = _next_cache_version(
        data.repo.type, data.repo.owner, data.repo.repo, data.language
    )
    cache_path = get_wiki_cache_path(
        data.repo.owner,
        data.repo.repo,
        data.repo.type,
        data.language,
        data.comprehensive,
        data.page_count,
        version=next_version,
    )
    logger.info(f"Attempting to save wiki cache as release v{next_version}. Path: {cache_path}")
    try:
        payload = WikiCacheData(
            wiki_structure=data.wiki_structure,
            generated_pages=data.generated_pages,
            repo=data.repo,
            provider=data.provider,
            model=data.model,
            comprehensive=data.comprehensive,
            page_count=data.page_count,
            version=next_version,
        )
        # Log size of data to be cached for debugging (avoid logging full content if large)
        try:
            payload_json = payload.model_dump_json()
            payload_size = len(payload_json.encode('utf-8'))
            logger.info(f"Payload prepared for caching. Size: {payload_size} bytes.")
        except Exception as ser_e:
            logger.warning(f"Could not serialize payload for size logging: {ser_e}")


        logger.info(f"Writing cache file to: {cache_path}")
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(payload.model_dump(), f, indent=2)
        logger.info(f"Wiki cache successfully saved to {cache_path} (release v{next_version})")
        return next_version
    except IOError as e:
        logger.error(f"IOError saving wiki cache to {cache_path}: {e.strerror} (errno: {e.errno})", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error saving wiki cache to {cache_path}: {e}", exc_info=True)
        return None

# --- Wiki Cache API Endpoints ---

@app.get("/api/wiki_cache", response_model=Optional[WikiCacheData])
async def get_cached_wiki(
    owner: str = Query(..., description="Repository owner"),
    repo: str = Query(..., description="Repository name"),
    repo_type: str = Query(..., description="Repository type (e.g., github, gitlab)"),
    language: str = Query(..., description="Language of the wiki content"),
    comprehensive: Optional[bool] = Query(
        None,
        description="Whether the wiki uses comprehensive sections",
    ),
    page_count: Optional[int] = Query(
        None,
        ge=1,
        le=50,
        description="Requested number of wiki pages",
    ),
    version: Optional[int] = Query(
        None,
        ge=0,
        description="Specific wiki release version to load (latest if omitted)",
    ),
):
    """
    Retrieves cached wiki data (structure and generated pages) for a repository.
    """
    # Language validation
    supported_langs = configs["lang_config"]["supported_languages"]
    if not supported_langs.__contains__(language):
        language = configs["lang_config"]["default"]

    logger.info(f"Attempting to retrieve wiki cache for {owner}/{repo} ({repo_type}), lang: {language}, version: {version}")
    cached_data = await read_wiki_cache(
        owner,
        repo,
        repo_type,
        language,
        comprehensive,
        page_count,
        version,
    )
    if cached_data:
        return cached_data
    else:
        # Return 200 with null body if not found, as frontend expects this behavior
        logger.info(f"Wiki cache not found for {owner}/{repo} ({repo_type}), lang: {language}")
        return None

@app.get("/api/wiki_cache/releases")
async def list_wiki_releases(
    owner: str = Query(..., description="Repository owner"),
    repo: str = Query(..., description="Repository name"),
    repo_type: str = Query(..., description="Repository type (e.g., github, gitlab)"),
    language: str = Query(..., description="Language of the wiki content"),
):
    """
    Lists every saved release (version) of a repository's wiki, newest first.
    Used by the frontend's "Wiki Release" dropdown to let the user read any
    previously generated version instead of an update silently overwriting it.
    """
    supported_langs = configs["lang_config"]["supported_languages"]
    if not supported_langs.__contains__(language):
        language = configs["lang_config"]["default"]

    files = _list_repo_cache_files(repo_type, owner, repo, language)
    releases = []
    for path in files:
        filename = os.path.basename(path)
        version = _parse_cache_version(filename)
        try:
            mtime = os.path.getmtime(path)
            with open(path, "r", encoding="utf-8") as f:
                cached = WikiCacheData(**json.load(f))
            releases.append({
                "version": version,
                "created_at": int(mtime * 1000),
                "comprehensive": cached.comprehensive,
                "page_count": len(cached.wiki_structure.pages),
                "provider": cached.provider,
                "model": cached.model,
                "title": cached.wiki_structure.title,
                "id": filename,
            })
        except Exception as e:
            logger.warning(f"Could not read release metadata from {filename}: {e}")
            continue

    # Newest release first (version desc, then mtime desc).
    releases.sort(key=lambda r: (r["version"], r["created_at"]), reverse=True)
    return {"releases": releases, "latest": releases[0]["version"] if releases else None}

@app.post("/api/wiki_cache")
async def store_wiki_cache(request_data: WikiCacheRequest):
    """
    Stores generated wiki data (structure and pages) to the server-side cache as
    a new versioned release. Returns the assigned version so the frontend can
    select it in the Wiki Release dropdown.
    """
    # Language validation
    supported_langs = configs["lang_config"]["supported_languages"]

    if not supported_langs.__contains__(request_data.language):
        request_data.language = configs["lang_config"]["default"]

    logger.info(f"Attempting to save wiki cache for {request_data.repo.owner}/{request_data.repo.repo} ({request_data.repo.type}), lang: {request_data.language}")
    version = await save_wiki_cache(request_data)
    if version is not None:
        return {"message": "Wiki cache saved successfully", "version": version}
    else:
        raise HTTPException(status_code=500, detail="Failed to save wiki cache")

@app.patch("/api/wiki_cache/page")
async def edit_wiki_page(request_data: PageEditRequest):
    """
    Saves manually or AI-edited content for a single wiki page. Reuses
    read_wiki_cache/save_wiki_cache as-is (same dedupe + versioning), so an
    edit is just "load a release, replace one page's content, save as a new
    release" -- it never touches the cache file format directly.
    """
    supported_langs = configs["lang_config"]["supported_languages"]
    language = (
        request_data.language
        if supported_langs.__contains__(request_data.language)
        else configs["lang_config"]["default"]
    )

    cached = await read_wiki_cache(
        request_data.repo.owner,
        request_data.repo.repo,
        request_data.repo.type,
        language,
        version=request_data.version,
    )
    if cached is None:
        raise HTTPException(status_code=404, detail="Wiki cache not found for this repository/language")
    if request_data.page_id not in cached.generated_pages:
        raise HTTPException(status_code=404, detail=f"Page '{request_data.page_id}' not found in this wiki release")

    updated_pages = dict(cached.generated_pages)
    updated_pages[request_data.page_id] = updated_pages[request_data.page_id].model_copy(
        update={"content": request_data.content}
    )

    save_request = WikiCacheRequest(
        repo=request_data.repo,
        language=language,
        wiki_structure=cached.wiki_structure,
        generated_pages=updated_pages,
        provider=cached.provider or "",
        model=cached.model or "",
        comprehensive=cached.comprehensive if cached.comprehensive is not None else True,
        page_count=cached.page_count if cached.page_count is not None else len(cached.wiki_structure.pages),
    )
    new_version = await save_wiki_cache(save_request)
    if new_version is None:
        raise HTTPException(status_code=500, detail="Failed to save edited page")
    return {"message": "Page updated successfully", "version": new_version, "page_id": request_data.page_id}

@app.post("/api/wiki/page/edit/stream")
async def edit_wiki_page_ai_stream(request_data: PageEditAIRequest):
    """
    Streams an AI-rewritten version of a single wiki page back to the
    caller. Purely a proposal -- nothing is persisted here; the frontend
    saves it (if the user accepts it) via PATCH /api/wiki_cache/page like
    any manual edit.
    """
    language_code = request_data.language or configs["lang_config"]["default"]
    supported_langs = configs["lang_config"]["supported_languages"]
    language_name = supported_langs.get(language_code, "English")

    prompt = PAGE_EDIT_AI_SYSTEM_PROMPT.format(
        page_title=request_data.page_title,
        current_content=request_data.current_content,
        instruction=request_data.instruction,
        language_name=language_name,
    )
    model_config = get_provider_model_config(request_data.provider, request_data.model)["model_kwargs"]

    async def response_stream():
        try:
            async for text in stream_provider_response(
                provider=request_data.provider,
                requested_model=request_data.model,
                prompt=prompt,
                model_config_kwargs=model_config,
                api_key=request_data.api_key,
                api_endpoint=request_data.api_endpoint,
            ):
                yield text
        except Exception as e:
            logger.error(f"Error in page edit AI stream: {e}")
            yield f"\nError: {str(e)}"

    return StreamingResponse(response_stream(), media_type="text/event-stream")

@app.post("/api/wiki/file_content")
async def get_wiki_file_content(request_data: FileContentRequest):
    """Full, untruncated content of one repo file, for the in-app code
    viewer opened by clicking a "sources consulted" file citation in a repo
    chat (see api/search_tool.py's format_sources_footer, which renders
    those citations as `codefile:` links the frontend intercepts instead of
    navigating). Unlike the chat agent's own READ_FILE tool
    (api/search_tool.py's read_file), this never truncates -- a human
    reading the file in a dedicated viewer should see all of it, not a
    context-budget-limited excerpt."""
    from api.data_pipeline import get_file_content as _get_file_content
    try:
        content = _get_file_content(request_data.repo_url, request_data.file_path, request_data.repo_type, request_data.token)
    except Exception as e:
        logger.error(f"Error reading file {request_data.file_path!r}: {e}")
        raise HTTPException(status_code=404, detail=f"Could not read file: {e}")
    return {"file_path": request_data.file_path, "content": content}

@app.post("/api/repo/structure")
async def get_repo_structure_endpoint(request_data: RepoStructureRequest):
    """File tree + README for a repo, read from a local clone (made fresh
    via a normal blocking `git clone` if one doesn't exist yet) instead of
    the GitHub/GitLab/Bitbucket REST API -- avoids that API's rate limit
    for the "determine wiki structure" step exactly like /api/wiki/file_content
    already does for individual source-file citations. HTTP fallback for
    /ws/repo/clone below when a WebSocket isn't available; blocks for the
    whole clone instead of streaming progress.
    """
    from api.data_pipeline import get_repo_structure as _get_repo_structure
    try:
        structure = await asyncio.to_thread(
            _get_repo_structure, request_data.repo_url, request_data.repo_type, request_data.token
        )
    except Exception as e:
        logger.error(f"Error building repo structure for {request_data.repo_url}: {e}")
        raise HTTPException(status_code=502, detail=f"Could not read repository structure: {e}")
    return structure

@app.websocket("/ws/repo/clone")
async def ws_repo_clone(websocket: WebSocket):
    """Clones (or reuses an existing local clone of) a github/gitlab/
    bitbucket repo and streams git's own --progress phases back as they
    happen, so "open a repo for the first time" shows a real progress bar
    instead of a silent multi-second hang -- then sends the resulting file
    tree + README in one final message. See fetchRepoStructureViaBackendClone
    in src/app/[owner]/[repo]/page.tsx for the client side.
    """
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        repo_url = (payload.get("repo_url") or "").strip()
        repo_type = payload.get("repo_type") or "github"
        token = payload.get("token") or None

        if not repo_url:
            await websocket.send_json({"type": "error", "message": "repo_url is required"})
            return

        from api.data_pipeline import (
            _local_clone_dir as _get_local_clone_dir,
            clone_repo_with_progress,
            _walk_repo_tree,
            _repo_default_branch,
        )

        local_dir = _get_local_clone_dir(repo_url, repo_type)

        async def on_progress(evt):
            await websocket.send_json({"type": "progress", **evt})

        await clone_repo_with_progress(repo_url, local_dir, repo_type, token, on_progress)

        tree, readme_content = await asyncio.to_thread(_walk_repo_tree, local_dir)
        default_branch = await asyncio.to_thread(_repo_default_branch, local_dir)

        await websocket.send_json({
            "type": "done",
            "default_branch": default_branch,
            "tree": tree,
            "readme": readme_content,
        })
    except Exception as e:
        logger.error(f"Error in /ws/repo/clone: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass

@app.delete("/api/wiki_cache")
async def delete_wiki_cache(
    owner: str = Query(..., description="Repository owner"),
    repo: str = Query(..., description="Repository name"),
    repo_type: str = Query(..., description="Repository type (e.g., github, gitlab)"),
    language: str = Query(..., description="Language of the wiki content"),
    authorization_code: Optional[str] = Query(None, description="Authorization code"),
    comprehensive: Optional[bool] = Query(None),
    page_count: Optional[int] = Query(None, ge=1, le=50),
    version: Optional[int] = Query(
        None,
        ge=0,
        description="Delete only this release version. If omitted, deletes all releases.",
    ),
):
    """
    Deletes wiki cache file(s) from the file system.

    With versioning, an update no longer deletes — it creates a new release. An
    explicit delete targets either a single release (``version`` given) or every
    release of the repo/language/type (``version`` omitted).
    """
    # Language validation
    supported_langs = configs["lang_config"]["supported_languages"]
    if not supported_langs.__contains__(language):
        raise HTTPException(status_code=400, detail="Language is not supported")

    if WIKI_AUTH_MODE:
        logger.info("check the authorization code")
        if not authorization_code or WIKI_AUTH_CODE != authorization_code:
            raise HTTPException(status_code=401, detail="Authorization code is invalid")

    logger.info(f"Attempting to delete wiki cache for {owner}/{repo} ({repo_type}), lang: {language}, version: {version}")

    prefix = _repo_cache_prefix(repo_type, owner, repo, language)
    cache_paths = []
    try:
        for filename in os.listdir(WIKI_CACHE_DIR):
            if not filename.endswith(".json"):
                continue
            if not (filename == f"{prefix}.json" or filename.startswith(f"{prefix}_")):
                continue
            if version is not None and _parse_cache_version(filename) != version:
                continue
            cache_paths.append(os.path.join(WIKI_CACHE_DIR, filename))
    except Exception as e:
        logger.error(f"Error scanning cache dir for deletion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scan wiki cache: {str(e)}")

    deleted_paths = []
    try:
        for cache_path in dict.fromkeys(cache_paths):
            if os.path.exists(cache_path):
                os.remove(cache_path)
                deleted_paths.append(cache_path)
                logger.info(f"Successfully deleted wiki cache: {cache_path}")
    except Exception as e:
        logger.error(f"Error deleting wiki cache {cache_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete wiki cache: {str(e)}")

    if deleted_paths:
        # The clone and embeddings db are shared by every release of this
        # repo (any language, any comprehensive/concise variant) -- only
        # safe to remove once none of them reference it anymore, and never
        # for a 'local' repo (that "clone" is the user's own folder).
        if repo_type in ("github", "gitlab", "bitbucket") and not _repo_has_any_cache(repo_type, owner, repo):
            try:
                _delete_local_repo_clone(repo_type, owner, repo)
            except Exception as e:
                logger.warning(f"Failed to delete local repo clone for {owner}/{repo}: {e}")
        return {
            "message": (
                f"Wiki cache for {owner}/{repo} ({language}) deleted successfully"
            )
        }
    else:
        logger.warning(
            "Wiki cache not found for %s/%s (%s), lang: %s",
            owner,
            repo,
            repo_type,
            language,
        )
        raise HTTPException(status_code=404, detail="Wiki cache not found")

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "freedeepwiki-api"
    }

@app.get("/")
async def root():
    """Root endpoint to check if the API is running and list available endpoints dynamically."""
    # Collect routes dynamically from the FastAPI app
    endpoints = {}
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            # Skip docs and static routes
            if route.path in ["/openapi.json", "/docs", "/redoc", "/favicon.ico"]:
                continue
            # Group endpoints by first path segment
            path_parts = route.path.strip("/").split("/")
            group = path_parts[0].capitalize() if path_parts[0] else "Root"
            method_list = list(route.methods - {"HEAD", "OPTIONS"})
            for method in method_list:
                endpoints.setdefault(group, []).append(f"{method} {route.path}")

    # Optionally, sort endpoints for readability
    for group in endpoints:
        endpoints[group].sort()

    return {
        "message": "Welcome to Streaming API",
        "version": "1.0.0",
        "endpoints": endpoints
    }

# --- Processed Projects Endpoint --- (New Endpoint)
@app.get("/api/processed_projects", response_model=List[ProcessedProjectEntry])
async def get_processed_projects():
    """
    Lists all processed projects found in the wiki cache directory.
    Projects are identified by files named like: freedeepwiki_cache_{repo_type}_{owner}_{repo}_{language}.json
    """
    project_entries: List[ProcessedProjectEntry] = []
    # WIKI_CACHE_DIR is already defined globally in the file

    try:
        if not os.path.exists(WIKI_CACHE_DIR):
            logger.info(f"Cache directory {WIKI_CACHE_DIR} not found. Returning empty list.")
            return []

        logger.info(f"Scanning for project cache files in: {WIKI_CACHE_DIR}")
        filenames = await asyncio.to_thread(os.listdir, WIKI_CACHE_DIR) # Use asyncio.to_thread for os.listdir

        newest_projects: Dict[tuple, ProcessedProjectEntry] = {}
        for filename in filenames:
            if filename.startswith("freedeepwiki_cache_") and filename.endswith(".json"):
                file_path = os.path.join(WIKI_CACHE_DIR, filename)
                try:
                    stats = await asyncio.to_thread(os.stat, file_path) # Use asyncio.to_thread for os.stat
                    cache_name = filename.replace("freedeepwiki_cache_", "").replace(".json", "")
                    # Strip the release version suffix (_vN) and the variant suffix
                    # (_comprehensive_N / _concise_N) so the remaining
                    # repo_type_owner_repo_language splits cleanly into parts.
                    cache_name = re.sub(r"_v\d+$", "", cache_name)
                    cache_name = re.sub(
                        r"_(?:comprehensive|concise)_\d+$",
                        "",
                        cache_name,
                    )
                    parts = cache_name.split('_')

                    # Expecting repo_type_owner_repo_language
                    # Example: freedeepwiki_cache_github_kroryan_FreeDeepWiki_en.json
                    # parts = [github, kroryan, FreeDeepWiki, en]
                    if len(parts) >= 4:
                        repo_type = parts[0]
                        owner = parts[1]
                        language = parts[-1] # language is the last part
                        repo = "_".join(parts[2:-1]) # repo can contain underscores

                        entry = ProcessedProjectEntry(
                                id=filename,
                                owner=owner,
                                repo=repo,
                                name=f"{owner}/{repo}",
                                repo_type=repo_type,
                                submittedAt=int(stats.st_mtime * 1000), # Convert to milliseconds
                                language=language
                        )
                        project_key = (repo_type, owner, repo, language)
                        previous = newest_projects.get(project_key)
                        if previous is None or entry.submittedAt > previous.submittedAt:
                            newest_projects[project_key] = entry
                    else:
                        logger.warning(f"Could not parse project details from filename: {filename}")
                except Exception as e:
                    logger.error(f"Error processing file {file_path}: {e}")
                    continue # Skip this file on error

        project_entries = list(newest_projects.values())

        # Mix in imported .zim archives, using the same list shape so the
        # frontend can render them alongside LLM-generated wikis. A .zim has
        # no owner/repo/language in the git-repo sense, so those fields are
        # synthesized: repo_type='zim' is what the frontend uses to route to
        # /zim/{id} instead of /{owner}/{repo}.
        for zim_entry in zim_library.list_all():
            project_entries.append(
                ProcessedProjectEntry(
                    id=zim_entry["id"],
                    owner="zim",
                    repo=zim_entry["id"],
                    name=zim_entry["title"],
                    repo_type="zim",
                    submittedAt=zim_entry["importedAt"],
                    language="",
                )
            )

        # Sort by most recent first
        project_entries.sort(key=lambda p: p.submittedAt, reverse=True)
        logger.info(f"Found {len(project_entries)} processed project entries.")
        return project_entries

    except Exception as e:
        logger.error(f"Error listing processed projects from {WIKI_CACHE_DIR}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list processed projects from server cache.")


# --- ZIM Archive Import & Reader Endpoints ---

class ZimImportRequest(BaseModel):
    path: str = Field(..., description="Absolute filesystem path to a .zim file")


def _register_zim_path(path: str) -> zim_library.ZimEntry:
    """Validate `path` is a real .zim file and register it. Raises
    HTTPException on failure; used by both /import (one explicit path) and
    /rescan (every new file already sitting in the drop folder)."""
    archive = zim_reader.open_archive(path)
    metadata = zim_reader.get_metadata(archive)
    return zim_library.register(
        path=path,
        title=metadata["title"],
        description=metadata["description"],
        article_count=metadata["articleCount"],
    )


@app.post("/api/zim/import")
async def import_zim(request: ZimImportRequest):
    """Register a local .zim file as a browsable/chattable project.

    The file is never copied or uploaded -- only its absolute path is stored.
    Validates the path exists and is a well-formed .zim archive before
    registering it.
    """
    path = request.path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="No path provided")
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail=f"File not found: {path}")

    try:
        return _register_zim_path(path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to open ZIM file {path}: {e}")
        raise HTTPException(status_code=400, detail=f"Not a valid .zim file: {e}")


@app.get("/api/zim/drop_dir")
async def get_zim_drop_dir():
    """Return the folder the user can drop .zim files into directly (useful
    for multi-gigabyte archives where typing/pasting a path is friction) --
    shown in the UI so the user knows where to put files before hitting
    Rescan."""
    return {"path": zim_library.ZIM_DROP_DIR}


@app.post("/api/zim/rescan")
async def rescan_zim_drop_dir():
    """Register every .zim file sitting in the drop folder that isn't
    already in the library. Lets a user drop a huge file into that folder
    with a file manager (or `cp`/`mv`) and pick it up here without typing an
    absolute path."""
    already_registered = zim_library.registered_paths()
    added: list[zim_library.ZimEntry] = []
    errors: list[dict] = []
    for path in zim_library.list_drop_dir_zim_files():
        if path in already_registered:
            continue
        try:
            added.append(_register_zim_path(path))
        except Exception as e:
            logger.error(f"Failed to auto-register dropped ZIM file {path}: {e}")
            errors.append({"path": path, "error": str(e)})
    return {"added": added, "errors": errors}


def _get_zim_entry_or_404(zim_id: str) -> zim_library.ZimEntry:
    entry = zim_library.get(zim_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="ZIM archive not found in library")
    return entry


def _open_zim_or_500(entry: zim_library.ZimEntry):
    try:
        return zim_reader.open_archive(entry["path"])
    except Exception as e:
        logger.error(f"Failed to open registered ZIM file {entry['path']}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not open ZIM file: {e}")


@app.get("/api/zim/{zim_id}")
async def get_zim_metadata(zim_id: str):
    entry = _get_zim_entry_or_404(zim_id)
    archive = _open_zim_or_500(entry)
    metadata = zim_reader.get_metadata(archive)
    return {**entry, **metadata}


@app.get("/api/zim/{zim_id}/search")
async def search_zim(zim_id: str, q: str = Query(..., min_length=1), limit: int = Query(20, ge=1, le=100)):
    entry = _get_zim_entry_or_404(zim_id)
    archive = _open_zim_or_500(entry)
    return zim_reader.search_entries(archive, q, limit=limit)


@app.get("/api/zim/{zim_id}/index")
async def get_zim_index(zim_id: str, limit: int = Query(500, ge=1, le=2000)):
    """Browsable list of the archive's pages, shown below the search box
    when the user isn't actively searching (see zim_reader.build_title_index)."""
    entry = _get_zim_entry_or_404(zim_id)
    archive = _open_zim_or_500(entry)
    return zim_reader.build_title_index(archive, limit=limit)


# ZIM content is arbitrary third-party HTML with its own CSS, rendered in an
# iframe sandboxed WITHOUT allow-same-origin (see the reader page for why --
# combining allow-scripts with allow-same-origin is a documented sandbox
# bypass). Scripts are additionally left OUT of the sandbox entirely: real
# .zim archives that ship a client-side app (seen firsthand: a Vue-based
# DevDocs bundle) rely on browser capabilities an opaque-origin sandboxed
# frame doesn't have (localStorage/sessionStorage throw instead of just
# being empty, no IndexedDB, no same-origin fetch), and when that app's
# startup code isn't defensive about it, it crashes mid-render -- which
# looked like "the good static page flashes, then gets replaced by a
# broken 'Loading...' panel that never resolves." Never executing the
# archive's scripts means whatever HTML/CSS it shipped is what actually
# stays on screen, for every .zim, not just the well-behaved ones. It also
# means re-theming it to match the app's dark/light mode isn't possible
# from here (no script access) -- each .zim keeps its own native look,
# wrapped by our own chrome around it rather than reskinned.
def _rewrite_zim_html(zim_id: str, entry_path: str, html_bytes: bytes) -> str:
    """Inject a <base> tag so an entry's own relative links/assets
    ("../../application.css", "../pagination/index") resolve against our raw
    proxy the same way they would against the ZIM's internal namespace.

    Relative URLs resolve against the *directory* of the current URL, so
    base must include entry_path's directory, not just the raw-proxy root --
    otherwise every entry not at the ZIM root (i.e. almost all of them)
    breaks its own asset paths.
    """
    html = html_bytes.decode("utf-8", errors="replace")
    entry_dir = entry_path.rsplit("/", 1)[0] + "/" if "/" in entry_path else ""
    base_tag = f'<base href="/api/zim/{zim_id}/raw/{entry_dir}">'
    if re.search(r"(?i)<head[^>]*>", html):
        html = re.sub(r"(?i)(<head[^>]*>)", r"\1" + base_tag, html, count=1)
    else:
        html = base_tag + html
    return html


@app.get("/api/zim/{zim_id}/entry", response_class=HTMLResponse)
async def get_zim_entry(zim_id: str, path: str = Query(...)):
    entry = _get_zim_entry_or_404(zim_id)
    archive = _open_zim_or_500(entry)
    try:
        content, mimetype = zim_reader.get_entry_content(archive, path)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Entry not found: {path}")

    if not mimetype.startswith("text/html"):
        # Non-HTML main entries (rare) -- send back through the raw proxy path
        # instead of trying to render them as a page.
        return Response(content=content, media_type=mimetype)

    html = _rewrite_zim_html(zim_id, path, content)
    return HTMLResponse(content=html, headers={"X-Content-Type-Options": "nosniff"})


@app.get("/api/zim/{zim_id}/raw/{entry_path:path}")
async def get_zim_raw(zim_id: str, entry_path: str):
    """Proxy raw bytes of an entry inside the ZIM namespace (images, CSS, JS,
    linked articles). `entry_path` is resolved entirely inside libzim's own
    archive namespace -- it is never used to build a filesystem path, so it
    cannot escape to the real filesystem regardless of its contents.

    HTML entries reached this way (the user clicked an in-page link to another
    article, which resolves through <base> to this raw route rather than
    /entry) get the same <base> rewrite as /entry, so their own relative
    links/assets keep resolving correctly -- otherwise browsing would break
    one hop after the first click.
    """
    entry = _get_zim_entry_or_404(zim_id)
    archive = _open_zim_or_500(entry)
    try:
        content, mimetype = zim_reader.get_entry_content(archive, entry_path)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Entry not found: {entry_path}")

    if mimetype.startswith("text/html"):
        html = _rewrite_zim_html(zim_id, entry_path, content)
        return HTMLResponse(content=html, headers={"X-Content-Type-Options": "nosniff"})

    return Response(
        content=content,
        media_type=mimetype,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.delete("/api/zim/{zim_id}")
async def delete_zim(zim_id: str):
    """Unregister a .zim from the library. Never deletes the underlying file."""
    entry = _get_zim_entry_or_404(zim_id)
    zim_reader.close_archive(entry["path"])
    zim_library.unregister(zim_id)
    return {"message": "ZIM archive removed from library"}
