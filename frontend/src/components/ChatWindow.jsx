import React, { useEffect, useRef } from 'react';
import { Loader2, Sparkles } from 'lucide-react';
import ChatMessage from './ChatMessage';

export default function ChatWindow({ messages, loading }) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-5 space-y-5">
      {messages.length === 0 && !loading && (
        <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 px-4">
          <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mb-3">
            <Sparkles className="w-6 h-6 text-indigo-400" />
          </div>
          <h2 className="text-base font-semibold text-slate-200 mb-1">
            Start a Conversation
          </h2>
          <p className="text-sm text-slate-400 max-w-md">
            Ask a question below. Responses are routed through Groq with automatic API key failover and LiteLLM caching.
          </p>
        </div>
      )}

      {messages.map((msg) => (
        <ChatMessage key={msg.id} message={msg} />
      ))}

      {loading && (
        <div className="flex justify-start w-full">
          <div className="inline-flex items-center gap-2.5 bg-slate-900 border border-slate-800 text-slate-300 rounded-2xl px-4 py-3 text-sm">
            <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
            <span>Generating response...</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
