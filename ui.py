"""
Session viewer UI with hierarchical folder navigation.
Clean breadcrumb-based browser for logs/ and runs/ hierarchies.
"""
import json
import os
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
DEFAULT_SESSIONS_DIR = LOG_DIR / "sessions"
RUNS_DIR = Path("runs")


@router.get("/browse")
async def browse_folders(path: str = ""):
    """
    Browse folder hierarchy.
    Returns folders and sessions at current path.
    """
    if not path:
        # Root level: show logs/ and runs/
        items = []
        if DEFAULT_SESSIONS_DIR.parent.exists():
            items.append({"type": "folder", "name": "logs", "path": "logs"})
        if RUNS_DIR.exists():
            items.append({"type": "folder", "name": "runs", "path": "runs"})
        return JSONResponse({"folders": items, "sessions": [], "files": []})
    
    parts = path.split("/")
    
    if parts[0] == "logs":
        if len(parts) == 1:
            # Show date folders under logs/sessions/
            folders = []
            if DEFAULT_SESSIONS_DIR.exists():
                for d in sorted(DEFAULT_SESSIONS_DIR.iterdir(), reverse=True):
                    if d.is_dir():
                        folders.append({"type": "folder", "name": d.name, "path": f"logs/{d.name}"})
            return JSONResponse({"folders": folders, "sessions": [], "files": []})
        else:
            # Show sessions for date
            date_dir = DEFAULT_SESSIONS_DIR / parts[1]
            return _list_sessions_in_dir(date_dir)
    
    elif parts[0] == "runs":
        if len(parts) == 1:
            # Show date folders under runs/<YYYY-MM-DD>/
            folders = []
            if RUNS_DIR.exists():
                date_names: set[str] = set()
                # Preferred layout: runs/<date>/<cache_mode>/<run_name>/
                for date_dir in RUNS_DIR.iterdir():
                    if date_dir.is_dir() and date_dir.name[:4].isdigit():
                        date_names.add(date_dir.name)
                # Backward compatibility: runs/<cache_mode>/<date>/<run_name>/
                for cache_dir in RUNS_DIR.iterdir():
                    if not cache_dir.is_dir():
                        continue
                    for maybe_date in cache_dir.iterdir():
                        if maybe_date.is_dir() and maybe_date.name[:4].isdigit():
                            date_names.add(maybe_date.name)
                for date_name in sorted(date_names, reverse=True):
                    folders.append({"type": "folder", "name": date_name, "path": f"runs/{date_name}"})
            return JSONResponse({"folders": folders, "sessions": [], "files": []})
        elif len(parts) == 2:
            # Show cache_mode folders for selected date
            folders = []
            run_date = parts[1]
            date_dir = RUNS_DIR / run_date
            seen_cache_modes: set[str] = set()
            if date_dir.exists():
                for cache_dir in sorted(date_dir.iterdir()):
                    if cache_dir.is_dir():
                        seen_cache_modes.add(cache_dir.name)
                        folders.append({"type": "folder", "name": cache_dir.name, "path": f"{path}/{cache_dir.name}"})
            # Backward compatibility with old layout
            for cache_dir in sorted(RUNS_DIR.iterdir()):
                if not cache_dir.is_dir() or cache_dir.name in seen_cache_modes:
                    continue
                legacy_date_dir = cache_dir / run_date
                if legacy_date_dir.is_dir():
                    folders.append({"type": "folder", "name": cache_dir.name, "path": f"{path}/{cache_dir.name}"})
            return JSONResponse({"folders": folders, "sessions": [], "files": []})
        elif len(parts) == 3:
            # Show run folders
            folders = []
            run_date = parts[1]
            cache_mode = parts[2]
            cache_dir = RUNS_DIR / run_date / cache_mode
            if not cache_dir.exists():
                # Backward compatibility: runs/<cache_mode>/<date>/
                cache_dir = RUNS_DIR / cache_mode / run_date
            if cache_dir.exists():
                for d in sorted(cache_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
                    if d.is_dir():
                        folders.append({"type": "folder", "name": d.name, "path": f"{path}/{d.name}"})
            return JSONResponse({"folders": folders, "sessions": [], "files": []})
        elif len(parts) == 4:
            # Show sessions plus run-level folders/files for a specific run
            run_date = parts[1]
            cache_mode = parts[2]
            run_name = parts[3]
            run_root_dir = _resolve_run_root(run_date, cache_mode, run_name)

            sessions_dir = run_root_dir / "sessions"
            sessions_payload = _list_sessions_in_dir(sessions_dir, artifacts_dir=run_root_dir)
            payload = json.loads(sessions_payload.body.decode("utf-8"))

            # Also expose run subfolders like virtual_fs/ and scenarios/
            extra_folders = []
            if run_root_dir.exists():
                for item in sorted(run_root_dir.iterdir(), key=lambda p: p.name.lower()):
                    if item.is_dir() and item.name != "sessions":
                        extra_folders.append(
                            {
                                "type": "folder",
                                "name": item.name,
                                "path": f"runs/{run_date}/{cache_mode}/{run_name}/{item.name}",
                            }
                        )
            payload["folders"] = extra_folders + payload.get("folders", [])
            return JSONResponse(payload)
        else:
            # Browse arbitrary sub-path inside selected run (e.g. virtual_fs/)
            run_date = parts[1]
            cache_mode = parts[2]
            run_name = parts[3]
            run_root_dir = _resolve_run_root(run_date, cache_mode, run_name)
            sub_path = "/".join(parts[4:])
            target_dir = run_root_dir / sub_path
            base_ui_path = f"runs/{run_date}/{cache_mode}/{run_name}/{sub_path}"
            return _list_directory_items(target_dir, base_ui_path)
    
    return JSONResponse({"folders": [], "sessions": [], "files": []})


def _list_sessions_in_dir(sessions_dir: Path, artifacts_dir: Path | None = None):
    """List all sessions in a directory."""
    files = []
    if artifacts_dir and artifacts_dir.exists():
        for artifact in sorted(artifacts_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not artifact.is_file():
                continue
            if artifact.name.startswith("session_") and artifact.suffix == ".jsonl":
                continue
            rel_path = artifact.as_posix().lstrip("./")
            files.append(
                {
                    "name": artifact.name,
                    "path": rel_path,
                    "type": artifact.suffix.lstrip(".") or "file",
                }
            )

    if not sessions_dir.exists():
        return JSONResponse({"folders": [], "sessions": [], "files": files})
    
    sessions = []
    for f in sorted(sessions_dir.rglob("session_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        turns = []
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        turns.append(json.loads(line))
                    except Exception:
                        pass
        except Exception:
            continue
        
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
    
    return JSONResponse({"folders": [], "sessions": sessions, "files": files})


def _resolve_run_root(run_date: str, cache_mode: str, run_name: str) -> Path:
    """Resolve run root supporting both new and legacy run layouts."""
    run_root = RUNS_DIR / run_date / cache_mode / run_name
    if run_root.exists():
        return run_root
    legacy = RUNS_DIR / cache_mode / run_date / run_name
    return legacy


def _list_directory_items(target_dir: Path, base_ui_path: str):
    """List folders/files for arbitrary directory browsing under runs/."""
    if not target_dir.exists() or not target_dir.is_dir():
        return JSONResponse({"folders": [], "sessions": [], "files": []})

    folders = []
    files = []
    for item in sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if item.is_dir():
            folders.append({"type": "folder", "name": item.name, "path": f"{base_ui_path}/{item.name}"})
        elif item.is_file():
            files.append(
                {
                    "name": item.name,
                    "path": item.as_posix().lstrip("./"),
                    "type": item.suffix.lstrip(".") or "file",
                }
            )
    return JSONResponse({"folders": folders, "sessions": [], "files": files})


@router.get("/artifact")
async def get_artifact(path: str):
    """Read an artifact under runs/ for UI preview."""
    normalized = os.path.normpath(path).replace("\\", "/")
    if normalized.startswith("../") or normalized.startswith("/"):
        return JSONResponse({"error": "invalid path"}, status_code=400)

    artifact_path = Path(normalized)
    if not artifact_path.exists() or not artifact_path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)

    runs_root = RUNS_DIR.resolve()
    resolved = artifact_path.resolve()
    if runs_root not in resolved.parents:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    size = artifact_path.stat().st_size
    if size > 1_000_000:
        return JSONResponse({"error": "file too large to preview"}, status_code=413)

    content = artifact_path.read_text(encoding="utf-8", errors="replace")
    return JSONResponse(
        {
            "path": normalized,
            "content": content,
            "extension": artifact_path.suffix.lower(),
            "size": size,
        }
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get session details by ID (searches recursively)."""
    # Search in logs/sessions/ recursively
    target_file = f"session_{session_id}.jsonl"
    
    search_dirs = []
    if DEFAULT_SESSIONS_DIR.exists():
        search_dirs.append(DEFAULT_SESSIONS_DIR)
    if RUNS_DIR.exists():
        search_dirs.append(RUNS_DIR)
    
    for base_dir in search_dirs:
        found_paths = list(base_dir.rglob(target_file))
        if found_paths:
            path = found_paths[0]
            turns = []
            with open(path, encoding="utf-8") as f:
                for line in f:
                    try:
                        turns.append(json.loads(line))
                    except Exception:
                        pass
            return JSONResponse(turns)
    
    return JSONResponse({"error": "not found"}, status_code=404)


@router.get("/ui", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(HTML)


HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Context Optimizer — Session Browser</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  
  #app { display: flex; height: 100vh; }
  #sidebar { width: 320px; background: #161b26; border-right: 1px solid #2d3748; 
             display: flex; flex-direction: column; overflow: hidden; }
  #main { flex: 1; overflow-y: auto; padding: 24px; }

  /* Breadcrumb navigation */
  .breadcrumb { padding: 16px; border-bottom: 1px solid #2d3748; background: #1a1f2e; }
  .breadcrumb-title { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; 
                      color: #718096; margin-bottom: 8px; }
  .breadcrumb-path { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .breadcrumb-item { font-size: 13px; color: #4299e1; cursor: pointer; padding: 4px 8px;
                     border-radius: 4px; transition: background 0.1s; }
  .breadcrumb-item:hover { background: #1e3a5f; }
  .breadcrumb-item.current { color: #e2e8f0; cursor: default; }
  .breadcrumb-item.current:hover { background: transparent; }
  .breadcrumb-sep { color: #4a5568; font-size: 12px; }

  /* Browser list */
  .browser-list { flex: 1; overflow-y: auto; }
  .folder-item, .session-item, .file-item { padding: 12px 16px; cursor: pointer; 
                                 border-bottom: 1px solid #1e2533; transition: background 0.1s;
                                 display: flex; align-items: center; gap: 12px; }
  .folder-item:hover, .session-item:hover, .file-item:hover { background: #1e2a3a; }
  .session-item.active, .file-item.active { background: #1e3a5f; border-left: 3px solid #4299e1; }
  .folder-icon, .session-icon, .file-icon { font-size: 16px; flex-shrink: 0; }
  .folder-icon { color: #90cdf4; }
  .session-icon { color: #68d391; }
  .file-icon { color: #f6ad55; }
  .item-content { flex: 1; min-width: 0; }
  .item-name { font-size: 13px; font-family: monospace; white-space: nowrap;
               overflow: hidden; text-overflow: ellipsis; }
  .item-meta { font-size: 11px; color: #718096; margin-top: 2px; }

  .empty { color: #4a5568; text-align: center; padding: 40px 20px; font-size: 13px; }

  /* Turn display */
  .turns-header { margin-bottom: 16px; }
  .turns-header h2 { font-size: 20px; font-weight: 600; }
  .turns-header .subtext { font-size: 13px; color: #718096; margin-top: 4px; }
  .stats-row { display: flex; gap: 16px; margin: 12px 0 20px; flex-wrap: wrap; }
  .stat-box { background: #161b26; border: 1px solid #2d3748; border-radius: 8px;
              padding: 10px 16px; min-width: 110px; }
  .stat-box .val { font-size: 22px; font-weight: 700; }
  .stat-box .lbl { font-size: 11px; color: #718096; margin-top: 2px; 
                   text-transform: uppercase; letter-spacing: .04em; }

  .turn-row { border: 1px solid #2d3748; border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
  .turn-header { display: flex; align-items: center; gap: 12px; padding: 10px 14px;
                 cursor: pointer; background: #161b26; transition: background .1s; }
  .turn-header:hover { background: #1a2235; }
  .turn-num { font-size: 12px; font-family: monospace; color: #4a5568; width: 36px; }
  .turn-summary { flex: 1; font-size: 13px; white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; }
  .turn-tokens { font-size: 12px; color: #718096; }
  .turn-badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; }
  .badge-error { background: #742a2a; color: #fc8181; }
  .badge-ok { background: #1a3a2a; color: #68d391; }
  .caret { font-size: 11px; color: #4a5568; transition: transform .15s; }
  .caret.open { transform: rotate(90deg); }

  .turn-body { padding: 12px 14px; background: #0f1117; display: none; border-top: 1px solid #2d3748; }
  .turn-body.open { display: block; }

  .msg-block { margin-bottom: 12px; }
  .role-label { display: inline-block; font-size: 10px; padding: 2px 7px; border-radius: 4px;
                font-weight: 600; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
  .role-user { background: #1e3a5f; color: #90cdf4; }
  .role-assistant { background: #1a3a2a; color: #68d391; }
  .role-tool { background: #44337a; color: #d6bcfa; }
  .role-system { background: #2d3748; color: #a0aec0; }

  .part-row { display: flex; gap: 8px; margin-bottom: 5px; padding-left: 8px;
              border-left: 2px solid #2d3748; }
  .part-tag { font-size: 10px; padding: 1px 5px; border-radius: 3px; margin-top: 2px; }
  .tag-text { background: #2d3748; color: #a0aec0; }
  .tag-call { background: #1e3a5f; color: #90cdf4; }
  .tag-result { background: #44337a; color: #d6bcfa; }
  .part-content { font-size: 12px; font-family: 'SF Mono', monospace;
                  color: #cbd5e0; white-space: pre-wrap; word-break: break-word; line-height: 1.6; }
  .expand-btn { font-size: 11px; color: #4299e1; cursor: pointer; margin-top: 4px;
                background: none; border: none; padding: 0; }
  .expand-btn:hover { text-decoration: underline; }
  .markdown-view { background: #161b26; border: 1px solid #2d3748; border-radius: 8px; padding: 16px; }
  .markdown-view h1, .markdown-view h2, .markdown-view h3 { margin: 8px 0; }
  .markdown-view pre { background: #0f1117; border: 1px solid #2d3748; border-radius: 6px; padding: 10px; overflow-x: auto; margin: 8px 0; }
  .markdown-view code { font-family: 'SF Mono', monospace; }
  .report-table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }
  .report-table th, .report-table td { padding: 8px 12px; text-align: left; border: 1px solid #2d3748; }
  .report-table th { background: #1a1f2e; font-weight: 600; color: #a0aec0; }
  .report-table tbody tr:hover { background: #1e2a3a; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div class="breadcrumb">
      <div class="breadcrumb-title">Navigation</div>
      <div class="breadcrumb-path" id="breadcrumb"></div>
    </div>
    <div class="browser-list" id="browser-list">
      <div class="empty">Loading...</div>
    </div>
  </div>
  <div id="main">
    <div class="empty">Select a session to view details</div>
  </div>
</div>

<script>
const BASE = window.location.origin;
let currentPath = '';
let activeSid = null;
let activeArtifactPath = null;
const FULL_TEXTS = {};

async function navigate(path) {
  currentPath = path || '';
  updateBreadcrumb();
  
  const res = await fetch(`${BASE}/browse?path=${encodeURIComponent(currentPath)}`);
  const data = await res.json();
  
  const list = document.getElementById('browser-list');
  const items = [];
  
  data.folders.forEach(f => {
    items.push(`
      <div class="folder-item" onclick="navigate('${f.path}')">
        <span class="folder-icon">📁</span>
        <div class="item-content">
          <div class="item-name">${escHtml(f.name)}</div>
        </div>
      </div>
    `);
  });
  
  data.sessions.forEach(s => {
    const isActive = activeSid === s.id ? 'active' : '';
    items.push(`
      <div class="session-item ${isActive}" onclick="loadSession('${s.id}')" id="sid-${s.id}">
        <span class="session-icon">📄</span>
        <div class="item-content">
          <div class="item-name">${s.id}</div>
          <div class="item-meta">${s.turns} turns · ${s.total_tokens.toLocaleString()} tok</div>
        </div>
      </div>
    `);
  });

  (data.files || []).forEach((f) => {
    const fileId = makeFileId(f.path);
    const isActive = activeArtifactPath === f.path ? 'active' : '';
    let icon = '📝';
    if (f.name === 'report.json') icon = '📊';
    else if (f.name === 'cli_output.txt') icon = '📟';
    else if (f.type === 'json') icon = '📊';
    else if (f.type === 'txt') icon = '📟';
    const typeLabel = (f.type || 'file').toUpperCase();
    items.push(`
      <div class="file-item ${isActive}" onclick="loadArtifact('${f.path}')" id="${fileId}">
        <span class="file-icon">${icon}</span>
        <div class="item-content">
          <div class="item-name">${escHtml(f.name)}</div>
          <div class="item-meta">${escHtml(typeLabel)} artifact</div>
        </div>
      </div>
    `);
  });
  
  if (items.length === 0) {
    list.innerHTML = '<div class="empty">No items here</div>';
  } else {
    list.innerHTML = items.join('');
  }
}

function updateBreadcrumb() {
  const crumbs = [];
  crumbs.push(`<span class="breadcrumb-item" onclick="navigate('')">🏠</span>`);
  
  if (currentPath) {
    const parts = currentPath.split('/');
    parts.forEach((part, i) => {
      const path = parts.slice(0, i + 1).join('/');
      const isLast = i === parts.length - 1;
      const cls = isLast ? 'breadcrumb-item current' : 'breadcrumb-item';
      const onclick = isLast ? '' : `onclick="navigate('${path}')"`;
      crumbs.push(`<span class="breadcrumb-sep">/</span>`);
      crumbs.push(`<span class="${cls}" ${onclick}>${escHtml(part)}</span>`);
    });
  }
  
  document.getElementById('breadcrumb').innerHTML = crumbs.join('');
}

async function loadSession(sid) {
  if (activeArtifactPath) {
    document.getElementById(makeFileId(activeArtifactPath))?.classList.remove('active');
    activeArtifactPath = null;
  }
  if (activeSid) document.getElementById('sid-'+activeSid)?.classList.remove('active');
  activeSid = sid;
  document.getElementById('sid-'+sid)?.classList.add('active');
  
  const main = document.getElementById('main');
  main.innerHTML = '<div class="empty">Loading session...</div>';
  
  const res = await fetch(`${BASE}/sessions/${sid}`);
  const turns = await res.json();
  renderSession(sid, turns, main);
}

async function loadArtifact(path) {
  if (activeSid) {
    document.getElementById('sid-'+activeSid)?.classList.remove('active');
    activeSid = null;
  }
  if (activeArtifactPath) {
    document.getElementById(makeFileId(activeArtifactPath))?.classList.remove('active');
  }
  activeArtifactPath = path;
  document.getElementById(makeFileId(path))?.classList.add('active');

  const main = document.getElementById('main');
  main.innerHTML = '<div class="empty">Loading markdown...</div>';

  const res = await fetch(`${BASE}/artifact?path=${encodeURIComponent(path)}`);
  const data = await res.json();
  if (!res.ok) {
    main.innerHTML = `<div class="empty">Failed to load artifact: ${escHtml(data.error || 'unknown error')}</div>`;
    return;
  }

  main.innerHTML = `
    <div class="turns-header">
      <h2>${escHtml(path.split('/').pop() || 'artifact')}</h2>
      <div class="subtext">${escHtml(data.path)} · ${Number(data.size || 0).toLocaleString()} bytes</div>
    </div>
    <div class="markdown-view">${renderArtifactContent(data.content, data.extension || '')}</div>
  `;
}

function renderSession(sid, turns, container) {
  const totalTok = turns.reduce((acc, t) => acc + (t.estimated_tokens || 0), 0);
  const models = [...new Set(turns.map(t => t.model.split('/').pop()))];
  const errorCount = turns.filter(t => hasError(t)).length;
  
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
      ${hasSystem ? '<div class="stat-box"><div class="val">✓</div><div class="lbl">System</div></div>' : ''}
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
    const toolsList = turn.tools.map((t) => {
      const fn = t.function || t;
      const name = fn.name || '?';
      const desc = fn.description || '';
      const uid = 'tool-' + Math.random().toString(36).slice(2);
      const short = desc.slice(0, 80);
      const long = desc.length > 80;
      if (long) FULL_TEXTS[uid] = desc;
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
      (Array.isArray(c) ? c.map(p => p.text||'').join(' ') : '');
    return /error|Error|ERROR/.test(text) && !/No.*error|0 error|no linter/i.test(text);
  });
}

function getTurnSummary(newMsgs, turn) {
  for (let i = newMsgs.length - 1; i >= 0; i--) {
    const m = newMsgs[i];
    if (m.role !== 'user') continue;
    const text = contentText(m.content);
    const match = text.match(/<user_query>([\s\S]*?)<\/user_query>/);
    if (match) return match[1].trim().slice(0, 100);
  }
  for (const m of newMsgs) {
    if (m.role === 'assistant') {
      const t = contentText(m.content).trim();
      if (t) return t.slice(0, 100);
    }
  }
  return `${turn.message_count} messages`;
}

function contentText(content) {
  if (!content) return '';
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(p => p.text || '').join(' ');
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
    let text = content;
    const qm = text.match(/<user_query>([\s\S]*?)<\/user_query>/);
    if (qm) text = qm[1].trim();
    else text = text.replace(/<[^>]+>/g, ' ').trim().slice(0, 2000);
    if (text) parts.push({ tag: 'text', text });
  }
  if (m.tool_calls) {
    for (const tc of m.tool_calls) {
      const fn = tc.function || {};
      parts.push({ tag: 'call', text: `${fn.name}(${(fn.arguments||'').slice(0,200)})` });
    }
  }
  return parts;
}

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

function makeFileId(path) {
  return `artifact-${path.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
}

function renderMarkdown(md) {
  let html = escHtml(md);
  html = html.replace(/```([\\s\\S]*?)```/g, (_, code) => `<pre><code>${code.trim()}</code></pre>`);
  html = html.replace(/^### (.*)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.*)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.*)$/gm, '<h1>$1</h1>');
  html = html.replace(/\\n/g, '<br>');
  return html;
}

function renderArtifactContent(content, extension) {
  const ext = (extension || '').toLowerCase();
  if (ext === '.md' || ext === '.markdown') {
    return renderMarkdown(content);
  }
  if (ext === '.json' || ext === '.jsonl') {
    // Try to render report.json as tables
    try {
      const parsed = JSON.parse(content);
      if (parsed.runs && Array.isArray(parsed.runs)) {
        return renderReportTables(parsed);
      }
    } catch (_) {
      // Fall through to plain JSON
    }
    return `<pre><code>${escHtml(prettyJson(content))}</code></pre>`;
  }
  return `<pre><code>${escHtml(content)}</code></pre>`;
}

function renderReportTables(report) {
  const parts = [];
  
  // Metadata section
  const meta = report.metadata || {};
  parts.push(`
    <div style="margin-bottom: 24px;">
      <h2>Run Metadata</h2>
      <table class="report-table">
        <tr><th>Timestamp</th><td>${escHtml(meta.timestamp || '')}</td></tr>
        <tr><th>Command</th><td><code>${escHtml(meta.command || '')}</code></td></tr>
        <tr><th>Cache Mode</th><td>${escHtml(meta.cache_mode_for_run_dir || '')}</td></tr>
      </table>
    </div>
  `);
  
  // Per-run results
  (report.runs || []).forEach((run, idx) => {
    parts.push(`<div style="margin-bottom: 24px;">
      <h2>Run ${idx + 1}: ${escHtml(run.scenario || '')}</h2>
      <p><strong>Model:</strong> ${escHtml(run.model || '')}</p>
      <p><strong>Strategies:</strong> ${(run.strategies_tested || []).join(', ')}</p>
      
      <h3>Results by Strategy</h3>
      <table class="report-table">
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Turns</th>
            <th>Tools</th>
            <th>Raw Input</th>
            <th>Cache Read</th>
            <th>Cache Create</th>
            <th>Billed Input</th>
            <th>Output</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
    `);
    
    for (const [strategy, result] of Object.entries(run.results || {})) {
      if (result.error) {
        parts.push(`<tr><td>${escHtml(strategy)}</td><td colspan="8">ERROR: ${escHtml(result.error)}</td></tr>`);
        continue;
      }
      const m = result.metrics || {};
      parts.push(`
        <tr>
          <td><strong>${escHtml(strategy)}</strong></td>
          <td>${m.turns || 0}</td>
          <td>${m.tool_calls || 0}</td>
          <td>${(m.raw_input_tokens || 0).toLocaleString()}</td>
          <td>${(m.cache_read_tokens || 0).toLocaleString()}</td>
          <td>${(m.cache_creation_tokens || 0).toLocaleString()}</td>
          <td>${(m.billed_input_tokens || 0).toLocaleString()}</td>
          <td>${(m.total_output_tokens || 0).toLocaleString()}</td>
          <td>${(m.total_tokens || 0).toLocaleString()}</td>
        </tr>
      `);
    }
    
    parts.push('</tbody></table>');
    
    // Comparison table
    if (run.comparison && Object.keys(run.comparison).length > 0) {
      parts.push(`
        <h3>Savings vs Baseline (none)</h3>
        <table class="report-table">
          <thead>
            <tr>
              <th>Strategy</th>
              <th>Raw Input Savings</th>
              <th>Raw Input %</th>
              <th>Billed Input Savings</th>
              <th>Billed Input %</th>
            </tr>
          </thead>
          <tbody>
      `);
      
      for (const [strategy, comp] of Object.entries(run.comparison)) {
        parts.push(`
          <tr>
            <td><strong>${escHtml(strategy)}</strong></td>
            <td>${(comp.raw_input_savings || 0).toLocaleString()}</td>
            <td>${(comp.raw_input_savings_pct || 0).toFixed(2)}%</td>
            <td>${(comp.billed_input_savings || 0).toLocaleString()}</td>
            <td>${(comp.billed_input_savings_pct || 0).toFixed(2)}%</td>
          </tr>
        `);
      }
      
      parts.push('</tbody></table>');
    }
    
    parts.push('</div>');
  });
  
  // Aggregate summary
  if (report.aggregate_summary) {
    parts.push(`
      <div style="margin-bottom: 24px;">
        <h2>Aggregate Summary (${Object.values(report.aggregate_summary)[0]?.runs || 0} runs)</h2>
        <table class="report-table">
          <thead>
            <tr>
              <th>Strategy</th>
              <th>Mean Savings</th>
              <th>Mean %</th>
              <th>Median Savings</th>
              <th>Median %</th>
            </tr>
          </thead>
          <tbody>
    `);
    
    for (const [strategy, summary] of Object.entries(report.aggregate_summary)) {
      parts.push(`
        <tr>
          <td><strong>${escHtml(strategy)}</strong></td>
          <td>${(summary.mean_savings || 0).toLocaleString()}</td>
          <td>${(summary.mean_pct || 0).toFixed(2)}%</td>
          <td>${(summary.median_savings || 0).toLocaleString()}</td>
          <td>${(summary.median_pct || 0).toFixed(2)}%</td>
        </tr>
      `);
    }
    
    parts.push('</tbody></table></div>');
  }
  
  return parts.join('');
}

function prettyJson(content) {
  try {
    return JSON.stringify(JSON.parse(content), null, 2);
  } catch (_) {
    return content;
  }
}

navigate('');
setInterval(() => navigate(currentPath), 30000);
</script>
</body>
</html>"""
