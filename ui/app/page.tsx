"use client";
import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8090";

export default function HomePage() {
  const [legalName, setLegalName] = useState("");
  const [dbaName, setDbaName] = useState("");
  const [websites, setWebsites] = useState("");
  const [industry, setIndustry] = useState("");
  const [vertical, setVertical] = useState("");
  const [country, setCountry] = useState("US");
  const [avgTicket, setAvgTicket] = useState<string>("");
  const [volumeBand, setVolumeBand] = useState<string>("");
  const [desc, setDesc] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any | null>(null);
  const [chatInput, setChatInput] = useState("");
  const [chatMsgs, setChatMsgs] = useState<Array<{role:string; content:string}>>([]);

  function formatArray(val: any): string | null {
    if (!val) return null;
    if (Array.isArray(val)) return val.filter(Boolean).join(", ");
    return String(val);
  }

  function BusinessDescription({ data }: { data: any }) {
    if (!data || typeof data !== "object") return null;
    const rows: Array<{ label: string; value?: string | null }> = [
      { label: "Core offering", value: data.core_offering || data.coreOffering },
      { label: "Primary revenue", value: data.primary_revenue_stream || data.primaryRevenue },
      { label: "Sales model", value: data.sales_model },
      { label: "Transaction flow", value: data.transaction_flow },
      { label: "Pricing model", value: data.pricing_model },
      { label: "Target customers", value: formatArray(data.target_customers) },
      { label: "Verticals", value: formatArray(data.verticals) },
      { label: "Integrations", value: formatArray(data.integrations) },
      { label: "Excluded lines", value: formatArray(data.excluded_lines) },
    ];
    const shown = rows.filter(r => r.value && String(r.value).trim().length > 0);
    if (shown.length === 0) return null;
    return (
      <div className="list">
        {shown.map((r, i) => (
          <div key={i}>
            <div className="meta">{r.label}</div>
            <div>{r.value}</div>
          </div>
        ))}
      </div>
    );
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setLoading(true); setResult(null);
    setChatMsgs([]); // clear chat on new analysis
    try {
      const payload: any = {
        merchant_id: legalName || dbaName || (websites.split(/[\s,]+/)[0] || "unknown"),
        legal_name: legalName || undefined,
        dba_name: dbaName || undefined,
        websites: websites.split(/[\s,]+/).filter(Boolean),
        merchant_description: desc || undefined,
        profile: {
          industry: industry || undefined,
          vertical: vertical || undefined,
          country: country || undefined,
          avg_ticket: avgTicket ? Number(avgTicket) : undefined,
          volume_band: volumeBand || undefined,
        },
        force: true,
      };
      const r = await fetch(`${API_URL}/api/v1/mcc/recommend`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setResult(data);
    } catch (err: any) {
      setError(err?.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  async function onChatSend(e: React.FormEvent) {
    e.preventDefault();
    const userMsg = { role: "user", content: chatInput };
    const newMsgs = [...chatMsgs, userMsg];
    setChatMsgs(newMsgs);
    setChatInput("");
    try {
      const r = await fetch(`${API_URL}/api/v1/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          merchant_id: result?.merchant_id,
          messages: newMsgs,
          context: {
            web_intel: result?.web_intel,
            business_description: result?.business_description,
            website_summary: result?.website_summary,
            mcc_proposal: result?.mcc_proposal,
            recommended_mcc: result?.recommended_mcc,
            recommended_mcc_description: result?.recommended_mcc_description,
            confidence: result?.confidence,
            justification: result?.recommendation_justification,
            supporting_evidence: result?.supporting_evidence,
          },
        }),
      });
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setChatMsgs(data.messages || newMsgs);
    } catch (err) {
      // keep UX simple
    }
  }

  return (
    <div className="container">
      <div className="header">
        <div>
          <div className="logo"><span className="logo-badge"/> MCC Underwriter</div>
          {loading && <div className="workbar"><div className="inner"/></div>}
        </div>
        <div className="kicker">Decision + Research</div>
      </div>

      <div className="grid">
        <div className="span-2">
          <div className="card" style={{marginBottom:12}}>
            <h2>Intake</h2>
            <form onSubmit={onSubmit}>
              <div className="row">
                <input className="input" placeholder="Legal name" value={legalName} onChange={e=>setLegalName(e.target.value)} />
                <input className="input" placeholder="DBA name" value={dbaName} onChange={e=>setDbaName(e.target.value)} />
              </div>
              <div style={{marginTop:10}}>
                <input className="input" placeholder="Websites (space or comma separated)" value={websites} onChange={e=>setWebsites(e.target.value)} />
              </div>
              <div style={{marginTop:10}}>
                <textarea className="input" placeholder="Merchant description (optional)" value={desc} onChange={e=>setDesc(e.target.value)} />
              </div>
              <div className="row" style={{marginTop:10}}>
                <input className="input" placeholder="Industry" value={industry} onChange={e=>setIndustry(e.target.value)} />
                <input className="input" placeholder="Vertical" value={vertical} onChange={e=>setVertical(e.target.value)} />
              </div>
              <div className="row-3" style={{marginTop:10}}>
                <input className="input" placeholder="Country" value={country} onChange={e=>setCountry(e.target.value)} />
                <input className="input" placeholder="Avg ticket" value={avgTicket} onChange={e=>setAvgTicket(e.target.value)} />
                <input className="input" placeholder="Volume band (small/mid/large)" value={volumeBand} onChange={e=>setVolumeBand(e.target.value)} />
              </div>
              <div style={{display:"flex",gap:10,alignItems:"center",marginTop:12}}>
                <button className="btn" disabled={loading}>{loading?<><span className="spinner"/>Analyzing...</>:"Analyze Merchant"}</button>
                {error && <span className="meta">{error}</span>}
              </div>
            </form>
          </div>
        </div>

        <div>
          <div className="card panel-scroll">
            <h2>Decision Panel</h2>
            <div className="panel-body">
              {!result && <div className="meta">Run an analysis to see recommendations.</div>}
              {result && (
                <div className="list">
                  <div>
                    <div><span className="badge">Final</span></div>
                    <div style={{marginTop:6}}>{result.recommended_mcc} — {result.recommended_mcc_description}</div>
                    <div className="meta">Confidence: {result.confidence}</div>
                    <div className="meta" style={{marginTop:6}}>Justification</div>
                    <div style={{whiteSpace:"pre-wrap",marginTop:4}}>{result.recommendation_justification}</div>
                  </div>
                  <div>
                    <div className="meta">Ranked Alternatives</div>
                    <div className="list">
                      {(result.mcc_proposal?.ranked||[]).map((r:any, idx:number)=> (
                        <div key={idx} className="card" style={{padding:10}}>
                          <div>{r.mcc} — {r.description}</div>
                          <div className="meta">Confidence: {r.confidence}</div>
                          <div className="meta" style={{marginTop:4}}>
                            IC avg: {r.benchmark?.average_ic_rate ?? "-"}, Decline avg: {r.benchmark?.average_decline_rate_pct ?? "-"}
                            {r.ic_bps_delta!==undefined && (<span> • IC Δbps: {r.ic_bps_delta.toFixed?.(2) ?? r.ic_bps_delta}</span>)}
                            {r.decline_pp_delta!==undefined && (<span> • Decline Δpp: {r.decline_pp_delta.toFixed?.(2) ?? r.decline_pp_delta}</span>)}
                          </div>
                          {r.benchmark?.example_merchant_name && (
                            <div className="meta" style={{marginTop:4}}>Example: <a href={r.benchmark.example_merchant_url || "#"} target="_blank">{r.benchmark.example_merchant_name}</a></div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                <div>
                  <div className="meta">Business Description</div>
                  <BusinessDescription data={result.business_description} />
                </div>
                {/* Compliance card removed per rollback */}
                </div>
              )}
            </div>
          </div>
        </div>

        <div>
          <div className="card chat">
            <h2>Research Chat</h2>
            <div className="chat-log">
              {chatMsgs.map((m, i)=> (
                <div key={i} className={m.role === "user" ? "chat-user" : "chat-assistant"}>{m.role}: {m.content}</div>
              ))}
            </div>
            <form onSubmit={onChatSend} className="chat-form">
              <input value={chatInput} onChange={e=>setChatInput(e.target.value)} placeholder="Ask about evidence, alternatives..." className="input" />
              <button className="btn">Send</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}


