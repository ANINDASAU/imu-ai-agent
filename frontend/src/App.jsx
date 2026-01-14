import React, {useState, useRef, useEffect} from 'react'

function ChatBubble({who, text}){
  return (
    <div className={"bubble " + (who==='user' ? 'user' : 'bot')}>{text}</div>
  )
}

export default function App(){
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const bottomRef = useRef()

  useEffect(()=>{ bottomRef.current?.scrollIntoView({behavior:'smooth'}) }, [messages])

  // helper to request the initial greeting from the backend
  async function getGreeting({session=null, replace=false} = {}){
    try{
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ session_id: session, message: '__start__' })
      })
      const data = await res.json()
      if(data.session_id) setSessionId(data.session_id)
      if(replace) setMessages([{who:'bot', text: data.response}])
      else setMessages(prev => [...prev, {who:'bot', text: data.response}])
    }catch(e){
      console.error('Failed to fetch initial greeting', e)
    }
  }

  // On mount: show the permanent banner (in UI) and request initial bot greeting from backend
  useEffect(()=>{
    getGreeting({session:null})
  }, [])

  async function send(){
    if(!input.trim()) return
    const msg = input.trim()
    setMessages(prev => [...prev, {who:'user', text: msg}])
    setInput('')

    const res = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ session_id: sessionId, message: msg })
    })
    const data = await res.json()
    // persist session id returned by server
    if(data.session_id && !sessionId) setSessionId(data.session_id)
    setMessages(prev => [...prev, {who:'bot', text: data.response}])
  }

  // Clears chat and fetches a fresh initial greeting (resets session)
  async function refreshChat(){
    setMessages([])
    setSessionId(null)
    await getGreeting({session:null, replace:true})
  }

  return (
    <div className="container">
      <h2>University Assistant</h2>
      <div className="banner">Welcome to Our Intelligent University Management Agent</div>
      <div className="chat">
        {messages.map((m, i)=> <ChatBubble key={i} who={m.who} text={m.text} />)}
        <div ref={bottomRef} />
      </div>
      <div className="controls">
        <input value={input} onChange={e=>setInput(e.target.value)} placeholder="Type your response or answer..." onKeyDown={(e)=>{ if(e.key==='Enter') send() }} />
        <button className="refresh" onClick={refreshChat} title="Refresh and clear chat">↻</button>
        <button onClick={send}>Send</button>
      </div>
    </div>
  )
}
