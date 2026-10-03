const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const {foldLiquidations,nearbySignals}=vm.runInNewContext(fs.readFileSync('dist/intelligence.js','utf8')+';({foldLiquidations,nearbySignals})');
test('liquidation folding keeps projects, venues and time buckets separate',()=>{const a={id:1,p:'near',source:'binance',publishedAt:100,providerKind:'liquidation'};const rows=[a,{...a,id:2},{...a,id:3,source:'bybit'},{...a,id:4,p:'pha'},{...a,id:5,publishedAt:900001}];const result=foldLiquidations(rows);assert.equal(result.length,4);assert.equal(result[0].foldedCount,2);assert.equal(rows[0].foldedCount,undefined)});
test('context only uses same project within one hour, never current snapshot',()=>{const a={id:1,p:'near',publishedAt:10000000};const b={id:2,p:'near',publishedAt:10000001,providerKind:'funding'};assert.equal(nearbySignals([b,{...b,id:3,p:'pha'},{...b,id:4,publishedAt:1}],a).length,1)});
const {upcomingCalendarItems,calendarTimeLabel}=vm.runInNewContext(fs.readFileSync('dist/intelligence.js','utf8')+';({upcomingCalendarItems,calendarTimeLabel})');
test('calendar removes past exact events but keeps date-only events for their source day',()=>{
 const now=Date.parse('2026-10-14T23:00:00Z');const items=[{id:'past',date:'2026-10-14',at:now-1,precision:'exact'},{id:'today',date:'2026-10-14',precision:'day',timeZone:'America/New_York'},{id:'old',date:'2026-10-13',precision:'day'},{id:'missing',date:'08:30',precision:'day'}];
 assert.deepEqual(Array.from(upcomingCalendarItems({items},now),r=>r.id),['today']);
});
test('calendar preserves before/after bounds instead of presenting exact times',()=>{
 assert.equal(calendarTimeLabel({precision:'session',constraint:'after',windowStart:123},String),'123 之后 · 仅时段');
 assert.match(calendarTimeLabel({precision:'day',date:'2026-10-14'},String),/仅日期/);
 assert.equal(calendarTimeLabel({precision:'exact',at:123},String),'123');
});
