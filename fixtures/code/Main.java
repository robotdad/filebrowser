// Main.java — Java fixture for CodeMirror syntax highlighting test.
// Exercises: public class, generics, interface, enum, lambda, streams,
// Optional, record, switch expression.

package com.example.filebrowser;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

/** Entry-point demonstrating the file categoriser. */
public class Main {

    /** Supported file categories. */
    public enum Category {
        MARKDOWN, CODE, IMAGE, VIDEO, AUDIO, DIAGRAM, DOCUMENT, TEXT, OTHER
    }

    /**
     * An immutable record representing one file-system entry.
     * Java 16+ record syntax.
     */
    public record FileEntry(String name, Path path, long size, boolean isDir) {

        /** Infer category from extension. */
        public Category category() {
            if (isDir) return Category.OTHER;
            String ext = extension().toLowerCase();
            return switch (ext) {
                case "md", "markdown"       -> Category.MARKDOWN;
                case "py", "js", "ts",
                     "go", "rs", "java",
                     "cpp", "c", "sh"       -> Category.CODE;
                case "png", "jpg", "jpeg",
                     "gif", "webp", "svg"   -> Category.IMAGE;
                case "mp4", "webm"          -> Category.VIDEO;
                case "mp3", "ogg", "wav"    -> Category.AUDIO;
                case "dot", "gv"            -> Category.DIAGRAM;
                case "pdf"                  -> Category.DOCUMENT;
                case "txt", "log", "csv",
                     "json", "yaml", "xml"  -> Category.TEXT;
                default                     -> Category.OTHER;
            };
        }

        /** Extract the file extension (without leading dot). */
        public String extension() {
            String name = path.getFileName().toString();
            int dot = name.lastIndexOf('.');
            return dot >= 0 ? name.substring(dot + 1) : "";
        }

        /** Human-readable size. */
        public String humanSize() {
            String[] units = {"B", "KB", "MB", "GB"};
            double n = size;
            int i = 0;
            while (n >= 1024 && i < units.length - 1) {
                n /= 1024;
                i++;
            }
            return i == 0 ? String.format("%.0f B", n)
                          : String.format("%.1f %s", n, units[i]);
        }
    }

    /** Read a directory and return a list of FileEntry objects. */
    public static List<FileEntry> listDir(Path dir) throws IOException {
        try (var stream = Files.list(dir)) {
            return stream
                .map(p -> {
                    try {
                        long size = Files.isDirectory(p) ? 0 : Files.size(p);
                        return new FileEntry(p.getFileName().toString(), p, size, Files.isDirectory(p));
                    } catch (IOException e) {
                        return new FileEntry(p.getFileName().toString(), p, 0, false);
                    }
                })
                .sorted(Comparator.comparing(FileEntry::name))
                .collect(Collectors.toList());
        }
    }

    /** Group entries by category. */
    public static Map<Category, List<FileEntry>> groupByCategory(List<FileEntry> entries) {
        return entries.stream().collect(Collectors.groupingBy(FileEntry::category));
    }

    /** Find first entry with a given name. */
    public static Optional<FileEntry> findByName(List<FileEntry> entries, String name) {
        return entries.stream()
            .filter(e -> e.name().equalsIgnoreCase(name))
            .findFirst();
    }

    public static void main(String[] args) throws IOException {
        Path root = args.length > 0 ? Path.of(args[0]) : Path.of(".");
        List<FileEntry> entries = listDir(root);

        System.out.printf("%-40s  %-10s  %s%n", "Name", "Size", "Category");
        System.out.println("-".repeat(70));
        entries.forEach(e ->
            System.out.printf("%-40s  %-10s  %s%n",
                e.name(), e.humanSize(), e.category()));

        System.out.println();
        groupByCategory(entries).forEach((cat, list) ->
            System.out.printf("%s: %d file(s)%n", cat, list.size()));
    }
}
