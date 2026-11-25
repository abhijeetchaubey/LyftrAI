import React from 'react';
import { Bot, User, AlertTriangle } from 'lucide-react';
import MessageMetadata from './MessageMetadata';

export default function ChatMessage({ message }) {
  const { role, content, metadata } = message;

  if (role === 'error') {
    return (
      <div className="flex justify-start w-full">
        <div className="flex items-start gap-2.5 max-w-[85%] bg-red-950/50 border border-red-500/40 text-red-200 rounded-2xl px-4 py-3 text-sm">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <p className="whitespace-pre-wrap break-words">{content}</p>
        </div>
      </div>
    );
  }

  const isAssistant = role === 'assistant';

  return (
    <div
      className={`flex w-full ${isAssistant ? 'justify-start' : 'justify-end'}`}
    >
      <div
        className={`flex items-start gap-3 max-w-[85%] sm:max-w-[78%] ${
          isAssistant ? 'flex-row' : 'flex-row-reverse'
        }`}
      >
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
            isAssistant
              ? 'bg-indigo-600/20 text-indigo-400 border border-indigo-500/30'
              : 'bg-slate-700 text-slate-200'
          }`}
        >
          {isAssistant ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
        </div>

        <div className="flex flex-col">
          <div
            data-testid={isAssistant ? 'assistant-message' : 'user-message'}
            className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              isAssistant
                ? 'bg-slate-900 border border-slate-800 text-slate-100 rounded-tl-sm'
                : 'bg-indigo-600 text-white rounded-tr-sm'
            }`}
          >
            <p className="whitespace-pre-wrap break-words">{content}</p>
          </div>

          {isAssistant && metadata && <MessageMetadata metadata={metadata} />}
        </div>
      </div>
    </div>
  );
}
