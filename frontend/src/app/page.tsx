'use client';

import { useState, useEffect } from 'react';

export default function Home() {
  const [provider, setProvider] = useState('gpt-4o');
  const [keys, setKeys] = useState({ openai: '', anthropic: '', gemini: '', glm: '' });
  
  const [productUrl, setProductUrl] = useState('');
  const [description, setDescription] = useState('');
  const [budget, setBudget] = useState('50.00');
  
  const [status, setStatus] = useState<'idle' | 'pending' | 'running' | 'success' | 'error'>('idle');
  const [taskId, setTaskId] = useState('');
  const [campaignData, setCampaignData] = useState<any>(null);
  const [csvOutput, setCsvOutput] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    setKeys({
      openai: localStorage.getItem('ads_openai_key') || '',
      anthropic: localStorage.getItem('ads_anthropic_key') || '',
      gemini: localStorage.getItem('ads_gemini_key') || '',
      glm: localStorage.getItem('ads_glm_key') || ''
    });

    let interval: NodeJS.Timeout;
    if (taskId && (status === 'pending' || status === 'running')) {
      interval = setInterval(async () => {
        try {
          const res = await fetch(`http://localhost:8007/api/tasks/${taskId}`);
          if (res.ok) {
            const data = await res.json();
            setStatus(data.status);
            if (data.status === 'success') {
              setCampaignData(data.campaign_data);
              setCsvOutput(data.csv_output);
              setMessage('Campaign architecture generated successfully!');
            } else if (data.status === 'error') {
              setMessage('Error generating campaign.');
            }
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [taskId, status]);

  const handleExecute = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!productUrl || !description) return;

    setStatus('pending');
    setMessage('Analyzing product intent and generating campaign keywords...');
    setCampaignData(null);
    setCsvOutput('');
    
    try {
      localStorage.setItem('ads_openai_key', keys.openai);
      localStorage.setItem('ads_anthropic_key', keys.anthropic);
      localStorage.setItem('ads_gemini_key', keys.gemini);
      localStorage.setItem('ads_glm_key', keys.glm);

      const res = await fetch('http://localhost:8007/api/execute', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          'X-OpenAI-Key': keys.openai,
          'X-Anthropic-Key': keys.anthropic,
          'X-Gemini-Key': keys.gemini,
          'X-GLM-Key': keys.glm
        },
        body: JSON.stringify({
          product_url: productUrl,
          description: description,
          budget: budget,
          provider: provider
        }),
      });
      
      const data = await res.json();
      if (res.ok) {
        setTaskId(data.task_id);
      } else {
        setStatus('error');
        setMessage(data.detail || 'Failed to start task.');
      }
    } catch (e) {
      console.error(e);
      setStatus('error');
      setMessage('Network error. Ensure backend is running.');
    }
  };

  const handleDownloadCsv = () => {
    if (!csvOutput) return;
    const blob = new Blob([csvOutput], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'google_ads_campaign.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <main className="dashboard-container">
      <div className="dashboard-header">
        <h1>Ads Runner AI</h1>
        <p style={{color: '#5f6368', fontSize: '1.1rem'}}>Autonomous Campaign Architect & Bulk CSV Generator</p>
      </div>

      <div style={{display: 'flex', gap: '30px'}}>
        <div style={{flex: 1}}>
          <div className="panel">
            <h2 className="panel-title">System Configuration</h2>
            <div className="form-group">
              <label>OpenAI (GPT-4o)</label>
              <input type="password" value={keys.openai} onChange={(e) => setKeys({...keys, openai: e.target.value})} disabled={status === 'pending' || status === 'running'} />
            </div>
            <div className="form-group">
              <label>Anthropic (Claude 3.5)</label>
              <input type="password" value={keys.anthropic} onChange={(e) => setKeys({...keys, anthropic: e.target.value})} disabled={status === 'pending' || status === 'running'} />
            </div>
            <div className="form-group">
              <label>Google AI (Gemini 1.5)</label>
              <input type="password" value={keys.gemini} onChange={(e) => setKeys({...keys, gemini: e.target.value})} disabled={status === 'pending' || status === 'running'} />
            </div>
            <div className="form-group">
              <label>ZhipuAI (GLM-4)</label>
              <input type="password" value={keys.glm} onChange={(e) => setKeys({...keys, glm: e.target.value})} disabled={status === 'pending' || status === 'running'} />
            </div>
            <div className="form-group">
              <label>AI Model</label>
              <select value={provider} onChange={(e) => setProvider(e.target.value)} disabled={status === 'pending' || status === 'running'}>
                <option value="gpt-4o">OpenAI (gpt-4o)</option>
                <option value="claude-3-5-sonnet-20240620">Anthropic (claude-3-5-sonnet)</option>
                <option value="gemini/gemini-1.5-pro">Google AI (gemini-1.5-pro)</option>
                <option value="zhipu/glm-4">ZhipuAI (glm-4)</option>
                <option value="ollama/llama3">Local Ollama (Llama 3)</option>
              </select>
            </div>
          </div>

          <div className="panel">
            <h2 className="panel-title">Campaign Parameters</h2>
            <form onSubmit={handleExecute}>
              <div className="form-group">
                <label>Final URL (Landing Page)</label>
                <input 
                  type="url" 
                  value={productUrl} 
                  onChange={(e) => setProductUrl(e.target.value)} 
                  placeholder="https://example.com/product"
                  required
                  disabled={status === 'pending' || status === 'running'}
                />
              </div>
              <div className="form-group">
                <label>Daily Budget ($)</label>
                <input 
                  type="number" 
                  value={budget} 
                  onChange={(e) => setBudget(e.target.value)} 
                  placeholder="50"
                  required
                  disabled={status === 'pending' || status === 'running'}
                />
              </div>
              <div className="form-group">
                <label>Product / Audience Description</label>
                <textarea 
                  value={description} 
                  onChange={(e) => setDescription(e.target.value)} 
                  placeholder="Describe what you are selling, key benefits, and who your target audience is." 
                  rows={5}
                  required
                  disabled={status === 'pending' || status === 'running'}
                />
              </div>
              <button 
                type="submit" 
                className="btn" 
                style={{width: '100%'}}
                disabled={status === 'pending' || status === 'running'}
              >
                {status === 'pending' || status === 'running' ? 'Architecting Campaign...' : 'Generate Google Ads Campaign'}
              </button>
            </form>
          </div>

          {status !== 'idle' && (
            <div className={`status-message ${status}`}>
              {status === 'running' && <strong>Building Ad Groups... </strong>}
              {message}
            </div>
          )}
        </div>

        <div style={{flex: 1}}>
          <div className="panel" style={{height: '100%', display: 'flex', flexDirection: 'column'}}>
            <h2 className="panel-title">Campaign Explorer</h2>
            
            <div style={{flex: 1, overflowY: 'auto', maxHeight: '600px', background: '#f8f9fa', padding: '15px', borderRadius: '4px', border: '1px solid #dadce0'}}>
              {status === 'idle' ? (
                <p style={{color: '#80868b', textAlign: 'center', marginTop: '40px'}}>No campaign generated yet.</p>
              ) : status === 'running' || status === 'pending' ? (
                <div style={{textAlign: 'center', marginTop: '40px'}}>
                  <p style={{color: 'var(--primary)', fontWeight: 'bold'}}>AI is clustering keywords...</p>
                  <p style={{fontSize: '0.9rem', color: '#5f6368', marginTop: '10px'}}>Generating high-intent ad copy...</p>
                </div>
              ) : campaignData ? (
                <div>
                  <h3 style={{fontWeight: 'bold', fontSize: '1.1rem', color: 'var(--primary)'}}>
                    Campaign: {campaignData.campaign_name}
                  </h3>
                  
                  {campaignData.ad_groups?.map((ag: any, index: number) => (
                    <div key={index} className="tree-node">
                      <strong style={{color: 'var(--accent)'}}>Ad Group: {ag.name}</strong>
                      
                      <div className="tree-node" style={{borderLeftColor: '#34a853'}}>
                        <strong>Keywords:</strong>
                        <ul style={{listStyle: 'circle', marginLeft: '20px', fontSize: '0.9rem'}}>
                          {ag.keywords?.map((kw: string, i: number) => (
                            <li key={i}>"{kw}"</li>
                          ))}
                        </ul>
                      </div>
                      
                      <div className="tree-node" style={{borderLeftColor: '#ea4335'}}>
                        <strong>Ad Copy:</strong>
                        {ag.ads?.map((ad: any, i: number) => (
                          <div key={i} style={{background: '#fff', padding: '10px', marginTop: '5px', border: '1px solid #ddd', borderRadius: '4px', fontSize: '0.85rem'}}>
                            <div><span style={{color: '#1a0dab', fontSize: '1rem'}}>{ad.headline_1} | {ad.headline_2} | {ad.headline_3}</span></div>
                            <div style={{color: '#006621'}}>{productUrl}</div>
                            <div style={{color: '#545454'}}>{ad.description_1} {ad.description_2}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p>Failed to parse campaign.</p>
              )}
            </div>
            
            {status === 'success' && csvOutput && (
              <div style={{marginTop: '20px'}}>
                <button onClick={handleDownloadCsv} className="btn btn-secondary" style={{width: '100%'}}>
                  Download CSV for Google Ads Editor
                </button>
                <p style={{fontSize: '0.8rem', color: '#5f6368', marginTop: '10px', textAlign: 'center'}}>
                  Import this CSV directly into Google Ads Editor to deploy the campaign instantly.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
