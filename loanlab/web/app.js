const $ = id => document.getElementById(id);
const names = {create_pending_loan:'准备待审批贷款',withdraw_loan:'提交撤回请求',verify_withdrawn:'核验最终状态'};
function node(tag, text, className){const el=document.createElement(tag); if(text!==undefined)el.textContent=text; if(className)el.className=className; return el;}
function render(report){
  $('planner-info').textContent=report.planner+(report.model_calls!==undefined?' · 模型请求 '+report.model_calls+' 次 · Token '+JSON.stringify(report.token_usage):'');
  $('empty').hidden=true; $('result').hidden=false;
  $('result-badge').textContent=report.status; $('result-badge').className='result-badge '+report.status;
  $('status').textContent=report.status; $('status').className=report.status;
  $('virtual').textContent=report.virtual_seconds===undefined?'—':report.virtual_seconds+' s';
  $('elapsed').textContent=report.elapsed_ms+' ms';
  $('trace').replaceChildren();
  for(const step of report.trace){const row=node('div',undefined,'step');const title=node('div',undefined,'step-title');title.append(node('span',names[step.tool]||step.tool),node('span',step.status,step.status));row.append(title,node('pre',JSON.stringify({input:step.args,output:step.output,error:step.error},null,2)));$('trace').append(row);}
  if(!report.trace.length)$('trace').append(node('p','计划未通过校验，没有执行任何工具。'));
  $('polls').replaceChildren();
  for(const item of report.polls)$('polls').append(node('div',`t=${item.virtual_second}s  ${item.status||item.error}`,'poll'));
  if(!report.polls.length)$('polls').append(node('p','没有查询记录'));
  $('evidence').textContent=JSON.stringify(report.evidence,null,2);
  $('diagnosis').replaceChildren();
  for(const [key,label] of [['fact','事实'],['root_cause','根因'],['next_step','下一步']]){if(report.diagnosis?.[key])$('diagnosis').append(node('div',label+'：'+report.diagnosis[key]));}
  $('download').href='/api/runs/'+report.run_id; $('download').download='loan-qa-'+report.run_id+'.json';
}
async function refreshHistory(){const r=await fetch('/api/runs');if(!r.ok)throw new Error('读取历史失败');const items=await r.json();$('history').replaceChildren();if(!items.length){$('history').textContent='暂无执行记录';return;}for(const item of items){const row=node('div',undefined,'history-row');row.tabIndex=0;row.setAttribute('role','button');row.append(node('span',item.status,item.status),node('span',item.scenario_label),node('small',new Date(item.created_at).toLocaleString('zh-CN')));const open=async()=>{try{const r=await fetch('/api/runs/'+item.run_id);if(!r.ok)throw new Error('报告读取失败');render(await r.json());}catch(e){$('error').textContent=e.message;}};row.onclick=open;row.onkeydown=e=>{if(e.key==='Enter')open();};$('history').append(row);}}
$('run').onclick=async()=>{const button=$('run');button.disabled=true;$('error').textContent='';button.textContent='正在执行…';try{const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task:$('task').value,scenario:$('scenario').value,planner:$('planner').value})});const data=await r.json();if(!r.ok)throw new Error(data.error||'执行失败');render(data);await refreshHistory();}catch(e){$('error').textContent=e.message;}finally{button.disabled=false;button.textContent='执行测试 →';}};
refreshHistory().catch(e=>{$('error').textContent=e.message;});

fetch('/api/config').then(r=>r.json()).then(c=>{$('model-status').textContent=(c.model_configured?'已检测到本机模型密钥，尚需实测连接。':'未配置模型密钥；选择 DeepSeek 会返回 ERROR。')+' 业务使用模拟数据与虚拟时间，不代表真实系统性能。';}).catch(()=>{$('model-status').textContent='配置状态读取失败';});

$('business-run').onclick=async()=>{const b=$('business-run');b.disabled=true;try{const r=await fetch('/api/business-suite',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await r.json();if(!r.ok)throw new Error(data.error||'业务套件失败');$('business-output').hidden=false;$('business-output').textContent=JSON.stringify(data,null,2);}catch(e){$('error').textContent=e.message;}finally{b.disabled=false;}};
