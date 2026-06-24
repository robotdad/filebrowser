/**
 * types.ts — TypeScript fixture for CodeMirror syntax highlighting test.
 * Exercises: interfaces, generics, union types, type guards, mapped types,
 * async functions, decorators (syntax only), enums.
 */

// --- Enums ---

export enum FileCategory {
  Markdown = "markdown",
  Code = "code",
  Image = "image",
  Video = "video",
  Audio = "audio",
  Diagram = "diagram",
  Document = "document",
  Text = "text",
  Other = "other",
}

// --- Interfaces ---

export interface FileInfo {
  name: string;
  path: string;
  size: number;
  modified: Date;
  isDir: boolean;
  category: FileCategory;
  mimeType: string;
}

export interface DirListing {
  path: string;
  entries: FileInfo[];
  total: number;
}

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
}

// --- Generics ---

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; error: ApiError };

export interface Paginated<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
  hasNext: boolean;
}

// --- Mapped / utility types ---

export type FileInfoUpdate = Partial<Pick<FileInfo, "name" | "path">>;

export type CategoryCounts = Record<FileCategory, number>;

// --- Type guards ---

export function isApiError(v: unknown): v is ApiError {
  return (
    typeof v === "object" &&
    v !== null &&
    "status" in v &&
    "message" in v &&
    typeof (v as ApiError).status === "number"
  );
}

export function isFileInfo(v: unknown): v is FileInfo {
  return (
    typeof v === "object" &&
    v !== null &&
    "name" in v &&
    "path" in v &&
    "isDir" in v
  );
}

// --- Generic async function ---

export async function fetchJson<T>(
  url: string,
  options?: RequestInit
): Promise<Result<T>> {
  try {
    const resp = await fetch(url, { credentials: "include", ...options });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      return {
        ok: false,
        error: { status: resp.status, message: resp.statusText, detail: text },
      };
    }
    const data = (await resp.json()) as T;
    return { ok: true, data };
  } catch (err) {
    return {
      ok: false,
      error: {
        status: 0,
        message: err instanceof Error ? err.message : String(err),
      },
    };
  }
}

// --- Concrete usage ---

export async function listDirectory(path: string): Promise<Result<DirListing>> {
  return fetchJson<DirListing>(`/api/files${path}`);
}

export function countByCategory(entries: FileInfo[]): CategoryCounts {
  const counts = {} as CategoryCounts;
  for (const cat of Object.values(FileCategory)) {
    counts[cat] = 0;
  }
  for (const entry of entries) {
    counts[entry.category] += 1;
  }
  return counts;
}
