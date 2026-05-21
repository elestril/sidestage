import type { ChatMessage } from '../types_ext';

export interface MessageItemProps {
  message: ChatMessage;
  isOwn: boolean;
}

/**
 * frontend-messageitem:
 * - frontend-messageitem-own: isOwn → right-aligned with distinct classes.
 * - frontend-messageitem-other: non-own → left-aligned.
 * - frontend-messageitem-sender: sender.name displayed above body.
 * - frontend-messageitem-data: carries `data-scene-id` and `data-index` for
 *   stable selectors (browser tests, debugging).
 */
export function MessageItem({ message, isOwn }: MessageItemProps) {
  return (
    <li
      data-testid="message-item"
      data-scene-id={message.scene_id}
      data-index={message.index}
      data-sender-id={message.sender.id}
      className={`flex ${isOwn ? 'justify-end' : 'justify-start'}`}
    >
      <div className={`flex max-w-[75%] flex-col ${isOwn ? 'items-end' : 'items-start'}`}>
        <span className="mb-0.5 text-xs font-medium text-slate-500">
          {message.sender.name}
        </span>
        <div
          className={`whitespace-pre-wrap rounded-lg px-3 py-2 text-sm shadow-sm ${
            isOwn
              ? 'bg-blue-600 text-white'
              : 'bg-white text-slate-900 ring-1 ring-slate-200'
          }`}
        >
          {message.body}
        </div>
      </div>
    </li>
  );
}
