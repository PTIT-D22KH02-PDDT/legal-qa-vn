import React from 'react';
import ChatArea from './components/ChatArea';
import RightSidebar from './components/RightSidebar';
import LeftSidebar from './components/LeftSidebar';
import { useChat } from './hooks/useChat';

function App() {
  const chatContext = useChat();

  return (
    <div className="app-container">
      <LeftSidebar />
      <ChatArea chatContext={chatContext} />
      <RightSidebar chatContext={chatContext} />
    </div>
  );
}

export default App;
