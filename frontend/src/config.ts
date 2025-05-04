// src/config.ts

const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

export const API_BASE_URL = isLocalhost ? 'http://localhost:5001/api' : import.meta.env.VITE_API_URL + '/api';
