// This only limits opening a local WebSocket. Model inference itself has no
// browser-side timeout, so remote Ollama hosts can take as long as needed.
export const WEBSOCKET_CONNECT_TIMEOUT_MS = 30_000;
