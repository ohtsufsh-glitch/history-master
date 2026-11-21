// 公開選択用の通常5匹と、内部モデル専用の秘密キャラを分離する。
function defineCharacters(definitions) {
  return Object.freeze(definitions.map(({ height, duration, feet, ...definition }) => Object.freeze({
    airJumps: 0, ...definition,
    jump: Object.freeze({ height, duration,
      initialVelocity: 4 * height / duration,
      gravity: 8 * height / (duration * duration) }),
    image: Object.freeze({ src: `../assets/plush/${definition.characterId}.webp`,
      maxSize: 100, feetRatio: feet / 512 }),
  })));
}

const CHARACTERS = defineCharacters([
  { characterId: "shiba", name: "しば犬", speed: 200, height: 120, duration: 0.90,
    ability: Object.freeze({ speed: "中", jump: "中" }), initialLives: 2, feature: "バランスよく走る", feet: 465 },
  { characterId: "sloth", name: "なまけもの", speed: 170, height: 125, duration: 1.10,
    ability: Object.freeze({ speed: "低", jump: "中" }), initialLives: 2, feature: "ゆっくり走る", feet: 512 },
  { characterId: "goldfish", name: "金魚", speed: 185, height: 160, duration: 1.05,
    ability: Object.freeze({ speed: "中", jump: "高" }), initialLives: 2, feature: "高くジャンプ", feet: 454 },
  { characterId: "salamander", name: "オオサンショウウオ", speed: 230, height: 105, duration: 0.82,
    ability: Object.freeze({ speed: "高", jump: "低" }), initialLives: 3, feature: "速く走る・低いジャンプ", feet: 466 },
  { characterId: "bear", name: "くま", speed: 180, height: 130, duration: 1.00,
    ability: Object.freeze({ speed: "低", jump: "中" }), initialLives: 3, feature: "ゆっくり走る・ハート3つ", feet: 440 },
]);

// 定義の取得は使用権の付与ではない。公開UIはCHARACTERSだけを参照する。
const SECRET_CHARACTERS = defineCharacters([
  { characterId: "secret_yuniko", name: "ゆにこ", speed: 200, height: 120, duration: 0.90,
    ability: Object.freeze({ speed: "中", jump: "中" }), initialLives: 3, airJumps: 1, feature: "空中で追加ジャンプ1回", feet: 414 },
]);

function getCharacter(characterId) {
  const character = [...CHARACTERS, ...SECRET_CHARACTERS].find(definition => definition.characterId === characterId);
  if (!character) throw new TypeError("有効なキャラクターIDが必要です。");
  return character;
}

export { CHARACTERS, getCharacter };
