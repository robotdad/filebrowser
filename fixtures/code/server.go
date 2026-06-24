// server.go — Go fixture for CodeMirror syntax highlighting test.
// Exercises: package, struct, method receiver, interface, goroutine,
// channel, error handling, defer, context.

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"
)

// FileEntry represents a single file or directory listing item.
type FileEntry struct {
	Name    string    `json:"name"`
	Path    string    `json:"path"`
	Size    int64     `json:"size"`
	IsDir   bool      `json:"is_dir"`
	ModTime time.Time `json:"mod_time"`
}

// Server holds the HTTP server state.
type Server struct {
	addr string
	mux  *http.ServeMux
	mu   sync.RWMutex
}

// NewServer constructs and registers routes on a new Server.
func NewServer(addr string) *Server {
	s := &Server{addr: addr, mux: http.NewServeMux()}
	s.mux.HandleFunc("/api/files/", s.handleFiles)
	s.mux.HandleFunc("/healthz", s.handleHealth)
	return s
}

// handleFiles serves directory listings as JSON.
func (s *Server) handleFiles(w http.ResponseWriter, r *http.Request) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	path := r.URL.Path[len("/api/files"):]
	if path == "" {
		path = "/"
	}

	entries, err := listDir(path)
	if err != nil {
		http.Error(w, fmt.Sprintf("error: %v", err), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(entries); err != nil {
		log.Printf("encode error: %v", err)
	}
}

// handleHealth returns a simple OK response.
func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte("ok"))
}

// listDir reads the filesystem directory and returns entries.
func listDir(path string) ([]FileEntry, error) {
	entries, err := os.ReadDir(path)
	if err != nil {
		return nil, err
	}
	result := make([]FileEntry, 0, len(entries))
	for _, e := range entries {
		info, err := e.Info()
		if err != nil {
			continue
		}
		result = append(result, FileEntry{
			Name:    e.Name(),
			Path:    path + "/" + e.Name(),
			Size:    info.Size(),
			IsDir:   e.IsDir(),
			ModTime: info.ModTime(),
		})
	}
	return result, nil
}

func main() {
	srv := NewServer(":8080")
	hs := &http.Server{Addr: srv.addr, Handler: srv.mux}

	// Start server in a goroutine.
	go func() {
		log.Printf("listening on %s", srv.addr)
		if err := hs.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("server error: %v", err)
		}
	}()

	// Wait for signal, then shut down gracefully.
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := hs.Shutdown(ctx); err != nil {
		log.Printf("shutdown error: %v", err)
	}
	log.Println("server stopped")
}
