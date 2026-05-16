"""
Session viewer UI — served at http://localhost:8000/ui
Provides REST endpoints for the session browser.

The UI supports two source modes:
  1. Default: live proxy sessions in `logs/sessions/`
  2. Run-scoped: A/B test sessions in `runs/<run_id>/sessions/`
     Pass `?source=<run_id>` query param (e.g. `?source=run_20260515_223741`)
"""
import json
import os
from pathlib import Path
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
DEFAULT_SESSIONS_DIR = LOG_DIR / "sessions"
RUNS_DIR = Path("runs")  # A/B test artifact root


def _resolve_sessions_dir(source: str | None) -> Path:
    """
    Resolve which sessions directory to read from based on `source` query.
    
    - source=None or "live": default proxy sessions dir
    - source="<run_id>": runs/<run_id>/sessions
    - source="logs": legacy/raw logs/sessions
    """
    if not source or source == "live" or source == "logs":
        return DEFAULT_SESSIONS_DIR
    # Look up the run dir under runs/
    candidate = RUNS_DIR / source / "sessions"
    if candidate.exists():
        return candidate
    return DEFAULT_SESSIONS_DIR


@router.get("/runs")
async def list_runs():
    """List all available A/B test runs (folders under runs/)."""
    if not RUNS_DIR.exists():
        return JSONResponse([])
    runs = []
    for d in sorted(RUNS_DIR.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        sessions_dir = d / "sessions"
        report_file = d / "report.json"
        session_count = len(list(sessions_dir.glob("session_*.jsonl"))) if sessions_dir.exists() else 0
        runs.append({
            "id": d.name,
            "session_count": session_count,
            "has_report": report_file.exists(),
            "mtime": d.stat().st_mtime,
        })
    return JSONResponse(runs)


@router.get("/sessions")
async def list_sessions(source: str | None = Query(None)):
    sessions_dir = _resolve_sessions_dir(source)
    if not sessions_dir.exists():
        return JSONResponse([])
    sessions = []
    for f in sorted(sessions_dir.glob("session_*.jsonl"), key=lambda p: p.stat().st_mtime):
        turns = []
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    turns.append(json.loads(line))
                except Exception:
                    pass
        if not turns:
            continue
        sessions.append({
            "id": f.stem.replace("session_", ""),
            "file": f.name,
            "turns": len(turns),
            "model": turns[-1].get("model", "?"),
            "total_tokens": sum(t.get("estimated_tokens", 0) for t in turns),
            "start_time": turns[0].get("timestamp", ""),
            "end_time": turns[-1].get("timestamp", ""),
        })
    return JSONResponse(sessions)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, source: str | None = Query(None)):
    sessions_dir = _resolve_sessions_dir(source)
    path = sessions_dir / f"session_{session_id}.jsonl"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    turns = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                turns.append(json.loads(line))
            except Exception:
                pass
    return JSONResponse(turns)


@router.get("/ui", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(HTML)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Context Optimizer — Session Viewer</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  a { color: inherit; text-decoration: none; }

  /* Layout */
  #app { display: flex; height: 100vh; overflow: hidden; }
  #sidebar { width: 280px; flex-shrink: 0; background: #161b26; border-right: 1px solid #2d3748;
             overflow-y: auto; display: flex; flex-direction: column; }
  #main { flex: 1; overflow-y: auto; padding: 24px; }

  /* Sidebar */
  .sidebar-header { padding: 16px; border-bottom: 1px solid #2d3748; }
  .sidebar-header h1 { font-size: 14px; font-weight: 600; color: #a0aec0; letter-spacing: .05em; text-transform: uppercase; }
  .source-select { width: 100%; margin-top: 10px; padding: 6px 8px; background: #0f1117;
                    border: 1px solid #2d3748; border-radius: 6px; color: #e2e8f0; font-size: 12px; }
  .source-select:focus { outline: none; border-color: #4299e1; }
  .session-item { padding: 12px 16px; cursor: pointer; border-bottom: 1px solid #1e2533; transition: background .1s; }
  .session-item:hover { background: #1e2a3a; }
  .session-item.active { background: #1e3a5f; border-left: 3px solid #4299e1; }
  .session-item .sid { font-size: 12px; font-family: monospace; color: #718096; }
  .session-item .meta { font-size: 11px; color: #4a5568; margin-top: 2px; }
  .session-item .model-tag { display: inline-block; font-size: 10px; padding: 1px 6px;
    background: #2d3748; border-radius: 4px; color: #90cdf4; margin-top: 4px; }

  /* Turn list */
  .turns-header { margin-bottom: 16px; }
  .turns-header h2 { font-size: 20px; font-weight: 600; }
  .turns-header .subtext { font-size: 13px; color: #718096; margin-top: 4px; }
  .stats-row { display: flex; gap: 16px; margin: 12px 0 20px; flex-wrap: wrap; }
  .stat-box { background: #161b26; border: 1px solid #2d3748; border-radius: 8px;
              padding: 10px 16px; min-width: 110px; }
  .stat-box .val { font-size: 22px; font-weight: 700; }
  .stat-box .lbl { font-size: 11px; color: #718096; margin-top: 2px; text-transform: uppercase; letter-spacing: .04em; }

  /* Turn rows */
  .turn-row { border: 1px solid #2d3748; border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
  .turn-header { display: flex; align-items: center; gap: 12px; padding: 10px 14px;
                 cursor: pointer; background: #161b26; transition: background .1s; }
  .turn-header:hover { background: #1a2235; }
  .turn-num { font-size: 12px; font-family: monospace; color: #4a5568; width: 36px; flex-shrink: 0; }
  .turn-summary { flex: 1; font-size: 13px; color: #e2e8f0; white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; }
  .turn-tokens { font-size: 12px; color: #718096; flex-shrink: 0; }
  .turn-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; flex-shrink: 0; }
  .badge-error { background: #742a2a; color: #fc8181; }
  .badge-ok { background: #1a3a2a; color: #68d391; }
  .caret { font-size: 11px; color: #4a5568; flex-shrink: 0; transition: transform .15s; }
  .caret.open { transform: rotate(90deg); }

  /* Turn body */
  .turn-body { padding: 12px 14px; background: #0f1117; display: none; border-top: 1px solid #2d3748; }
  .turn-body.open { display: block; }

  /* Messages */
  .msg-block { margin-bottom: 12px; }
  .role-label { display: inline-block; font-size: 10px; padding: 2px 7px; border-radius: 4px;
                font-weight: 600; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
  .role-user    { background: #1e3a5f; color: #90cdf4; }
  .role-assistant { background: #1a3a2a; color: #68d391; }
  .role-tool    { background: #44337a; color: #d6bcfa; }
  .role-system  { background: #2d3748; color: #a0aec0; }

  .part-row { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 5px; padding-left: 8px;
              border-left: 2px solid #2d3748; }
  .part-tag { font-size: 10px; padding: 1px 5px; border-radius: 3px; flex-shrink: 0; margin-top: 2px; }
  .tag-text   { background: #2d3748; color: #a0aec0; }
  .tag-call   { background: #1e3a5f; color: #90cdf4; }
  .tag-result { background: #44337a; color: #d6bcfa; }
  .part-content { font-size: 12px; font-family: 'SF Mono', 'Fira Code', monospace;
                  color: #cbd5e0; white-space: pre-wrap; word-break: break-word; line-height: 1.6; }
  .part-content.expanded { max-height: none; }
  .expand-btn { font-size: 11px; color: #4299e1; cursor: pointer; margin-top: 4px;
                background: none; border: none; padding: 0; display: block; }
  .expand-btn:hover { text-decoration: underline; }

  /* Divider */
  hr { border: none; border-top: 1px solid #2d3748; margin: 8px 0; }

  /* Empty state */
  .empty { color: #4a5568; text-align: center; padding: 60px 20px; font-size: 14px; }
  .loading { color: #4a5568; padding: 24px; font-size: 13px; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div class="sidebar-header">
      <h1>Sessions</h1>
      <select id="source-select" class="source-select" onchange="onSourceChange()">
        <option value="live">Live proxy (logs/sessions)</option>
      </select>
    </div>
    <div id="session-list"><div class="loading">Loading...</div></div>
  </div>
  <div id="main">
    <div class="empty">Select a session from the sidebar</div>
  </div>
</div>

<script>
const BASE = window.location.origin;
let activeSid = null;
let currentSource = 'live';

async function loadRuns() {
  // Populate the source dropdown with available A/B test runs
  try {
    const res = await fetch(`${BASE}/runs`);
    const runs = await res.json();
    const sel = document.getElementById('source-select');
    // Keep the default "live" option, then append runs
    const liveOpt = sel.options[0];
    sel.innerHTML = '';
    sel.appendChild(liveOpt);
    runs.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.id;
      opt.textContent = `${r.id} (${r.session_count} sessions)`;
      sel.appendChild(opt);
    });
    sel.value = currentSource;
  } catch (e) {
    console.warn('Failed to load runs', e);
  }
}

function onSourceChange() {
  const sel = document.getElementById('source-select');
  currentSource = sel.value;
  activeSid = null;
  document.getElementById('main').innerHTML = '<div class="empty">Select a session from the sidebar</div>';
  loadSessions();
}

function sourceQuery() {
  return currentSource && currentSource !== 'live' ? `?source=${encodeURIComponent(currentSource)}` : '';
}

async function loadSessions() {
  const res = await fetch(`${BASE}/sessions${sourceQuery()}`);
  const sessions = await res.json();
  const list = document.getElementById('session-list');
  if (!sessions.length) { list.innerHTML = '<div class="loading">No sessions yet.</div>'; return; }
  list.innerHTML = sessions.map(s => `
    <div class="session-item" onclick="loadSession('${s.id}')" id="sid-${s.id}">
      <div class="sid">${s.id}</div>
      <div style="font-size:13px;margin-top:2px;">${s.turns} turns &nbsp;·&nbsp; ${s.total_tokens.toLocaleString()} tok</div>
      <div class="meta">${s.start_time.slice(11,19)} → ${s.end_time.slice(11,19)} UTC</div>
      <div class="model-tag">${s.model.split('/').pop()}</div>
    </div>`).join('');
}

async function loadSession(sid) {
  if (activeSid) document.getElementById('sid-'+activeSid)?.classList.remove('active');
  activeSid = sid;
  document.getElementById('sid-'+sid)?.classList.add('active');
  const main = document.getElementById('main');
  main.innerHTML = '<div class="loading">Loading session...</div>';
  const res = await fetch(`${BASE}/sessions/${sid}${sourceQuery()}`);
  const turns = await res.json();
  renderSession(sid, turns, main);
}

function renderSession(sid, turns, container) {
  const totalTok = turns.reduce((acc, t) => acc + (t.estimated_tokens || 0), 0);
  const models = [...new Set(turns.map(t => t.model.split('/').pop()))];
  const errorCount = turns.filter(t => hasError(t)).length;

  // Get system prompt and tools from first turn
  const firstTurn = turns[0] || {};
  const hasSystem = !!firstTurn.system;
  const hasTools = firstTurn.tools && firstTurn.tools.length > 0;

  container.innerHTML = `
    <div class="turns-header">
      <h2>Session ${sid}</h2>
      <div class="subtext">${models.join(' → ')}</div>
    </div>
    <div class="stats-row">
      <div class="stat-box"><div class="val">${turns.length}</div><div class="lbl">Turns</div></div>
      <div class="stat-box"><div class="val">${totalTok.toLocaleString()}</div><div class="lbl">Total tokens</div></div>
      <div class="stat-box"><div class="val">${errorCount}</div><div class="lbl">Error turns</div></div>
      ${hasSystem ? '<div class="stat-box"><div class="val">✓</div><div class="lbl">System Prompt</div></div>' : ''}
      ${hasTools ? `<div class="stat-box"><div class="val">${firstTurn.tools.length}</div><div class="lbl">Tools</div></div>` : ''}
    </div>
    ${hasSystem || hasTools ? renderSystemAndTools(firstTurn) : ''}
    <div id="turn-list"></div>`;

  const tl = document.getElementById('turn-list');
  turns.forEach((turn, i) => {
    const prev = i > 0 ? turns[i-1] : null;
    const prevCount = prev ? prev.message_count : 0;
    const newMsgs = (turn.messages || []).slice(prevCount);
    const summary = getTurnSummary(newMsgs, turn);
    const err = hasError(turn);
    const domId = `turn-${sid}-${turn.turn}`;

    const div = document.createElement('div');
    div.className = 'turn-row';
    div.innerHTML = `
      <div class="turn-header" onclick="toggleTurn('${domId}')">
        <span class="turn-num">T${turn.turn}</span>
        <span class="turn-summary">${escHtml(summary)}</span>
        <span class="turn-tokens">${(turn.estimated_tokens||0).toLocaleString()} tok</span>
        <span class="turn-badge ${err ? 'badge-error' : 'badge-ok'}">${err ? 'error' : 'ok'}</span>
        <span class="caret" id="caret-${domId}">&#9658;</span>
      </div>
      <div class="turn-body" id="body-${domId}">${renderMessages(newMsgs)}</div>`;
    tl.appendChild(div);
  });
}

function renderSystemAndTools(turn) {
  const parts = [];
  
  if (turn.system) {
    parts.push(`
      <div class="turn-row" style="margin-bottom: 16px;">
        <div class="turn-header" onclick="toggleTurn('system-prompt')" style="background: #1a2433;">
          <span class="turn-num">📋</span>
          <span class="turn-summary">System Prompt</span>
          <span class="caret" id="caret-system-prompt">&#9658;</span>
        </div>
        <div class="turn-body" id="body-system-prompt">
          <div class="msg-block">
            <div class="role-label role-system">system</div>
            <div class="part-row">
              <span class="part-tag tag-text">prompt</span>
              <div style="min-width:0;flex:1">
                <div class="part-content">${escHtml(turn.system)}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `);
  }
  
  if (turn.tools && turn.tools.length > 0) {
    const toolsList = turn.tools.map((t, i) => {
      const fn = t.function || t;
      const name = fn.name || '?';
      const desc = fn.description || '';
      const uid = 'tool-' + Math.random().toString(36).slice(2);
      const short = desc.slice(0, 80);
      const long = desc.length > 80;
      FULL_TEXTS[uid] = desc;
      return `
        <div class="part-row" style="margin-bottom: 8px;">
          <span class="part-tag" style="background: #1e3a5f; color: #90cdf4;">${name}</span>
          <div style="min-width:0;flex:1">
            <div class="part-content" id="${uid}" style="font-size: 11px; color: #a0aec0;">${escHtml(short)}${long ? '…' : ''}</div>
            ${long ? `<button class="expand-btn" onclick="expandPart('${uid}')">Show full description</button>` : ''}
          </div>
        </div>
      `;
    }).join('');
    
    parts.push(`
      <div class="turn-row" style="margin-bottom: 16px;">
        <div class="turn-header" onclick="toggleTurn('tools-list')" style="background: #1a2433;">
          <span class="turn-num">🔧</span>
          <span class="turn-summary">${turn.tools.length} Available Tools</span>
          <span class="caret" id="caret-tools-list">&#9658;</span>
        </div>
        <div class="turn-body" id="body-tools-list">
          <div class="msg-block">
            ${toolsList}
          </div>
        </div>
      </div>
    `);
  }
  
  return parts.join('');
}

function toggleTurn(id) {
  const body = document.getElementById('body-'+id);
  const caret = document.getElementById('caret-'+id);
  body.classList.toggle('open');
  caret.classList.toggle('open');
}

function hasError(turn) {
  return (turn.messages||[]).some(m => {
    const c = m.content;
    const text = typeof c === 'string' ? c :
      (Array.isArray(c) ? c.map(p => p.text||p.content||'').join(' ') : '');
    return /error|Error|ERROR/.test(text) && !/No.*error|0 error|no linter/i.test(text);
  });
}

function getTurnSummary(newMsgs, turn) {
  // Find last user message with user_query
  for (let i = newMsgs.length - 1; i >= 0; i--) {
    const m = newMsgs[i];
    if (m.role !== 'user') continue;
    const text = contentText(m.content);
    const match = text.match(/<user_query>([\s\S]*?)<\/user_query>/);
    if (match) return match[1].trim().slice(0, 100);
  }
  // Fall back to assistant text
  for (const m of newMsgs) {
    if (m.role === 'assistant') {
      const t = contentText(m.content).trim();
      if (t) return t.slice(0, 100);
    }
  }
  // Fall back to tool outputs
  for (const m of newMsgs) {
    if (m.role === 'tool') {
      const t = contentText(m.content).trim();
      if (t) return t.slice(0, 80);
    }
  }
  return `${turn.message_count} messages`;
}

function contentText(content) {
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(p => p.text || p.content || '').join(' ');
  return String(content);
}

function renderMessages(msgs) {
  if (!msgs.length) return '<div style="color:#4a5568;font-size:12px;">No new messages</div>';
  return msgs.map(m => renderMessage(m)).join('');
}

function renderMessage(m) {
  const role = m.role || 'unknown';
  const parts = buildParts(m);
  if (!parts.length) return '';
  return `<div class="msg-block">
    <div class="role-label role-${role}">${role}</div>
    ${parts.map(p => renderPart(p)).join('')}
  </div>`;
}

function buildParts(m) {
  const content = m.content;
  const parts = [];
  if (Array.isArray(content)) {
    for (const p of content) {
      if (p.type === 'text') parts.push({ tag: 'text', text: p.text || '' });
      else if (p.type === 'tool_use') parts.push({ tag: 'call', text: `${p.name}(${JSON.stringify(p.input||{}).slice(0,200)})` });
      else if (p.type === 'tool_result') {
        const c = Array.isArray(p.content) ? p.content.map(x=>x.text||'').join('\n') : (p.content||'');
        parts.push({ tag: 'result', text: c });
      }
    }
  } else if (typeof content === 'string') {
    // Strip system boilerplate
    let text = content;
    const qm = text.match(/<user_query>([\s\S]*?)<\/user_query>/);
    if (qm) text = qm[1].trim();
    else text = text.replace(/<[^>]+>/g, ' ').trim().slice(0, 2000);
    if (text) parts.push({ tag: 'text', text });
  }
  // OpenAI tool_calls on assistant message
  if (m.tool_calls) {
    for (const tc of m.tool_calls) {
      const fn = tc.function || {};
      parts.push({ tag: 'call', text: `${fn.name}(${(fn.arguments||'').slice(0,200)})` });
    }
  }
  return parts;
}

// Global store for full text — keyed by uid, avoids any HTML/attribute escaping issues
const FULL_TEXTS = {};

function renderPart(p) {
  const uid = 'pc-' + Math.random().toString(36).slice(2);
  const short = p.text.slice(0, 600);
  const long = p.text.length > 600;
  if (long) FULL_TEXTS[uid] = p.text;
  return `<div class="part-row">
    <span class="part-tag tag-${p.tag}">${p.tag}</span>
    <div style="min-width:0;flex:1">
      <div class="part-content" id="${uid}">${escHtml(short)}${long ? '…' : ''}</div>
      ${long ? `<button class="expand-btn" onclick="expandPart('${uid}')">Show all (${p.text.length} chars)</button>` : ''}
    </div>
  </div>`;
}

function expandPart(uid) {
  const el = document.getElementById(uid);
  const full = FULL_TEXTS[uid];
  if (!el || !full) return;
  el.textContent = full;
  const btn = el.nextElementSibling;
  if (btn) btn.remove();
  delete FULL_TEXTS[uid];
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

loadRuns().then(loadSessions);
setInterval(() => { loadRuns(); loadSessions(); }, 30000);
</script>
</body>
</html>"""
