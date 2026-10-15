import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight, Bot, CircleAlert, CircleCheck, Globe2, LoaderCircle, LogOut, MessageCircle, Send, Sparkles, Square } from "lucide-react";
import { ApiError, isAbortError } from "./api/client";
import { listCompanies, createCompany } from "./api/companies";
import { askCompany, uniqueSources } from "./api/chat";
import { cancelCrawl, listCrawlJobs, startCrawl } from "./api/crawl";
import { useAuth } from "./hooks/useAuth";
import { useCurrentTab } from "./hooks/useCurrentTab";
import { useCrawlStatus } from "./hooks/useCrawlStatus";
import { companyMatchesSite } from "./utils/site";
import type { ChatResponse, Company, CrawlJob } from "./types";

type Message = { role: "user" | "assistant"; text: string; sources?: ChatResponse["sources"] };
const terminal = new Set(["COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"]);
const errorMessage = (error: unknown) => {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Your session has expired. Please sign in again.";
    if (error.status === 404) return "This website is not connected.";
    if (error.status === 502 || error.status === 503) return "The AI service is temporarily unavailable. Please try again.";
    if (error.status === 408) return "The server took too long to respond. Please try again.";
  }
  return error instanceof Error ? error.message : "Something went wrong. Please try again.";
};
const duration = (seconds: number | null) => seconds == null ? "—" : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;

function Login({ onLogin }: { onLogin: (email: string, password: string) => Promise<void> }) {
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  async function submit(e: FormEvent) { e.preventDefault(); setLoading(true); setError(""); try { await onLogin(email, password); } catch (err) { setError(errorMessage(err)); } finally { setLoading(false); } }
  return <main className="login"><div className="logo"><span>F</span> fieldnote</div><div className="login-kicker">Website AI</div><h1>Ask the web<br /><i>better.</i></h1><p className="muted">A grounded assistant for the website you’re viewing.</p><form onSubmit={submit}><label>Email<input type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" /></label><label>Password<input type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="Your password" autoComplete="current-password" /></label>{error && <div role="alert" className="alert"><CircleAlert size={15} />{error}</div>}<button className="button primary" disabled={loading}>{loading ? "Signing in…" : "Sign in"}<ArrowUpRight size={16} /></button></form></main>;
}

function App() {
  const auth = useAuth();
  if (auth.loading) return <main className="center" role="status"><LoaderCircle className="spin" /> Restoring your session…</main>;
  if (!auth.token) return <Login onLogin={auth.signIn} />;
  return <Assistant onLogout={auth.signOut} />;
}

function Assistant({ onLogout }: { onLogout: () => Promise<void> }) {
  const site = useCurrentTab();
  if (site === undefined) return <main className="center" role="status"><LoaderCircle className="spin" /> Checking this website…</main>;
  return <WebsiteAssistant key={site?.hostname ?? "unsupported"} site={site} onLogout={onLogout} />;
}

function WebsiteAssistant({ site, onLogout }: { site: { url: string; hostname: string } | null; onLogout: () => Promise<void> }) {
  const [company, setCompany] = useState<Company | null>(null); const [latest, setLatest] = useState<CrawlJob | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(""); const [jobId, setJobId] = useState<number | null>(null); const [messages, setMessages] = useState<Message[]>([]); const crawl = useCrawlStatus(company?.id ?? null, jobId); const [question, setQuestion] = useState(""); const [chatLoading, setChatLoading] = useState(false); const chatEnd = useRef<HTMLDivElement>(null);
  const [loadingJobs, setLoadingJobs] = useState(false);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const actionPending = useRef(false);
  const chatRequest = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; chatRequest.current?.abort(); chatRequest.current = null; }; }, []);
  useEffect(() => {
    setCompany(null); setLatest(null); setJobId(null); setMessages([]); setQuestion(""); setError("");
    if (!site) { setLoading(false); return; }
    let active = true; setLoading(true);
    listCompanies().then(all => { if (!active) return; setCompany(all.find(item => companyMatchesSite(item, site)) ?? null); }).catch(e => { if (active) setError(errorMessage(e)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [site?.hostname]);
  useEffect(() => {
    if (!company) return;
    let active = true; setLoadingJobs(true);
    listCrawlJobs(company.id).then(jobs => { if (!active) return; const next = jobs[0] ?? null; setLatest(next); if (next && ["QUEUED", "RUNNING"].includes(next.status)) setJobId(next.job_id); }).catch(e => { if (active) setError(errorMessage(e)); }).finally(() => { if (active) setLoadingJobs(false); });
    return () => { active = false; };
  }, [company]);
  useEffect(() => { if (crawl.job) { setLatest(crawl.job); if (terminal.has(crawl.job.status)) setJobId(null); } }, [crawl.error, crawl.job]);
  useEffect(() => { chatEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, chatLoading]);
  async function addAndCrawl() {
    if (!site || actionPending.current) return;
    actionPending.current = true; setStarting(true); setError("");
    try {
      const target = company ?? await createCompany({ name: site.hostname, website_url: site.url });
      if (!mounted.current) return;
      setCompany(target);
      const job = await startCrawl(target.id);
      if (mounted.current) setJobId(job.job_id);
    } catch (error) { if (mounted.current) setError(errorMessage(error)); }
    finally { actionPending.current = false; if (mounted.current) setStarting(false); }
  }
  async function send(event: FormEvent) {
    event.preventDefault(); const text = question.trim();
    if (!text || !company || chatRequest.current) return;
    const controller = new AbortController();
    chatRequest.current = controller;
    setQuestion(""); setError(""); setMessages(current => [...current, { role: "user", text }]); setChatLoading(true);
    try {
      const answer = await askCompany(company.id, text, controller.signal);
      if (chatRequest.current === controller) setMessages(current => [...current, { role: "assistant", text: answer.answer, sources: uniqueSources(answer.sources) }]);
    } catch (error) {
      if (chatRequest.current !== controller) return;
      if (!isAbortError(error)) { setError(errorMessage(error)); setQuestion(text); }
    } finally {
      if (chatRequest.current === controller) { chatRequest.current = null; setChatLoading(false); }
    }
  }
  function stopAnswer() {
    chatRequest.current?.abort(); chatRequest.current = null; setChatLoading(false);
    const lastQuestion = [...messages].reverse().find(message => message.role === "user")?.text;
    setQuestion(lastQuestion ?? ""); setError("Answer stopped. You can edit your question and try again.");
  }
  async function stop() {
    if (!company || !jobId || cancelling) return;
    setCancelling(true);
    try { await cancelCrawl(company.id, jobId); if (mounted.current) crawl.retry(); }
    catch (error) { if (mounted.current) setError(errorMessage(error)); }
    finally { if (mounted.current) setCancelling(false); }
  }
  const supported = Boolean(site); const ready = Boolean(company && (latest?.status === "COMPLETED" || (latest?.pages_indexed ?? 0) > 0)); const preparing = Boolean(starting || (jobId && (!crawl.job || !terminal.has(crawl.job.status))));
  return <main className="assistant"><header><div className="logo"><span>F</span> fieldnote</div><button className="logout" aria-label="Sign out" onClick={onLogout}><LogOut size={14} /></button></header><div className="site"><div className={`site-icon ${supported ? "live" : ""}`}><Globe2 size={18} /></div><div><div className="label">Current website</div><strong>{site?.hostname ?? "Unsupported page"}</strong></div><div className={`connection ${ready ? "ready" : ""}`}><span />{ready ? "Ready" : preparing ? "Preparing" : supported ? "Not connected" : "Unavailable"}</div></div>{(error || crawl.error) && <div role="alert" className="alert"><CircleAlert size={15} />{error || crawl.error}{crawl.error && <button onClick={crawl.retry}>Retry now</button>}<button aria-label="Dismiss message" onClick={() => setError("")}>×</button></div>}{loading || loadingJobs ? <div className="center" role="status"><LoaderCircle className="spin" size={22} /> Checking this website…</div> : !supported ? <Empty icon={<CircleAlert />} title="This page isn't supported" copy="Open a normal http or https website to use Website AI." /> : company ? <><div className="company-name"><span className="label">Connected company</span><h1>{company.name}</h1></div>{preparing && !crawl.job ? <div className="center" role="status"><LoaderCircle className="spin" /> Preparing this website…</div> : preparing && crawl.job ? <CrawlCard job={crawl.job} onCancel={stop} cancelling={cancelling} /> : !ready ? <PrepareCard job={latest} onStart={addAndCrawl} pending={starting} /> : <Chat messages={messages} question={question} setQuestion={setQuestion} loading={chatLoading} onStop={stopAnswer} onSend={send} endRef={chatEnd} />}</> : <Empty icon={<Sparkles />} title="This website isn't connected yet" copy="Prepare it once, then ask questions grounded in its pages." action={<button className="button primary" disabled={starting} onClick={addAndCrawl}>{starting ? "Starting…" : "Add & crawl"} <ArrowUpRight size={16} /></button>} />}</main>;
}

function Empty({ icon, title, copy, action }: { icon: React.ReactNode; title: string; copy: string; action?: React.ReactNode }) { return <section className="empty"><div className="empty-icon">{icon}</div><h2>{title}</h2><p>{copy}</p>{action}</section>; }
function PrepareCard({ job, onStart, pending }: { job: CrawlJob | null; onStart: () => Promise<void>; pending: boolean }) {
  const ended = job && terminal.has(job.status);
  const message = job?.error || (job?.status === "TIMED_OUT" ? "The last crawl timed out. Try a smaller crawl or try again." : job?.status === "CANCELLED" ? "The last crawl was cancelled. Start again when you're ready." : "We’ll safely crawl its public pages and build a searchable knowledge base.");
  return <section className="prepare"><div className="prepare-icon"><Sparkles size={21} /></div><h2>{ended ? "Ready to try again?" : "Prepare this website for AI chat"}</h2><p>{message}</p><button className="button primary" disabled={pending} onClick={onStart}>{pending ? "Starting…" : ended ? "Try again" : "Start crawl"}<ArrowUpRight size={16} /></button></section>;
}
function CrawlCard({ job, onCancel, cancelling }: { job: CrawlJob; onCancel: () => Promise<void>; cancelling: boolean }) { return <section className="crawl"><div className="crawl-title"><div><div className="label">Website preparation</div><h2>{job.status === "QUEUED" ? "Queued" : "Crawling pages"}</h2></div><span className="pulse"><span />{job.status}</span></div><div className="stats"><Stat label="Discovered" value={job.pages_discovered} /><Stat label="Crawled" value={job.pages_crawled} /><Stat label="Indexed" value={job.pages_indexed} /><Stat label="Failed" value={job.pages_failed} /></div><div className="substats"><span>New {job.pages_new}</span><span>Changed {job.pages_changed}</span><span>Unchanged {job.pages_unchanged}</span><span>Deactivated {job.pages_deactivated}</span></div><button className="cancel" disabled={cancelling} onClick={onCancel}><Square size={13} />{cancelling ? "Cancelling…" : "Cancel crawl"}</button></section>; }
function Stat({ label, value }: { label: string; value: number }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function FormattedAnswer({ text }: { text: string }) { return <div className="formatted-answer">{text.split(/\n{2,}/).map((block, index) => { const lines = block.split("\n"); const bullets = lines.filter(line => /^\s*[-*]\s+/.test(line)); return bullets.length === lines.length && bullets.length > 0 ? <ul key={index}>{bullets.map((line, bulletIndex) => <li key={bulletIndex}>{line.replace(/^\s*[-*]\s+/, "")}</li>)}</ul> : <p key={index}>{block}</p>; })}</div>; }
function Chat({ messages, question, setQuestion, loading, onStop, onSend, endRef }: { messages: Message[]; question: string; setQuestion: (value: string) => void; loading: boolean; onStop: () => void; onSend: (event: FormEvent) => Promise<void>; endRef: React.RefObject<HTMLDivElement> }) { const suggestions = ["What does this company do?", "What products or services do they offer?", "Who founded this company?", "Summarize this website."]; return <section className="chat"><div className="chat-intro"><MessageCircle size={18} /><div><div className="label">Company knowledge</div><h2>Ask anything about this website.</h2></div></div><div className="messages">{messages.length === 0 && <div className="suggestions">{suggestions.map(suggestion => <button key={suggestion} className="suggestion" onClick={() => setQuestion(suggestion)}>{suggestion}<ArrowUpRight size={13} /></button>)}</div>}{messages.map((message, index) => <div className={`message ${message.role}`} key={`${message.role}-${index}`}><div className="message-mark">{message.role === "assistant" ? <Bot size={14} /> : "You"}</div><div className="message-body">{message.role === "assistant" ? <FormattedAnswer text={message.text} /> : <p>{message.text}</p>}{message.sources && message.sources.length > 0 && <div className="source-list"><div className="source-label">Sources</div>{message.sources.map(source => <a className="source" href={source.url} target="_blank" rel="noreferrer" key={source.url}><Globe2 size={12} /><span>{source.title || source.url}</span><ArrowUpRight size={12} /></a>)}</div>}</div></div>)}{loading && <div className="message assistant"><div className="message-mark"><Bot size={14} /></div><div className="thinking" role="status" aria-label="Preparing your answer"><span /><span /><span /></div><button type="button" className="cancel" onClick={onStop}>Stop</button></div>}<div ref={endRef} /></div><form className="composer" onSubmit={onSend}><textarea aria-label="Question" value={question} onChange={e => setQuestion(e.target.value.slice(0, 2000))} maxLength={2000} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} placeholder="Ask a question…" rows={2} disabled={loading} /><button disabled={!question.trim() || loading} aria-label="Send"><Send size={16} /></button></form><div className="chat-note">Answers are grounded in indexed website content.</div></section>; }
export default App;
