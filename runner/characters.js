// 通常キャラクターの初期能力。ステージと独立し、記録・獲得条件には接続しない。
const CHARACTERS = Object.freeze([
  { characterId: "shiba", name: "しば犬", speed: 200, height: 120, duration: 0.90,
    initialLives: 2, feature: "バランスよく走る", feet: 465 },
  { characterId: "sloth", name: "なまけもの", speed: 170, height: 125, duration: 1.10,
    initialLives: 3, feature: "ゆっくり走る・残機多め", feet: 512 },
  { characterId: "goldfish", name: "金魚", speed: 185, height: 160, duration: 1.05,
    initialLives: 2, feature: "高くジャンプ", feet: 454 },
  { characterId: "salamander", name: "オオサンショウウオ", speed: 230, height: 105, duration: 0.82,
    initialLives: 2, feature: "速く走る・低いジャンプ", feet: 466 },
].map(({ height, duration, feet, ...definition }) => Object.freeze({ ...definition,
  jump: Object.freeze({ height, duration,
    initialVelocity: 4 * height / duration,
    gravity: 8 * height / (duration * duration) }),
  image: Object.freeze({ src: `../assets/plush/${definition.characterId}.webp`,
    maxSize: 100, feetRatio: feet / 512 }),
})));

function getCharacter(characterId) {
  const character = CHARACTERS.find(definition => definition.characterId === characterId);
  if (!character) throw new TypeError("通常キャラクターのIDが必要です。");
  return character;
}

export { CHARACTERS, getCharacter };
