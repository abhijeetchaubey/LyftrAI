import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const postChat = async (payload, simulateFailureHeader = null) => {
  const headers = {};
  if (simulateFailureHeader && simulateFailureHeader.trim()) {
    headers['X-Simulate-Failure'] = simulateFailureHeader.trim();
  }
  const response = await api.post('/chat', payload, { headers });
  return response.data;
};

export const getHealth = async () => {
  const response = await api.get('/health');
  return response.data;
};

export const getSessionMessages = async (sessionId) => {
  const response = await api.get(`/sessions/${encodeURIComponent(sessionId)}/messages`);
  return response.data;
};

export default api;
