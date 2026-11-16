// 表示専用。購入・保存・ゲーム物理には触れない。
export function describeCharacter(c) {
  return `${c.name} ／ 走力：${c.ability.speed} ／ ジャンプ：${c.ability.jump} ／ ハート：${"♥".repeat(c.initialLives)}（${c.initialLives}個） ／ ${c.feature}`;
}
export function selectionItems(stages, characters, unlocked, secret = false) {
  return {
    stages: stages.map(s => ({id:s.stageId, name:`${s.stageId} ${s.name}`, icon:"🚩",
      detail:`難易度 ${s.difficulty}`, locked:!unlocked.includes(s.stageId),
      lockHelp:"前のステージをクリアすると遊べるよ"})),
    characters: [...characters.map(c => ({id:c.characterId, name:c.name,
      image:new URL(c.image.src, import.meta.url).href})),
      ...(!secret ? [{id:"secret-locked", name:"？？？", icon:"🔒", locked:true,
        lockHelp:"UFOキャッチャーで見つけよう"}] : [])]
  };
}
export function renderSelectionCards(container, items, selected, disabled, onSelect) {
  // 同じボタンを使い続け、更新でキーボード／VoiceOverのフォーカスを失わない。
  const existing = new Map([...container.children].map(b => [b.dataset.choice, b]));
  for (const item of items) {
    let button = existing.get(item.id);
    if (!button) {
      button = document.createElement("button");
      button.type = "button"; button.className = "runner-choice-card";
      button.dataset.choice = item.id;
      const icon = document.createElement(item.image ? "img" : "span");
      if (item.image) {icon.src=item.image; icon.alt=""; icon.width=72; icon.height=72;}
      else icon.textContent=item.icon;
      icon.setAttribute("aria-hidden", "true");
      const name=document.createElement("strong"); name.textContent=item.name;
      const detail=document.createElement("small"); detail.textContent=item.locked?`🔒 ${item.lockHelp}`:item.detail||"";
      const mark=document.createElement("span"); mark.className="runner-choice-mark";mark.setAttribute("aria-hidden","true");
      button.append(icon,name,detail,mark); container.append(button);
    }
    existing.delete(item.id);
    button.querySelector("small").textContent=item.locked?`🔒 ${item.lockHelp}`:item.detail||"";
    button.disabled=disabled||!!item.locked;
    button.setAttribute("aria-pressed",String(selected===item.id));
    button.setAttribute("aria-label",`${item.name}${item.locked?`、ロック中。${item.lockHelp}`:item.detail?`、${item.detail}`:""}`);
    button.querySelector('.runner-choice-mark').textContent=selected===item.id?"✓ 選択中":"";
    button.onclick=()=>{if(!button.disabled)onSelect(item.id);};
  }
  for (const button of existing.values()) button.remove();
}
