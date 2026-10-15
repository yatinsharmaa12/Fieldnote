import { useCallback, useEffect, useRef, useState } from "react";
import { Link, Navigate, Route, Routes, useNavigate, useParams } from "react-router-dom";
import { ArrowUpRight, Bot, CircleStop, Clock3, Globe2, LogOut, Plus, RefreshCw, Search, Send, Sparkles, X } from "lucide-react";
import { ApiError, api } from "./api";
import { useAuth } from "./auth";
import { ChatPanel } from "./components/ChatPanel";
import { Dialog } from "./components/Dialog";
import { useCrawlStatus } from "./hooks/useCrawlStatus";
import type { Company, CrawlJob } from "./types";

const terminal = ["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"];
const fmtDate = (value: string | null) => value ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + "Z").toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "—";
const fmtDuration = (seconds: number | null) => seconds == null ? "—" : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
const errorText = (error: unknown) => error instanceof ApiError ? error.message : "The service is unavailable. Check the connection and try again.";

function Shell({ children }: { children: React.ReactNode }) {
  const { logout } = useAuth();
  return <div className="app-shell"><aside className="sidebar"><Link to="/" className="brand"><span className="brand-mark">F</span><span>fieldnote</span></Link><div className="side-label">Workspace</div><Link to="/" className="side-link"><Globe2 size={17} /> Companies</Link><div className="sidebar-bottom"><div className="status-dot"><span /> Company workspace</div><button className="side-link side-button" onClick={logout}><LogOut size={17} /> Sign out</button></div></aside><main className="main-content">{children}</main></div>;
}

function Login() {
  const { token, login } = useAuth(); const navigate = useNavigate();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  if (token) return <Navigate to="/" replace />;
  async function submit(event: React.FormEvent) { event.preventDefault(); setError(""); setLoading(true); try { await login(email, password); navigate("/"); } catch (e) { setError(errorText(e)); } finally { setLoading(false); } }
  return <div className="login-page"><div className="login-art"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-copy"><span className="eyebrow">Company intelligence, in motion</span><h1>Turn a website into a working knowledge base.</h1><p>Fieldnote crawls the public web, keeps you close to the work, and gives your team a grounded way to ask questions.</p></div><div className="art-foot">crawl / observe / ask</div></div><div className="login-form-wrap"><div className="login-form"><Link to="/" className="brand"><span className="brand-mark">F</span><span>fieldnote</span></Link><div className="eyebrow">Welcome back</div><h2>Sign in to your workspace</h2><p className="muted">Your company knowledge is waiting.</p><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" placeholder="you@company.com" /></label><label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required autoComplete="current-password" placeholder="••••••••" /></label>{error && <div role="alert" className="alert error">{error}</div>}<button className="primary full" disabled={loading}>{loading ? "Signing in…" : "Sign in"}<ArrowUpRight size={17} /></button></form><p className="auth-switch">Don’t have an account? <Link to="/signup">Create one</Link></p></div></div></div>;
}

function Signup() {
  const { login } = useAuth(); const navigate = useNavigate();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [confirmation, setConfirmation] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (password !== confirmation) { setError("Passwords do not match."); return; }
    setError(""); setLoading(true);
    try { await api.register(email, password); await login(email, password); navigate("/", { replace: true }); }
    catch (e) { setError(errorText(e)); }
    finally { setLoading(false); }
  }
  return <div className="login-page"><div className="login-art"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-copy"><span className="eyebrow">A clearer company workspace</span><h1>Start with the website your team needs to understand.</h1><p>Create a workspace, crawl its public knowledge, and ask grounded questions.</p></div><div className="art-foot">crawl / observe / ask</div></div><div className="login-form-wrap"><div className="login-form"><Link to="/" className="brand"><span className="brand-mark">F</span><span>fieldnote</span></Link><div className="eyebrow">New workspace</div><h2>Create your account</h2><p className="muted">Start turning websites into useful company knowledge.</p><form onSubmit={submit}><label>Email<input type="email" value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" placeholder="you@company.com" /></label><label>Password<input type="password" value={password} onChange={e => setPassword(e.target.value)} required minLength={8} autoComplete="new-password" placeholder="At least 8 characters" /></label><label>Confirm password<input type="password" value={confirmation} onChange={e => setConfirmation(e.target.value)} required minLength={8} autoComplete="new-password" placeholder="Repeat your password" /></label>{error && <div role="alert" className="alert error">{error}</div>}<button className="primary full" disabled={loading}>{loading ? "Creating account…" : "Create account"}<ArrowUpRight size={17} /></button></form><p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p></div></div></div>;
}

function Companies() {
  const [companies, setCompanies] = useState<Company[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [open, setOpen] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true; setLoading(true); setError("");
    api.companies().then(result => { if (active) setCompanies(result); }).catch(error => { if (active) setError(errorText(error)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [revision]);
  return <Shell><header className="topbar"><div><div className="eyebrow">Workspace / overview</div><h1>Companies</h1></div><button className="primary" onClick={() => setOpen(true)}><Plus size={18} /> Add company</button></header><section className="hero-strip"><div><span className="eyebrow">The starting point</span><h2>Give us a website.<br />We’ll map the signal.</h2></div><div className="hero-stamp"><Sparkles size={19} /><span>Knowledge, grounded<br />in the source.</span></div></section>{error && <div role="alert" className="alert error">{error} <button className="text-button" onClick={() => setRevision(value => value + 1)}>Try again</button></div>}{loading ? <Loading label="Loading your companies" /> : error ? null : companies.length === 0 ? <EmptyState title="No companies yet" copy="Add your first company to start crawling its public knowledge." action={<button className="primary" onClick={() => setOpen(true)}>Add your first company <Plus size={17} /></button>} /> : <div className="company-grid">{companies.map(company => <Link className="company-card" to={`/companies/${company.id}`} key={company.id}><div className="card-kicker">Company {String(company.id).padStart(3, "0")}</div><h3>{company.name}</h3><div className="website"><Globe2 size={15} />{company.website_url.replace(/^https?:\/\//, "")}</div><span className="card-arrow"><ArrowUpRight size={18} /></span></Link>)}</div>}{open && <CompanyModal onClose={() => setOpen(false)} onCreated={company => { setCompanies(current => [company, ...current]); setOpen(false); }} />}</Shell>;
}

function CompanyModal({ onClose, onCreated }: { onClose: () => void; onCreated: (company: Company) => void }) {
  const [name, setName] = useState(""); const [website_url, setWebsite] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  async function submit(e: React.FormEvent) { e.preventDefault(); setLoading(true); setError(""); try { onCreated(await api.createCompany({ name, website_url })); } catch (err) { setError(errorText(err)); } finally { setLoading(false); } }
  return <Dialog label="Add a company" onClose={onClose}><button className="icon-button close" onClick={onClose} aria-label="Close"><X /></button><div className="eyebrow">New workspace</div><h2>Add a company</h2><p className="muted">We’ll use the public website as the crawl starting point.</p><form onSubmit={submit}><label>Company name<input value={name} onChange={e => setName(e.target.value)} required placeholder="Acme, Inc." /></label><label>Website URL<input type="url" value={website_url} onChange={e => setWebsite(e.target.value)} required placeholder="https://example.com" /></label>{error && <div role="alert" className="alert error">{error}</div>}<button className="primary full" disabled={loading}>{loading ? "Creating…" : "Create company"}<ArrowUpRight size={17} /></button></form></Dialog>;
}

function CompanyDetailRoute() { const { companyId } = useParams(); return <CompanyDetail key={companyId} />; }

function CompanyDetail() {
  const { companyId } = useParams(); const id = Number(companyId); const [company, setCompany] = useState<Company | null>(null); const [jobs, setJobs] = useState<CrawlJob[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [showCrawl, setShowCrawl] = useState(false); const [selected, setSelected] = useState<number | null>(null);
  const active = useRef(true);
  const load = useCallback(async () => { setError(""); try { const [companyResult, jobsResult] = await Promise.all([api.company(id), api.crawlJobs(id)]); if (active.current) { setCompany(companyResult); setJobs(jobsResult); } } catch (e) { if (active.current) setError(errorText(e)); } finally { if (active.current) setLoading(false); } }, [id]);
  useEffect(() => { active.current = true; void load(); return () => { active.current = false; }; }, [load]);
  const watched = jobs.find(job => !terminal.includes(job.status));
  const progress = useCrawlStatus(id, selected ? null : watched?.job_id ?? null);
  useEffect(() => { if (progress.job) setJobs(current => current.map(job => job.job_id === progress.job!.job_id ? progress.job! : job)); }, [progress.job]);
  if (loading) return <Shell><Loading label="Loading company" /></Shell>;
  if (error || !company) return <Shell><div role="alert" className="alert error">{error || "Company not found"} <button className="text-button" onClick={load}>Try again</button></div></Shell>;
  const latest = jobs[0];
  return <Shell>{progress.error && <div role="alert" className="alert error">{progress.error} <button className="text-button" onClick={progress.retry}>Retry now</button></div>}<header className="topbar"><div><Link className="back-link" to="/">← All companies</Link><h1>{company.name}</h1><div className="website"><Globe2 size={15} />{company.website_url}</div></div><button className="primary" onClick={() => setShowCrawl(true)}><RefreshCw size={17} /> Start crawl</button></header><div className="detail-grid"><section className="panel latest-panel"><div className="panel-heading"><div><div className="eyebrow">Latest crawl</div><h2>{latest ? statusLabel(latest.status) : "Not crawled yet"}</h2></div>{latest && <StatusBadge status={latest.status} />}</div>{latest ? <><div className="latest-meta"><span><Clock3 size={15} /> {fmtDate(latest.created_at)}</span><span>{fmtDuration(latest.duration_seconds)}</span></div><button className="text-button" onClick={() => setSelected(latest.job_id)}>Open crawl details <ArrowUpRight size={16} /></button></> : <p className="muted">Start a crawl to create your first company snapshot.</p>}</section><ChatPanel key={company.id} company={company} /></div><section className="history-section"><div className="section-heading"><div><div className="eyebrow">Archive</div><h2>Crawl history</h2></div><span className="count-label">{jobs.length} {jobs.length === 1 ? "run" : "runs"}</span></div>{jobs.length === 0 ? <div className="empty-inline">No crawl history yet.</div> : <div className="history-table"><div className="history-head"><span>Status</span><span>Created</span><span>Duration</span><span>Pages</span><span>Attempts</span><span /></div>{jobs.map(job => <button className="history-row" key={job.job_id} onClick={() => setSelected(job.job_id)}><StatusBadge status={job.status} /><span>{fmtDate(job.created_at)}</span><span>{fmtDuration(job.duration_seconds)}</span><span>{job.pages_crawled} / {job.pages_discovered}</span><span>{job.attempt_count}</span><ArrowUpRight size={17} /></button>)}</div>}</section>{showCrawl && <CrawlModal companyId={id} onClose={() => setShowCrawl(false)} onCreated={jobId => { setShowCrawl(false); setSelected(jobId); load(); }} />}{selected && <CrawlDrawer companyId={id} jobId={selected} onClose={() => setSelected(null)} onChanged={load} />}</Shell>;
}

function CrawlModal({ companyId, onClose, onCreated }: { companyId: number; onClose: () => void; onCreated: (id: number) => void }) { const [max_pages, setPages] = useState(5); const [max_depth, setDepth] = useState(1); const [error, setError] = useState(""); const [loading, setLoading] = useState(false); async function submit(e: React.FormEvent) { e.preventDefault(); setLoading(true); try { const job = await api.createCrawl(companyId, { max_pages, max_depth }); onCreated(job.job_id); } catch (err) { setError(errorText(err)); } finally { setLoading(false); } } return <Dialog label="Start a crawl" onClose={onClose}><button className="icon-button close" onClick={onClose} aria-label="Close"><X /></button><div className="eyebrow">New crawl</div><h2>Set the boundaries</h2><p className="muted">The crawler will stay inside the company website.</p><form onSubmit={submit}><div className="form-row"><label>Max pages<input type="number" min="1" max="100" value={max_pages} onChange={e => setPages(Number(e.target.value))} /></label><label>Max depth<input type="number" min="0" max="10" value={max_depth} onChange={e => setDepth(Number(e.target.value))} /></label></div>{error && <div role="alert" className="alert error">{error}</div>}<button className="primary full" disabled={loading}>{loading ? "Starting…" : "Start crawl"}<ArrowUpRight size={17} /></button></form></Dialog>; }

function CrawlDrawer({ companyId, jobId, onClose, onChanged }: { companyId: number; jobId: number; onClose: () => void; onChanged: () => void }) {
  const { job, error: pollingError, retry } = useCrawlStatus(companyId, jobId);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const onChange = useRef(onChanged);
  onChange.current = onChanged;
  useEffect(() => { if (job && terminal.includes(job.status)) onChange.current(); }, [job?.status]);
  async function cancel() {
    if (cancelling) return;
    setCancelling(true); setError("");
    try { await api.cancelCrawl(companyId, jobId); retry(); }
    catch (error) { setError(errorText(error)); }
    finally { setCancelling(false); }
  }
  return <Dialog drawer label="Crawl details" onClose={onClose}>
    <div className="drawer-top"><div><div className="eyebrow">Crawl #{jobId}</div><h2>{job ? statusLabel(job.status) : "Loading crawl…"}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close"><X /></button></div>
    {(error || pollingError) && <div role="alert" className="alert error">{error || pollingError} <button type="button" className="text-button" onClick={retry}>Retry now</button></div>}
    {!job && !pollingError && <Loading label="Loading crawl details" />}
    {job && <><div className="crawl-state" role="status"><StatusBadge status={job.status} /><span>{job.error || (terminal.includes(job.status) ? "Run finished" : "The crawler is working through the site")}</span></div>
      <div className="stats-grid"><Stat label="Duration" value={fmtDuration(job.duration_seconds)} /><Stat label="Attempts" value={job.attempt_count} /><Stat label="Discovered" value={job.pages_discovered} /><Stat label="Crawled" value={job.pages_crawled} /><Stat label="Indexed" value={job.pages_indexed} /><Stat label="Failed" value={job.pages_failed} /></div>
      <div className="incremental"><div className="eyebrow">Incremental changes</div><div className="incremental-grid"><Stat label="New" value={job.pages_new} /><Stat label="Changed" value={job.pages_changed} /><Stat label="Unchanged" value={job.pages_unchanged} /><Stat label="Deactivated" value={job.pages_deactivated} /></div></div>
      <div className="time-list"><div><span>Started</span><b>{fmtDate(job.started_at)}</b></div><div><span>Completed</span><b>{fmtDate(job.completed_at)}</b></div></div>
      {!terminal.includes(job.status) && <button className="danger-button" disabled={cancelling} onClick={cancel}><CircleStop size={17} />{cancelling ? "Cancelling…" : "Cancel crawl"}</button>}
    </>}
  </Dialog>;
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) { return <div className="stat"><span>{label}</span><strong>{value}</strong></div>; }
function StatusBadge({ status }: { status: string }) { return <span className={`status-badge ${status.toLowerCase()}`}><span />{status}</span>; }
function statusLabel(status: string) { return (status.charAt(0) + status.slice(1).toLowerCase()).replace(/_/g, " "); }
function Loading({ label }: { label: string }) { return <div className="loading"><div className="spinner" />{label}…</div>; }
function EmptyState({ title, copy, action }: { title: string; copy: string; action: React.ReactNode }) { return <div className="empty-state"><div className="empty-icon"><Globe2 size={23} /></div><h2>{title}</h2><p>{copy}</p>{action}</div>; }
function Protected() { const { token } = useAuth(); return token ? <Routes><Route path="/" element={<Companies />} /><Route path="/companies/:companyId" element={<CompanyDetailRoute />} /></Routes> : <Navigate to="/login" replace />; }
export default function App() { return <Routes><Route path="/login" element={<Login />} /><Route path="/signup" element={<Signup />} /><Route path="*" element={<Protected />} /></Routes>; }
