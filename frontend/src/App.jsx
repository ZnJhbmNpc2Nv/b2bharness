import { useState, useEffect } from 'react'
import axios from 'axios'
import PipelineGraph from './PipelineGraph'

function App() {
  const [keyActive, setKeyActive] = useState(false)
  const [key, setKey] = useState("")
  const [intentText, setIntentText] = useState("")
  const [refinedIntent, setRefinedIntent] = useState(null)
  const [artifact, setArtifact] = useState(null)
  const [status, setStatus] = useState("Loading...")
  const [sessionId, setSessionId] = useState("session_001")

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axios.get('/api/health')
        setStatus(res.data.state)
        
        const statusRes = await axios.get('/api/config/status')
        setKeyActive(statusRes.data.active)

        if (res.data.state === "INTENT" || res.data.state === "PLAN") {
           const art = await axios.get(`/api/pipeline/artifacts/${sessionId}/discovery`)
           setArtifact(art.data.content)
        }
      } catch (e) {
        console.error(e)
      }
    }
    fetchData()
  }, [sessionId])

  const refineIntent = async () => {
    const res = await axios.post('/api/pipeline/refine-intent', { text: intentText })
    setRefinedIntent(res.data.refined_text)
  }

  const clearToken = async () => {
    await axios.delete('/api/config/keys')
    setKeyActive(false)
  }

  // ... (далее в render)


  const saveKey = async () => {
    try {
      await axios.post('/api/config/keys', { key_name: 'GIGACODE', value: key })
      alert("Key saved!")
    } catch (e) {
      alert("Error saving key")
    }
  }

  const approveAndAdvance = async () => {
    try {
      await axios.post('/api/pipeline/approve')
      const res = await axios.post('/api/pipeline/advance', {}, { headers: { 'session-id': sessionId, 'user-id': 'admin' } })
      setStatus(res.data.state)
      alert("Approved & Advanced!")
      window.location.reload()
    } catch (err) {
      alert(err.response?.data?.detail || "Action failed")
    }
  }

  const advancePipeline = () => {
    axios.post('/api/pipeline/advance', {}, { headers: { 'session-id': sessionId, 'user-id': 'admin' } })
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
      <PipelineGraph />
      <p><strong>Current Stage:</strong> {status}</p>
      
      {artifact && (
        <div style={{ border: '1px solid #ccc', padding: '10px', marginTop: '20px' }}>
          <h3>Review Artifact</h3>
          <pre style={{ whiteSpace: 'pre-wrap', background: '#f4f4f4' }}>{artifact}</pre>
        </div>
      )}

      <div style={{ marginTop: '20px' }}>
        {!keyActive ? (
          <>
            <input value={key} onChange={e => setKey(e.target.value)} placeholder="API Key" />
            <button onClick={saveKey}>Save Key</button>
          </>
        ) : (
          <>
            <button onClick={clearToken} style={{ background: '#ffcccc' }}>Clear Token</button>
            <div style={{ marginTop: '10px' }}>
              <textarea value={intentText} onChange={e => setIntentText(e.target.value)} placeholder="Describe your intent..." />
              <button onClick={refineIntent}>Refine Intent</button>
            </div>
          </>
        )}
      </div>

      {refinedIntent && (
        <div style={{ border: '1px solid green', padding: '10px', marginTop: '10px' }}>
          <h3>Refined Intent:</h3>
          <p>{refinedIntent}</p>
          <button onClick={approveAndAdvance}>Approve & Advance</button>
        </div>
      )}
    </div>
  )
}

export default App
