import React from 'react';
import { Plus, MessageSquare } from 'lucide-react';
import './RightSidebar.css';

interface RightSidebarProps {
  chatContext: any;
}

const RightSidebar: React.FC<RightSidebarProps> = ({ chatContext }) => {
  const { sessions, activeSessionId, setActiveSessionId, createNewSession } = chatContext;

  return (
    <div className="right-sidebar">
      <button className="new-chat-btn" onClick={createNewSession}>
        <Plus size={18} className="btn-icon" />
        Cuộc trò chuyện mới
      </button>

      <div className="recent-section">
        <h3 className="recent-title">Gần đây</h3>
        <p className="recent-subtitle">30 ngày gần đây</p>
        
        <div className="history-list">
          {sessions.map((session: any) => (
            <div 
              key={session.id}
              className={`history-item ${session.id === activeSessionId ? 'active' : ''}`}
              onClick={() => setActiveSessionId(session.id)}
            >
              <MessageSquare size={16} className="history-icon" />
              <span className="history-text">{session.title}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default RightSidebar;
