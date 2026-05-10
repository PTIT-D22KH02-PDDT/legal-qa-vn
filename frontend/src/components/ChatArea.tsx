import React from 'react';
import { Download, Send, Zap } from 'lucide-react';
import ChatMessage from './ChatMessage';
import './ChatArea.css';

interface ChatAreaProps {
  chatContext: any;
}

const ChatArea: React.FC<ChatAreaProps> = ({ chatContext }) => {
  const { messages, input, setInput, isLoading, sendMessage, handleKeyPress, messagesEndRef, activeSession } = chatContext;

  const currentTitle = activeSession?.title || 'Cuộc trò chuyện mới';

  return (
    <div className="chat-area">
      <div className="chat-header">
        <h2 className="chat-title">{currentTitle}</h2>
        <button className="download-btn">
          <Download size={20} />
        </button>
      </div>

      <div className="chat-messages-container">
        {messages.map((msg: any) => (
          <ChatMessage
            key={msg.id}
            role={msg.role}
            content={msg.content}
            citation={msg.citation}
            time={msg.time}
          />
        ))}
        {isLoading && (
          <div className="loading-indicator">
            <div className="typing-dot"></div>
            <div className="typing-dot"></div>
            <div className="typing-dot"></div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-wrapper">
        <div className="chat-input-container">
          <button className="advanced-ai-btn">
            <Zap size={14} className="btn-icon" />
            AI nâng cao
          </button>
          
          <input
            type="text"
            className="chat-input"
            placeholder="Nhập thắc mắc của bạn tại đây..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={isLoading}
          />
          
          <div className="input-actions">
            <span className="char-count">{input.length} / 2000 từ</span>
            <button 
              className={`send-btn ${input.trim() ? 'active' : ''}`}
              onClick={sendMessage}
              disabled={isLoading || !input.trim()}
            >
              <Send size={18} />
            </button>
          </div>
        </div>
        <p className="input-disclaimer">AI pháp luật đang hoàn thiện mỗi ngày. Hãy kiểm tra những thông tin quan trọng.</p>
      </div>
    </div>
  );
};

export default ChatArea;
