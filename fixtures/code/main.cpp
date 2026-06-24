// main.cpp — C++ fixture for CodeMirror syntax highlighting test.
// Exercises: includes, struct, template function, std::variant, ranges,
// RAII, smart pointers, lambda, and main().

#include <algorithm>
#include <filesystem>
#include <format>
#include <iostream>
#include <memory>
#include <ranges>
#include <string>
#include <variant>
#include <vector>

namespace fs = std::filesystem;

// ---- Enums & constants ----

enum class FileCategory {
    Markdown, Code, Image, Video, Audio, Diagram, Document, Text, Other
};

constexpr std::string_view categoryName(FileCategory cat) {
    switch (cat) {
        case FileCategory::Markdown: return "markdown";
        case FileCategory::Code:     return "code";
        case FileCategory::Image:    return "image";
        case FileCategory::Video:    return "video";
        case FileCategory::Audio:    return "audio";
        case FileCategory::Diagram:  return "diagram";
        case FileCategory::Document: return "document";
        case FileCategory::Text:     return "text";
        default:                     return "other";
    }
}

// ---- Data model ----

struct FileEntry {
    std::string  name;
    fs::path     path;
    std::uintmax_t size;
    bool         isDir;
    FileCategory category;

    /// Human-readable file size.
    [[nodiscard]] std::string humanSize() const {
        double n = static_cast<double>(size);
        const char* units[] = {"B", "KB", "MB", "GB", "TB"};
        int i = 0;
        while (n >= 1024.0 && i < 4) { n /= 1024.0; ++i; }
        return i == 0
            ? std::format("{:.0f} B", n)
            : std::format("{:.1f} {}", n, units[i]);
    }
};

// ---- Categorisation ----

FileCategory categorize(const fs::path& p) {
    const auto ext = p.extension().string();
    if (ext == ".md" || ext == ".markdown") return FileCategory::Markdown;
    if (ext == ".py" || ext == ".js"  || ext == ".ts" ||
        ext == ".go" || ext == ".rs"  || ext == ".cpp" ||
        ext == ".c"  || ext == ".java"|| ext == ".sh")
        return FileCategory::Code;
    if (ext == ".png" || ext == ".jpg" || ext == ".gif"  ||
        ext == ".webp"|| ext == ".svg")
        return FileCategory::Image;
    if (ext == ".mp4" || ext == ".webm")  return FileCategory::Video;
    if (ext == ".mp3" || ext == ".ogg")   return FileCategory::Audio;
    if (ext == ".dot" || ext == ".gv")    return FileCategory::Diagram;
    if (ext == ".pdf")                    return FileCategory::Document;
    if (ext == ".txt" || ext == ".log"  ||
        ext == ".csv" || ext == ".json" ||
        ext == ".yaml"|| ext == ".xml")   return FileCategory::Text;
    return FileCategory::Other;
}

// ---- Generic filter template ----

template <typename Range, typename Pred>
auto filter_entries(Range&& entries, Pred pred)
    -> std::vector<FileEntry>
{
    std::vector<FileEntry> result;
    for (auto& e : entries) {
        if (pred(e)) result.push_back(e);
    }
    return result;
}

// ---- Directory lister ----

std::vector<FileEntry> listDir(const fs::path& dir) {
    std::vector<FileEntry> entries;
    for (const auto& de : fs::directory_iterator(dir)) {
        const bool isDir = de.is_directory();
        const auto size  = isDir ? 0 : de.file_size();
        entries.push_back({
            de.path().filename().string(),
            de.path(),
            size,
            isDir,
            isDir ? FileCategory::Other : categorize(de.path())
        });
    }
    std::ranges::sort(entries, {}, &FileEntry::name);
    return entries;
}

// ---- Main ----

int main(int argc, char* argv[]) {
    const fs::path root = argc > 1 ? argv[1] : ".";

    if (!fs::is_directory(root)) {
        std::cerr << "Not a directory: " << root << "\n";
        return 1;
    }

    auto entries = listDir(root);

    std::cout << std::format("{:<40}  {:<10}  {}\n", "Name", "Size", "Category");
    std::cout << std::string(70, '-') << "\n";
    for (const auto& e : entries) {
        std::cout << std::format("{:<40}  {:<10}  {}\n",
            e.name, e.humanSize(), categoryName(e.category));
    }

    // Filter to code files using the template function
    auto codeFiles = filter_entries(entries, [](const FileEntry& e) {
        return e.category == FileCategory::Code;
    });
    std::cout << "\nCode files: " << codeFiles.size() << "\n";

    return 0;
}
