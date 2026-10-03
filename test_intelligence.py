import unittest,tempfile,json
from pathlib import Path
from intelligence import normalize,merge,calendar_rows,calendar_error,listing_type,Store
from alerts import evaluate,validate
NOW=1800000000000
P={'id':'near','name':'NEAR Protocol','symbol':'NEAR','account':'NEARProtocol'}
class IntelligenceTests(unittest.TestCase):
 def row(self,**kw):return {'id':'1','text':'NEAR/USDT OI 5min Down 5%','ts':NOW,'engineType':'market','newsType':'oi_change','coins':[{'symbol':'NEAR'}],**kw}
 def test_no_url_keeps_distinct_events_and_html_is_plain(self):
  a=normalize(self.row(text='<b>NEAR/USDT</b> OI 5min Down 5%'),P,lambda x:x,NOW)
  b=normalize(self.row(id='2'),P,lambda x:x,NOW)
  self.assertEqual(a['url'],'');self.assertNotIn('<b>',a['summary']);self.assertEqual(len(merge([], [a,b],NOW)),2)
  self.assertEqual(len(merge([a,b],[a],NOW)),2)
 def test_ambiguous_mapping_future_and_old_rejected(self):
  for r in [self.row(text='near the station'),self.row(ts=NOW+1),self.row(ts=NOW-8*86400000)]:self.assertIsNone(normalize(r,P,lambda x:x,NOW))
 def test_listing_classification_does_not_claim_generic_comments_are_listings(self):
  self.assertEqual(listing_type('Coinbase CEO likes Linux'),'其他公告');self.assertEqual(listing_type('Withdrawals suspended'),'充提调整');self.assertEqual(listing_type('will delist ABC'),'下架')
 def test_calendar_business_failure_and_unknown_schema_visible(self):
  for response in [{'data':{'status':'upstream_error'}},{'data':{'events':[{'unexpected':1}]}}]:
   with self.assertRaises(ValueError):calendar_rows(response,lambda x:None)
  rows=calendar_rows({'data':{'status':'ok','events':[{'title':'CPI','date':'2026-10-01','estimated_schedule':True}]}},lambda x:None)
  self.assertTrue(rows[0]['estimated']);self.assertEqual(rows[0]['precision'],'day')
 def test_new_event_alerts_dedupe_threshold_and_old_suppression(self):
  rule={'id':'r','p':'near','type':'liquidation','name':'清算','period':'event','threshold':100000,'cooldownMinutes':1,'on':True,'createdAt':NOW-100}
  self.assertEqual(validate(rule,['near'])['period'],'event')
  e=normalize(self.row(newsType='liquidation',text='NEAR/USDT Liquidated: $250K'),P,lambda x:x,NOW)
  self.assertEqual(e['amountUsd'],250000)
  rt={};self.assertEqual(len(evaluate(rule,rt,{},[e],NOW)),1);self.assertEqual(evaluate(rule,rt,{},[e],NOW),[])
  self.assertEqual(evaluate(rule,{}, {},[{**e,'amountUsd':None}],NOW),[])
  self.assertEqual(evaluate(rule,{}, {},[{**e,'publishedAt':NOW-1000}],NOW),[])
 def test_failed_collection_keeps_old_data_and_marks_error(self):
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/'state.json');store.data['calendar']['lastAttemptAt']=9999999999999
   def request(*args):raise ValueError('private token should never appear')
   store.collect([P],request,lambda x:x,True)
   self.assertEqual(store.snapshot()['sources']['公告']['status'],'error')
   self.assertNotIn('private',json.dumps(store.snapshot()))

 def test_calendar_diagnostics_are_specific_and_redacted(self):
  import urllib.error
  self.assertEqual(calendar_error(urllib.error.HTTPError('https://example.test',403,'private token',{},None))['errorCode'],'http_403')
  self.assertEqual(calendar_error(urllib.error.URLError(TimeoutError()))['errorCode'],'timeout')
  self.assertEqual(calendar_error(ValueError('calendar_shape'))['errorCode'],'schema')
  self.assertNotIn('private',json.dumps(calendar_error(ValueError('private token'))))

 def test_provider_query_failure_classification_does_not_save_body(self):
  import urllib.error,io
  error=urllib.error.HTTPError('https://example.test',400,'Bad Request',{},io.BytesIO(b'{"error":"query failed","private":"secret"}'))
  result=calendar_error(error)
  self.assertEqual(result['errorCode'],'provider_query_failed');self.assertEqual(result['httpStatus'],400)
  self.assertNotIn('secret',json.dumps(result));error.close()

class CalendarScheduleTests(unittest.TestCase):
 def rows(self,*rows):return calendar_rows({'success':True,'data':{'events':list(rows)}},lambda x:None)
 def test_utc_datetime_wins_over_clock_time(self):
  row=self.rows({'title':'CPI','event_date':'2026-10-14','event_time':'08:30','event_datetime_utc':'2026-10-14T12:30:00Z','timezone':'America/New_York','source_status':'estimated_schedule','evidence_url':'https://example.test/calendar'})[0]
  self.assertEqual(row['at'],1791981000000);self.assertTrue(row['estimated']);self.assertEqual(row['precision'],'exact');self.assertEqual(row['url'],'https://example.test/calendar')
 def test_session_is_not_exact_and_preserves_window(self):
  row=self.rows({'title':'Earnings','event_date':'2026-10-06','time_precision':'session','event_session':'post_market','source_status':'provider_estimate','time_constraint':'after','time_window_start_utc':'2026-10-06T20:00:00Z'})[0]
  self.assertIsNone(row['at']);self.assertEqual(row['precision'],'session');self.assertTrue(row['estimated']);self.assertIsNotNone(row['windowStart'])
 def test_local_time_requires_timezone_and_unambiguous_dst(self):
  base={'title':'Schedule','event_date':'2026-10-13','event_time':'08:30'}
  self.assertIsNone(self.rows(base)[0]['at'])
  self.assertEqual(self.rows({**base,'timezone':'America/New_York'})[0]['at'],1791894600000)
  ambiguous={**base,'event_date':'2026-11-01','event_time':'01:30','timezone':'America/New_York'}
  self.assertIsNone(self.rows(ambiguous)[0]['at'])
 def test_invalid_dates_rejected_and_duplicate_keys_collapsed(self):
  with self.assertRaises(ValueError):self.rows({'title':'Bad','event_date':'2026-99-99'})
  row={'event_key':'abc','title':'One','date':'2026-10-06'}
  self.assertEqual(len(self.rows(row,row)),1)
 def test_provider_schedule_is_not_estimated_or_independently_verified(self):
  row=self.rows({'title':'Earnings call','event_date':'2026-10-13','source_status':'provider_schedule'})[0]
  self.assertFalse(row['estimated']);self.assertEqual(row['sourceStatus'],'provider_schedule');self.assertIsNone(row['at'])
 def test_collect_recovery_partial_result_throttle_and_failure_cache(self):
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/'state.json');store.data['calendar']={'status':'error','httpStatus':400,'items':[]}
   def request(*args):return json.dumps({'success':True,'data':{'status':'partial_result','events':[{'title':'CPI','date':'2026-10-14'}]}})
   with patch('intelligence.time.time',return_value=NOW/1000):store.collect_calendar(request,lambda x:None,True)
   good=store.snapshot()['calendar'];self.assertEqual(good['status'],'partial');self.assertNotIn('httpStatus',good)
   calls=[]
   with patch('intelligence.time.time',return_value=NOW/1000+10):store.collect_calendar(lambda *args:calls.append(args),lambda x:None,True)
   self.assertEqual(calls,[])
   def fail(*args):raise ValueError('private-token')
   with patch('intelligence.time.time',return_value=NOW/1000+4000):store.collect_calendar(fail,lambda x:None,True)
   bad=store.snapshot()['calendar'];self.assertEqual(bad['status'],'error');self.assertEqual(bad['items'],good['items']);self.assertEqual(bad['lastSuccessAt'],good['lastSuccessAt']);self.assertNotIn('private',json.dumps(bad))
