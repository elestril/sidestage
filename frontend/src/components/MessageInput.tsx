import { useState, type KeyboardEvent } from 'react';

export interface MessageInputProps {
  connected: boolean;
  onSend: (body: string) => void;
}

/**
 * frontend-messageinput:
 * - frontend-input-disabled: input + button disabled when not connected.
 * - frontend-input-submit-button: send button calls onSend(body) and clears.
 * - frontend-input-submit-enter: Enter (without Shift) submits.
 */
export function MessageInput({ connected, onSend }: MessageInputProps) {
  const [body, setBody] = useState('');

  const submit = () => {
    const trimmed = body.trim();
    if (!trimmed || !connected) return;
    onSend(trimmed);
    setBody('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2">
      <textarea
        className="min-h-[2.5rem] flex-1 resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
        rows={1}
        placeholder={connected ? 'Type a message…' : 'Disconnected'}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={!connected}
      />
      <button
        type="button"
        className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-300"
        onClick={submit}
        disabled={!connected || !body.trim()}
      >
        Send
      </button>
    </div>
  );
}
