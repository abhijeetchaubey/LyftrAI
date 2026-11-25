// src/hooks/useChat.jsx
import { useState, useCallback } from 'react';
import { postChat, getHealth, getSessionMessages } from '../services/api';

// Utility to generate a random session id (max 128 chars)
const generateSessionId = () => {
  const rand = Math.random().toString(36).substring(2, 10);
  return `session-${Date.now()}-${rand}`;
};

export default function useChat() {
  const [sessionId] = useState(() => generateSessionId());
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState('');

  const sendMessage = useCallback(
    async (text) => {
      setLoading(true);
      try {
        // optimistic UI: add user message immediately
        const userMsg = { role: 'user', content: text };
        setMessages((prev) => [...prev, userMsg]);

        const payload = {
          session_id: sessionId,
          message: text,
          system_prompt: systemPrompt || undefined,
        };
        const resp = await postChat(payload);
        const data = resp.data;
        const assistantMsg = {
          role: 'assistant',
          content: data.reply,
          metadata: data.metadata,
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        console.error('Chat error', err);
        // on error, replace the optimistic user message with error info
        setMessages((prev) => {
          const withoutLast = prev.slice(0, -1);
          return [...withoutLast, { role: 'assistant', content: 'Error: unable to get response', metadata: {} }];
        });
      } finally {
        setLoading(false);
      }
    },
    [sessionId, systemPrompt]
  );

  // optional helper to load existing history (not used on first load)
  const loadHistory = useCallback(async () => {
    try {
      const resp = await getSessionMessages(sessionId);
      setMessages(resp.data.messages.map((m) => ({ role: m.role, content: m.content, metadata: m.metadata })));
    } catch (e) {
      // ignore 404 (no history yet)
    }
  }, [sessionId]);

  // expose health check for possible UI use
  const checkHealth = useCallback(async () => {
    const resp = await getHealth();
    return resp.data;
  }, []);

  return {
    sessionId,
    messages,
    loading,
    systemPrompt,
    setSystemPrompt,
    sendMessage,
    loadHistory,
    checkHealth,
  };
}
