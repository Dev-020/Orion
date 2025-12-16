import { useNavigate } from 'react-router-dom';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Standardized API Wrapper
 * Automatically handles:
 * 1. Base URL
 * 2. Authorization Header
 * 3. Ngrok Bypass Header
 * 4. Content-Type keys
 */
export const orionApi = {
    get: async (endpoint) => {
        return request(endpoint, { method: 'GET' });
    },
    
    post: async (endpoint, body) => {
        return request(endpoint, { 
            method: 'POST', 
            body: body instanceof FormData ? body : JSON.stringify(body),
            // Let browser set Content-Type for FormData
            headers: body instanceof FormData ? {} : { 'Content-Type': 'application/json' }
        });
    }
};

const request = async (endpoint, options = {}) => {
    const token = localStorage.getItem('orion_auth_token');
    
    // Merge headers
    const headers = {
        'ngrok-skip-browser-warning': 'true', // The Fix
        ...(options.headers || {})
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    // Ensure leading slash
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

    const config = {
        ...options,
        headers
    };

    try {
        const response = await fetch(`${API_BASE}${path}`, config);
        
        // Handle global auth errors (401)
        if (response.status === 401) {
            console.warn("Unauthorized access - Token might be expired.");
            // Optional: Trigger logout logic if we had access to context, 
            // but simpler to let component handle or event bus.
        }

        return response;
    } catch (error) {
        console.error(`API Request Failed: ${path}`, error);
        throw error;
    }
};
