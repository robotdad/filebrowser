import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from filebrowser.routes.files import router as files_router, get_fs
from filebrowser.auth import require_auth
from filebrowser.services.filesystem import FilesystemService


@pytest.fixture
def client(tmp_home):
    app = FastAPI()
    app.include_router(files_router)
    app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
    app.dependency_overrides[require_auth] = lambda: "testuser"
    with TestClient(app) as c:
        yield c


@pytest.fixture
def unauth_client(tmp_home):
    app = FastAPI()
    app.include_router(files_router)
    app.dependency_overrides[get_fs] = lambda: FilesystemService(tmp_home)
    with TestClient(app) as c:
        yield c


class TestListDirectory:
    def test_list_root(self, client):
        response = client.get("/api/files", params={"path": ""})
        assert response.status_code == 200
        names = [e["name"] for e in response.json()]
        assert "docs" in names
        assert "hello.txt" in names

    def test_list_subdirectory(self, client):
        response = client.get("/api/files", params={"path": "docs"})
        assert response.status_code == 200
        names = [e["name"] for e in response.json()]
        assert "readme.md" in names

    def test_list_nonexistent_returns_404(self, client):
        response = client.get("/api/files", params={"path": "nonexistent"})
        assert response.status_code == 404

    def test_list_traversal_returns_403(self, client):
        response = client.get("/api/files", params={"path": "../../etc"})
        assert response.status_code == 403


class TestFileInfo:
    def test_file_info(self, client):
        response = client.get("/api/files/info", params={"path": "hello.txt"})
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "hello.txt"
        assert data["type"] == "file"
        assert data["category"] == "text"

    def test_info_not_found(self, client):
        response = client.get("/api/files/info", params={"path": "nope.txt"})
        assert response.status_code == 404


class TestFileContent:
    def test_read_text_file(self, client):
        response = client.get("/api/files/content", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert "Hello World" in response.text

    def test_content_not_found(self, client):
        response = client.get("/api/files/content", params={"path": "nope.txt"})
        assert response.status_code == 404

    def test_content_traversal_returns_403(self, client):
        response = client.get("/api/files/content", params={"path": "../../etc/passwd"})
        assert response.status_code == 403
    
    def test_svg_has_correct_content_type(self, client):
        """SVG files must be served with image/svg+xml for browser rendering."""
        response = client.get("/api/files/content", params={"path": "images/logo.svg"})
        assert response.status_code == 200
        assert response.headers.get("content-type") == "image/svg+xml"
        assert "<svg" in response.text
    
    def test_svg_has_security_headers(self, client):
        """SVG files must have XSS prevention headers to block embedded scripts."""
        response = client.get("/api/files/content", params={"path": "images/logo.svg"})
        assert response.status_code == 200
        # Verify X-Content-Type-Options header prevents MIME sniffing
        assert response.headers.get("x-content-type-options") == "nosniff"
        # Verify CSP sandboxes the SVG and blocks script execution
        csp = response.headers.get("content-security-policy")
        assert csp is not None
        assert "default-src 'none'" in csp
        assert "sandbox" in csp
    
    def test_text_file_content_type_remains_text_plain(self, client):
        """Text files should still be served as text/plain (regression guard)."""
        response = client.get("/api/files/content", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/plain; charset=utf-8"
    
    def test_jpg_has_correct_content_type(self, client):
        """JPEG images should be served with image/jpeg."""
        response = client.get("/api/files/content", params={"path": "images/photo.jpg"})
        assert response.status_code == 200
        content_type = response.headers.get("content-type")
        assert content_type in ("image/jpeg", "image/jpg")
    
    def test_pdf_has_correct_content_type(self, client):
        """PDF files must be served with application/pdf for browser rendering."""
        response = client.get("/api/files/content", params={"path": "sample.pdf"})
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
    
    def test_pdf_does_not_set_content_disposition(self, client):
        """PDF files must NOT set Content-Disposition: attachment (viewing, not downloading)."""
        response = client.get("/api/files/content", params={"path": "sample.pdf"})
        assert response.status_code == 200
        cd = response.headers.get("content-disposition", "")
        assert "attachment" not in cd
    
    def test_html_has_correct_content_type(self, client):
        """HTML files must be served with text/html for browser rendering."""
        response = client.get("/api/files/content", params={"path": "page.html"})
        assert response.status_code == 200
        assert response.headers.get("content-type") == "text/html; charset=utf-8"
        assert "<h1>Hello HTML</h1>" in response.text
    
    def test_html_has_security_headers(self, client):
        """HTML files must have XSS prevention headers to block embedded scripts and data exfiltration."""
        response = client.get("/api/files/content", params={"path": "malicious.html"})
        assert response.status_code == 200
        # Verify X-Content-Type-Options header prevents MIME sniffing
        assert response.headers.get("x-content-type-options") == "nosniff"
        # Verify CSP sandboxes the HTML and blocks script execution + external resource loading
        csp = response.headers.get("content-security-policy")
        assert csp is not None
        # Must include default-src 'none' to block external resource loading (data exfiltration)
        assert "default-src 'none'" in csp
        # Must include style-src 'unsafe-inline' to allow inline styles
        assert "style-src 'unsafe-inline'" in csp
        # Must include sandbox to create opaque origin
        assert "sandbox" in csp
        # Ensure CSP does NOT contain allow-scripts or allow-same-origin
        assert "allow-scripts" not in csp
        assert "allow-same-origin" not in csp
    
    def test_html_body_is_rendered(self, client):
        """HTML files should render as HTML, not as plain text."""
        response = client.get("/api/files/content", params={"path": "page.html"})
        assert response.status_code == 200
        # Verify the response contains HTML tags (rendering, not source text)
        assert "<html>" in response.text or "<HTML>" in response.text
        assert "<h1>" in response.text
    
    @pytest.mark.parametrize("path,description", [
        ("hello.txt", "text files"),
        ("images/logo.svg", "SVG images"),
        ("images/photo.jpg", "JPEG images"),
        ("sample.pdf", "PDF files"),
        ("page.html", "HTML files"),
    ])
    def test_content_has_cache_control_no_cache(self, client, path, description):
        """All content endpoints must set Cache-Control: no-cache to prevent stale content.
        
        This forces browser revalidation on every request while still allowing cheap 304
        responses via ETag/Last-Modified headers. Prevents the browser from serving stale
        file content from disk cache after on-disk file changes.
        """
        response = client.get("/api/files/content", params={"path": path})
        assert response.status_code == 200
        cache_control = response.headers.get("cache-control")
        assert cache_control is not None, f"{description} must have Cache-Control header"
        assert "no-cache" in cache_control, f"{description} must have Cache-Control: no-cache"


class TestDownload:
    def test_download_sets_content_disposition(self, client):
        response = client.get("/api/files/download", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert "attachment" in response.headers.get("content-disposition", "")


class TestUpload:
    def test_upload_file(self, client, tmp_home):
        response = client.post(
            "/api/files/upload",
            params={"path": ""},
            files={"file": ("uploaded.txt", b"file content", "text/plain")},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "uploaded.txt"
        assert (tmp_home / "uploaded.txt").read_text() == "file content"

    def test_upload_to_subdirectory(self, client, tmp_home):
        response = client.post(
            "/api/files/upload",
            params={"path": "docs"},
            files={"file": ("new.txt", b"new content", "text/plain")},
        )
        assert response.status_code == 200
        assert (tmp_home / "docs" / "new.txt").read_text() == "new content"

    def test_upload_to_nonexistent_dir_returns_error(self, client):
        response = client.post(
            "/api/files/upload",
            params={"path": "nonexistent"},
            files={"file": ("test.txt", b"data", "text/plain")},
        )
        assert response.status_code in (400, 404)


class TestMkdir:
    def test_create_directory(self, client, tmp_home):
        response = client.post("/api/files/mkdir", params={"path": "new_folder"})
        assert response.status_code == 200
        assert (tmp_home / "new_folder").is_dir()


class TestRename:
    def test_rename_file(self, client, tmp_home):
        response = client.put(
            "/api/files/rename",
            json={"old_path": "hello.txt", "new_path": "renamed.txt"},
        )
        assert response.status_code == 200
        assert not (tmp_home / "hello.txt").exists()
        assert (tmp_home / "renamed.txt").exists()

    def test_rename_nonexistent_returns_404(self, client):
        response = client.put(
            "/api/files/rename",
            json={"old_path": "nonexistent.txt", "new_path": "other.txt"},
        )
        assert response.status_code == 404


class TestDelete:
    def test_delete_file(self, client, tmp_home):
        response = client.delete("/api/files", params={"path": "hello.txt"})
        assert response.status_code == 200
        assert not (tmp_home / "hello.txt").exists()

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete("/api/files", params={"path": "nope.txt"})
        assert response.status_code == 404

    def test_delete_traversal_returns_403(self, client):
        response = client.delete("/api/files", params={"path": "../../etc/passwd"})
        assert response.status_code == 403


class TestAuthEnforcement:
    def test_list_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/files", params={"path": ""})
        assert response.status_code == 401

    def test_content_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/files/content", params={"path": "hello.txt"})
        assert response.status_code == 401

    def test_upload_requires_auth(self, unauth_client):
        response = unauth_client.post(
            "/api/files/upload",
            params={"path": ""},
            files={"file": ("test.txt", b"data", "text/plain")},
        )
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauth_client):
        response = unauth_client.delete("/api/files", params={"path": "hello.txt"})
        assert response.status_code == 401
