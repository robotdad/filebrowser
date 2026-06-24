/**
 * app.js — JavaScript fixture for CodeMirror syntax highlighting test.
 * Exercises: async/await, class, arrow functions, template literals,
 * destructuring, spread, optional chaining, nullish coalescing.
 */

const API_BASE = "/api";

/**
 * Lightweight API client for the FileBrowser backend.
 */
class FileBrowserClient {
  #baseUrl;
  #headers;

  constructor(baseUrl = API_BASE) {
    this.#baseUrl = baseUrl;
    this.#headers = { "Content-Type": "application/json" };
  }

  async #request(method, path, body = null) {
    const opts = {
      method,
      credentials: "include",
      headers: this.#headers,
    };
    if (body !== null) opts.body = JSON.stringify(body);

    const resp = await fetch(`${this.#baseUrl}${path}`, opts);
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`HTTP ${resp.status} ${resp.statusText}: ${text}`);
    }
    const ct = resp.headers.get("content-type") ?? "";
    return ct.includes("application/json") ? resp.json() : resp.text();
  }

  listDir = async (path) => this.#request("GET", `/files${path}`);
  readFile = async (path) => this.#request("GET", `/files${path}?content=true`);
  mkdir = async (path) => this.#request("POST", `/files${path}?mkdir=true`);
  delete = async (path) => this.#request("DELETE", `/files${path}`);

  rename = async (from, to) =>
    this.#request("POST", `/files${to}?rename=${encodeURIComponent(from)}`);

  upload = async (dir, file) => {
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch(`${this.#baseUrl}/files${dir}/${file.name}`, {
      method: "POST",
      body: form,
      credentials: "include",
    });
    if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
    return resp.json();
  };
}

/** Format a byte count as a human-readable string. */
const formatBytes = (n) => {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
};

/** Debounce a function so it only fires after `delay` ms of silence. */
const debounce = (fn, delay = 250) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
};

// Export for module environments; silently skip in browser globals.
if (typeof module !== "undefined") {
  module.exports = { FileBrowserClient, formatBytes, debounce };
}
