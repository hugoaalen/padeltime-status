"""Public, independent PadelTime health monitor. Standard library only."""
import json
import os
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

HEALTH_URL='https://padeltime-two.vercel.app/api/health'
REPOSITORY='hugoaalen/padeltime-status'
MARKER='<!-- padeltime-monitor-incident-v1 -->'
TITLE='PadelTime: incidencia del servicio'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def request_json(url,method='GET',data=None,token=None):
    headers={'Accept':'application/json','User-Agent':'PadelTime-Monitor/1.0','Cache-Control':'no-cache'}
    if token:
        if not url.startswith('https://api.github.com/repos/'+REPOSITORY+'/'):raise ValueError('Unexpected authenticated destination')
        headers.update(Authorization='Bearer '+token,**{'X-GitHub-Api-Version':'2022-11-28'})
    body=json.dumps(data).encode() if data is not None else None
    if body is not None:headers['Content-Type']='application/json'
    with build_opener(NoRedirect()).open(Request(url,data=body,headers=headers,method=method),timeout=12) as response:
        raw=response.read(131073)
        if len(raw)>131072:raise ValueError('Response too large')
        return json.loads(raw) if raw else {}

def age(value,now):
    if not isinstance(value,str):return None
    try:
        date=datetime.fromisoformat(value.replace('Z','+00:00'))
        if date.tzinfo is None:return None
        return (now-date).total_seconds()
    except ValueError:return None

def diagnose(data,now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(data,dict) or data.get('demo') is not False:return ['invalid_health']
    collector=data.get('collector')
    if not isinstance(collector,dict) or collector.get('enabled') is not True:return ['collector_unconfigured']
    issues=[]
    for key,label in [('last_attempt','collector_stopped'),('last_success','collection_stalled')]:
        seconds=age(collector.get(key),now)
        if seconds is None or seconds>600:issues.append(label)
        elif seconds< -60:issues.append('clock_invalid')
    if collector.get('state') in {'blocked','error'}:issues.append('collection_failed')
    if collector.get('state')!='idle':
        seconds=age(data.get('fetched_at'),now)
        if seconds is None or seconds>600:issues.append('source_delayed')
        elif seconds< -60:issues.append('clock_invalid')
    service=data.get('service')
    if isinstance(service,dict):
        advertised=service.get('issues',[])
        if isinstance(advertised,list):issues.extend(code for code in advertised if code in {'source_blocked','free_limit_reached'})
    return sorted(set(issues))

class AppPage(HTMLParser):
    def __init__(self):super().__init__();self.root=False;self.bundle=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='div' and attrs.get('id')=='root':self.root=True
        if tag=='script' and attrs.get('type')=='module' and re.fullmatch(r'/assets/[a-zA-Z0-9_.-]+\.js',attrs.get('src','')):self.bundle=attrs['src']

def check_frontend():
    opener=build_opener(NoRedirect());base='https://padeltime-two.vercel.app'
    with opener.open(Request(base+'/',headers={'User-Agent':'PadelTime-Monitor/1.0','Cache-Control':'no-cache'}),timeout=12) as response:
        raw=response.read(524289)
        if len(raw)>524288:return ['invalid_frontend']
        page=AppPage();page.feed(raw.decode('utf-8'))
        if not page.root or not page.bundle:return ['invalid_frontend']
    with opener.open(Request(base+page.bundle,method='HEAD'),timeout=12) as response:
        if 'javascript' not in response.headers.get('Content-Type','').lower():return ['invalid_frontend_bundle']
    return []

def probe(get=request_json,now=None,frontend=check_frontend):
    checked=now or datetime.now(timezone.utc)
    try:
        issues=diagnose(get(HEALTH_URL+'?monitor='+str(int(checked.timestamp()))),checked)
        return issues or frontend()
    except HTTPError as error:return ['http_'+str(error.code)]
    except (URLError,TimeoutError,OSError):return ['unreachable']
    except (ValueError,TypeError):return ['invalid_health']

def confirmed_probe(check=probe,pause=time.sleep):
    first=check()
    if not first:return []
    pause(15)
    return check()

class GitHub:
    def __init__(self,token,call=request_json):self.token=token;self.call=call
    def api(self,path,method='GET',data=None):return self.call('https://api.github.com/repos/'+REPOSITORY+'/'+path,method,data,self.token)
    def incidents(self):
        rows=self.api('issues?state=open&per_page=100')
        if not isinstance(rows,list):raise ValueError('Invalid issue response')
        return [row for row in rows if not row.get('pull_request') and row.get('title')==TITLE and MARKER in (row.get('body') or '') and row.get('user',{}).get('login')=='github-actions[bot]']
    def open(self,issues,run_url,drill=False):
        title='[PRUEBA] PadelTime: aviso del monitor' if drill else TITLE
        body=('Simulacro solicitado; no indica una caída real.\n\n' if drill else MARKER+'\n\n')+'Comprobaciones: '+', '.join(issues)+'.\n\nEjecución: '+run_url+'\n\nFuente: '+HEALTH_URL+'\n\nSe comprueba de nuevo en el siguiente ciclo. No se incluyen datos de usuarios.'
        return self.api('issues','POST',{'title':title,'body':body,'assignees':['hugoaalen']})
    def recover(self,issue,run_url):
        number=issue['number']
        if not isinstance(number,int) or number<=0:raise ValueError('Invalid issue number')
        self.api('issues/'+str(number)+'/comments','POST',{'body':'Servicio comprobado sin incidencias. Ejecución: '+run_url})
        self.api('issues/'+str(number),'PATCH',{'state':'closed','state_reason':'completed'})

def reconcile(github,issues,run_url,drill=False):
    if drill:
        issue=github.open(['notification_drill'],run_url,True)
        github.recover(issue,run_url)
        return 'drill_sent'
    opened=github.incidents()
    if issues:
        if not opened:github.open(issues,run_url)
        return 'incident_existing' if opened else 'incident_opened'
    for issue in opened:github.recover(issue,run_url)
    return 'recovered' if opened else 'healthy'

def main():
    # Job-level guard also prevents a private fork from scheduling a paid runner.
    if os.getenv('GITHUB_REPOSITORY')!=REPOSITORY:raise ValueError('Unexpected repository')
    run=os.environ['GITHUB_RUN_ID']
    if not re.fullmatch(r'\d+',run):raise ValueError('Invalid run identifier')
    run_url='https://github.com/'+REPOSITORY+'/actions/runs/'+run
    drill=os.getenv('MONITOR_DRILL')=='true'
    issues=[] if drill else confirmed_probe()
    state=reconcile(GitHub(os.environ['GITHUB_TOKEN']),issues,run_url,drill)
    summary='PadelTime monitor: '+state+'\nChecks: '+(', '.join(issues) or 'ok')+'\n'
    print(summary)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as file:file.write(summary+'\nService incidents are tracked in Issues; a successful monitor run means the check and notification process completed.\n')

if __name__=='__main__':main()
