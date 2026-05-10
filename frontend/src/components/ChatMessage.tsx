import React from 'react';
import { Sparkles, User } from 'lucide-react';
import './ChatMessage.css';

export interface MessageProps {
  role: 'user' | 'ai';
  content: string;
  time?: string;
  citation?: string;
}

const ChatMessage: React.FC<MessageProps> = ({ role, content, time, citation }) => {
  const isUser = role === 'user';

  return (
    <div className={`chat-message ${isUser ? 'user' : 'ai'}`}>
      <div className="message-avatar">
        {isUser ? (
          <div className="avatar-icon user-avatar">
            <User size={16} />
          </div>
        ) : (
          <div className="avatar-icon ai-avatar">
            <Sparkles size={16} />
          </div>
        )}
      </div>
      
      <div className="message-content-wrapper">
        <div className="message-header">
          <span className="message-sender">{isUser ? 'Bạn' : 'AI pháp luật'}</span>
          {!isUser && <span className="verified-badge">✔</span>}
        </div>
        
        <div className="message-bubble">
          {citation && (
            <div className="citation-block">
              {citation.split('\n').map((line, idx) => (
                <p key={idx}>{line}</p>
              ))}
            </div>
          )}
          
          <div className="message-text">
            {content.split('\n').map((line, idx) => (
              <p key={idx}>{line}</p>
            ))}
          </div>

          {time && <div className="message-time">{time}</div>}
        </div>
      </div>
    </div>
  );
};

export default ChatMessage;
