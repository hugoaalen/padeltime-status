import unittest
from datetime import datetime,timezone,timedelta
from urllib.error import HTTPError,URLError
from monitor import diagnose,probe,confirmed_probe,reconcile,GitHub,MARKER,TITLE
NOW=datetime(2026,11,15,12,tzinfo=timezone.utc)
def healthy(**patch):
 value={'demo':False,'fetched_at':NOW.isoformat(),'collector':{'enabled':True,'state':'running','last_attempt':NOW.isoformat(),'last_success':NOW.isoformat()},'service':{'issues':[]}}
 value.update(patch);return value
class HealthTests(unittest.TestCase):
 def test_fresh_running_and_idle_without_matches(self):
  self.assertEqual(diagnose(healthy(),NOW),[])
  data=healthy(fetched_at='2020-01-01T00:00:00Z');data['collector']['state']='idle'
  data['service']['issues']=['schedule_pending','source_delayed']
  self.assertEqual(diagnose(data,NOW),[])
 def test_clock_stopped_even_when_endpoint_returns_200(self):
  data=healthy();data['collector']['last_attempt']=(NOW-timedelta(minutes=11)).isoformat()
  self.assertIn('collector_stopped',diagnose(data,NOW))
 def test_stalled_success_and_stale_active_source(self):
  data=healthy(fetched_at=(NOW-timedelta(minutes=11)).isoformat());data['collector']['last_success']=None
  self.assertEqual(diagnose(data,NOW),['collection_stalled','source_delayed'])
 def test_blocked_or_free_limit_is_not_silently_healthy(self):
  data=healthy();data['collector']['state']='blocked';data['service']['issues']=['source_blocked','free_limit_reached']
  self.assertEqual(diagnose(data,NOW),['collection_failed','free_limit_reached','source_blocked'])
 def test_malformed_demo_timezone_and_future_clock(self):
  self.assertEqual(diagnose({'demo':True},NOW),['invalid_health'])
  self.assertEqual(diagnose(healthy(collector=None),NOW),['collector_unconfigured'])
  data=healthy();data['collector']['last_success']='2026-11-15T12:00:00'
  self.assertIn('collection_stalled',diagnose(data,NOW))
  data=healthy();data['collector']['last_attempt']=(NOW+timedelta(minutes=3)).isoformat()
  self.assertIn('clock_invalid',diagnose(data,NOW))
 def test_http_redirect_and_network_errors_do_not_become_success(self):
  def redirect(url):raise HTTPError(url,302,'redirect',{},None)
  def offline(url):raise URLError('private diagnostic not logged')
  self.assertEqual(probe(redirect,NOW),['http_302']);self.assertEqual(probe(offline,NOW),['unreachable'])
 def test_two_failures_required_and_transient_failure_recovers(self):
  checks=iter([['unreachable'],[]]);waits=[]
  self.assertEqual(confirmed_probe(lambda:next(checks),waits.append),[]);self.assertEqual(waits,[15])
  self.assertEqual(confirmed_probe(lambda:['unreachable'],lambda _:None),['unreachable'])
class FakeGitHub:
 def __init__(self,opened=None):self.opened=opened or [];self.calls=[]
 def incidents(self):return self.opened
 def open(self,issues,url,drill=False):self.calls.append(('open',issues,drill));return {'number':1}
 def recover(self,issue,url):self.calls.append(('recover',issue['number']))
class NotificationTests(unittest.TestCase):
 def test_first_failure_creates_one_incident_and_repeats_do_not_spam(self):
  gh=FakeGitHub();self.assertEqual(reconcile(gh,['unreachable'],'run'),'incident_opened');self.assertEqual(len(gh.calls),1)
  gh=FakeGitHub([{'number':1}]);self.assertEqual(reconcile(gh,['source_delayed'],'run'),'incident_existing');self.assertEqual(gh.calls,[])
 def test_recovery_closes_existing_incident_and_healthy_run_is_silent(self):
  gh=FakeGitHub([{'number':1}]);self.assertEqual(reconcile(gh,[],'run'),'recovered');self.assertEqual(gh.calls,[('recover',1)])
  gh=FakeGitHub();self.assertEqual(reconcile(gh,[],'run'),'healthy');self.assertEqual(gh.calls,[])
 def test_drill_is_labelled_and_does_not_claim_real_service_failure(self):
  gh=FakeGitHub();self.assertEqual(reconcile(gh,[],'run',True),'drill_sent');self.assertEqual(gh.calls,[('open',['notification_drill'],True),('recover',1)])
 def test_public_issue_spoof_cannot_suppress_monitor_notification(self):
  rows=[{'title':TITLE,'body':MARKER,'user':{'login':'attacker'}},{'title':TITLE,'body':MARKER,'user':{'login':'github-actions[bot]'},'number':2}]
  gh=GitHub('fake',lambda *args:rows);self.assertEqual([i['number'] for i in gh.incidents()],[2])
if __name__=='__main__':unittest.main()
