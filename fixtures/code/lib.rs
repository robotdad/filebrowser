// lib.rs — Rust fixture for CodeMirror syntax highlighting test.
// Exercises: struct, impl, enum, Result/Option, traits, iterators, lifetimes.

use std::fmt;
use std::path::{Path, PathBuf};

/// Category of a file based on its extension.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FileCategory {
    Markdown,
    Code,
    Image,
    Video,
    Audio,
    Diagram,
    Document,
    Text,
    Other,
}

impl fmt::Display for FileCategory {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s = match self {
            FileCategory::Markdown => "markdown",
            FileCategory::Code => "code",
            FileCategory::Image => "image",
            FileCategory::Video => "video",
            FileCategory::Audio => "audio",
            FileCategory::Diagram => "diagram",
            FileCategory::Document => "document",
            FileCategory::Text => "text",
            FileCategory::Other => "other",
        };
        write!(f, "{}", s)
    }
}

/// Metadata for a single file or directory entry.
#[derive(Debug, Clone)]
pub struct FileEntry {
    pub name: String,
    pub path: PathBuf,
    pub size: u64,
    pub is_dir: bool,
    pub category: FileCategory,
}

impl FileEntry {
    /// Create a new FileEntry, inferring the category from the extension.
    pub fn new(path: impl AsRef<Path>, size: u64, is_dir: bool) -> Self {
        let path = path.as_ref().to_path_buf();
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();
        let category = if is_dir {
            FileCategory::Other
        } else {
            categorize(&path)
        };
        FileEntry { name, path, size, is_dir, category }
    }

    /// Human-readable size string.
    pub fn human_size(&self) -> String {
        let mut n = self.size as f64;
        for unit in &["B", "KB", "MB", "GB"] {
            if n < 1024.0 {
                return format!("{:.1} {}", n, unit);
            }
            n /= 1024.0;
        }
        format!("{:.1} TB", n)
    }
}

/// Infer a FileCategory from a path's extension.
pub fn categorize(path: &Path) -> FileCategory {
    match path.extension().and_then(|e| e.to_str()) {
        Some("md" | "markdown") => FileCategory::Markdown,
        Some("py" | "js" | "ts" | "go" | "rs" | "java" | "cpp" | "c" | "sh") => {
            FileCategory::Code
        }
        Some("png" | "jpg" | "jpeg" | "gif" | "webp" | "svg") => FileCategory::Image,
        Some("mp4" | "webm" | "ogv") => FileCategory::Video,
        Some("mp3" | "ogg" | "wav" | "flac") => FileCategory::Audio,
        Some("dot" | "gv") => FileCategory::Diagram,
        Some("pdf") => FileCategory::Document,
        Some("txt" | "log" | "csv" | "json" | "yaml" | "toml" | "xml") => FileCategory::Text,
        _ => FileCategory::Other,
    }
}

/// Filter entries to only those matching a given category.
pub fn filter_by_category<'a>(
    entries: &'a [FileEntry],
    category: &FileCategory,
) -> Vec<&'a FileEntry> {
    entries.iter().filter(|e| &e.category == category).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_categorize_markdown() {
        assert_eq!(categorize(Path::new("README.md")), FileCategory::Markdown);
    }

    #[test]
    fn test_categorize_code() {
        assert_eq!(categorize(Path::new("main.rs")), FileCategory::Code);
        assert_eq!(categorize(Path::new("app.py")), FileCategory::Code);
    }

    #[test]
    fn test_human_size() {
        let e = FileEntry::new("test.txt", 1536, false);
        assert_eq!(e.human_size(), "1.5 KB");
    }
}
