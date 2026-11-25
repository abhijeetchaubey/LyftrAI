import React from 'react';
import { SlidersHorizontal } from 'lucide-react';

export default function SystemPrompt({ systemPrompt, setSystemPrompt, disabled }) {
  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-3">
      <label
        htmlFor="system-prompt-input"
        className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400 mb-2"
      >
        <SlidersHorizontal className="w-3.5 h-3.5 text-indigo-400" />
        System Prompt
      </label>
      <textarea
        id="system-prompt-input"
        data-testid="system-prompt-input"
        className="w-full bg-slate-950/80 text-slate-200 text-sm rounded-lg border border-slate-800 px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 placeholder-slate-500 transition"
        rows={2}
        value={systemPrompt}
        onChange={(e) => setSystemPrompt(e.target.value)}
        placeholder="Optional system prompt (e.g., You are a helpful AI assistant.)"
        disabled={disabled}
      />
    </div>
  );
}
