import React, { useState, useEffect } from 'react';
import './DocumentRelationModal.css';

interface Document {
  so_hieu: string;
  ten_van_ban: string;
}

interface DocumentRelationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const DocumentRelationModal: React.FC<DocumentRelationModalProps> = ({ isOpen, onClose }) => {
  const [file, setFile] = useState<File | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Document[]>([]);
  const [selectedTarget, setSelectedTarget] = useState<Document | null>(null);
  const [relationType, setRelationType] = useState('Thay thế');
  const [availableTypes, setAvailableTypes] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ type: '', message: '' });

  const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

  useEffect(() => {
    if (isOpen) {
      fetchRelationTypes();
    }
  }, [isOpen]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchQuery.length >= 2) {
        handleSearch();
      } else {
        setSearchResults([]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const fetchRelationTypes = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/relation-types`);
      const data = await response.json();
      setAvailableTypes(data);
      if (data.length > 0 && !data.includes(relationType)) {
        setRelationType(data[0]);
      }
    } catch (error) {
      console.error('Error fetching relation types:', error);
    }
  };

  const handleSearch = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/documents/search?query=${encodeURIComponent(searchQuery)}`);
      const data = await response.json();
      setSearchResults(data);
    } catch (error) {
      console.error('Error searching documents:', error);
    }
  };

  const handleUpload = async () => {
    if (!file || !selectedTarget) {
      setStatus({ type: 'error', message: 'Vui lòng chọn file và văn bản quan hệ' });
      return;
    }

    setLoading(true);
    setStatus({ type: 'info', message: 'Đang xử lý...' });

    const formData = new FormData();
    formData.append('file', file);
    formData.append('replaced_so_hieu', selectedTarget.so_hieu);
    formData.append('relation_type', relationType);

    try {
      const response = await fetch(`${API_BASE_URL}/api/replace-document`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      if (response.ok) {
        setStatus({ type: 'success', message: `Thành công! Đã tạo quan hệ giữa văn bản mới và ${selectedTarget.so_hieu}` });
        setTimeout(() => {
          onClose();
          setStatus({ type: '', message: '' });
          setFile(null);
          setSelectedTarget(null);
        }, 2000);
      } else {
        setStatus({ type: 'error', message: data.detail || 'Lỗi không xác định' });
      }
    } catch (error) {
      setStatus({ type: 'error', message: 'Lỗi kết nối server' });
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Quản lý quan hệ văn bản</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        
        <div className="modal-body">
          <div className="form-section">
            <label>1. Tải lên văn bản mới:</label>
            <div className="file-input-wrapper">
              <input 
                id="file-upload"
                type="file" 
                accept=".doc,.docx" 
                onChange={e => setFile(e.target.files?.[0] || null)}
                style={{ display: 'none' }}
              />
              <label htmlFor="file-upload" className="custom-file-btn">
                {file ? 'Đổi file khác' : 'Chọn file...'}
              </label>
              {file && <span className="file-name-display" title={file.name}>{file.name}</span>}
            </div>
          </div>

          <div className="form-section">
            <label>2. Tìm văn bản quan hệ (Gốc):</label>
            <div className="search-box">
              <input 
                type="text" 
                placeholder="Nhập số hiệu hoặc tên văn bản..." 
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
              {searchResults.length > 0 && (
                <ul className="search-dropdown">
                  {searchResults.map(doc => (
                    <li key={doc.so_hieu} onClick={() => {
                      setSelectedTarget(doc);
                      setSearchQuery('');
                      setSearchResults([]);
                    }}>
                      <span className="res-so-hieu">{doc.so_hieu}</span>
                      <span className="res-ten">{doc.ten_van_ban}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {selectedTarget && (
              <div className="selected-tag">
                Đang chọn: <strong>{selectedTarget.so_hieu}</strong>
                <button onClick={() => setSelectedTarget(null)}>&times;</button>
              </div>
            )}
          </div>

          <div className="form-section">
            <label>3. Loại quan hệ:</label>
            <select value={relationType} onChange={e => setRelationType(e.target.value)}>
              {availableTypes.map(t => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>

          {status.message && (
            <div className={`modal-status ${status.type}`}>
              <div className="status-header">
                {status.type === 'error' ? '❌ Lỗi hệ thống' : 'ℹ️ Thông báo'}
              </div>
              <div className="status-body">
                {typeof status.message === 'string' ? status.message : JSON.stringify(status.message)}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="cancel-btn" onClick={onClose}>Hủy bỏ</button>
          <button 
            className="submit-btn" 
            onClick={handleUpload}
            disabled={loading || !file || !selectedTarget}
          >
            {loading ? 'Đang xử lý...' : 'Xác nhận liên kết'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DocumentRelationModal;
