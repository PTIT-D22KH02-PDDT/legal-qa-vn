import React, { useState } from 'react';
import { Home, Sparkles, MessageSquare, LogOut, FileEdit } from 'lucide-react';
import './LeftSidebar.css';
import DocumentRelationModal from './DocumentRelationModal';

const LeftSidebar: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);

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

        <div className="sidebar-section">
          <div className="section-title">
            <span>QUẢN LÝ VĂN BẢN</span>
          </div>
          <div className="nav-item" onClick={() => setIsModalOpen(true)}>
            <FileEdit className="nav-icon" size={18} />
            <span>Liên kết văn bản</span>
          </div>
        </div>
      </div>

      <DocumentRelationModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
      />

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
