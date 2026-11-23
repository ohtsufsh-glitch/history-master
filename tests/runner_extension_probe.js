// Real startJump/updateRunner inputs only; no position, life, shield or velocity edits.
function extensionProbe(m) {
  function run(stage, inputs, hz=60, onFrame=()=>{}) {
    const s=m.createRunnerState(stage); s.mode='running';
    const jumps=[],landings=[],hits=[],stars=[],collapses=[],encounters=new Map();let next=0;
    for(let frame=0;frame<hz*55 && s.mode==='running';frame++) {
      if(next<inputs.length && frame/hz+1e-9>=inputs[next]) {
        jumps.push({t:s.elapsed,x:s.distance,support:s.supportId,ok:m.startJump(s)});next++;
      }
      const support=s.supportId,lives=s.lives,count=s.collectedStarIds.length;
      const pending=s.crumbling.filter(c=>s.supportId===c.id).map(c=>({id:c.id,deadline:s.landingUntil-.12+c.seconds}));
      m.updateRunner(s,1/hz);
      if(s.score>100)throw Error("score exceeds 100");
      if(s.supportId!==null && s.supportId!==support)landings.push({t:s.elapsed,x:s.distance,height:470-s.feetY,support:s.supportId});
      if(s.lives<lives)hits.push({t:s.elapsed,x:s.distance,lives:s.lives});
      if(s.collectedStarIds.length>count)stars.push({t:s.elapsed,x:s.distance,ids:s.collectedStarIds.slice(count)});
      for(const c of pending)if(!s.objects.some(o=>o.id===c.id))collapses.push({...c,t:s.elapsed,x:s.distance});
      for(const [type,objects,center] of [['bird',s.birds,m.birdCenter],['spike',s.spikes,m.spikeCenter]]) {
        objects.forEach((o,i)=>{const p=center(s,o),dx=Math.abs(p.x-m.CHARACTER_X),key=type+i;
          if(!encounters.has(key)||dx<encounters.get(key).dx)encounters.set(key,{type,index:i,t:s.elapsed,x:s.distance,dx,height:470-p.y,feetHeight:470-s.feetY});});
      }
      onFrame(s,frame);
    }
    return {reason:s.reason,score:s.score,lives:s.lives,distance:s.distance,time:s.elapsed,jumps,landings,hits,stars,collapses,encounters:[...encounters.values()]};
  }
  const good=r=>r.reason==='clear'&&r.score===100&&r.lives===2&&r.jumps.every(j=>j.ok);
  function land(id,target,inputs,hz=120) {
    let result;run(m.getStage(id,8),inputs,hz,s=>{if(!result&&s.supportId===target)result=structuredClone(s);});
    if(!result)throw Error('missing landing '+id+'/'+target);return result;
  }
  function fast(stage,inputs,hz) {
    const s=m.createRunnerState(stage);s.mode='running';let n=0;
    for(let f=0;f<hz*55&&s.mode==='running';f++){
      if(n<inputs.length&&f/hz+1e-9>=inputs[n]){if(!m.startJump(s))return false;n++;}
      m.updateRunner(s,1/hz);
      if(s.score>100)throw Error("score exceeds 100");
      if(s.lives!==2)return false;
    }
    return s.reason==='clear'&&s.score===100&&n===inputs.length;
  }
  return {run,good,land,fast};
}
