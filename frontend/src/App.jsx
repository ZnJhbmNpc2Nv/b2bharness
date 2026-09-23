import { useState, useEffect } from 'react'
import axios from 'axios'

function App() {
  const [status, setStatus] = useState("Loading...")
  const [key, setKey] = useState("")
  const [artifact, setArtifact] = useState(null)
  const [sessionId, setSessionId] = useState("session_001")

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axios.get('http://localhost:8000/health')
        setStatus(res.data.state)
        
        if (res.data.state === "INTENT" || res.data.state === "PLAN") {
           const art = await axios.get(`http://localhost:8000/pipeline/artifacts/${sessionId}/discovery`)
           setArtifact(art.data.content)
        }
      } catch (e) {
        console.error(e)
      }
    }
    fetchData()
  }, [sessionId])

  const saveKey = async () => {
    try {
      await axios.post('http://localhost:8000/config/keys', { key_name: 'GIGACODE', value: key })
      alert("Key saved!")
    } catch (e) {
      alert("Error saving key")
    }
  }

  const approvePipeline = () => {
    axios.post('http://localhost:8000/pipeline/approve')
      .then(res => alert("Approved!"))
      .catch(err => alert("Error approving"));
  }

  const advancePipeline = () => {
    axios.post('http://localhost:8000/pipeline/advance', {}, { headers: { 'session-id': sessionId, 'user-id': 'admin' } })
      .then(res => {
        setStatus(res.data.state);
      })
      .catch(err => {
        alert(err.response?.data?.detail || "Action failed");
      });
  }

  return (
    <div style={{ padding: '20px' }}>
      <h1>B2B Harness Dashboard</h1>
      <p><strong>Current Stage:</strong> {status}</p>
      
      {artifact && (
        <div style={{ border: '1px solid #ccc', padding: '10px', marginTop: '20px' }}>
          <h3>Review Artifact</h3>
          <pre style={{ whiteSpace: 'pre-wrap', background: '#f4f4f4' }}>{artifact}</pre>
        </div>
      )}

      <div style={{ marginTop: '20px' }}>
        <input value={key} onChange={e => setKey(e.target.value)} placeholder="API Key" />
        <button onClick={saveKey}>Save Key</button>
      </div>

      <div style={{ marginTop: '20px' }}>
        <button onClick={approvePipeline}>Approve</button>
        <button onClick={advancePipeline} style={{ marginLeft: '10px' }}>Advance Pipeline</button>
      </div>
    </div>
  )
}

export default App
