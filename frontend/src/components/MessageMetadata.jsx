import React from 'react';
import { Zap, Database, Clock, ArrowUpRight, ArrowDownLeft, KeyRound, RefreshCw } from 'lucide-react';

export default function MessageMetadata({ metadata }) {
  if (!metadata) return null;

  const {
    resolution_source,
    model,
    latency_ms,
    input_tokens,
    output_tokens,
    key_id,
    fallback_attempts,
  } = metadata;

  const isCache = resolution_source === 'LLM_CACHE';

  return (
    <div
      className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400"
      data-testid="metadata-panel"
    >
      <span
        data-testid="meta-source"
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium border ${
          isCache
            ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
            : 'bg-indigo-500/10 text-indigo-300 border-indigo-500/30'
        }`}
      >
        {isCache ? <Database className="w-3 h-3" /> : <Zap className="w-3 h-3" />}
        {resolution_source}
      </span>

      <span
        data-testid="meta-model"
        className="inline-flex items-center px-2 py-0.5 rounded-md bg-slate-800/80 text-slate-300 border border-slate-700/60"
      >
        {model}
      </span>

      <span
        data-testid="meta-latency"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-800/60 text-slate-300"
      >
        <Clock className="w-3 h-3 text-slate-400" />
        {latency_ms} ms
      </span>

      <span
        data-testid="meta-input-tokens"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-800/60 text-slate-300"
        title="Input tokens"
      >
        <ArrowUpRight className="w-3 h-3 text-sky-400" />
        In: {input_tokens}
      </span>

      <span
        data-testid="meta-output-tokens"
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-800/60 text-slate-300"
        title="Output tokens"
      >
        <ArrowDownLeft className="w-3 h-3 text-violet-400" />
        Out: {output_tokens}
      </span>

      {key_id && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-800/60 text-slate-400">
          <KeyRound className="w-3 h-3" />
          {key_id}
        </span>
      )}

      {typeof fallback_attempts === 'number' && fallback_attempts > 0 && (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-amber-500/10 text-amber-300 border border-amber-500/30">
          <RefreshCw className="w-3 h-3" />
          Retries: {fallback_attempts}
        </span>
      )}
    </div>
  );
}
