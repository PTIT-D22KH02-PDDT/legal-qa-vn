import { useState, useRef, useEffect } from 'react';

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
  citation?: string;
  time?: string;
}

export interface Session {
  id: string;
  title: string;
  messages: Message[];
}

export const useChat = () => {
  const [sessions, setSessions] = useState<Session[]>([
    {
      id: '1',
      title: 'Luật thừa kế, hàng thừa kế',
      messages: [
        {
          id: '1',
          role: 'user',
          content: 'luật thừa kế, hàng thừa kế đầu tiên là gì',
          time: '05:54:55 14/04/2026'
        },
        {
          id: '2',
          role: 'ai',
          citation: 'Căn cứ vào Điều 651 Bộ luật Dân sự của Quốc hội, số 91/2015/QH13 có hiệu lực từ ngày 01/01/2017 thì hàng thừa kế đầu tiên (hàng thừa kế thứ nhất) được quy định như sau:\n\n1. Những người thừa kế theo pháp luật được quy định theo thứ tự sau đây:\na) Hàng thừa kế thứ nhất gồm: vợ, chồng, cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi, con đẻ, con nuôi của người chết;',
          content: 'Theo quy định trên, hàng thừa kế thứ nhất bao gồm: vợ, chồng, cha đẻ, mẹ đẻ, cha nuôi, mẹ nuôi, con đẻ, con nuôi của người chết.',
          time: '05:55:01 14/04/2026'
        }
      ]
    }
  ]);
  
  const [activeSessionId, setActiveSessionId] = useState<string>('1');
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find(s => s.id === activeSessionId) || sessions[0];
  const messages = activeSession ? activeSession.messages : [];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const getCurrentTime = () => {
    const now = new Date();
    return `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')} ${now.getDate().toString().padStart(2, '0')}/${(now.getMonth() + 1).toString().padStart(2, '0')}/${now.getFullYear()}`;
  };

  const createNewSession = () => {
    const newSession: Session = {
      id: Date.now().toString(),
      title: 'Cuộc trò chuyện mới',
      messages: []
    };
    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;
    
    const currentInput = input;
    setInput('');
    setIsLoading(true);

    const newUserMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: currentInput,
      time: getCurrentTime()
    };

    setSessions(prevSessions => prevSessions.map(session => {
      if (session.id === activeSessionId) {
        // Nếu là tin nhắn đầu tiên, cập nhật title bằng câu hỏi
        const newTitle = session.messages.length === 0 
          ? (currentInput.length > 30 ? currentInput.substring(0, 30) + '...' : currentInput)
          : session.title;
          
        return {
          ...session,
          title: newTitle,
          messages: [...session.messages, newUserMsg]
        };
      }
      return session;
    }));

    // Gọi API thật tới backend api_server.py
    try {
      const response = await fetch('http://localhost:8001/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: currentInput,
          use_remote_embedding: true,
          use_remote_rerank: true
        }),
      });

      if (!response.ok) {
        throw new Error('Network response was not ok');
      }

      const data = await response.json();
      
      const newAiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        citation: data.context ? 'Tài liệu tham khảo:\n' + data.context : 'Không tìm thấy tài liệu tham khảo phù hợp.',
        content: data.answer,
        time: getCurrentTime()
      };
      
      setSessions(prevSessions => prevSessions.map(session => {
        if (session.id === activeSessionId) {
          return {
            ...session,
            messages: [...session.messages, newAiMsg]
          };
        }
        return session;
      }));
    } catch (error) {
      console.error('Error fetching RAG response:', error);
      const errorMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: 'ai',
        content: 'Đã có lỗi xảy ra khi kết nối tới máy chủ AI. Vui lòng đảm bảo api_server.py đang chạy.',
        time: getCurrentTime()
      };
      
      setSessions(prevSessions => prevSessions.map(session => {
        if (session.id === activeSessionId) {
          return {
            ...session,
            messages: [...session.messages, errorMsg]
          };
        }
        return session;
      }));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      sendMessage();
    }
  };

  return {
    sessions,
    activeSessionId,
    setActiveSessionId,
    createNewSession,
    activeSession,
    messages,
    input,
    setInput,
    isLoading,
    sendMessage,
    handleKeyPress,
    messagesEndRef
  };
};
