import React from 'react';
import { Home, Sparkles, MessageSquare, LogOut, Info } from 'lucide-react';
import './LeftSidebar.css';

const LeftSidebar: React.FC = () => {
  return (
    <div className="left-sidebar">
      <div className="sidebar-top">
        <div className="sidebar-header">
          <span className="logo-text">CỔNG THÔNG TIN</span>
        </div>
        
        <div className="sidebar-nav">
          <div className="nav-item">
            <Home className="nav-icon" size={18} />
            <span>Cổng pháp luật quốc gia</span>
          </div>
        </div>

        <div className="sidebar-section">
          <div className="section-title">
            <span>TIỆN ÍCH</span>
            <span className="badge-new">Mới</span>
          </div>
          <div className="nav-item active">
            <Sparkles className="nav-icon" size={18} />
            <span>AI pháp luật</span>
          </div>
        </div>
      </div>

      <div className="sidebar-bottom">
        <div className="nav-item">
          <MessageSquare className="nav-icon" size={18} />
          <span>Hỗ trợ và góp ý</span>
        </div>
        <div className="nav-item">
          <LogOut className="nav-icon" size={18} />
          <span>Thoát</span>
        </div>

        <div className="footer-info">
          <p>Phát triển và vận hành bởi</p>
          <p className="bold">AI Luật - Trợ lý LuatVietnam.vn</p>
          <p>Tổng đài hỗ trợ: <span className="highlight">0938 36 1919</span></p>
        </div>
      </div>
    </div>
  );
};

export default LeftSidebar;
