import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowUpRight, Bot, Search, Send, Sparkles } from "lucide-react";
import { api, isAbortError } from "../api";
import type { ChatResponse, Company } from "../types";

export function ChatPanel({ company }: { company: Company }) {
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => () => { request.current?.abort(); request.current = null; }, []);
  useEffect(() => {
    if (!loading) { setSlow(false); return; }
    const timer = window.setTimeout(() => setSlow(true), 8000);
    return () => window.clearTimeout(timer);
  }, [loading]);

  async function ask(text: string) {
    const cleaned = text.trim();
    if (!cleaned || request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setAsked(cleaned); setLoading(true); setError(""); setResponse(null);
    try {
      const result = await api.chat(company.id, cleaned, controller.signal);
      if (request.current !== controller) return;
      setResponse(result); setQuestion("");
    } catch (error) {
      if (request.current !== controller) return;
      if (!isAbortError(error)) setError(error instanceof Error ? error.message : "Unable to get an answer. Please try again.");
    } finally {
      if (request.current === controller) {
        request.current = null;
        setLoading(false);
        input.current?.focus();
      }
    }
  }
  function stop() {
    request.current?.abort(); request.current = null;
    setLoading(false); setQuestion(asked); setError("Answer stopped. You can edit your question and try again.");
    input.current?.focus();
  }
  function submit(event: FormEvent) { event.preventDefault(); void ask(question); }

  return <section className="panel chat-panel" aria-label="Company chat" aria-busy={loading}>
    <div className="panel-heading"><div><div className="eyebrow">Ask the knowledge base</div><h2>Company chat</h2></div><Bot size={22} /></div>
    {asked && <div className="asked-question"><span className="eyebrow">Your question</span><p>{asked}</p></div>}
    {loading ? <div className="answer-progress" role="status"><span className="spinner" /><span>{slow ? "Still working on your answer. You can stop and try again." : "Finding relevant pages and preparing your answer…"}</span><button type="button" className="text-button" onClick={stop}>Stop</button></div> : response ?
      <div className="answer" aria-live="polite"><div className="answer-mark">AI</div><p className="answer-text">{response.answer}</p>
        {response.sources.length > 0 && <div className="sources"><div className="eyebrow">Sources</div>{response.sources.filter(source => /^https?:\/\//i.test(source.url)).map((source, index) => <a href={source.url} target="_blank" rel="noreferrer" key={source.url + index}><Search size={14} /><span>{source.title || source.url}</span><ArrowUpRight size={14} /></a>)}</div>}
      </div> : !asked && <><div className="chat-empty"><Sparkles size={20} /><p>Ask about the company, its products, or anything in the crawled site.</p></div><div className="question-suggestions">{["What does this company do?", "What products do they offer?"].map(text => <button type="button" key={text} onClick={() => { setQuestion(text); input.current?.focus(); }}>{text}</button>)}</div></>}
    {error && <div role="alert" className="alert error">{error} <button type="button" className="text-button" onClick={() => void ask(asked)}>Try again</button></div>}
    <form className="chat-input" onSubmit={submit}><input ref={input} aria-label="Question" value={question} onChange={event => setQuestion(event.target.value)} placeholder="What would you like to know?" readOnly={loading} maxLength={2000} /><button aria-label="Send question" disabled={loading || !question.trim()}><Send size={17} /></button></form>
  </section>;
}
