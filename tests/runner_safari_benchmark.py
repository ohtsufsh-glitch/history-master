"""Issue #102 benchmark: python tests/runner_safari_benchmark.py [--baseline] [--slow].
Isolated browser/IndexedDB; --baseline serves origin/main from a temporary directory.
"""
import sys,json,subprocess,tempfile,tarfile,io
from pathlib import Path
import plush_test
if '--baseline' in sys.argv:
 temp=tempfile.TemporaryDirectory()
 with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','archive','origin/main'],cwd=plush_test.ROOT))) as archive:
  archive.extractall(temp.name,filter='data')
 plush_test.ROOT=Path(temp.name)
from runner_session_test import RunnerSessionTest
RunnerSessionTest.setUpClass()
t=RunnerSessionTest()
try:
 for n in [0,5000]:
  for run in range(3):
   t.setUp();p=t.page
   p.set_viewport_size(dict(width=390,height=844))
   if '--slow' in sys.argv:
    t.context.new_cdp_session(p).send('Emulation.setCPUThrottlingRate',{'rate':4})
   p.evaluate('''async n=>{
    await install(100); const base=await buy();
    await runnerTransaction(['runnerPlays','reviewEvents'],tx=>{
     for(let i=0;i<n;i++){const record={...base,id:'history'+i,status:'finished',result:{reason:'gameover',at:base.updatedAt,livesRemaining:0}};delete record.snapshot;tx.objectStore('runnerPlays').put(record);}
     for(let i=0;i<n*4;i++)tx.objectStore('reviewEvents').put({key:'history'+i,profile:'student',amount:1});
    });
    await navigate('runner');
   }''',n)
   p.frame_locator('iframe').locator('#runner-toggle').wait_for()
   out=p.evaluate('''async()=>{
    // No rendering-driven motion: drive the real parent bridge in controlled frame batches.
    formalRunner.frame.contentWindow.stopFormalRunner();
    await formalRunner.session.resume();
    const originalSave=saveRunnerState,originalLobby=runnerLobbyData;
    let end=0,saved=0,recalc=0,ui=0,reads=0,refreshes=0,saves=0;
    const orig=IDBObjectStore.prototype.getAll;
    IDBObjectStore.prototype.getAll=function(...a){reads++;return orig.apply(this,a);};
    saveRunnerState=async(...a)=>{saves++;const p=await originalSave(...a);if(p.status==='finished'&&!saved)saved=performance.now();return p;};
    runnerLobbyData=async(...a)=>{refreshes++;const d=await originalLobby(...a);if(saved&&!recalc)recalc=performance.now();return d;};
    const f=formalRunner.frame.contentWindow.refreshFormalRunner;
    formalRunner.frame.contentWindow.refreshFormalRunner=()=>{f();if(formalRunner.bridge.view.result&&!ui)ui=performance.now();};
    while(formalRunner.session.view.state.mode==='running'){
     const pending=[];
     for(let i=0;i<10&&formalRunner.session.view.state.mode==='running';i++){
      pending.push(formalRunner.bridge.advance(.05));
      if(formalRunner.session.view.state.mode==='finished')end=performance.now();
     }
     await Promise.all(pending);
    }
    return {save:saved-end,recalculate:recalc-saved,ui:ui-recalc,total:ui-end,reads,refreshes,saves};
   }''')
   print(n,run,json.dumps(out),flush=True);t.tearDown()
finally:RunnerSessionTest.tearDownClass()
