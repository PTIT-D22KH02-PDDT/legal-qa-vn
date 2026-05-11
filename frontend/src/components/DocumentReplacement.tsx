import React, { useState, useEffect } from 'react';
import './DocumentReplacement.css';

interface Document {
  so_hieu: string;
  ten_van_ban: string;
}

const DocumentReplacement: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedSoHieu, setSelectedSoHieu] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [status, setStatus] = useState<string>('');

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const response = await fetch('/api/documents');
      if (!response.ok) {
        throw new Error('Failed to fetch documents');
      }
      const data = await response.json();
      if (Array.isArray(data)) {
        setDocuments(data);
      } else {
        console.error('Invalid documents data:', data);
        setDocuments([]);
      }
    } catch (error) {
      console.error('Error fetching documents:', error);
      setStatus('Lỗi khi tải danh sách văn bản');
      setDocuments([]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleReplace = async () => {
    if (!selectedSoHieu || !file) {
      setStatus('Vui lòng chọn văn bản và file upload');
      return;
    }

    setLoading(true);
    setStatus('Đang xử lý...');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('replaced_so_hieu', selectedSoHieu);

    try {
      const response = await fetch('/api/replace-document', {
        method: 'POST',
        body: formData,
      });

      const result = await response.json();
      if (response.ok) {
        setStatus(`Thành công! Đã thay thế bằng văn bản: ${result.new_so_hieu}`);
        // Refresh list
        fetchDocuments();
      } else {
        setStatus(`Lỗi: ${result.detail || 'Không xác định'}`);
      }
    } catch (error) {
      console.error('Error replacing document:', error);
      setStatus('Lỗi kết nối server');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="doc-replace-container">
      <h3>Thay thế văn bản</h3>
      
      <div className="form-group">
        <label htmlFor="doc-select">Chọn văn bản muốn thay thế:</label>
        <select 
          id="doc-select" 
          value={selectedSoHieu} 
          onChange={(e) => setSelectedSoHieu(e.target.value)}
        >
          <option value="">-- Chọn văn bản --</option>
          {documents.map((doc) => (
            <option key={doc.so_hieu} value={doc.so_hieu}>
              [{doc.so_hieu}] {doc.ten_van_ban}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="file-upload">Upload văn bản hợp nhất (.doc, .docx):</label>
        <input 
          type="file" 
          id="file-upload" 
          accept=".doc,.docx" 
          onChange={handleFileChange} 
        />
      </div>

      <button 
        className="replace-btn" 
        onClick={handleReplace} 
        disabled={loading || !selectedSoHieu || !file}
      >
        {loading ? 'Đang xử lý...' : 'Thực hiện thay thế'}
      </button>

      {status && <div className={`status-msg ${status.includes('Thành công') ? 'success' : ''}`}>{status}</div>}
    </div>
  );
};

export default DocumentReplacement;
