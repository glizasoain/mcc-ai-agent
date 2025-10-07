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

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setLoading(true); setResult(null);
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

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100">
      <div className="max-w-6xl mx-auto p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
        <section className="space-y-4">
          <h1 className="text-xl font-semibold">MCC Underwriter</h1>
          <form onSubmit={onSubmit} className="space-y-3 bg-neutral-900/60 p-4 rounded border border-neutral-800">
            <div className="grid grid-cols-2 gap-3">
              <input placeholder="Legal name" value={legalName} onChange={e=>setLegalName(e.target.value)} className="bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
              <input placeholder="DBA name" value={dbaName} onChange={e=>setDbaName(e.target.value)} className="bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
            </div>
            <input placeholder="Websites (space or comma separated)" value={websites} onChange={e=>setWebsites(e.target.value)} className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
            <textarea placeholder="Merchant description (optional)" value={desc} onChange={e=>setDesc(e.target.value)} className="w-full bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
            <div className="grid grid-cols-2 gap-3">
              <input placeholder="Industry" value={industry} onChange={e=>setIndustry(e.target.value)} className="bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
              <input placeholder="Vertical" value={vertical} onChange={e=>setVertical(e.target.value)} className="bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <input placeholder="Country" value={country} onChange={e=>setCountry(e.target.value)} className="bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
              <input placeholder="Avg ticket" value={avgTicket} onChange={e=>setAvgTicket(e.target.value)} className="bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
              <input placeholder="Volume band (small/mid/large)" value={volumeBand} onChange={e=>setVolumeBand(e.target.value)} className="bg-neutral-900 border border-neutral-800 rounded px-3 py-2" />
            </div>
            <button disabled={loading} className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded px-4 py-2">{loading?"Analyzing...":"Analyze Merchant"}</button>
            {error && <div className="text-red-400 text-sm">{error}</div>}
          </form>
          {result && (
            <div className="space-y-4">
              <div className="bg-neutral-900/60 p-4 rounded border border-neutral-800">
                <h2 className="font-semibold mb-2">Final Recommendation</h2>
                <div className="text-sm text-neutral-300">{result.recommended_mcc} — {result.recommended_mcc_description}</div>
                <div className="text-sm">Confidence: {result.confidence}</div>
                <div className="mt-2 text-sm text-neutral-300 whitespace-pre-wrap">{result.recommendation_justification}</div>
              </div>
              <div className="bg-neutral-900/60 p-4 rounded border border-neutral-800">
                <h3 className="font-semibold mb-2">Ranked Alternatives</h3>
                <div className="space-y-2">
                  {(result.mcc_proposal?.ranked||[]).map((r:any, idx:number)=> (
                    <div key={idx} className="border border-neutral-800 rounded p-3">
                      <div className="text-sm">{r.mcc} — {r.description}</div>
                      <div className="text-xs text-neutral-400">Confidence: {r.confidence}</div>
                      {r.benchmark && (
                        <div className="text-xs text-neutral-400 mt-1">
                          IC avg: {r.benchmark.average_ic_rate ?? "-"}, Decline avg: {r.benchmark.average_decline_rate_pct ?? "-"}
                          {r.ic_bps_delta!==undefined && (<span> • IC Δbps: {r.ic_bps_delta.toFixed?.(2) ?? r.ic_bps_delta}</span>)}
                          {r.decline_pp_delta!==undefined && (<span> • Decline Δpp: {r.decline_pp_delta.toFixed?.(2) ?? r.decline_pp_delta}</span>)}
                          {r.benchmark.example_merchant_name && (
                            <div>Example: <a className="text-blue-400 underline" href={r.benchmark.example_merchant_url || "#"} target="_blank">{r.benchmark.example_merchant_name}</a></div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
              <div className="bg-neutral-900/60 p-4 rounded border border-neutral-800">
                <h3 className="font-semibold mb-2">Business Description</h3>
                <pre className="text-xs whitespace-pre-wrap text-neutral-300">{JSON.stringify(result.business_description, null, 2)}</pre>
              </div>
            </div>
          )}
        </section>
        <section className="bg-neutral-900/60 p-4 rounded border border-neutral-800">
          <h2 className="font-semibold mb-2">Research Chat (coming soon)</h2>
          <p className="text-sm text-neutral-400">Ask questions about evidence, compare alternatives, and view sources.</p>
        </section>
      </div>
    </main>
  );
}


