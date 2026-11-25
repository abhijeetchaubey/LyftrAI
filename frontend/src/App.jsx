import React from 'react';
import { Bot, RotateCcw } from 'lucide-react';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';
import SystemPrompt from './components/SystemPrompt';
import useChat from './hooks/useChat';

export default function App() {
  const {
    sessionId,
    messages,
    loading,
    systemPrompt,
    setSystemPrompt,
    healthStatus,
    sendMessage,
    resetSession,
  } = useChat();

  const isHealthy = healthStatus?.status === 'ok';

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-indigo-600 flex items-center justify-center shadow-md shadow-indigo-600/20">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-base sm:text-lg font-semibold tracking-tight text-white">
                Lyftr AI Chatbot
              </h1>
              <p className="text-xs text-slate-400">
                Groq • Multi-Key Failover • LiteLLM Cache
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {healthStatus && (
              <span
                className={`hidden sm:inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border ${
                  isHealthy
                    ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                    : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                }`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    isHealthy ? 'bg-emerald-400' : 'bg-amber-400'
                  }`}
                />
                {isHealthy
                  ? `${healthStatus.keys_configured} Keys • Cache On`
                  : 'Service Degraded'}
              </span>
            )}

            <button
              type="button"
              onClick={resetSession}
              className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition"
              title={`Current Session: ${sessionId}`}
            >
              <RotateCcw className="w-3.5 h-3.5" />
              New Chat
            </button>
          </div>
        </div>
      </header>

      {/* Main Chat Container */}
      <main className="flex-1 max-w-4xl w-full mx-auto px-3 sm:px-4 py-4 flex flex-col gap-3 min-h-0">
        <SystemPrompt
          systemPrompt={systemPrompt}
          setSystemPrompt={setSystemPrompt}
          disabled={loading}
        />

        <div className="flex-1 flex flex-col bg-slate-900/40 border border-slate-800 rounded-2xl overflow-hidden min-h-[420px] max-h-[calc(100vh-230px)]">
          <ChatWindow messages={messages} loading={loading} />
          <ChatInput onSend={sendMessage} disabled={loading} />
        </div>
      </main>
    </div>
  );
}
