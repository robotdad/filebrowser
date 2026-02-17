class ApiClient {
    async request(url, options = {}) {
        const response = await fetch(url, {
            credentials: 'same-origin',
            ...options,
        });

        if (response.status === 401) {
            window.dispatchEvent(new CustomEvent('auth:logout'));
            throw new Error('Unauthorized');
        }

        if (!response.ok) {
            const body = await response.json().catch(() => ({ error: response.statusText }));
            this.showToast(body.error || body.detail?.error || 'An error occurred');
            throw new Error(body.error || response.statusText);
        }

        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        }
        return response.text();
    }

    get(url) {
        return this.request(url);
    }

    post(url, body) {
        const isFormData = body instanceof FormData;
        return this.request(url, {
            method: 'POST',
            headers: isFormData ? {} : { 'Content-Type': 'application/json' },
            body: isFormData ? body : JSON.stringify(body),
        });
    }

    put(url, body) {
        return this.request(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    }

    del(url) {
        return this.request(url, { method: 'DELETE' });
    }

    showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'toast toast-error';
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }
}

export const api = new ApiClient();
