"""Evidence-preserving OpenNews signals and macro calendar; no trading actions."""
import datetime as dt,hashlib,html,json,re,threading,time,urllib.error
from pathlib import Path
from zoneinfo import ZoneInfo
from html.parser import HTMLParser
LABELS={'listing':'交易所公告','funding':'资金费率','liquidation':'大额清算','flow':'资金动态','oi':'短时 OI','price':'价格异动'}
class Text(HTMLParser):
 def __init__(self):super().__init__();self.parts=[]
 def handle_data(self,data):self.parts.append(data)
 def handle_starttag(self,tag,attrs):
  if tag in {'br','p','div'}:self.parts.append(' ')
def plain(value):
 parser=Text();parser.feed(str(value or ''));return ' '.join(html.unescape(' '.join(parser.parts)).split())
def kind(row):
 engine=row.get('engineType');source=row.get('newsType','')
 if engine=='listing':return 'listing'
 if source in {'funding_rate','funding_diff'}:return 'funding'
 if source=='liquidation':return 'liquidation'
 if source in {'smart_money','6551OnChain'} or engine=='onchain':return 'flow'
 if engine=='market' and source in {'oi_change','price_change'}:return 'oi' if source=='oi_change' else 'price'
 return None
def listing_type(text):
 for name,pattern in [('下架',r'delist|下架'),('充提调整',r'withdraw|deposit|充提|提币|提款|充值'),('合约调整',r'perpetual|futures|leverage|合约|杠杆'),('上币',r'will list|new listing|trading.*(?:start|open)|上线|上市')]:
  if re.search(pattern,text,re.I):return name
 return '其他公告'
def amount(text):
 # Only use explicitly labelled liquidation amount, never position size or a price.
 match=re.search(r'(?:liquidat(?:ed|ion)(?:\s+(?:value|amount))?|清算金额|爆仓金额)\s*[:：]?\s*\$([\d,]+(?:\.\d+)?)\s*([KMB])?\b',text,re.I)
 if not match:return None
 return float(match[1].replace(',',''))*{'K':1e3,'M':1e6,'B':1e9}.get((match[2] or '').upper(),1)
def normalize(row,p,stamp,current):
 category=kind(row)
 if not category:return None
 text=plain(row.get('text'));symbol=p['symbol'].upper()
 coins={str(c.get('symbol','')).upper() for c in row.get('coins',[]) if isinstance(c,dict)}
 # Provider mapping PLUS explicit token syntax / project identity. Never accept bare NEAR/SOON.
 explicit=bool(re.search(r'\$'+re.escape(symbol)+r'\b|(?<![\w])'+re.escape(symbol)+r'(?:/|[-_])(?:USDT|USD|USDC)\b|(?<![\w])'+re.escape(symbol)+r'USDT\b',text,re.I))
 from news_quality import relevant
 if not ((symbol in coins and (explicit or relevant(p['id'],text,p))) or relevant(p['id'],text,p)):return None
 date=stamp(row.get('ts'))
 if not date or not 0<=current-date<=7*86400000:return None
 rid=str(row.get('id') or hashlib.sha256(text.encode()).hexdigest())
 source=str(row.get('source') or row.get('newsType') or 'OpenNews')
 url=str(row.get('link') or '');url=url if url.startswith('https://') else ''
 return dict(id='news-'+hashlib.sha256((p['id']+'opennews:'+rid).encode()).hexdigest()[:20],providerId=rid,p=p['id'],type='news',channel='opennews',title=text[:140],summary=text,url=url,publishedAt=date,discoveredAt=current,source=source,providerKind=category,providerSubtype=row.get('newsType'),engineType=row.get('engineType'),topic=LABELS[category],listingType=listing_type(text) if category=='listing' else None,amountUsd=amount(text) if category=='liquidation' else None,providerRating=row.get('aiRating') or {},coins=row.get('coins') or [],matchReason='项目标识与来源资产信息匹配，仍需核对同名资产',evidence='OpenNews 事件记录；非连续行情',high=False,priorityReason='按需配置独立提醒',freshness='recent',datePrecision='source')
def merge(old,new,current):
 rows={e['id']:e for e in old if 0<=current-e.get('publishedAt',0)<=7*86400000}
 for e in new:rows[e['id']]={**e,'discoveredAt':rows.get(e['id'],e)['discoveredAt']}
 return sorted(rows.values(),key=lambda e:e['publishedAt'],reverse=True)[:1500]
def calendar_error(error):
 # Persist only allowlisted classifications, never raw provider bodies or exception messages.
 if isinstance(error,urllib.error.HTTPError):
  code=error.code
  if code==400:
   try:
    body=json.loads(error.read(4096))
    if body.get('error')=='query failed':return {'errorCode':'provider_query_failed','errorMessage':'供应方日历查询失败；普通新闻接口可单独使用','httpStatus':400}
   except (ValueError,OSError,AttributeError):pass
  label={400:'供应方拒绝请求，需核对接口参数或服务状态',401:'凭证认证失败',403:'此接口访问被拒绝，请核对权限',404:'供应方接口不存在',429:'供应方限流，稍后重试'}.get(code,'供应方 HTTP 错误')
  return {'errorCode':'http_'+str(code),'errorMessage':label,'httpStatus':code}
 if isinstance(error,TimeoutError) or isinstance(error,urllib.error.URLError) and isinstance(error.reason,TimeoutError):
  return {'errorCode':'timeout','errorMessage':'连接或读取超时，未取得日历结果'}
 if isinstance(error,urllib.error.URLError):return {'errorCode':'network','errorMessage':'网络连接失败，未取得日历结果'}
 if isinstance(error,ValueError) and str(error)=='calendar_shape':return {'errorCode':'schema','errorMessage':'供应方日历格式暂不兼容'}
 return {'errorCode':'provider_response','errorMessage':'供应方未返回可用的日历结果'}
CALENDAR_SCHEMA=2

def calendar_instant(value):
 # A clock time or timezone-free datetime must never become a UTC instant.
 try:
  parsed=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
  if parsed.tzinfo is not None:return int(parsed.timestamp()*1000)
 except (ValueError,TypeError,OverflowError):pass
 return None

def calendar_rows(response,stamp):
 if not isinstance(response,dict) or response.get('success') is False:raise ValueError('calendar_failed')
 data=response.get('data',{})
 if isinstance(data,dict):
  if data.get('status') not in {None,'ok','partial_result'}:raise ValueError('calendar_'+str(data['status']))
  if 'events' not in data and 'items' not in data:raise ValueError('calendar_shape')
  rows=data.get('events',data.get('items'))
 elif isinstance(data,list):rows=data
 else:raise ValueError('calendar_shape')
 if not isinstance(rows,list):raise ValueError('calendar_shape')
 out={}
 for row in rows:
  if not isinstance(row,dict):continue
  title=plain(row.get('title') or row.get('event_name') or row.get('name') or row.get('event'))
  raw=row.get('event_datetime_utc') or row.get('event_datetime_local') or row.get('scheduled_at') or row.get('datetime') or row.get('event_time') or ''
  date=str(row.get('event_date') or row.get('date') or '')
  if not date and re.match(r'^\d{4}-\d{2}-\d{2}',str(raw)):date=str(raw)[:10]
  try:dt.date.fromisoformat(date)
  except (ValueError,TypeError):continue
  if not title:continue
  zone=str(row.get('timezone') or '')
  at=calendar_instant(raw)
  # Accept separate local date/time only with an explicit IANA timezone.
  if at is None and re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?',str(raw)) and zone:
   try:
    local=dt.datetime.fromisoformat(date+'T'+raw);tz=ZoneInfo(zone)
    candidate=local.replace(tzinfo=tz)
    # Ambiguous/nonexistent DST wall times remain unresolved.
    if candidate.utcoffset()==candidate.replace(fold=1).utcoffset() and candidate.astimezone(dt.timezone.utc).astimezone(tz).replace(tzinfo=None)==local:at=int(candidate.timestamp()*1000)
   except (ValueError,KeyError,OverflowError):pass
  precision='session' if row.get('time_precision')=='session' or row.get('event_session') else 'exact' if at is not None else 'day'
  if precision=='session':at=None
  source_status=str(row.get('source_status') or '')
  estimated=row.get('estimated_schedule') is True or row.get('status')=='estimated_schedule' or source_status in {'provider_estimate','estimated_schedule'} or isinstance(row.get('raw'),dict) and row['raw'].get('estimated') is True
  url=str(row.get('evidence_url') or row.get('source_url') or row.get('url') or '')
  if not url.startswith('https://'):url=''
  category=str(row.get('category') or '')
  label={'us_cpi':'美国消费者价格指数（CPI）发布','us_ppi':'美国生产者价格指数（PPI）发布','us_nonfarm_payrolls':'美国非农就业数据发布','fomc':'美联储议息日程'}.get(row.get('event_type'))
  if not label and category=='earnings':label=plain(row.get('company_name') or row.get('ticker') or title)+' · '+plain(row.get('fiscal_period'))+' 财报相关日程'
  ident=str(row.get('event_key') or hashlib.sha256((title+date+str(at)).encode()).hexdigest()[:20])
  out[ident]={'id':ident,'title':title,'labelZh':label,'date':date,'at':at,'estimated':bool(estimated),'source':plain(row.get('source')),'sourceStatus':source_status,'url':url,'importance':row.get('importance'),'timeZone':zone,'precision':precision,'category':category,'ticker':plain(row.get('ticker')),'session':row.get('event_session'),'constraint':row.get('time_constraint'),'windowStart':calendar_instant(row.get('time_window_start_utc')),'windowEnd':calendar_instant(row.get('time_window_end_utc'))}
 if rows and not out:raise ValueError('calendar_shape')
 return sorted(out.values(),key=lambda i:(i['date'],i['at'] or i['windowStart'] or i['windowEnd'] or 0,i['id']))

class Store:
 def __init__(self,path):
  self.path=Path(path);self.lock=threading.RLock();self.data={'events':[],'sources':{},'calendar':{'status':'pending','items':[]}}
  if self.path.exists():
   try:self.data.update(json.loads(self.path.read_text()))
   except (ValueError,OSError):pass
 def snapshot(self):
  with self.lock:return json.loads(json.dumps(self.data))
 def collect(self,projects,request,stamp,token):
  current=int(time.time()*1000)
  if not token:
   with self.lock:self.data['sources']={'OpenNews':{'status':'missing_credential'}};self.data['calendar']['status']='missing_credential'
   return
  # Three shared queries per round, not three per project; bounded pagination and visible coverage.
  tasks={'公告':{'listing':[]},'市场异动':{'market':['funding_rate','funding_diff','liquidation','oi_change','price_change','smart_money']},'机构动态':{'news':['6551OnChain']}}
  for label,engines in tasks.items():
   try:
    response=json.loads(request('https://ai.6551.io/open/news_search',{'engineTypes':engines,'coins':list(dict.fromkeys(p['symbol'] for p in projects)),'limit':100,'page':1}))
    if response.get('success') is False or not isinstance(response.get('data'),list):raise ValueError('invalid_response')
    incoming=[e for r in response['data'] for p in projects if (e:=normalize(r,p,stamp,current))]
    with self.lock:
     self.data['events']=merge(self.data['events'],incoming,current);self.data['sources'][label]={'status':'ok','lastSuccessAt':current,'count':len(incoming),'returned':len(response['data']),'limited':len(response['data'])>=100}
   except Exception:
    with self.lock:self.data['sources'][label]={**self.data['sources'].get(label,{}),'status':'error','lastAttemptAt':current}
  self.collect_calendar(request,stamp,token)
  with self.lock:
   self.data['events']=merge(self.data['events'],[],current)
   self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.data,ensure_ascii=False));tmp.replace(self.path)

 def collect_calendar(self,request,stamp,token,force=False):
  current=int(time.time()*1000)
  with self.lock:
   previous=self.data['calendar'];last=previous.get('lastAttemptAt',0)
   if not token:self.data['calendar']={**previous,'status':'missing_credential'};return
   if not force and previous.get('schemaVersion')==CALENDAR_SCHEMA and current-last<3600000:return
  today=dt.datetime.now(dt.timezone.utc).date();query={'start_date':str(today),'end_date':str(today+dt.timedelta(days=14)),'importance':'high','limit':50}
  try:
   response=json.loads(request('https://ai.6551.io/open/finance-enhance/key-market-events',query))
   items=calendar_rows(response,stamp);data=response.get('data',{})
   with self.lock:self.data['calendar']={'status':'partial' if isinstance(data,dict) and data.get('status')=='partial_result' else 'ok','items':items,'lastSuccessAt':current,'lastAttemptAt':current,'schemaVersion':CALENDAR_SCHEMA,'query':query,'limited':len(items)>=query['limit']}
  except Exception as error:
   with self.lock:self.data['calendar']={**self.data['calendar'],'status':'error','lastAttemptAt':current,'schemaVersion':CALENDAR_SCHEMA,**calendar_error(error)}
  with self.lock:
   self.path.parent.mkdir(parents=True,exist_ok=True);tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(self.data,ensure_ascii=False));tmp.replace(self.path)
