import { readSseStream } from "./sse.js";

export async function fetchProviderStatus() {
  const response = await fetch("/provider-status");
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchSearchResults(endpoint, query) {
  const response = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function streamChat(endpoint, message, history, onEvent) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  await readSseStream(response, onEvent);
}

export async function fetchDocumentDetail(docId) {
  const response = await fetch(`/documents/${encodeURIComponent(docId)}`);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}
