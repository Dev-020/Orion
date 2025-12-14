
import React, { useState, useEffect, useRef } from 'react'
import { Send, Paperclip } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import 'katex/dist/katex.min.css'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useAuth } from './context/AuthContext'

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

export default function ChatInterface({ session }) {
  const { user } = useAuth(); // Get user from context
  const token = localStorage.getItem('orion_auth_token'); // Get raw token for WS

  const [messages, setMessages] = useState([
    { role: 'assistant', content: `Hello ${user?.username || 'traveler'}! I am Orion. How can I help you today?`, id: 'init' }
  ])
  const [input, setInput] = useState('')
  const [isConnected, setIsConnected] = useState(false)
  const ws = useRef(null)
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
         
         if (history.length > 0) {
            const formattedMessages = []
            
            history.forEach((exchange, index) => {
               // --- Helper to extract text from complex objects ---
               const extractText = (content) => {
                   if (!content) return "";
                   
                   // 1. If it's literally an object with user_prompt
                   if (typeof content === 'object' && content !== null) {
                       if (content.user_prompt) return content.user_prompt;
                       if (content.parts && Array.isArray(content.parts)) {
                           return content.parts.map(p => p.text).join('');
                       }
                       // If tool calls exist, maybe show a summary?
                       if (content.tool_calls) return `[Used Tools: ${content.tool_calls.length}]`;
                       
                       // Fallback for objects: try to look for prompt/text keys
                       if (content.prompt) return content.prompt;
                       if (content.text) return content.text;
                   }
                   
                   // 2. If it's a string, try strictly parsing, then Regex
                   if (typeof content === 'string') {
                       // A. Try JSON Parse
                       try {
                           if (content.trim().startsWith('{')) {
                               const parsed = JSON.parse(content);
                               if (parsed.user_prompt) return parsed.user_prompt;
                               if (parsed.text) return parsed.text;
                               if (parsed.prompt) return parsed.prompt;
                           }
                       } catch (e) { 
                           // Ignore parse error, proceed to Regex
                       }

                       // B. Regex Extraction (Handles Python dict strings or JSON)
                       // Look for "user_prompt": "..." OR 'user_prompt': '...'
                       const doubleQuoteMatch = content.match(/"user_prompt"\s*:\s*"((?:[^"\\]|\\.)*)"/);
                       if (doubleQuoteMatch) return doubleQuoteMatch[1];
                       
                       const singleQuoteMatch = content.match(/'user_prompt'\s*:\s*'((?:[^'\\]|\\.)*)'/);
                       if (singleQuoteMatch) return singleQuoteMatch[1];
                       
                       // C. Cleanup if it looks like just a quoted string?
                       if (content.startsWith('"') && content.endsWith('"')) {
                           try { return JSON.parse(content); } catch (e) {}
                       }
                       
                       return content;
                   }

                   return JSON.stringify(content);
               }

               const userText = extractText(exchange.user_content);
               const modelText = extractText(exchange.model_content);
               
               // Extract timestamp if available
               const timestamp = exchange.timestamp_utc || new Date().toISOString();
               // Formatter
               const timeStr = new Date(timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

               formattedMessages.push({ 
                   role: 'user', 
                   content: userText, 
                   id: `hist-user-${index}`,
                   timestamp: timeStr,
                   username: exchange.user_name || 'User'
               })
               formattedMessages.push({ 
                   role: 'assistant', 
                   content: modelText, 
                   id: `hist-ai-${index}`,
                   timestamp: timeStr,
                   username: 'Orion'
               })
            })
            
            setMessages(formattedMessages)
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

  const textareaRef = useRef(null)

  const sendMessage = () => {
    if (!input.trim() || !ws.current) return

    logToServer('info', `User sending prompt: "${input.substring(0, 50)}..."`)

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
        username: user?.username || 'User' 
    }
    setMessages(prev => [...prev, userMsg])

    // Send to Backend
    // Backend will overwrite session_id and user_id from token if present, 
    // but sending username is good for logs or echo
    ws.current.send(JSON.stringify({
      type: 'prompt',
      prompt: input,
      session_id: session, 
      username: user?.username || 'WebUser'
    }))

    setInput('')
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
      {/* Header */}
      <div style={{
        padding: '1rem 2rem', 
        // borderBottom: 'var(--glass-border)', // Removed to seamless look
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'transparent' // Seamless with main background
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
          // ... (Messages Content Omitted - Unchanged) ...
          // Just referencing lines to be safe, but actually I need to Replace the Whole Block or specific chunks?
          // The instruction says "Update textarea styles...".
          // I will target the Input Area specifically to key modifications.
          <div key={idx} className={`message-appear ${msg.role === 'user' ? 'user-msg' : 'ai-msg'}`} 
            style={{
                alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem'
            }}
          >
             {/* ... */}
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
                 <span style={{fontSize:'0.75rem', opacity:0.6}}>{msg.timestamp}</span>
             </div>

             {/* Thought Bubble (assistant) */}
             {msg.role === 'assistant' && msg.thought && (
               <details className="thought-details" open={msg.isThinking}>
                 <summary>Thinking Process</summary>
                 <div className="thought-content">{msg.thought}</div>
               </details>
             )}

             <div style={{
               display: 'flex',
               gap: '1rem',
               justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
             }}>
                 {msg.role === 'assistant' && (
                   <div style={{
                     minWidth: '32px', height: '32px', borderRadius: '8px', 
                     background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                     display: 'flex', alignItems: 'center', justifyContent: 'center',
                     fontSize: '0.8rem', fontWeight: 'bold'
                   }}>
                     AI
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
                          {msg.content}
                        </ReactMarkdown>
                      </>
                    )}
                 </div>
             </div>
          </div>
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
          {/* Attach Button */}
          <button style={{
             padding: '0.75rem', 
             color: '#a1a1aa', 
             background: 'rgba(255,255,255,0.05)', 
             border: '1px solid rgba(255,255,255,0.1)', 
             borderRadius: '12px',
             cursor: 'pointer',
             height: '44px', 
             width: '44px',
             display: 'flex', alignItems: 'center', justifyContent: 'center',
             marginBottom: '1px' // Align deeply
           }}>
            <Paperclip size={20} />
          </button>
          
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
            onClick={sendMessage}
            disabled={!input.trim()}
            style={{
              padding: '0.75rem', 
              background: input.trim() ? '#6366f1' : 'rgba(255,255,255,0.05)', 
              color: input.trim() ? '#fff' : 'rgba(255,255,255,0.3)',
              border: input.trim() ? 'none' : '1px solid rgba(255,255,255,0.1)', 
              borderRadius: '12px', 
              cursor: input.trim() ? 'pointer' : 'default',
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
