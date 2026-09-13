#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render_todos.py — 把 harvest.py 产出的待办清单渲染成一份本地 HTML 页面
=====================================================================================
产出一份**自包含**的 todos.html：内联 CSS / JS，无外部依赖、不联网，双击即可看。

用法
  python3 render_todos.py                                  # 读同目录 todos.json → 写 todos.html
  python3 render_todos.py --data ./todos.json --out ./todos.html
  python3 render_todos.py --state ./todo-state.json        # 一并带上人工判定档案

页面能做什么
  · 按项目分组查看；项目名 / 事由 / 来源文件 / 日期一目了然
  · 项目与状态筛选；分组折叠
  · 勾选框（存 localStorage，刷新不丢）
  · 调整归属：自动分错项目时点条目右侧「改组」手工纠正，同样存本地、随导出写回
  · 一键导出结果 → checked.json，交给 harvest.py --apply-checked 写回

页面**不能**做什么
  · 直接改磁盘文件（浏览器做不了）。勾选与归属调整要写回，必须走导出 + 命令行两步。
    这是刻意设计：归集产物与人工判定都落在你自己的磁盘上，页面只是视图。
"""
import argparse
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--bd:#e6e8eb;--tx:#1f2328;--tx2:#5b6570;--tx3:#8b949e;
--pri:#0e9f8e;--pri-d:#0b7f72;--amber:#b45309;--amber-bg:#fffbeb;--amber-bd:#fcd34d;
--purple:#6d28d9;--purple-bg:#f5f3ff;--purple-bd:#ddd6fe;--blue-bg:#e6f1fb;--blue-tx:#075985;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:20px;font-weight:600;margin:0 0 4px}
.sub{font-size:12px;color:var(--tx3);margin:0 0 20px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:18px}
.stat{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:12px 14px}
.stat .n{font-size:22px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.2}
.stat .l{font-size:12px;color:var(--tx2);margin-top:2px}
.chips{background:var(--card);border:1px solid var(--bd);border-radius:10px;overflow:hidden;margin-bottom:16px}
.row{display:flex;align-items:flex-start;gap:12px;padding:10px 14px}
.row+.row{border-top:1px solid var(--bd)}
.lb{flex:0 0 30px;font-size:11px;font-weight:600;color:var(--tx3);letter-spacing:1px;line-height:24px}
.set{display:flex;flex-wrap:wrap;gap:6px;flex:1;min-width:0}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:2px 9px;border-radius:6px;
border:1px solid var(--bd);background:var(--bg);color:var(--tx2);cursor:pointer;line-height:20px;white-space:nowrap}
.chip:hover{border-color:var(--pri);color:var(--pri-d)}
.chip.on{background:var(--pri);border-color:var(--pri);color:#fff}
.chip .n{font-size:11px;font-weight:600;opacity:.75;font-variant-numeric:tabular-nums}
.chip .dot{width:6px;height:6px;border-radius:50%;flex:0 0 auto}
.grp{background:var(--card);border:1px solid var(--bd);border-radius:10px;margin-bottom:10px;overflow:hidden}
.gh{display:flex;align-items:center;gap:10px;padding:11px 15px;cursor:pointer;user-select:none}
.gh:hover{background:#fafbfc}
.gh .ar{transition:transform .18s;color:var(--tx3);flex:0 0 auto}
.grp.open .gh .ar{transform:rotate(90deg)}
.gh .nm{font-size:14px;font-weight:600;flex:1}
.gh .ct{font-size:12px;color:var(--tx3);font-variant-numeric:tabular-nums}
.gh .ex{font-size:12px;color:var(--tx2);font-variant-numeric:tabular-nums}
.gb{display:none;padding:0 15px 8px}
.grp.open .gb{display:block}
.pbar{padding:8px 10px;margin:4px 0 10px;border-radius:8px;background:#f7f9fa;font-size:12px;line-height:1.8}
.pbar .nx{color:var(--tx3)}
.pbar .bk{color:var(--amber)}
.it{display:flex;gap:10px;padding:8px 0;border-top:1px solid #f0f2f4}
.it:first-child{border-top:0}
.it.done .ti{text-decoration:line-through;color:var(--tx3)}
.ck{flex:0 0 auto;width:18px;height:18px;border:1.5px solid var(--bd);border-radius:5px;margin-top:2px;
cursor:pointer;display:flex;align-items:center;justify-content:center;background:var(--card)}
.ck.on{background:var(--pri);border-color:var(--pri)}
.ck svg{opacity:0;stroke:#fff}
.ck.on svg{opacity:1}
.mn{flex:1;min-width:0}
.ti{font-size:13.5px;word-break:break-word}
.mt{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}
.bd{font-size:11px;padding:1px 7px;border-radius:4px;background:#f1f3f5;color:var(--tx2);line-height:18px;
max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bd.ctx{background:var(--blue-bg);color:var(--blue-tx);font-weight:500}
.bd.prj{background:var(--purple-bg);color:var(--purple);font-weight:500}
.bd.stale{background:#f1f5f9;color:#64748b}
.bd.new{background:#fef3c7;color:#92400e}
.src{font-size:11px;color:var(--tx3);margin-top:3px;word-break:break-all}
.it .pk{flex:0 0 auto;margin-top:2px;padding:1px 8px;border-radius:6px;border:1px solid var(--bd);
background:var(--card);color:var(--tx3);font-size:11px;line-height:18px;white-space:nowrap;cursor:pointer}
.it .pk:hover{border-color:var(--pri);color:var(--pri-d)}
.mask{position:fixed;inset:0;background:rgba(15,23,32,.42);display:flex;align-items:center;
justify-content:center;padding:16px;z-index:99}
.panel{width:min(420px,100%);max-height:min(76vh,560px);display:flex;flex-direction:column;
background:var(--card);border:1px solid var(--bd);border-radius:12px;overflow:hidden}
.ph{padding:14px 16px 2px;font-size:15px;font-weight:600}
.ps{padding:0 16px 10px;font-size:12px;color:var(--tx3);line-height:1.5}
.ps b{color:var(--pri-d)}
.pl{flex:1;overflow-y:auto;padding:0 8px 8px}
.pi{display:flex;align-items:center;gap:10px;width:100%;text-align:left;min-height:40px;padding:8px 10px;
border-radius:8px;color:var(--tx);font-size:13.5px;border:0;background:none;cursor:pointer}
.pi:hover{background:var(--bg)}
.pi .tk{flex:0 0 16px;color:var(--pri-d);font-weight:700}
.pi .nm2{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pi.cur{background:#eefaf8;font-weight:600}
.pf{padding:10px 16px;border-top:1px solid var(--bd);display:flex;justify-content:flex-end}
.bar{display:flex;gap:8px;align-items:center;margin:14px 0 18px;flex-wrap:wrap}
.btn{font-size:13px;padding:6px 14px;border-radius:7px;border:1px solid var(--bd);background:var(--card);
color:var(--tx);cursor:pointer}
.btn:hover{border-color:var(--pri);color:var(--pri-d)}
.btn.pri{background:var(--pri);border-color:var(--pri);color:#fff}
.btn.pri:hover{background:var(--pri-d);color:#fff}
.tip{font-size:12px;color:var(--tx3)}
.empty{padding:26px;text-align:center;color:var(--tx3);font-size:13px}
</style>
</head>
<body>
<div class="wrap">
<h1>__TITLE__</h1>
<p class="sub" id="sub"></p>
<div class="stats" id="stats"></div>
<div class="bar">
  <button class="btn pri" id="exp">导出勾选结果</button>
  <button class="btn" id="clr">清空本地勾选</button>
  <span class="tip" id="tip"></span>
</div>
<div class="chips" id="chips"></div>
<div id="list"></div>
</div>
<div id="gpHost" hidden></div>
<script type="application/json" id="payload">__DATA__</script>
<script>
(function(){
var P=JSON.parse(document.getElementById('payload').textContent);
var S=P.sessions||[], PR=P.projects||[];
var LS='memory_todo_harvest_checked';
var LA='memory_todo_harvest_assign';
var checked={};    /* 条目 id → 勾选态 */
var checkedT={};   /* 规范化标题 → 勾选态：记忆里的文字被改写后 id 会变，用它兜住 */
var assign={};     /* 条目 id → 调整后的项目 id（空串 = 未分类） */
try{checked=JSON.parse(localStorage.getItem(LS)||'{}')}catch(e){checked={}}
try{checkedT=JSON.parse(localStorage.getItem(LS+'__t')||'{}')}catch(e){checkedT={}}
try{assign=JSON.parse(localStorage.getItem(LA)||'{}')}catch(e){assign={}}
function save(){try{localStorage.setItem(LS,JSON.stringify(checked))}catch(e){}
try{localStorage.setItem(LS+'__t',JSON.stringify(checkedT))}catch(e){}}
function saveAssign(){try{localStorage.setItem(LA,JSON.stringify(assign))}catch(e){}}
var byId={};S.forEach(function(t){byId[t.id]=t;t._orig=t.projectId||''});
/* 把本地调整过的归属应用到数据上：条目按调整后的项目归组，刷新页面依然生效 */
Object.keys(assign).forEach(function(id){if(byId[id])byId[id].projectId=assign[id]});
function norm(s){return String(s==null?'':s).toLowerCase().replace(/[^\\w\\u4e00-\\u9fff]+/g,'')}
function titleHit(t){var n=norm(t.title);if(n.length<6)return false;
for(var k in checkedT){if(checkedT[k]&&k.length>=6&&(k.indexOf(n)>=0||n.indexOf(k)>=0))return true}
return false}
function pn(id){for(var i=0;i<PR.length;i++){if(PR[i].id===id)return PR[i].name}return ''}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function isDone(t){return !!t.done||!!checked[t.id]||titleHit(t)}
var pend=S.filter(function(t){return t.pending&&!isDone(t)});
var act=S.filter(function(t){return !isDone(t)&&!t.stale&&!t.pending});
var stale=S.filter(function(t){return !isDone(t)&&t.stale&&!t.pending});
var done=S.filter(isDone);
var F={proj:'',st:'',open:{}};
function pass(t){
  if(F.proj==='__closed__'){return false}
  if(F.proj==='__none__'){if(t.projectId)return false}
  else if(F.proj){if((t.projectId||'')!==F.proj)return false}
  if(F.st==='pending'){return t.pending&&!isDone(t)}
  if(F.st==='undone'){return !isDone(t)&&!t.stale&&!t.pending}
  if(F.st==='stale'){return !isDone(t)&&t.stale&&!t.pending}
  if(F.st==='done'){return isDone(t)}
  return true}
document.getElementById('sub').textContent=
  (P.meta&&P.meta.generatedAt?('生成于 '+P.meta.generatedAt+' · '):'')+
  '共 '+S.length+' 条 · 数据源 '+(P.meta&&P.meta.data||'todos.json');
function drawStats(){
  var h='';[['当前待办',act.length],['历史遗留',stale.length],['新发现',pend.length],
  ['已完成',done.length],['项目',PR.length]].forEach(function(x){
    h+='<div class="stat"><div class="n">'+x[1]+'</div><div class="l">'+x[0]+'</div></div>'});
  document.getElementById('stats').innerHTML=h}
function drawChips(){
  var pc={};S.forEach(function(t){pc[t.projectId||'']=(pc[t.projectId||'']||0)+1});
  var h='<div class="row"><span class="lb">项目</span><div class="set">';
  h+=chip('proj','','全部',S.length,'');
  PR.forEach(function(p){var n=pc[p.id]||0;if(n)h+=chip('proj',p.id,p.name,n,'')});
  if(pc[''])h+=chip('proj','__none__','未分类',pc[''],'');
  h+='</div></div><div class="row"><span class="lb">状态</span><div class="set">';
  if(pend.length)h+=chip('st','pending','新发现',pend.length,'#8b5cf6');
  h+=chip('st','undone','当前待办',act.length,'#0e9f8e');
  h+=chip('st','stale','历史遗留',stale.length,'#f59e0b');
  h+=chip('st','done','已完成',done.length,'#94a3b8');
  h+='</div></div>';
  document.getElementById('chips').innerHTML=h}
function chip(k,v,l,n,dot){
  return '<button class="chip'+(F[k]===v?' on':'')+'" data-k="'+k+'" data-v="'+esc(v)+'">'+
  (dot?'<span class="dot" style="background:'+dot+'"></span>':'')+esc(l)+
  '<span class="n">'+n+'</span></button>'}
/* ---- 调整归属 ----
   自动归属是「按标题 / 事由 / 章节打分猜出来的」，只能猜。猜错时在这里手工纠正：
   选择记在本地（刷新不丢），导出时随 checked.json 一起带走，由 harvest.py
   --apply-checked 写进判定档案，下次归集优先采用 —— 只改页面不写档案，
   下次归集会被重算覆盖。 */
var pickId='';
function groupOpts(cur){
  var h='<button class="pi'+(cur===''?' cur':'')+'" data-pid="">'+
  '<span class="tk">'+(cur===''?'✓':'')+'</span><span class="nm2">未分类</span></button>';
  PR.forEach(function(p){
    h+='<button class="pi'+(cur===p.id?' cur':'')+'" data-pid="'+esc(p.id)+'">'+
    '<span class="tk">'+(cur===p.id?'✓':'')+'</span><span class="nm2">'+esc(p.name)+'</span></button>'});
  return h}
function openPick(id){
  var t=byId[id];if(!t)return;
  pickId=id;var cur=t.projectId||'';
  document.getElementById('gpHost').innerHTML=
  '<div class="mask" id="gmask"><div class="panel">'+
  '<div class="ph">这条待办归到哪个项目？</div>'+
  '<div class="ps">当前：<b>'+esc(pn(cur)||'未分类')+'</b>。选好后点「导出勾选结果」，'+
  '再执行 harvest.py --apply-checked 写回，下次归集就按新的来。</div>'+
  '<div class="pl">'+groupOpts(cur)+'</div>'+
  '<div class="pf"><button class="btn" id="gclose">取消</button></div></div></div>';
  document.getElementById('gpHost').hidden=false}
function closePick(){var g=document.getElementById('gpHost');
  g.hidden=true;g.innerHTML='';pickId=''}
function applyPick(pid){
  var t=byId[pickId];if(!t){closePick();return}
  t.projectId=pid;
  if(pid===(t._orig||''))delete assign[t.id];else assign[t.id]=pid;
  saveAssign();closePick();draw()}
function item(t,gp){
  var cls='it'+(isDone(t)?' done':'');
  var h='<div class="'+cls+'"><div class="ck'+(isDone(t)?' on':'')+'" data-id="'+esc(t.id)+'">'+
  '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div><div class="mn">'+
  '<div class="ti">'+esc(t.title)+'</div><div class="mt">';
  if(gp)h+='<span class="bd prj">'+esc(gp)+'</span>';
  if(t.context)h+='<span class="bd ctx" title="事由">'+esc(t.context)+'</span>';
  if(t.pending&&!isDone(t))h+='<span class="bd new">新发现</span>';
  if(t.stale&&!isDone(t))h+='<span class="bd stale">遗留</span>';
  if(t.logDate)h+='<span class="bd">'+esc(t.logDate)+'</span>';
  if(t.source)h+='<span class="bd">'+esc(t.source)+'</span>';
  h+='</div>';
  if(t.logBase)h+='<div class="src">'+esc(t.logBase)+'</div>';
  h+='</div>';
  if(!isDone(t))h+='<button class="pk" data-pick="'+esc(t.id)+'" title="调整归属：自动分错时手工纠正，导出后写回">改组</button>';
  return h+'</div>'}
function grp(name,count,extra,inner,key){
  var op=F.open[key]!==false;
  if(name==='已完成'||name==='历史遗留')op=!!F.open[key];
  return '<div class="grp'+(op?' open':'')+'" data-k="'+esc(key)+'"><div class="gh">'+
  '<svg class="ar" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>'+
  '<span class="nm">'+esc(name)+'</span><span class="ct">'+count+' 条</span>'+
  (extra?'<span class="ex">'+esc(extra)+'</span>':'')+'</div><div class="gb">'+inner+'</div></div>'}
function draw(){
  drawStats();drawChips();
  var h='';
  var p0=pend.filter(pass);
  if(p0.length)h+=grp('新发现 · 待确认',p0.length,'',p0.map(function(t){return item(t,pn(t.projectId))}).join(''),'G_NEW');
  var by={};act.forEach(function(t){var k=t.projectId||'__none__';(by[k]=by[k]||[]).push(t)});
  PR.forEach(function(p){
    var l=(by[p.id]||[]).filter(pass);if(!l.length)return;
    var dn=S.filter(function(t){return (t.projectId||'')===p.id&&isDone(t)}).length;
    var tot=l.length+dn,pct=tot?Math.round(dn/tot*100):0;
    var pb='';if(p.stage||p.next||p.blocker){
      pb='<div class="pbar">'+(p.stage?'<div>进度：'+esc(p.stage)+'</div>':'')+
      (p.next?'<div><span class="nx">下一步</span> '+esc(p.next)+'</div>':'')+
      (p.blocker?'<div class="bk"><span style="font-weight:500">卡点</span> '+esc(p.blocker)+'</div>':'')+'</div>'}
    h+=grp(p.name,l.length,dn+'/'+tot+' · '+pct+'%',pb+l.map(function(t){return item(t,'')}).join(''),p.id)});
  if(by['__none__']){var l0=by['__none__'].filter(pass);
    if(l0.length)h+=grp('未分类',l0.length,'',l0.map(function(t){return item(t,'')}).join(''),'G_NONE')}
  var s0=stale.filter(pass);
  if(s0.length)h+=grp('历史遗留 · 超 __STALE__ 天未完成',s0.length,'',
    s0.map(function(t){return item(t,pn(t.projectId))}).join(''),'G_STALE');
  var d0=done.filter(pass);
  if(d0.length)h+=grp('已完成',d0.length,'',
    d0.map(function(t){return item(t,pn(t.projectId))}).join(''),'G_DONE');
  document.getElementById('list').innerHTML=h||'<div class="empty">当前筛选没有匹配的待办</div>';
  var nc=Object.keys(checked).filter(function(k){return checked[k]}).length;
  var na=Object.keys(assign).length;
  document.getElementById('tip').textContent=(nc||na)?
    ('本地已勾选 '+nc+' 条'+(na?('、调整归属 '+na+' 条'):'')+'，点「导出勾选结果」生成 checked.json'):'';
}
document.addEventListener('click',function(e){
  var c=e.target.closest('.chip');
  if(c){F[c.dataset.k]=F[c.dataset.k]===c.dataset.v?'':c.dataset.v;F.open={};draw();return}
  var p=e.target.closest('[data-pid]');
  if(p){applyPick(p.dataset.pid);return}
  if(e.target.closest('#gclose')||e.target.id==='gmask'){closePick();return}
  var k=e.target.closest('.ck');
  if(k){var id=k.dataset.id;checked[id]=!checked[id];save();draw();return}
  var pk=e.target.closest('[data-pick]');
  if(pk){openPick(pk.dataset.pick);return}
  var g=e.target.closest('.gh');
  if(g){var G=g.parentElement;var key=G.dataset.k;G.classList.toggle('open');
    F.open[key]=G.classList.contains('open');return}});
document.getElementById('exp').addEventListener('click',function(){
  var on=[],off=[];S.forEach(function(t){(checked[t.id]?on:off).push(t.id)});
  var out={generatedAt:new Date().toISOString(),checked:on,unchecked:off};
  var na=Object.keys(assign).length;
  if(na)out.assign=assign;      /* 归属调整随勾选结果一起导出 */
  var b=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
  var a=document.createElement('a');a.href=URL.createObjectURL(b);
  a.download='checked.json';a.click();URL.revokeObjectURL(a.href);
  document.getElementById('tip').textContent='已导出 checked.json（'+on.length+' 条勾选'+
  (na?('、'+na+' 条归属调整'):'')+'）';});
document.getElementById('clr').addEventListener('click',function(){
  checked={};save();draw();document.getElementById('tip').textContent='本地勾选已清空';});
draw();
})();
</script>
</body>
</html>
"""


def render(data_path, out_path, state_path=None, title=None):
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    sessions = data.get("sessions") or []
    projects = data.get("projects") or []

    state = {}
    if state_path and os.path.isfile(state_path):
        try:
            with open(state_path, encoding="utf-8") as f:
                state = json.load(f) or {}
        except Exception as e:
            sys.stderr.write(f"[warn] 判定档案读取失败：{e}\n")

    proj_name = {p.get("id"): p.get("name") or "" for p in projects}

    payload = {
        "sessions": sessions,
        "projects": projects,
        "state": {"done": list((state.get("done") or {}).keys())},
        "meta": {
            "generatedAt": __import__("time").strftime("%Y-%m-%d %H:%M"),
            "data": os.path.basename(data_path),
        },
    }
    blob = json.dumps(payload, ensure_ascii=False)
    # 防止 JSON 里的 "</script" 提前闭合脚本块
    blob = blob.replace("</", "<\\/")

    stale_days = "14"
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(data_path)),
                                "harvest.config.json")
        if os.path.isfile(cfg_path):
            with open(cfg_path, encoding="utf-8") as f:
                stale_days = str(json.load(f).get("stale_days", 14))
    except Exception:
        pass

    doc = (TEMPLATE
           .replace("__TITLE__", html.escape(title or "待办清单"))
           .replace("__DATA__", blob)
           .replace("__STALE__", stale_days))

    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(doc)
    os.replace(tmp, out_path)          # 原子替换

    n_done = sum(1 for s in sessions if s.get("done"))
    print(f"✅ 已生成 {out_path}｜条目 {len(sessions)} 条（已完成 {n_done}）｜项目 {len(projects)} 个")
    return out_path


def main():
    p = argparse.ArgumentParser(description="把待办清单渲染成本地 HTML 页面")
    p.add_argument("--data", default=os.path.join(HERE, "todos.json"), help="todos.json 路径")
    p.add_argument("--state", default=os.path.join(HERE, "todo-state.json"), help="判定档案路径")
    p.add_argument("--out", default=None, help="输出 HTML 路径（默认与 data 同目录 todos.html）")
    p.add_argument("--title", default="待办清单", help="页面标题")
    args = p.parse_args()

    if not os.path.isfile(args.data):
        print(f"❌ 找不到 {args.data}，先跑 harvest.py 生成清单")
        return 1
    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.data)), "todos.html")
    render(args.data, out, args.state, args.title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
