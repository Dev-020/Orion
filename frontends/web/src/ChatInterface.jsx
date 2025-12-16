
import React, { useState, useEffect, useRef } from 'react'
import { Send, Archive, Inbox, X, Plus, FileText, User } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useAuth } from './context/AuthContext'
import UserAvatar from './components/UserAvatar'

// Log helper
const logToServer = async (level, message) => {
  try {
    // We send this to the WEB SERVER (8001), not the backend
    await fetch('http://localhost:8001/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ level, message })
    })
  } catch (e) {
    console.error('Failed to log to server', e)
  }
}


// Helper to format timestamps
const formatTimestamp = (ts) => {
    if (!ts) return ''
    if (ts.length < 10 && ts.includes(':')) return ts
    
    try {
        const date = new Date(ts)
        if (isNaN(date.getTime())) return ts
        return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})
    } catch (e) {
        return ts
    }
}

// Regex to normalize LaTeX math to Markdown math
const preprocessContent = (content) => {
    if (!content) return "";
    return content
        .replace(/\\\[([\s\S]*?)\\\]/g, '$$$$$1$$$$') // \[ ... \] -> $$ ... $$
        .replace(/\\\(([\s\S]*?)\\\)/g, '$$$1$$')     // \( ... \) -> $ ... $
}

// Memoized Message Component to prevent re-renders (Typing Lag Fix)
const MessageItem = React.memo(({ msg, userAvatar }) => {
    // Local state for Accordion
    const [isExpanded, setIsExpanded] = React.useState(msg.isThinking);

    // Sync with msg.isThinking if it changes (e.g. while streaming)
    React.useEffect(() => {
        setIsExpanded(!!msg.isThinking);
    }, [msg.isThinking]);

    return (
        <div className={`message-appear ${msg.role === 'user' ? 'user-msg' : 'ai-msg'}`} 
            style={{
                alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem'
            }}
        >
            {/* Metadata Header */}
            <div style={{
                display:'flex', gap:'0.75rem', 
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                alignItems: 'center',
                fontSize: '0.8rem',
                opacity: 0.7,
                padding: '0 0.5rem'
            }}>
                <span style={{fontWeight:'bold'}}>{msg.username}</span>
                <span style={{fontSize:'0.75rem', opacity:0.6}}>{formatTimestamp(msg.timestamp)}</span>
            </div>

            {/* Thought Bubble (assistant) - Accordion Version */}
            {msg.role === 'assistant' && msg.thought && (
            <div className="thought-block">
                <div className="thought-header" onClick={() => setIsExpanded(!isExpanded)}>
                    Thinking Process
                </div>
                <div className={`thought-accordion ${isExpanded ? 'open' : ''}`}>
                    <div className="thought-inner">
                        <div className="thought-content">
                            <ReactMarkdown 
                                remarkPlugins={[remarkMath]}
                                rehypePlugins={[rehypeKatex]}
                                components={{
                                    code({node, inline, className, children, ...props}) {
                                        const match = /language-(\w+)/.exec(className || '')
                                        return !inline && match ? (
                                            <div style={{borderRadius: '8px', overflow: 'hidden', margin: '0.5rem 0'}}>
                                                <div style={{
                                                    background: '#1e1e1e', 
                                                    padding: '0.25rem 0.75rem', 
                                                    fontSize: '0.75rem', 
                                                    color: '#a1a1aa',
                                                    borderBottom: '1px solid #333',
                                                    display: 'flex', justifyContent: 'space-between'
                                                }}>
                                                    <span>{match[1]}</span>
                                                    <span>Copy</span>
                                                </div>
                                                <SyntaxHighlighter
                                                    style={vscDarkPlus}
                                                    language={match[1]}
                                                    PreTag="div"
                                                    customStyle={{margin: 0, borderRadius: 0}}
                                                    {...props}
                                                >
                                                    {String(children).replace(/\n$/, '')}
                                                </SyntaxHighlighter>
                                            </div>
                                        ) : (
                                            <code className={className} style={{
                                                background: 'rgba(255,255,255,0.1)', 
                                                padding: '0.2rem 0.4rem', 
                                                borderRadius: '4px',
                                                fontSize: '0.9em'
                                            }} {...props}>
                                                {children}
                                            </code>
                                        )
                                    }
                                }}
                            >
                                {preprocessContent(msg.thought)}
                            </ReactMarkdown>
                        </div>
                    </div>
                </div>
            </div>
            )}

            <div style={{
            display: 'flex',
            gap: '1rem',
            justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
            }}>
                {msg.role === 'assistant' && (
                <div style={{
                     // Container style handled generally, but we can override
                     marginRight: '0'
                }}>
                    <UserAvatar 
                        avatarUrl="/orion_avatar.png" // Change to .webm for video!
                        size={32}
                    />
                </div>
                )}
                
                <div style={{
                background: msg.role === 'user' ? 'rgba(99, 102, 241, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                border: msg.role === 'user' ? '1px solid rgba(99, 102, 241, 0.3)' : '1px solid rgba(255, 255, 255, 0.1)',
                padding: '1rem 1.5rem',
                borderRadius: '12px',
                borderTopLeftRadius: msg.role === 'assistant' ? '2px' : '12px',
                borderTopRightRadius: msg.role === 'user' ? '2px' : '12px',
                lineHeight: '1.6',
                width: '100%',
                position: 'relative',
                boxShadow: '0 4px 6px rgba(0,0,0,0.1)'
                }}>
                    {msg.role === 'system' ? (
                        <span style={{color: '#ef4444'}}>{msg.content}</span>
                    ) : (
                        <>
                        {!msg.content && msg.isThinking && (
                            <span style={{opacity: 0.5, letterSpacing: '2px'}} className="animate-pulse">...</span>
                        )}
                        <ReactMarkdown 
                            remarkPlugins={[remarkMath]}
                            rehypePlugins={[rehypeKatex]}
                            components={{
                                code({node, inline, className, children, ...props}) {
                                    const match = /language-(\w+)/.exec(className || '')
                                    return !inline && match ? (
                                        <div style={{borderRadius: '8px', overflow: 'hidden', margin: '0.5rem 0'}}>
                                            <div style={{
                                                background: '#1e1e1e', 
                                                padding: '0.25rem 0.75rem', 
                                                fontSize: '0.75rem', 
                                                color: '#a1a1aa',
                                                borderBottom: '1px solid #333',
                                                display: 'flex', justifyContent: 'space-between'
                                            }}>
                                                <span>{match[1]}</span>
                                                <span>Copy</span>
                                            </div>
                                            <SyntaxHighlighter
                                                style={vscDarkPlus}
                                                language={match[1]}
                                                PreTag="div"
                                                customStyle={{margin: 0, borderRadius: 0}}
                                                {...props}
                                            >
                                                {String(children).replace(/\n$/, '')}
                                            </SyntaxHighlighter>
                                        </div>
                                    ) : (
                                        <code className={className} style={{
                                            background: 'rgba(255,255,255,0.1)', 
                                            padding: '0.2rem 0.4rem', 
                                            borderRadius: '4px',
                                            fontSize: '0.9em'
                                        }} {...props}>
                                            {children}
                                        </code>
                                    )
                                }
                            }}
                        >
                            {preprocessContent(msg.content)}
                        </ReactMarkdown>
                        </>
                    )}
                </div>



                {/* User Avatar */}
                {msg.role === 'user' && (
                    <div style={{
                        marginTop: '0', marginLeft: '0.75rem' // Margin for alignment
                    }}>
                         <UserAvatar 
                            avatarUrl={userAvatar} 
                            size={32} 
                         />
                    </div>
                )}
            </div>
        </div>
    )
})

// File Grid Item for Popup
const FileGridItem = ({ file, onRemove }) => {
    const [isHovered, setIsHovered] = useState(false);
    return (
        <div 
            style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem',
                position: 'relative',
                width: '100%',
                cursor: 'default'
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            title={file.display_name} // Tooltip
        >
            {/* Icon Container */}
            <div style={{
                position: 'relative',
                width: '48px', height: '48px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: '8px',
                overflow: 'hidden',
                // Pulse if pending
                animation: file.isPending ? 'pulse-glow 1.5s infinite ease-in-out' : 'none'
            }}>
                <FileText size={24} color="#a1a1aa" style={{
                    filter: isHovered || file.isPending ? 'blur(2px)' : 'none', // Also blur if pending? Or just pulse. User said "pulse as well". Maybe blur too.
                    transition: 'filter 0.2s'
                }}/>
                
                {/* Red X Overlay - Allow removing even if pending? Yes. */}
                <div className="interactive-btn" style={{
                    position: 'absolute',
                    inset: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'rgba(0,0,0,0.4)',
                    opacity: isHovered ? 1 : 0,
                    transition: 'opacity 0.2s',
                    cursor: 'pointer'
                }} onClick={onRemove}>
                   <X size={20} color="#ef4444" />
                </div>
            </div>
            
            {/* Filename */}
            <span style={{
                fontSize: '0.75rem', 
                color: '#d4d4d8', 
                maxWidth: '100%', 
                whiteSpace: 'nowrap', 
                overflow: 'hidden', 
                textOverflow: 'ellipsis',
                textAlign: 'center'
            }}>
                {file.display_name}
            </span>
        </div>
    )
}

export default function ChatInterface({ session }) {
  const { user } = useAuth(); // Get user from context
  const token = localStorage.getItem('orion_auth_token'); // Get raw token for WS

  const [messages, setMessages] = useState([
    { role: 'assistant', content: `Hello ${user?.username || 'traveler'}! I am Orion. How can I help you today?`, id: 'init' }
  ])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const [files, setFiles] = useState([])
  const [isUploading, setIsUploading] = useState(false)
  const [showFilePopup, setShowFilePopup] = useState(false)
  const [isHoveringBucket, setIsHoveringBucket] = useState(false)
  const ws = useRef(null)
  const fileInputRef = useRef(null)
  const messagesEndRef = useRef(null)
  const lastLoggedType = useRef(null) // For log throttling

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // --- GLOBAL CONSOLE INTERCEPTOR ---
  useEffect(() => {
      const originalLog = console.log;
      const originalWarn = console.warn;
      const originalError = console.error;
      const originalInfo = console.info;

      console.log = (...args) => {
          originalLog(...args);
          // Convert args to string safely
          const msg = args.map(a => (typeof a === 'object' ? JSON.stringify(a) : a)).join(' ');
          logToServer('info', `[LOG] ${msg}`);
      };
      
      console.warn = (...args) => {
          originalWarn(...args);
          const msg = args.map(a => (typeof a === 'object' ? JSON.stringify(a) : a)).join(' ');
          logToServer('warning', `[WARN] ${msg}`);
      };

      console.error = (...args) => {
          originalError(...args);
          const msg = args.map(a => (typeof a === 'object' ? JSON.stringify(a) : a)).join(' ');
          logToServer('error', `[ERROR] ${msg}`);
      };

      console.info = (...args) => {
          originalInfo(...args);
          const msg = args.map(a => (typeof a === 'object' ? JSON.stringify(a) : a)).join(' ');
          logToServer('info', `[INFO] ${msg}`);
      };

      return () => {
          // Restore on cleanup
          console.log = originalLog;
          console.warn = originalWarn;
          console.error = originalError;
          console.info = originalInfo;
      };
  }, []); // Run once on mount

  // WebSocket Connection
  useEffect(() => {
    // 1. Establish WebSocket connection to Python Backend (FastAPI on 8000)
    // Pass token in URL query params
    const wsUrl = token ? `ws://localhost:8000/ws?token=${token}` : 'ws://localhost:8000/ws';
    
    logToServer('info', `Initializing WebSocket connection to ${wsUrl}...`)
    
    const socket = new WebSocket(wsUrl)

    socket.onopen = () => {
      console.log('Connected to Orion Backend')
      logToServer('info', 'WebSocket Connected to Backend (8000)')
      setIsConnected(true)
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        // Log generic info, but throttle 'thought' and skip 'token'
        if (data.type === 'token') {
            // Do not log tokens
        } else if (data.type === 'thought' || data.type === 'detailed_thought') {
            // Only log the FIRST thought packet in a sequence
            if (lastLoggedType.current !== data.type) {
                logToServer('info', `[Client] Received Message: ${data.type} (Stream Started)`)
            }
        } else {
            // Log everything else (status, error, etc)
             logToServer('info', `[Client] Received Message: ${data.type}`)
        }
        
        lastLoggedType.current = data.type;
        handleIncomingMessage(data)
      } catch (e) {
        console.error('Failed to parse message', e)
        logToServer('error', `JSON Parse Error: ${e.message}`)
      }
    }

    socket.onclose = () => {
      console.log('Disconnected')
      logToServer('warning', 'WebSocket Disconnected')
      setIsConnected(false)
    }
    
    socket.onerror = (err) => {
         logToServer('error', 'WebSocket encountered an error.')
    }

    ws.current = socket

    return () => {
      socket.close()
    }
  }, [session])

  // --- HISTORY LOADING ---
  useEffect(() => {
    const fetchHistory = async () => {
       if (!token) return;

       try {
         const res = await fetch('http://localhost:8000/get_history', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
         })
         if (!res.ok) throw new Error("Failed to fetch history")
         
         const data = await res.json()
         const history = data.history || []

         logToServer('info', `History loaded: ${history.length} messages`)
         
         if (history.length > 0) {
            // The backend now returns CLEAN history via sanitize_history_for_client
            // Structure: { role, content, username, timestamp, id }
            // So we can use it directly!
            setMessages(history)
         }
       } catch (e) {
         console.error("History Load Error:", e)
         logToServer('error', `Failed to load history: ${e.message}`)
       }
    }
    
    fetchHistory()
  }, [session])

  const handleIncomingMessage = (data) => {
    if (data.type === 'token') {
      setMessages(prev => {
        const last = prev[prev.length - 1]
        
        // If last message is user, start new assistant message
        if (last.role === 'user') {
          return [...prev, { 
              role: 'assistant', 
              content: data.content, 
              id: Date.now(), 
              isThinking: false, 
              timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
              username: 'Orion'
          }]
        }
        
        // If last message is assistant, append content and Stop Thinking
        if (last.role === 'assistant') {
          return [
            ...prev.slice(0, -1),
            { ...last, content: last.content + data.content, isThinking: false }
          ]
        }
        return prev
      })
    }
    // Handle STATUS/THOUGHTS (The Thinking Proces) 
    else if (data.type === 'status' || data.type === 'thought' || data.type === 'detailed_thought') {
       
       let chunk = data.content;
       if (data.type === 'status') {
           chunk = (chunk.endsWith('\n') ? chunk : chunk + '\n');
       }
       
       setMessages(prev => {
         const last = prev[prev.length - 1]
         
         if (last.role === 'assistant') {
            const currentThoughts = last.thought || "";
            return [
               ...prev.slice(0, -1),
               { ...last, thought: currentThoughts + chunk, isThinking: true }
            ]
         }
         
         if (last.role === 'user') {
            return [...prev, { 
              role: 'assistant', 
              content: '', 
              thought: chunk, 
              isThinking: true, 
              id: Date.now(),
              timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
              username: 'Orion' 
            }]
         }
         
         return prev
       })
    }
    else if (data.type === 'error') {
      logToServer('error', `Backend reported error: ${data.content}`)
      setMessages(prev => [...prev, { role: 'system', content: `Error: ${data.content}`, id: Date.now() }])
    }
  }



  // Ref to track active upload controllers for cancellation
  const activeUploads = useRef({})

  // File Upload Logic
  const handleFileSelect = async (e) => {
      if (!e.target.files.length) return
      
      const MAX_SIZE = 25 * 1024 * 1024; // 25MB
      const selectedFiles = Array.from(e.target.files)
      
      const validFiles = []
      const invalidFiles = []

      if (files.length >= 6) {
          alert("You can only attach up to 6 files.");
          if (fileInputRef.current) fileInputRef.current.value = '';
          return;
      }

      const remainingSlots = 6 - files.length;
      
      selectedFiles.forEach(file => {
          if (file.size > MAX_SIZE) {
              invalidFiles.push(file.name)
          } else {
              validFiles.push(file)
          }
      })
      
      if (validFiles.length > remainingSlots) {
          alert(`Only the first ${remainingSlots} file(s) will be added due to the 6-file limit.`);
          validFiles.length = remainingSlots; 
      }
      
      if (invalidFiles.length > 0) {
          alert(`The following files are too large (>25MB) and will not be uploaded:\n- ${invalidFiles.join('\n- ')}`)
          if (validFiles.length === 0) {
              if (fileInputRef.current) fileInputRef.current.value = ''
              return; 
          }
      }

      // 1. Create Staged Pending Files
      const pendingFiles = validFiles.map(f => ({
          display_name: f.name,
          isPending: true, // Marker for UI pulse
          tempId: Math.random().toString(36).substr(2, 9) // temporary ID for tracking
      }))

      // 2. Add to UI immediately and Open Popup
      setFiles(prev => [...prev, ...pendingFiles])
      setShowFilePopup(true) 
      
      // 3. Upload Background Process
      setIsUploading(true)
      logToServer('file_upload_start', `Starting upload of ${validFiles.length} files`)

      try {
          const uploadPromises = validFiles.map((file, index) => {
              const formData = new FormData()
              formData.append('file', file)
              formData.append('display_name', file.name)
              formData.append('mime_type', file.type || 'application/octet-stream')
              
              const myTempId = pendingFiles[index].tempId;
              
              // Create AbortController
              const controller = new AbortController();
              activeUploads.current[myTempId] = controller;

              return fetch('http://localhost:8000/upload_file', {
                  method: 'POST',
                  body: formData,
                  signal: controller.signal
              })
              .then(res => {
                  if (!res.ok) throw new Error('Upload failed')
                  return res.json()
              })
              .then(data => {
                  // Swap pending for real upon completion
                  setFiles(prev => prev.map(f => {
                      if (f.tempId === myTempId) {
                          return data // The real StartableFile object from server
                      }
                      return f
                  }))
                  return data
              })
              .finally(() => {
                  // Cleanup controller
                  delete activeUploads.current[myTempId];
              })
          })

          const results = await Promise.all(uploadPromises)
          logToServer('file_upload_success', `Uploaded ${results.length} files`)
          
      } catch (error) {
          if (error.name === 'AbortError') {
              console.log("Upload aborted by user")
          } else {
              console.error("Upload failed:", error)
              logToServer('error', `Upload Failed: ${error}`)
              alert("Failed to upload one or more files.")
          }
          
          // Cleanup any stuck pending files (that aren't aborted but failed otherwise)
          setFiles(prev => prev.filter(p => !p.isPending))
      } finally {
          setIsUploading(false)
          if (fileInputRef.current) fileInputRef.current.value = ''
      }
  }

  const removeFile = (index) => {
      setFiles(prev => {
        const fileToRemove = prev[index];
        logToServer('file_remove', `Removing file ${fileToRemove ? fileToRemove.display_name : 'unknown'}`)
        
        // Cancel upload if pending
        if (fileToRemove.isPending && fileToRemove.tempId && activeUploads.current[fileToRemove.tempId]) {
            console.log(`Aborting upload for ${fileToRemove.display_name}`);
            activeUploads.current[fileToRemove.tempId].abort();
            delete activeUploads.current[fileToRemove.tempId];
        }

        const newFiles = [...prev];
        newFiles.splice(index, 1);
        return newFiles;
      })
  }

  const textareaRef = useRef(null)

  const sendMessage = () => {
    if ((!input.trim() && files.length === 0) || !ws.current || isUploading) return

    logToServer('info', `User sending prompt: "${input.substring(0, 50)}..." [Files: ${files.length}]`)

    // Reset height manually
    if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'; // Reset to default
    }

    // Add User Message
    const userMsg = { 
        role: 'user', 
        content: input, 
        id: Date.now(),
        timestamp: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
        username: user?.username || 'User',
        files: files // Store locally for display if we update message item later
    }
    setMessages(prev => [...prev, userMsg])

    // Send to Backend
    // Backend will overwrite session_id and user_id from token if present, 
    // but sending username is good for logs or echo
    ws.current.send(JSON.stringify({
      type: 'prompt',
      prompt: input,
      session_id: session, 
      username: user?.username || 'WebUser',
      files: files
    }))

    setInput('')
    setFiles([])
  }

  const handleKeyDown = (e) => {
    // Ctrl + Enter to send
    if (e.key === 'Enter' && e.ctrlKey) {
      e.preventDefault()
      sendMessage()
    }
  }
  
  const handleInput = (e) => {
      setInput(e.target.value);
      
      // Auto-grow logic
      const target = e.target;
      
      // Reset height to auto to correctly calculate shrink
      // To prevent jitter: only reset if we suspect a shrink (delete) 
      // OR we accept small jitter for correctness. 
      // Given bottom-alignment ('flex-end'), the jitter is visible because 'auto' 
      // snaps the top edge down.
      
      // Better approach: Set height to 'auto' but maintain min-height to reduce collapse visual
      target.style.height = 'auto'; 
      target.style.height = `${target.scrollHeight}px`;
  }



  return (
    <div style={{display: 'flex', flexDirection: 'column', height: '100%'}}>
      <input type="file" multiple ref={fileInputRef} style={{display:'none'}} onChange={handleFileSelect} />
      {/* Header */}
      <div style={{
        padding: '1rem 2rem', 
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'transparent'
      }}>
        <span style={{fontWeight: 600}}>Current Session</span>
        <div style={{display:'flex', alignItems:'center', gap:'0.5rem', fontSize:'0.8rem'}}>
          <div style={{
            width: '8px', height: '8px', borderRadius: '50%', 
            background: isConnected ? '#4ade80' : '#ef4444',
            boxShadow: isConnected ? '0 0 10px #4ade80' : 'none'
          }}></div>
          {isConnected ? 'Online' : 'Disconnected'}
        </div>
      </div>

      {/* Styles for Animations */}
      <style>{`
        @keyframes pulse-glow {
          0%, 100% { opacity: 1; filter: drop-shadow(0 0 5px rgba(99, 102, 241, 0.5)); }
          50% { opacity: 0.6; filter: drop-shadow(0 0 12px rgba(99, 102, 241, 0.8)); }
        }
        @keyframes shadow-pulse {
          0%, 100% { box-shadow: 0px 5px 10px -2px rgba(99, 102, 241, 0.3); } 
          50% { box-shadow: 0px 10px 20px -2px rgba(99, 102, 241, 0.8); border-color: rgba(99, 102, 241, 0.6); }
        }
      `}</style>

      {/* Messages Area */}
      <div style={{
        flex: 1, 
        overflowY: 'auto', 
        padding: '2rem', 
        display: 'flex', 
        flexDirection: 'column', 
        gap: '2rem',
        maskImage: 'linear-gradient(to bottom, transparent 0%, black 5%, black 95%, transparent 100%)',
        WebkitMaskImage: 'linear-gradient(to bottom, transparent 0%, black 5%, black 95%, transparent 100%)'
      }}>
        {messages.map((msg, idx) => (
             <MessageItem key={idx} msg={msg} userAvatar={user?.avatar_url} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div style={{padding: '0 2rem 2rem 2rem', maxWidth: '900px', width: '100%', margin: '0 auto'}}>
        
        <div style={{
          display: 'flex',
          alignItems: 'flex-end',
          gap: '1rem',
        }}>
          {/* Bucket Button */}
          <div style={{position: 'relative', marginBottom: '1px'}}>
              {/* Tooltip */}
              {isHoveringBucket && !showFilePopup && (
                  <div style={{
                      position: 'absolute',
                      bottom: '120%',
                      left: '50%',
                      transform: 'translateX(-50%)',
                      background: 'rgba(0,0,0,0.8)',
                      padding: '0.4rem 0.6rem',
                      borderRadius: '6px',
                      fontSize: '0.75rem',
                      whiteSpace: 'nowrap',
                      pointerEvents: 'none',
                      border: '1px solid rgba(255,255,255,0.1)',
                      zIndex: 20
                  }}>
                      {files.length === 0 ? "Click to attach files" : `${files.length} file(s) attached`}
                  </div>
              )}

              {/* Popup Manager */}
              {showFilePopup && (
                  <>
                    <div 
                        style={{position: 'fixed', inset: 0, zIndex: 40}} 
                        onClick={() => setShowFilePopup(false)}
                    />
                    <div style={{
                        position: 'absolute',
                        bottom: '120%',
                        left: '0',
                        // Explicit width based on columns to ensure tight fit without overflow
                        width: (files.length + (files.length < 6 ? 1 : 0)) >= 3 ? '300px' : 
                               (files.length + (files.length < 6 ? 1 : 0)) === 2 ? '210px' : '110px',
                        background: 'rgba(30, 30, 35, 0.6)', 
                        backdropFilter: 'blur(16px)', 
                        border: '1px solid rgba(255,255,255,0.1)',
                        borderRadius: '12px',
                        padding: '0.75rem',
                        boxShadow: '0 10px 25px -5px rgba(0,0,0,0.5)',
                        zIndex: 50,
                        display: 'flex', flexDirection: 'column', gap: '0.5rem'
                    }}>
                        {/* Header Row */}
                        <div style={{display:'flex', justifyContent:'space-between', alignItems:'center'}}>
                            <span style={{fontWeight:600, color:'#f4f4f5'}}>({files.length}/6)</span>
                            <button onClick={() => setShowFilePopup(false)} className="interactive-btn" style={{
                                background:'none', border:'none', cursor:'pointer', color:'#a1a1aa'
                            }}>
                                <X size={18} />
                            </button>
                        </div>
                        {/* Grid Layout */}
                        <div style={{
                            display: 'grid', 
                            // minmax(0, 1fr) is CRITICAL for text truncation in grids
                            gridTemplateColumns: `repeat(${Math.min(files.length + (files.length < 6 ? 1 : 0), 3)}, minmax(0, 1fr))`, 
                            gap: '0.5rem', 
                        }}>
                            {files.map((f, i) => (
                                <FileGridItem key={i} file={f} onRemove={() => removeFile(i)} />
                            ))}
                            
                            {/* Add More Ghost Button */}
                            {files.length < 6 && (
                                <div style={{
                                    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem',
                                    width: '100%',
                                    cursor: 'default'
                                }}>
                                    <button
                                        onClick={() => fileInputRef.current?.click()}
                                        style={{
                                            width: '48px', height: '48px',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            background: 'transparent',
                                            border: '2px dashed rgba(255,255,255,0.2)',
                                            borderRadius: '8px',
                                            color: 'rgba(255,255,255,0.3)',
                                            cursor: 'pointer',
                                            transition: 'all 0.2s',
                                            padding: 0
                                        }}
                                        onMouseEnter={(e) => {
                                            e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.5)';
                                            e.currentTarget.style.color = 'rgba(99, 102, 241, 0.8)';
                                        }}
                                        onMouseLeave={(e) => {
                                            e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)';
                                            e.currentTarget.style.color = 'rgba(255,255,255,0.3)';
                                        }}
                                    >
                                        <Plus size={24} />
                                    </button>
                                    <span style={{fontSize: '0.75rem', color: 'rgba(255,255,255,0.3)'}}>Add</span>
                                </div>
                            )}
                        </div>
                    </div>
                  </>
              )}

              {/* Main Button */}
              <button 
                className="interactive-btn"
                onClick={() => {
                    if (files.length === 0) {
                        fileInputRef.current?.click()
                    } else {
                        setShowFilePopup(!showFilePopup)
                    }
                }}
                onMouseEnter={() => setIsHoveringBucket(true)}
                onMouseLeave={() => setIsHoveringBucket(false)}
                // Removed disabled={isUploading} to allow checking progress
                style={{
                    padding: '0.75rem', 
                    // Matches Send Button Glow logic
                    color: (isUploading || files.length > 0) ? '#fff' : '#a1a1aa', 
                    background: (isUploading || files.length > 0) ? '#6366f1' : 'rgba(255,255,255,0.05)', 
                    border: (isUploading || files.length > 0) ? 'none' : '1px solid rgba(255,255,255,0.1)', 
                    borderRadius: '12px',
                    cursor: isUploading ? 'not-allowed' : 'pointer',
                    height: '44px', 
                    width: '44px',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 0.2s',
                    opacity: 1, // Full opacity to show glow clearly
                    // Add pulsing shadow if uploading, static glow if active
                    animation: isUploading ? 'shadow-pulse 1.5s infinite ease-in-out' : 'none',
                    boxShadow: (!isUploading && files.length > 0) ? '0 0 10px rgba(99, 102, 241, 0.3)' : 'none'
                }}>
                    {isUploading ? (
                        <div style={{animation: 'pulse-glow 1.5s infinite ease-in-out'}}>
                           <Archive size={20} style={{filter: 'blur(1px)'}} />
                        </div>
                    ) : (
                        <Archive size={20} />
                    )}
              </button>
          </div>
          
          {/* Text Area Container */}
          <div style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            padding: '0',
            display: 'flex',
            alignItems: 'center',
            position: 'relative' 
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', width: '100%' }}>
              <textarea
                  ref={textareaRef}
                  value={input}
                  onChange={handleInput}
                  onKeyDown={handleKeyDown}
                  placeholder="Send a message (Ctrl + Enter)"
                  style={{
                    width: '98%',
                    background: 'transparent', 
                    border: 'none',
                    color: '#fff',
                    fontSize: '1rem',
                    lineHeight: '1.5',
                    resize: 'none',
                    // Balanced padding for single line height (~24px content + 8px padding = 32px)
                    // This prevents the "2-line" initial look while keeping text grounded.
                    padding: '0.5px 0.5rem 0.5px 0.5rem', 
                    outline: 'none',
                    maxHeight: '200px',
                    minHeight: '32px', // Start smaller (was 40px)
                    overflowY: 'auto',
                    // Enhanced GLOW: Use spread radius and lighter color for a "glow"
                    boxShadow: '0px 10px 10px -5px rgba(99, 102, 241, 0.5)' 
                  }}
                  rows={1}
              />
              <div style={{
                  marginTop: '1px',
                  height: '1px',
                  width: '100%',
                  background: 'rgba(255,255,255,0.3)',
              }} />
            </div>
          </div>

          {/* Send Button */}
          <button 
            className="interactive-btn"
            onClick={sendMessage}
            disabled={(!input.trim() && files.length === 0)}
            style={{
              padding: '0.75rem', 
              background: (input.trim() || files.length > 0) ? '#6366f1' : 'rgba(255,255,255,0.05)', 
              color: (input.trim() || files.length > 0) ? '#fff' : 'rgba(255,255,255,0.3)',
              border: (input.trim() || files.length > 0) ? 'none' : '1px solid rgba(255,255,255,0.1)', 
              borderRadius: '12px', 
              cursor: (input.trim() || files.length > 0) ? 'pointer' : 'default',
              transition: 'all 0.2s',
              height: '44px',
              width: '44px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: '1px'
            }}
          >
            <Send size={18} />
          </button>
        </div>
        
        <div style={{textAlign: 'center', fontSize: '0.75rem', color: '#555', marginTop: '0.75rem'}}>
          Orion AI may generate inaccurate info.
        </div>
      </div>
    </div>
  )
}
