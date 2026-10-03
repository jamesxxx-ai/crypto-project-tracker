/* Optional project intelligence, preserving provider attribution and observation times. */
const intelligenceLabels={listing:'交易所公告',funding:'资金费率',liquidation:'大额清算',flow:'资金动态',oi:'短时 OI',price:'价格异动'};
let intelligenceFilter='all';
function foldLiquidations(rows){const groups=new Map();return rows.filter(e=>{if(e.providerKind!=='liquidation')return true;const key=e.p+'|'+e.source+'|'+Math.floor(e.publishedAt/900000);if(!groups.has(key)){groups.set(key,e);return true}return false}).map(e=>e.providerKind==='liquidation'?{...e,foldedCount:rows.filter(x=>x.providerKind==='liquidation'&&x.p===e.p&&x.source===e.source&&Math.floor(x.publishedAt/900000)===Math.floor(e.publishedAt/900000)).length}:e)}
function nearbySignals(rows,event){return rows.filter(x=>x.id!==event.id&&x.p===event.p&&x.providerKind&&Math.abs(x.publishedAt-event.publishedAt)<=3600000).sort((a,b)=>a.publishedAt-b.publishedAt).slice(0,12)}
function upcomingCalendarItems(calendar,now=Date.now()){
 return (calendar.items||[]).filter(i=>{
  if(i.precision==='exact'&&Number.isFinite(i.at))return i.at>=now;
  let date;try{date=new Intl.DateTimeFormat('sv-SE',{timeZone:i.timeZone||'UTC'}).format(now)}catch{date=new Date(now).toISOString().slice(0,10)}
  return /^\d{4}-\d{2}-\d{2}$/.test(i.date)&&i.date>=date;
 }).sort((a,b)=>a.date.localeCompare(b.date)||(a.at||a.windowStart||a.windowEnd||0)-(b.at||b.windowStart||b.windowEnd||0));
}
function calendarTimeLabel(item,format){
 if(item.precision==='exact'&&Number.isFinite(item.at))return format(item.at);
 if(item.precision==='session'){
  if(item.constraint==='after'&&Number.isFinite(item.windowStart))return format(item.windowStart)+' 之后 · 仅时段';
  if(item.constraint==='before'&&Number.isFinite(item.windowEnd))return format(item.windowEnd)+' 之前 · 仅时段';
  return item.date+' · '+({pre_market:'盘前',post_market:'盘后',during_market:'盘中'}[item.session]||'时间待定')+'（来源时区）';
 }
 return item.date+' · 仅日期，时间待定（来源时区）';
}
if(typeof document!=='undefined'){
 const oldFilterIntelligence=filteredEvents;
 filteredEvents=function(){let rows=oldFilterIntelligence();if(intelligenceFilter!=='all')rows=rows.filter(e=>e.providerKind===intelligenceFilter);return foldLiquidations(rows)};
 const oldCardIntelligence=eventCard;
 eventCard=function(e){let value=oldCardIntelligence(e);if(!e.providerKind)return value;return value.replace('<div class="event-bottom">',`<div class="event-bottom"><span class="tag">${escapeHtml(intelligenceLabels[e.providerKind])}${e.listingType?' · '+escapeHtml(e.listingType):''}</span>${e.foldedCount>1?`<span class="tag">同项目同来源 15 分钟内 ${e.foldedCount} 条 · 展开详情查看</span>`:''}`)};
 function eventButtons(rows){return rows.map(e=>`<button class="intel-event" data-event="${e.id}"><small>${formatTime(e.publishedAt)} · ${escapeHtml(e.source)} · ${escapeHtml(intelligenceLabels[e.providerKind]||'动态')}</small><span>${escapeHtml(e.titleZh||e.title)}</span></button>`).join('')||'<p class="module-note">当前已采集样本暂无相关事件。</p>'}
 const oldRenderIntelligence=render;
 render=function(){oldRenderIntelligence();const data=liveData?.intelligence;if(!data||state.view!=='feed')return;
  const controls=$('#feed-controls');if(controls&&!$('#intelligence-filter'))controls.insertAdjacentHTML('beforeend',`<label class="intel-filter">事件分类 <select id="intelligence-filter"><option value="all">全部</option>${Object.entries(intelligenceLabels).map(([k,v])=>`<option value="${k}" ${k===intelligenceFilter?'selected':''}>${v}</option>`).join('')}</select></label>`);
  if($('#intelligence-filter'))$('#intelligence-filter').value=intelligenceFilter;
  const statuses=Object.entries(data.sources||{}).map(([k,v])=>`${k}：${v.status==='ok'?'最近成功 '+formatTime(v.lastSuccessAt)+(Date.now()-v.lastSuccessAt>900000?' · 数据可能过期':'')+(v.count?'':' · 本轮无匹配')+(v.limited?' · 已达单轮上限':''):v.status==='missing_credential'?'未配置凭证':'采集失败'+(v.lastSuccessAt?' · 保留 '+formatTime(v.lastSuccessAt)+' 的结果':'')}`).join('；');
  if(state.project){const rows=events.filter(e=>e.p===state.project&&e.providerKind);const block=`<section class="project-section intelligence-panel"><h3>资金与市场异动</h3><p class="module-note">OpenNews 事件流 · 每 5 分钟检查 · 每类首批最多 100 条，非完整历史。费率、清算和 OI 的单位与周期以原文为准；缺失数值不补造。</p><p class="module-note">${escapeHtml(statuses)}</p>${['listing','funding','liquidation','flow','oi'].map(k=>`<details class="intel-group" ${k==='funding'?'open':''}><summary>${intelligenceLabels[k]} · ${rows.filter(e=>e.providerKind===k).length} 条</summary>${eventButtons(foldLiquidations(rows.filter(e=>e.providerKind===k)).slice(0,8))}</details>`).join('')}</section>`;
   const chart=document.querySelector('.linked-chart');if(chart)chart.insertAdjacentHTML('afterend',block);else $('#project-overview').insertAdjacentHTML('beforeend',block);
  }else if(state.view==='feed'){const calendar=data.calendar||{};const items=upcomingCalendarItems(calendar);const estimated=items.filter(i=>i.estimated).length;
   const macroItems=items.filter(i=>i.category!=='earnings'),earningsItems=items.filter(i=>i.category==='earnings');
   const itemHtml=i=>`<article><div class="calendar-item-heading"><strong>${escapeHtml(i.labelZh||i.titleZh||i.title)}</strong><span class="tag ${i.estimated?'calendar-estimated':''}">${i.estimated?'预计 · 待核对':i.sourceStatus==='official_schedule'?'供应方标为官方日程':i.sourceStatus==='provider_schedule'?'供应方收录日程':'来源状态未说明'}</span></div><p>${escapeHtml(calendarTimeLabel(i,formatTime))}</p><small>${escapeHtml(i.source||'OpenNews 日历')}${i.timeZone?' · 来源时区 '+escapeHtml(i.timeZone):''}${i.ticker?' · '+escapeHtml(i.ticker):''}</small>${i.url?` <a href="${escapeHtml(safeUrl(i.url))}" target="_blank" rel="noopener noreferrer">核对来源 ↗</a>`:''}<details><summary>显示原文</summary><p>${escapeHtml(i.title)}</p></details></article>`;
   $('#feed').insertAdjacentHTML('afterbegin',`<details class="macro-calendar" data-reader-key="macro-calendar"><summary>未来重要事件 <span>未来两周 · ${items.length} 项${estimated?' · '+estimated+' 项预计':''}</span></summary><p class="module-note">OpenNews · 每小时检查 · 时间已转换为本机时区（${escapeHtml(Intl.DateTimeFormat().resolvedOptions().timeZone)}），仅日期按来源时区保留。${calendar.status==='ok'||calendar.status==='partial'?'最近成功 '+formatTime(calendar.lastSuccessAt):calendar.status==='missing_credential'?'未配置凭证':calendar.status==='pending'?'等待首次查询':'接口暂不可用，保留已有结果'}。${calendar.status==='partial'?'仅返回部分结果。':''}${calendar.lastSuccessAt&&Date.now()-calendar.lastSuccessAt>7200000?'缓存超过两小时，日程可能过期。':''}${calendar.status==='error'?escapeHtml(calendar.errorMessage||'未取得有效响应')+(calendar.httpStatus?'（HTTP '+Number(calendar.httpStatus)+'）':'')+'；最近尝试 '+formatTime(calendar.lastAttemptAt)+'。':''}${calendar.limited?'已达单轮上限，可能不完整。':''}</p><p class="module-note">预计日期按规律或供应方预估生成，尚未逐条核实；此日历仅供查阅，不自动触发提醒。财报只覆盖供应方配置的公司，不是关注代币的解锁日历。</p>${macroItems.length?`<h4>宏观经济 · ${macroItems.length}</h4>${macroItems.map(itemHtml).join('')}`:''}${earningsItems.length?`<h4>公司财报相关日程 · ${earningsItems.length}</h4>${earningsItems.map(itemHtml).join('')}`:''}${!items.length?'<p>本次查询没有可展示的未来日程；不代表未来没有重要事件。</p>':''}</details><p class="module-note intel-status">${escapeHtml(statuses)}</p>`);
  }
 };
 const oldDetailIntelligence=openDetail;
 openDetail=function(id){oldDetailIntelligence(id);const e=events.find(x=>x.id===id);if(!e)return;const footer=$('#detail-content .modal-footer');
  if(e.providerKind){footer?.insertAdjacentHTML('beforebegin',`<div class="evidence">${escapeHtml(intelligenceLabels[e.providerKind])} · ${escapeHtml(e.providerSubtype||'')} · ${escapeHtml(e.source)}<br>供应方事件记录，非实时完整行情。${e.amountUsd!=null?'明确标注的清算金额 $'+number(e.amountUsd):''}${!e.url?'<br>此事件未提供原文链接；保留供应方原文与事件编号。':''}<br>供应方事件编号：${escapeHtml(e.providerId||'未提供')}</div>`);
   if(!e.url)document.querySelectorAll('#detail-content .source-row a').forEach(a=>{const span=document.createElement('span');span.textContent=e.source+' · 未提供链接';a.replaceWith(span)});
  }
  if(e.providerKind==='liquidation'){const matches=events.filter(x=>x.providerKind==='liquidation'&&x.p===e.p&&x.source===e.source&&Math.floor(x.publishedAt/900000)===Math.floor(e.publishedAt/900000));if(matches.length>1)footer?.insertAdjacentHTML('beforebegin',`<section class="intel-context"><h3>同一时间段清算记录</h3>${matches.map(x=>`<p>${formatTime(x.publishedAt)} · ${escapeHtml(x.summaryZh||x.summary)}</p>`).join('')}</section>`)}
  if(e.type==='news'&&e.publishedAt){footer?.insertAdjacentHTML('beforebegin',`<section class="intel-context"><h3>消息与行情一起看</h3><p class="module-note">同项目、消息前后各 1 小时内的已采集异动。时间接近不代表因果关系；不以当前价格冒充事件发生时价格。</p>${eventButtons(nearbySignals(events,e))}<button class="secondary" data-intel-chart="${escapeHtml(e.p)}">打开 K 线与新闻标记</button></section>`)}
 };
 document.addEventListener('change',e=>{if(e.target.id==='intelligence-filter'){intelligenceFilter=e.target.value;render()}});
 document.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.intelChart){$('#detail-dialog').close();state.project=b.dataset.intelChart;state.view='feed';intelligenceFilter='all';render();document.querySelector('.linked-chart')?.scrollIntoView({behavior:'smooth'})}});
 document.addEventListener('click',e=>{const b=e.target.closest('button');if(b&&(b.dataset.project||b.dataset.view||b.dataset.action==='clear'))intelligenceFilter='all'},true);
 render();
}
