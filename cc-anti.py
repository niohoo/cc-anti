#!/usr/bin/env python3
"""
cc-anti — Claude Code ↔ Antigravity 对话互导工具 (单文件版)

功能:
  1. CC → 项目目录: 将 CC 对话导出为 .cc_history.md 放到项目根目录
  2. AG → CC: 将 AG brain artifacts 生成 CC 可读的 JSONL
  3. AG ♻️ 恢复: 将 AG brain artifacts 导出到项目根目录 (.ag_brain/)

运行: python3 cc-anti.py
"""

import os, sys, json, uuid, re, shutil, urllib.parse
from pathlib import Path
from datetime import datetime, timezone
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

CLAUDE_HOME = Path.home() / ".claude"
CLAUDE_PROJECTS = CLAUDE_HOME / "projects"
AG_HOME = Path.home() / ".gemini" / "antigravity"
AG_CONVERSATIONS = AG_HOME / "conversations"
AG_BRAIN = AG_HOME / "brain"

# ═══════════════════════════════════════════
#  CC 解析逻辑
# ═══════════════════════════════════════════

def load_sessions_index(pdir):
    idx = pdir / "sessions-index.json"
    if idx.exists():
        try: return json.loads(idx.read_text())
        except: pass
    return {}

def convert_cc_to_md(jsonl_path):
    entries = []
    with open(jsonl_path, "r") as f:
        for line in f:
            if line.strip():
                try: entries.append(json.loads(line.strip()))
                except: pass
    if not entries: return "# 空会话"

    rounds, cur, seen = [], None, set()
    for e in entries:
        if e.get("type") in ("file-history-snapshot","queue-operation","progress","system"): continue
        if e.get("isMeta"): continue
        msg = e.get("message")
        if not isinstance(msg, dict): continue
        role, content = msg.get("role"), msg.get("content", "")

        if role == "user":
            if isinstance(content, list) and all(isinstance(c, dict) and c.get("type") == "tool_result" for c in content): continue
            text = content if isinstance(content, str) else "\n".join(c.get("text","") for c in content if isinstance(c, dict) and c.get("type") == "text")
            if text.strip():
                if cur: rounds.append(cur)
                cur = {"user": text.strip(), "assistant": []}
                seen.clear()
        elif role == "assistant" and cur is not None:
            if isinstance(content, str): text = content
            elif isinstance(content, list):
                text = "\n\n".join(c.get("text","") for c in content if isinstance(c, dict) and c.get("type") == "text")
            else: text = str(content)
            text = re.sub(r'<details>.*?</details>', '', text, flags=re.DOTALL).strip()
            if not text: continue
            key = text[:100]
            if key in seen: continue
            seen.add(key)
            cur["assistant"].append(text)
    if cur: rounds.append(cur)

    md = [f"# Claude Code 历史对话记录\n",
          f"> 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
          f"> 共 {len(rounds)} 个对话回合\n---\n"]
    for i, r in enumerate(rounds, 1):
        md.append(f"## 回合 {i}\n\n### 👤 用户\n\n{r['user']}\n")
        md.append(f"### 🤖 助手\n\n" + "\n\n".join(r['assistant']) + "\n\n---\n")
    return "\n".join(md)

# ═══════════════════════════════════════════
#  AG 解析逻辑
# ═══════════════════════════════════════════

def get_ag_info(cid):
    info = {"id": cid, "has_pb": False, "has_brain": False, "artifacts": [], "artifact_names": []}
    pb = AG_CONVERSATIONS / f"{cid}.pb"
    if pb.exists():
        info["has_pb"] = True
        info["pb_size"] = pb.stat().st_size
        info["mtime"] = datetime.fromtimestamp(pb.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    bdir = AG_BRAIN / cid
    if bdir.exists() and bdir.is_dir():
        info["has_brain"] = True
        for f in sorted(bdir.iterdir()):
            if f.is_file() and f.suffix in (".md",".txt") and ".metadata" not in f.name and ".resolved" not in f.name:
                info["artifacts"].append(f)
                info["artifact_names"].append(f.name)
        # Also check .system_generated/logs
        logs = bdir / ".system_generated" / "logs"
        if logs.exists():
            for f in sorted(logs.iterdir()):
                if f.is_file():
                    info["artifacts"].append(f)
                    info["artifact_names"].append(f"logs/{f.name}")
    return info

def preview_ag(cid):
    info = get_ag_info(cid)
    if not info["artifacts"]:
        return f"# AG {cid[:8]}\n\n> ⚠️ 无 Markdown 制品 (PB 加密)"
    md = [f"# Antigravity 对话 ({cid[:8]})\n"]
    for f in info["artifacts"]:
        md.append(f"## 📄 {f.name}\n")
        try: md.append(f.read_text())
        except: md.append("*(读取失败)*")
        md.append("\n---\n")
    return "\n".join(md)

# ═══════════════════════════════════════════
#  HTTP Handler
# ═══════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        for h in ['Access-Control-Allow-Origin','Access-Control-Allow-Methods','Access-Control-Allow-Headers']:
            self.send_header(h, '*')
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        qs = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))

        if path == "/":
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode())
            return

        if path == "/api/projects":
            projects = []
            if CLAUDE_PROJECTS.exists():
                for pdir in sorted(CLAUDE_PROJECTS.iterdir()):
                    if not pdir.is_dir(): continue
                    sessions = [s for s in pdir.glob("*.jsonl") if s.stat().st_size > 100]
                    if not sessions: continue
                    idx = load_sessions_index(pdir)
                    # Extract real path from first JSONL's cwd field
                    real_path = pdir.name.replace("-","/")
                    for jf in sessions:
                        try:
                            with open(jf) as rf:
                                for line in rf:
                                    e = json.loads(line.strip())
                                    if e.get("cwd"):
                                        real_path = e["cwd"]; break
                            break
                        except: pass
                    sl = []
                    for s in sessions:
                        summary = ""
                        for k,v in idx.items():
                            if isinstance(v, dict) and v.get("sessionId") == s.stem:
                                summary = v.get("summary","")[:80]; break
                        sl.append({"id":s.stem,"path":str(s),"size":s.stat().st_size,
                                   "summary":summary,"mtime":datetime.fromtimestamp(s.stat().st_mtime).strftime("%m-%d %H:%M")})
                    projects.append({"name":pdir.name.replace("-","/"),"dir":pdir.name,
                                     "real_path":real_path,
                                     "sessions":sorted(sl,key=lambda x:x["mtime"],reverse=True)})
            self.send_json({"projects":projects})
            return

        if path == "/api/conversations":
            convs = []
            if AG_CONVERSATIONS.exists():
                for pb in AG_CONVERSATIONS.glob("*.pb"):
                    info = get_ag_info(pb.stem)
                    convs.append({"id":pb.stem,"size":info.get("pb_size",0),
                                  "mtime":info.get("mtime",""),
                                  "has_artifacts":len(info["artifacts"])>0,
                                  "artifact_names":info.get("artifact_names",[])})
            self.send_json({"conversations":sorted(convs,key=lambda x:x["mtime"],reverse=True)})
            return

        if path.startswith("/api/preview/cc/"):
            sid = path.split("/")[-1]
            for pdir in CLAUDE_PROJECTS.iterdir():
                sp = pdir / f"{sid}.jsonl"
                if sp.exists():
                    self.send_json({"markdown":convert_cc_to_md(sp)})
                    return
            self.send_json({"markdown":"未找到"},404)
            return

        if path.startswith("/api/preview/ag/"):
            cid = path.split("/")[-1]
            self.send_json({"markdown":preview_ag(cid)})
            return

        self.send_response(404); self.end_headers()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length',0)))) if int(self.headers.get('Content-Length',0)) else {}

        # ── 1. CC → 项目根目录 ──
        if path == "/api/cc2project":
            sp = Path(body.get("session_path",""))
            target = body.get("target_dir","").strip()
            if not sp.exists():
                self.send_json({"ok":False,"msg":"源文件不存在: "+str(sp)})
                return
            if not target or not Path(target).exists():
                self.send_json({"ok":False,"msg":f"目标目录不存在: {target}"})
                return
            try:
                md = convert_cc_to_md(sp)
                out = Path(target) / "cc_history.md"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(md, encoding="utf-8")
                self.send_json({"ok":True,"msg":f"✅ 已导出到 {out}","path":str(out),"size":f"{out.stat().st_size/1024:.0f}KB"})
            except Exception as ex:
                self.send_json({"ok":False,"msg":f"导出失败: {ex}"})
            return

        # ── 2. AG → CC JSONL ──
        if path == "/api/ag2cc":
            cid = body.get("conversation_id","")
            target = body.get("target_project","")
            if not cid or not target:
                self.send_json({"ok":False,"msg":"缺少参数"})
                return
            info = get_ag_info(cid)
            if not info["artifacts"]:
                self.send_json({"ok":False,"msg":"无制品可导出"})
                return

            sid = str(uuid.uuid4())
            encoded = target.replace("/","-")
            pdir = CLAUDE_PROJECTS / encoded
            pdir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]+"Z"

            entries = [{"type":"file-history-snapshot","messageId":str(uuid.uuid4()),
                        "snapshot":{"messageId":str(uuid.uuid4()),"trackedFileBackups":{},"timestamp":ts},"isSnapshotUpdate":False}]
            parent = None
            # User message
            uid = str(uuid.uuid4())
            entries.append({"parentUuid":parent,"isSidechain":False,"userType":"external",
                            "cwd":target,"sessionId":sid,"version":"2.1.63","type":"user",
                            "message":{"role":"user","content":f"[AG {cid[:8]} 导入] 包含 {len(info['artifacts'])} 个制品"},
                            "uuid":uid,"timestamp":ts})
            parent = uid
            # Each artifact as assistant
            for f in info["artifacts"]:
                aid = str(uuid.uuid4())
                try: content = f.read_text()
                except: content = "(读取失败)"
                entries.append({"parentUuid":parent,"isSidechain":False,"userType":"external",
                                "cwd":target,"sessionId":sid,"version":"2.1.63","type":"assistant",
                                "message":{"id":f"msg_{str(uuid.uuid4())[:24]}","type":"message","role":"assistant",
                                           "content":[{"type":"text","text":f"## 📄 {f.name}\n\n{content}"}],
                                           "model":"imported-from-antigravity","stop_reason":"end_turn","stop_sequence":None,
                                           "usage":{"input_tokens":0,"output_tokens":0,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}},
                                "uuid":aid,"timestamp":ts})
                parent = aid

            jpath = pdir / f"{sid}.jsonl"
            with open(jpath,"w") as fj:
                for e in entries: fj.write(json.dumps(e,ensure_ascii=False)+"\n")
            # Update index
            idx_path = pdir / "sessions-index.json"
            idx = {}
            if idx_path.exists():
                try: idx = json.loads(idx_path.read_text())
                except: pass
            idx[sid] = {"sessionId":sid,"summary":f"AG导入 ({cid[:8]})","createdAt":ts}
            idx_path.write_text(json.dumps(idx,ensure_ascii=False,indent=2))

            self.send_json({"ok":True,"msg":f"✅ 已生成 CC 会话 ({sid[:8]})","path":str(jpath)})
            return

        # ── 3. AG ♻️ 恢复到项目根目录 ──
        if path == "/api/ag_recover":
            cid = body.get("conversation_id","")
            target = body.get("target_dir","")
            selected = body.get("selected_artifacts",[])  # 用户选择的制品名
            if not cid or not target:
                self.send_json({"ok":False,"msg":"缺少参数"})
                return
            info = get_ag_info(cid)
            if not info["artifacts"]:
                self.send_json({"ok":False,"msg":"无制品可恢复"})
                return

            # Create .ag_brain/<conv_id_short>_<timestamp>/ in project root
            ts_str = datetime.now().strftime("%Y%m%d_%H%M")
            folder_name = f"{cid[:8]}_{ts_str}"
            out_dir = Path(target) / "ag_brain" / folder_name
            out_dir.mkdir(parents=True, exist_ok=True)

            copied = []
            for f in info["artifacts"]:
                # If user selected specific artifacts, filter
                if selected and f.name not in selected and f"logs/{f.name}" not in selected:
                    continue
                try:
                    dest = out_dir / f.name
                    shutil.copy2(f, dest)
                    copied.append(f.name)
                except Exception as ex:
                    copied.append(f"{f.name} (失败: {ex})")

            # Write a manifest
            manifest = {"conversation_id": cid, "recovered_at": ts_str,
                        "source": str(AG_BRAIN / cid), "artifacts": copied}
            (out_dir / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

            self.send_json({"ok":True,
                            "msg":f"♻️ 已恢复 {len(copied)} 个制品到 {out_dir.relative_to(Path(target))}",
                            "path":str(out_dir),"artifacts":copied})
            return

        self.send_response(404); self.end_headers()


# ═══════════════════════════════════════════
#  Embedded HTML/JS/CSS
# ═══════════════════════════════════════════

HTML = r"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>cc⇌anti</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⇌</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#0d1117;--bgs:#161b22;--bgt:#21262d;--bgh:#272c33;--bd:#30363d;--fg:#e6edf3;--fgm:#8b949e;--fgd:#6e7681;--blue:#58a6ff;--green:#3fb950;--purple:#bc8cff;--orange:#d29922;--red:#f85149}
*{box-sizing:border-box;font-family:'Inter',-apple-system,sans-serif}
body{margin:0;background:var(--bg);color:var(--fg);display:flex;flex-direction:column;height:100vh;overflow:hidden}
header{padding:10px 20px;background:var(--bgs);border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center}
.logo{font-size:20px;font-weight:700;background:linear-gradient(135deg,#d4a574,#58a6ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sub{font-size:11px;color:var(--fgd);margin-left:10px}
main{display:flex;flex:1;overflow:hidden}
.col{flex:1;display:flex;flex-direction:column;border-right:1px solid var(--bd);min-width:0}
.col:last-of-type{border-right:none}
.col-hd{padding:10px 14px;background:var(--bgs);border-bottom:1px solid var(--bd);font-weight:600;font-size:14px;display:flex;align-items:center;gap:8px;flex-shrink:0}
.col-hd .badge{font-size:10px;padding:2px 7px;border-radius:10px;background:var(--bgt);color:var(--fgm);border:1px solid var(--bd);margin-left:auto}
.list{flex:1;overflow-y:auto;padding:6px}
.list::-webkit-scrollbar{width:5px}
.list::-webkit-scrollbar-thumb{background:var(--bd);border-radius:3px}
.grp{margin-bottom:2px}
.grp-hd{display:flex;align-items:center;gap:6px;padding:6px 10px;cursor:pointer;border-radius:5px;font-size:12px;color:var(--fgm)}
.grp-hd:hover{background:var(--bgt)}
.grp-hd.exp{color:var(--fg)}
.chv{font-size:9px;transition:transform .2s;width:14px;text-align:center}
.chv.exp{transform:rotate(90deg)}
.grp-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500}
.grp-cnt{font-size:10px;color:var(--fgd);background:var(--bgt);padding:1px 5px;border-radius:7px}
.sl{padding-left:10px}
.item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:5px;cursor:pointer;border:1px solid transparent;margin-bottom:1px;font-size:12px}
.item:hover{background:var(--bgt);border-color:var(--bd)}
.item.sel{background:rgba(88,166,255,.1);border-color:var(--blue)}
.item.sel-ag{background:rgba(188,140,255,.1);border-color:var(--purple)}
.dot{width:6px;height:6px;border-radius:50%;flex-shrink:0}
.dot.lg{background:var(--blue)}.dot.md{background:var(--green)}.dot.sm{background:var(--fgd)}
.dot.has{background:var(--green)}.dot.no{background:var(--fgd)}
.info{flex:1;min-width:0}
.id{font-size:11px;font-family:'SF Mono',Monaco,monospace;color:var(--fgm);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sum{font-size:11px;color:var(--fg);margin-top:1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.meta{display:flex;flex-direction:column;align-items:flex-end;gap:1px;flex-shrink:0;font-size:10px;color:var(--fgd)}
.abadge{font-size:9px;padding:1px 5px;border-radius:3px;background:var(--bgt);color:var(--green);border:1px solid rgba(63,185,80,.3)}
.center{width:56px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:10px;border-right:1px solid var(--bd);flex-shrink:0;background:var(--bgs)}
.btn{width:38px;height:38px;border-radius:19px;border:1.5px solid var(--bd);background:var(--bgt);color:var(--fgm);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:15px;transition:all .15s;position:relative}
.btn:hover:not(:disabled){border-color:var(--blue);color:var(--blue);background:rgba(88,166,255,.08);transform:scale(1.08)}
.btn.recover:hover:not(:disabled){border-color:var(--green);color:var(--green);background:rgba(63,185,80,.08)}
.btn:disabled{opacity:.25;cursor:not-allowed}
.btn .tip{display:none;position:absolute;white-space:nowrap;font-size:10px;padding:3px 7px;background:var(--bgh);border:1px solid var(--bd);border-radius:4px;color:var(--fg);pointer-events:none;z-index:10}
.btn:hover .tip{display:block}
.btn .tip.right{left:44px}.btn .tip.left{right:44px}
.preview{flex:1.3;display:flex;flex-direction:column;border-left:1px solid var(--bd);min-width:0}
.preview.hidden{display:none}
.pv-hd{padding:8px 14px;background:var(--bgs);border-bottom:1px solid var(--bd);display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.pv-title{font-size:13px;font-weight:600}
.pv-close{width:24px;height:24px;border-radius:4px;border:none;background:0;color:var(--fgm);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px}
.pv-close:hover{background:var(--bgt);color:var(--fg)}
.pv-body{flex:1;overflow-y:auto;padding:16px;font-size:13px;line-height:1.65}
.pv-body::-webkit-scrollbar{width:5px}.pv-body::-webkit-scrollbar-thumb{background:var(--bd);border-radius:3px}
.pv-body h1{font-size:18px;margin:12px 0 6px;color:var(--fg)}
.pv-body h2{font-size:15px;margin:16px 0 6px;color:var(--blue);border-bottom:1px solid var(--bd);padding-bottom:4px}
.pv-body h3{font-size:13px;margin:10px 0 4px;color:var(--fg)}
.pv-body pre{background:var(--bgs);padding:10px;border-radius:5px;overflow-x:auto;border:1px solid var(--bd);font-size:12px}
.pv-body code{font-family:'SF Mono',Monaco,monospace;font-size:12px}
.pv-body blockquote{border-left:3px solid var(--blue);padding-left:10px;margin:6px 0;color:var(--fgm)}
.pv-body table{border-collapse:collapse;width:100%;margin:6px 0;font-size:11px}
.pv-body th,.pv-body td{border:1px solid var(--bd);padding:4px 8px;text-align:left}
.pv-body th{background:var(--bgt);color:var(--fgm)}
.pv-body hr{border:none;border-top:1px solid var(--bd);margin:12px 0}
.pv-body ul,.pv-body ol{padding-left:18px;margin:4px 0}
.pv-body li{margin:2px 0}
.toast{position:fixed;bottom:16px;right:16px;padding:12px 18px;border-radius:8px;background:var(--bgs);border:1px solid var(--bd);box-shadow:0 4px 12px rgba(0,0,0,.5);font-size:13px;animation:slideIn .3s;z-index:999;max-width:400px;display:flex;align-items:center;gap:8px}
.toast.ok{border-color:var(--green)}
.toast.err{border-color:var(--red)}
@keyframes slideIn{from{transform:translateX(100%);opacity:0}to{transform:translateX(0);opacity:1}}
.spinner{width:18px;height:18px;border:2px solid var(--bd);border-top-color:var(--blue);border-radius:50%;animation:spin .7s linear infinite;margin:30px auto}
@keyframes spin{to{transform:rotate(360deg)}}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:var(--fgd);text-align:center;padding:20px}
.empty-icon{font-size:32px;margin-bottom:8px;opacity:.5}
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;z-index:100}
.modal{background:var(--bgs);border:1px solid var(--bd);border-radius:10px;padding:20px;width:420px;max-height:80vh;overflow-y:auto;box-shadow:0 8px 24px rgba(0,0,0,.6)}
.modal h3{margin:0 0 12px;font-size:15px}
.modal label{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:4px;cursor:pointer;font-size:13px}
.modal label:hover{background:var(--bgt)}
.modal input[type=checkbox]{accent-color:var(--green)}
.modal input[type=text]{width:100%;padding:8px 10px;border-radius:5px;border:1px solid var(--bd);background:var(--bgt);color:var(--fg);font-size:13px;margin:6px 0}
.modal-btns{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.modal-btn{padding:6px 16px;border-radius:5px;border:1px solid var(--bd);background:var(--bgt);color:var(--fg);cursor:pointer;font-size:12px}
.modal-btn:hover{background:var(--bgh)}
.modal-btn.primary{background:var(--green);border-color:var(--green);color:#000;font-weight:600}
.modal-btn.primary:hover{opacity:.9}
</style></head><body>
<header>
  <div><span class="logo">cc⇌anti</span><span class="sub">Claude Code ↔ Antigravity 对话互导</span></div>
  <div style="font-size:11px;color:var(--fgd)" id="status"></div>
</header>
<main>
  <div class="col">
    <div class="col-hd">☰ Claude Code <span class="badge" id="cc-cnt">-</span></div>
    <div class="list" id="cc-list"><div class="spinner"></div></div>
  </div>
  <div class="center">
    <button class="btn" id="btn-c2p" disabled title="CC→项目目录" onclick="cc2project()">📤<span class="tip right">导出到项目目录</span></button>
    <button class="btn" id="btn-a2c" disabled title="AG→CC" onclick="ag2cc()">⬅<span class="tip left">导入到 CC</span></button>
    <button class="btn recover" id="btn-rec" disabled title="AG恢复" onclick="agRecover()">♻️<span class="tip left">恢复到项目目录</span></button>
  </div>
  <div class="col">
    <div class="col-hd">✦ Antigravity <span class="badge" id="ag-cnt">-</span></div>
    <div class="list" id="ag-list"><div class="spinner"></div></div>
  </div>
  <div class="preview hidden" id="preview">
    <div class="pv-hd"><span class="pv-title" id="pv-title">预览</span><button class="pv-close" onclick="closePreview()">✕</button></div>
    <div class="pv-body" id="pv-body"></div>
  </div>
</main>
<div id="modal-root"></div>
<script>
const API='';
let st={cc:null,ag:null,ccProj:'',agData:[]};

function renderMd(md){
  return(md||'')
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g,'<b>$1</b>')
    .replace(/```\w*\n([\s\S]*?)```/g,'<pre><code>$1</code></pre>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/^> (.+)$/gm,'<blockquote>$1</blockquote>')
    .replace(/^---+$/gm,'<hr>')
    .replace(/^- (.+)$/gm,'<li>$1</li>')
    .replace(/\n\n/g,'<br><br>')
    .replace(/(<li>[\s\S]*?<\/li>)+/g,'<ul>$&</ul>');
}

function toast(msg,ok=true){
  const d=document.createElement('div');
  d.className='toast '+(ok?'ok':'err');
  d.innerHTML=(ok?'✅':'❌')+' '+msg;
  document.body.appendChild(d);setTimeout(()=>d.remove(),4000);
}

async function load(){
  const[cc,ag]=await Promise.all([fetch('/api/projects').then(r=>r.json()),fetch('/api/conversations').then(r=>r.json())]);
  st.agData=ag.conversations||[];
  let total=0,ccH='';
  (cc.projects||[]).forEach(p=>{
    total+=p.sessions.length;
    ccH+=`<div class="grp"><div class="grp-hd" onclick="togGrp(this)"><span class="chv">▶</span><span class="grp-name" title="${p.name}">${p.name}</span><span class="grp-cnt">${p.sessions.length}</span></div><div class="sl" style="display:none">`;
    p.sessions.forEach(s=>{
      const cls=s.size>1048576?'lg':s.size>10240?'md':'sm';
      ccH+=`<div class="item" data-id="${s.id}" data-path="${s.path}" data-proj="${p.name}" data-realpath="${p.real_path}" onclick="selCC(this)"><div class="dot ${cls}"></div><div class="info"><div class="id">${s.id.slice(0,8)}</div>${s.summary?`<div class="sum">${s.summary}</div>`:''}</div><div class="meta"><span>${(s.size/1024).toFixed(0)}KB</span><span>${s.mtime}</span></div></div>`;
    });
    ccH+=`</div></div>`;
  });
  document.getElementById('cc-list').innerHTML=ccH||'<div class="empty"><div class="empty-icon">📭</div>无 CC 项目</div>';
  document.getElementById('cc-cnt').textContent=total;

  let agH='';
  st.agData.forEach(c=>{
    const badge=c.has_artifacts?`<span class="abadge">制品</span>`:'';
    agH+=`<div class="item" data-id="${c.id}" onclick="selAG(this)"><div class="dot ${c.has_artifacts?'has':'no'}"></div><div class="info"><div class="id">${c.id.slice(0,8)} ${badge}</div><div class="sum" style="font-size:10px;color:var(--fgd)">${(c.size/1024).toFixed(0)}KB | ${c.mtime}</div></div></div>`;
  });
  document.getElementById('ag-list').innerHTML=agH||'<div class="empty"><div class="empty-icon">📭</div>无 AG 对话</div>';
  document.getElementById('ag-cnt').textContent=st.agData.length;
  document.getElementById('status').textContent=`CC: ${total} 会话 | AG: ${st.agData.length} 对话`;
}

function togGrp(el){
  const sl=el.nextElementSibling,exp=sl.style.display!=='none';
  sl.style.display=exp?'none':'block';
  el.classList.toggle('exp',!exp);
  el.querySelector('.chv').classList.toggle('exp',!exp);
}

function selCC(el){
  document.querySelectorAll('#cc-list .item').forEach(e=>e.classList.remove('sel'));
  el.classList.add('sel');
  st.cc={id:el.dataset.id,path:el.dataset.path,proj:el.dataset.proj,realpath:el.dataset.realpath};
  document.getElementById('btn-c2p').disabled=false;
  showPreview('cc',st.cc.id);
}

function selAG(el){
  document.querySelectorAll('#ag-list .item').forEach(e=>e.classList.remove('sel-ag'));
  el.classList.add('sel-ag');
  st.ag=el.dataset.id;
  document.getElementById('btn-a2c').disabled=false;
  document.getElementById('btn-rec').disabled=false;
  showPreview('ag',st.ag);
}

async function showPreview(type,id){
  const pv=document.getElementById('preview');
  pv.classList.remove('hidden');
  document.getElementById('pv-title').textContent=(type==='cc'?'☰ ':'✦ ')+id.slice(0,8)+'…';
  document.getElementById('pv-body').innerHTML='<div class="spinner"></div>';
  const r=await fetch(`/api/preview/${type}/${id}`).then(r=>r.json());
  document.getElementById('pv-body').innerHTML=renderMd(r.markdown);
}

function closePreview(){
  document.getElementById('preview').classList.add('hidden');
}

async function cc2project(){
  if(!st.cc)return;
  const target=prompt('导出到项目目录 (绝对路径):',st.cc.realpath);
  if(!target)return;
  try{
    const r=await fetch('/api/cc2project',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({session_path:st.cc.path,target_dir:target})}).then(r=>r.json());
    toast(r.msg,r.ok);
  }catch(e){toast('请求失败: '+e.message,false);}
}

async function ag2cc(){
  if(!st.ag)return;
  const target=prompt('目标 CC 项目路径:','/Users');
  if(!target)return;
  try{
    const r=await fetch('/api/ag2cc',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({conversation_id:st.ag,target_project:target})}).then(r=>r.json());
    toast(r.msg,r.ok);if(r.ok)load();
  }catch(e){toast('请求失败: '+e.message,false);}
}

function agRecover(){
  if(!st.ag)return;
  const conv=st.agData.find(c=>c.id===st.ag);
  const names=conv?.artifact_names||[];
  if(!names.length){toast('此对话无制品可恢复',false);return;}

  let html=`<div class="modal-overlay" onclick="if(event.target===this)closeModal()"><div class="modal">
    <h3>♻️ 恢复 AG 制品到项目目录</h3>
    <p style="font-size:12px;color:var(--fgm);margin-bottom:10px">对话 ${st.ag.slice(0,8)} 包含 ${names.length} 个制品</p>
    <div style="margin-bottom:8px">`;
  names.forEach(n=>{
    html+=`<label><input type="checkbox" value="${n}" checked> ${n}</label>`;
  });
  html+=`</div>
    <div style="font-size:12px;color:var(--fgm);margin-bottom:4px">目标项目根目录:</div>
    <input type="text" id="rec-target" value="/Users" placeholder="/path/to/project">
    <div class="modal-btns">
      <button class="modal-btn" onclick="closeModal()">取消</button>
      <button class="modal-btn primary" onclick="doRecover()">♻️ 恢复</button>
    </div>
  </div></div>`;
  document.getElementById('modal-root').innerHTML=html;
}

function closeModal(){document.getElementById('modal-root').innerHTML='';}

async function doRecover(){
  const checks=document.querySelectorAll('#modal-root input[type=checkbox]:checked');
  const selected=[...checks].map(c=>c.value);
  const target=document.getElementById('rec-target').value;
  if(!target){toast('请输入目标路径');return;}
  closeModal();
  try{
    const r=await fetch('/api/ag_recover',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({conversation_id:st.ag,target_dir:target,selected_artifacts:selected})}).then(r=>r.json());
    toast(r.msg,r.ok);
  }catch(e){toast('请求失败: '+e.message,false);}
}

load();
</script></body></html>"""

if __name__ == "__main__":
    PORT = 8766
    server = HTTPServer(('127.0.0.1', PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"🚀 cc-anti 启动: {url}")
    webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: print("\n🛑 已停止"); server.server_close()
