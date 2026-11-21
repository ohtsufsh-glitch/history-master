"""Issue #85 v8: new routes; published v7 inputs remain in balance_cases unchanged."""
from runner_balance_cases import INPUTS as V7_INPUTS
INPUTS = {**V7_INPUTS,
          'S05': [*V7_INPUTS['S05'], 37.05, 38.75],
          'S06': [*V7_INPUTS['S06'], 39.9, 41.4, 43.15]}

# Synthetic historical purchase only. Never used by the app or real student data.
HISTORICAL = """async (stageId,version,profile='test',characterId='shiba')=>{
 const stage=m.getStage(stageId,version),at=new Date().toISOString();
 const p={id:crypto.randomUUID(),profile,game:'runner',schemaVersion:1,stageId,stageVersion:version,characterId,
  startedAt:at,updatedAt:at,status:'active',score:0,snapshot:m.snapshotRunner(m.createRunnerState(stage,characterId))};
 await runnerTransaction(['runnerPlays','coinSpends'],tx=>{
  tx.objectStore('runnerPlays').add(p);tx.objectStore('coinSpends').add({id:p.id,profile,game:'runner',amount:profile==='test'?0:30,at});
 });return p;
}"""
