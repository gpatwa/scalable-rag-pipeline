import { Compass, Search, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { createDiscoveryClient, type SearchResponse } from './api/client';
import './styles.css';

const demoResponse: SearchResponse = {
  schema_version: 'imd-search-v1',
  request_id: 'local-demo',
  total_matches: 3,
  fallback: true,
  error: null,
  results: [
    { experience_id: 'skybound-studio', title: 'Skybound Studio', rank: 1, score: 0.96, reason_codes: ['lexical_match'], evidence: ['title'] },
    { experience_id: 'tiny-town', title: 'Tiny Town Builders', rank: 2, score: 0.82, reason_codes: ['lexical_match'], evidence: ['title', 'genre'] },
    { experience_id: 'reef-runners', title: 'Reef Runners', rank: 3, score: 0.67, reason_codes: ['safe_catalog_fallback'], evidence: ['genre'] },
  ],
};

const client = createDiscoveryClient(import.meta.env.VITE_DISCOVERY_API_URL ?? '');

export default function App() {
  const [query, setQuery] = useState('cozy building games');
  const [response, setResponse] = useState<SearchResponse>(demoResponse);
  const [loading, setLoading] = useState(false);

  async function runSearch() {
    setLoading(true);
    try {
      const next = await client.search({
        query,
        context: { tenant_id: 'demo', principal_id: 'synthetic-user-1', request_id: crypto.randomUUID(), locale: 'en-US', device: 'web', age_band: 'teen', purpose: 'search' },
        page_size: 20,
      });
      setResponse(next);
    } catch {
      setResponse({ ...demoResponse, fallback: true });
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar"><div className="brand"><Compass size={22} /><span>COMPASS / DISCOVERY</span></div><span className="status"><span className="dot" /> LOCAL DEMO</span></header>
      <section className="intro"><p className="eyebrow">IMMERSIVE DISCOVERY</p><h1>Find your next world.</h1><p className="lede">A governed search surface for experiences, creators, and communities.</p></section>
      <section className="search-panel" aria-label="Discovery search"><div className="search-row"><Search size={21} /><input aria-label="Search experiences" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void runSearch()} /><button type="button" onClick={() => void runSearch()} disabled={loading}>{loading ? 'Searching' : 'Explore'}</button></div><div className="chips"><span>Personalized when permitted</span><span>Policy-aware results</span><span>Evidence-backed ranking</span></div></section>
      <section className="results"><div className="results-heading"><div><p className="eyebrow">CURATED FOR YOU</p><h2>{response.total_matches} worlds to explore</h2></div><span className="trace"><Sparkles size={15} /> {response.fallback ? 'Safe catalog fallback' : 'Ranked locally'}</span></div><div className="result-grid">{response.results.map((result) => <article className="result" key={result.experience_id}><div className="result-art"><span>{String(result.rank).padStart(2, '0')}</span></div><div className="result-copy"><h3>{result.title}</h3><p>{result.reason_codes.join(' · ')}</p><small>{Math.round(result.score * 100)}% relevance</small></div></article>)}</div></section>
    </main>
  );
}
