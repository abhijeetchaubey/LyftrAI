import { useState, useCallback, useEffect } from 'react';
import { postChat, getHealth } from '../services/api';

function createSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `session-${crypto.randomUUID()}`;
  }
  const rand = Math.random().toString(36).substring(2, 10);
  return `session-${Date.now()}-${rand}`;
}

export default function useChat() {
  // Generate a new session_id on every page load and store in sessionStorage
  const [sessionId] = useState(() => {
    const newId = createSessionId();
    try {
      sessionStorage.setItem('chat_session_id', newId);
    } catch {
      // Ignore storage errors in restricted environments
    }
    return newId;
  });

  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful AI assistant.');
  const [healthStatus, setHealthStatus] = useState(null);

  useEffect(() => {
    let active = true;
    getHealth()
      .then((data) => {
        if (active) setHealthStatus(data);
      })
      .catch(() => {
        if (active) setHealthStatus({ status: 'degraded', keys_configured: 0, cache_enabled: false });
      });
    return () => {
      active = false;
    };
  }, []);

  const formatErrorMessage = (err) => {
    const status = err?.response?.status;
    const detail = err?.response?.data?.detail;

    if (status === 422) {
      if (Array.isArray(detail) && detail.length > 0) {
        const firstMsg = detail[0]?.msg || 'Validation error';
        return `Validation error (422): ${firstMsg}`;
      }
      return `Validation error (422): ${typeof detail === 'string' ? detail : 'Invalid request payload.'}`;
    }

    if (status === 503) {
      return `Service unavailable (503): ${typeof detail === 'string' ? detail : 'All LLM providers are currently unavailable. Please try again.'}`;
    }

    if (typeof detail === 'string') {
      return `Error (${status || 'network'}): ${detail}`;
    }

    return err?.message || 'Unable to reach the server. Please check your connection.';
  };

  const sendMessage = useCallback(
    async (text) => {
      if (!text || !text.trim() || loading) return;

      const userMsg = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
      };
      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);

      try {
        const payload = {
          session_id: sessionId,
          message: text,
          system_prompt: systemPrompt.trim() ? systemPrompt.trim() : undefined,
        };
        const data = await postChat(payload);

        const assistantMsg = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        const errorMsg = {
          id: `error-${Date.now()}`,
          role: 'error',
          content: formatErrorMessage(err),
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setLoading(false);
      }
    },
    [sessionId, systemPrompt, loading]
  );

  const resetSession = useCallback(() => {
    window.location.reload();
  }, []);

  return {
    sessionId,
    messages,
    loading,
    systemPrompt,
    setSystemPrompt,
    healthStatus,
    sendMessage,
    resetSession,
  };
}
