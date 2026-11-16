import { describeCharacter, selectionItems, renderSelectionCards } from "./selection.js?v=1.7.34";
import { STAGES } from "./stages.js?v=1.7.34";
import { CHARACTERS, getCharacter } from "./characters.js?v=1.7.34";

// 正式な30コイン課金を導入する際は必ずfalseにするか、試遊入口を削除する。
// この無料入口は権限検証の代わりにはならない。課金・保存処理とは接続しない。
const STAGE_PREVIEW_ENABLED = true;

// すべての描画はこの論理座標で行い、CSS表示サイズ・実ピクセル数と分離する。
const WORLD = Object.freeze({ width: 960, height: 540 });
const MAX_DPR = 2; // 最大1920×1080（RGBAで約8MiB）。表示を拡大しすぎない。
const SCROLL_SPEED = 200; // course[].atの基準速度。実際の走力はstate.speed。
const JUMP_HEIGHT = 120;
const JUMP_DURATION = 0.9;
const JUMP = Object.freeze({ height: JUMP_HEIGHT, duration: JUMP_DURATION,
  initialVelocity: 4 * JUMP_HEIGHT / JUMP_DURATION,
  gravity: 8 * JUMP_HEIGHT / (JUMP_DURATION * JUMP_DURATION) });
const MAX_FRAME_SECONDS = 0.05; // 長い処理停止後の急な飛びを防ぐ。
const COURSE_LENGTH = 6400; // 既存の独立コース用。各ステージの距離はstate.goalDistanceで扱う。
const SIMULATION_STEP = 1 / 120;
const RESPAWN_INVINCIBLE_SECONDS = 1;
const HIT_FEEDBACK_SECONDS = 0.24;
const CHARACTER_X = 186;
const GROUND_Y = 470;
const CHARACTER_IMAGE = Object.freeze({ src: "../assets/plush/shiba.webp", maxSize: 100,
  feetRatio: 465 / 512 }); // 既存画像の透明余白を含む、足元の基準位置。
// 素材は右向きのまま使用。足元の透明余白だけをコマごとに補正する。
const CHARACTER_SET = Object.freeze({ maxSize: 100, runFrameSeconds: 0.1,
  landingSeconds: 0.12, apexHalfWindow: 0.06,
  frames: Object.freeze(Object.fromEntries([
    ["idle", 465], ["run_1", 464], ["run_2", 465], ["run_3", 466], ["run_4", 464],
    ["jump_up", 465], ["jump_top", 465], ["jump_down", 464], ["land", 466],
  ].map(([name, feet]) => [name, Object.freeze({
    src: `./assets/shiba/${name}.webp`, feetRatio: feet / 512,
  })]))) });
// 画像の実体の足先を確認した補正値（512px基準）。物理座標は変更しない。
const ANIMATION_SETS = Object.freeze({
  shiba: CHARACTER_SET,
  ...Object.fromEntries(Object.entries({
    sloth: [461,461,461,461,461,461,461,461,461],
    goldfish: [460,461,459,461,461,461,461,460,461],
    salamander: [460,461,460,461,461,461,461,461,461],
    secret_yuniko: [461,461,460,461,460,461,461,461,461],
  }).map(([id, feet]) => [id, Object.freeze({
    maxSize: 100, runFrameSeconds: 0.1, bob: false,
    frames: Object.freeze(Object.fromEntries(Object.keys(CHARACTER_SET.frames).map((pose, i) =>
      [pose, Object.freeze({src: `./assets/${id}/${pose}.webp`, feetRatio: feet[i] / 512})]))),
  })])),
});

function loadedImage(image) {
  return !!(image?.complete && image.naturalWidth && image.naturalHeight);
}

// 選択時だけ生成。失敗したImageも保持するので404を再試行しない。
function loadCharacterImages(cache, id, redraw) {
  if (cache[id]) return cache[id];
  const set = ANIMATION_SETS[id], definition = getCharacter(id);
  const images = cache[id] = {last: null};
  for (const [pose, frame] of Object.entries({...set.frames, fallback: definition.image})) {
    const image = images[pose] = new Image();
    image.onload = image.onerror = redraw;
    image.src = new URL(frame.src, import.meta.url).href;
  }
  return images;
}
const OBSTACLE_WIDTH = 80;
// 元画像の下端2pxは透明。実体の底面Y=464を地面に合わせる。
const OBSTACLE_IMAGE = Object.freeze({ src: "./assets/spike-rock.webp", width: OBSTACLE_WIDTH,
  height: OBSTACLE_WIDTH * 466 / 640, feetRatio: 464 / 466 });
const PLATFORM = Object.freeze({ width: 190, thickness: 32, height: 80, footHalfWidth: 20 });
const PHYSICS_EPSILON = 1e-9;
const SPAWN_X = WORLD.width + 48;
// 幅80pxの岩本体と3本のトゲの内側。座標は障害物中心X・地面Yからの論理px。
// 全体を1つの矩形にせず、上部の透明な隙間は判定から外す。
const COLLISION = Object.freeze({ characterRadius: 28, starRadius: 20, starHitRadius: 18,
  obstacleRegions: Object.freeze([
    { left: -34, right: 34, top: -20, bottom: -3 },
    { left: -28, right: 28, top: -34, bottom: -18 },
    { left: -4, right: 4, top: -53, bottom: -32 },
    { left: -27, right: -20, top: -41, bottom: -32 },
    { left: 20, right: 27, top: -41, bottom: -32 },
  ].map(region => Object.freeze(region))) });
// 時刻は右端での出現時刻。heightはスターの地上基準位置からの上昇量。
// トゲ岩の初接触は約5.34秒後、以後3秒間隔。滞空0.9秒の後に着地猶予を残す。
const COURSE = Object.freeze([
  { at: 0.25, type: "star", height: 0 },
  ...Array.from({ length: 8 }, (_, index) => [
    { at: 1.5 + index * 3, type: "obstacle" },
    { at: 1.5 + index * 3, type: "star", height: JUMP.height },
  ]).flat(),
  { at: 24.25, type: "star", height: 0 },
  { at: 26, type: "platform" }, // 最後のスター取得後に乗れる任意の足場。
].map(entry => Object.freeze(entry)));

function createRunnerState(course = COURSE, characterId = course?.characterId ?? "shiba") {
  // 旧COURSE配列APIを維持し、ステージ定義／前回stateからのリトライも受け付ける。
  const stage = Array.isArray(course) ? { course, goalDistance: COURSE_LENGTH } : course;
  if (!stage || !Array.isArray(stage.course) ||
      !Number.isFinite(stage.goalDistance) || stage.goalDistance <= 0) {
    throw new TypeError("コース配列と正のゴール距離が必要です。");
  }
  const character = getCharacter(characterId);
  return { stageId: stage.stageId ?? null, goalDistance: stage.goalDistance,
    characterId: character.characterId, speed: character.speed, jump: character.jump,
    initialLives: character.initialLives, airJumpsRemaining: character.airJumps,
    hitFeedbackRemaining: 0, hitPoint: null,
    mode: "ready", lives: character.initialLives, invincibleRemaining: 0, distance: 0, animationTime: 0,
    feetY: GROUND_Y, velocityY: 0, supportId: "ground", jumpOriginY: GROUND_Y, airAction: null,
    landingUntil: 0,
    collectedStarIds: [], elapsed: 0, score: 0, reason: null, objects: [], nextSpawn: 0,
    course: stage.course.map(entry => ({ ...entry })).sort((a, b) => a.at - b.at) };
}

function platformBounds(object) {
  const width = object.width ?? PLATFORM.width;
  const thickness = object.thickness ?? PLATFORM.thickness;
  const top = GROUND_Y - (object.height ?? PLATFORM.height);
  return { left: object.x - width / 2, right: object.x + width / 2,
    top, bottom: top + thickness, width, thickness };
}

// 壁は地面からの矩形。描画と接触で同じ実体を使い、足場にはしない。
function wallBounds(object) {
  return { left: object.x - object.width / 2, right: object.x + object.width / 2,
    top: GROUND_Y - object.height, bottom: GROUND_Y,
    width: object.width, height: object.height };
}

function overlapsPlatform(object, x = object.x) {
  const halfWidth = (object.width ?? PLATFORM.width) / 2;
  return x + halfWidth > CHARACTER_X - PLATFORM.footHalfWidth + PHYSICS_EPSILON &&
    x - halfWidth < CHARACTER_X + PLATFORM.footHalfWidth - PHYSICS_EPSILON;
}

function objectHalfWidth(object) {
  if (object.type === "platform") return (object.width ?? PLATFORM.width) / 2;
  if (object.type === "wall") return object.width / 2;
  return object.type === "star" ? COLLISION.starRadius : OBSTACLE_IMAGE.width / 2;
}

function advanceMotion(state, seconds) {
  let remaining = seconds;
  // objectsはサブステップ終了位置。途中の接地・端離脱時刻へXを戻して判定する。
  while (remaining > PHYSICS_EPSILON) {
    if (state.supportId === "ground") {
      state.feetY = GROUND_Y;
      state.velocityY = 0;
      return;
    }
    if (state.supportId !== null) {
      const platform = state.objects.find(object => object.type === "platform" && object.id === state.supportId);
      if (platform && overlapsPlatform(platform, platform.x + state.speed * remaining)) {
        const bounds = platformBounds(platform);
        state.feetY = bounds.top;
        const untilEdge = (bounds.right + state.speed * remaining -
          (CHARACTER_X - PLATFORM.footHalfWidth)) / state.speed;
        if (untilEdge > remaining + PHYSICS_EPSILON) return;
        remaining = Math.max(0, remaining - Math.max(0, untilEdge));
      }
      state.supportId = null;
      state.airAction = "fall";
      state.jumpOriginY = state.feetY;
      state.velocityY = 0;
    }

    const startY = state.feetY, velocity = state.velocityY;
    const endY = startY + velocity * remaining + state.jump.gravity * remaining * remaining / 2;
    let landing = null;
    function considerSurface(top, id, platform = null) {
      // 上面とほぼ同じ高さの頂点では、丸め誤差による小さな負値を0に戻す。
      const discriminant = velocity * velocity + 2 * state.jump.gravity * (top - startY);
      if (discriminant < -2 * state.jump.gravity * PHYSICS_EPSILON) return;
      // 下降側の根のみ。1ステップ内で頂点をまたぐ場合も取りこぼさない。
      const crossing = (-velocity + Math.sqrt(Math.max(0, discriminant))) / state.jump.gravity;
      if (crossing < -PHYSICS_EPSILON || crossing > remaining + PHYSICS_EPSILON) return;
      const time = Math.max(0, Math.min(remaining, crossing));
      if (platform) {
        const distance = state.distance - state.speed * (remaining - time);
        const spawnDistance = platform.spawnDistance ??
          (platform.at === undefined ? -Infinity : platform.at * SCROLL_SPEED);
        if (spawnDistance > distance + PHYSICS_EPSILON ||
            !overlapsPlatform(platform, platform.x + state.speed * (remaining - time))) return;
      }
      if (!landing || time < landing.time) landing = { time, top, id };
    }
    considerSurface(GROUND_Y, "ground");
    for (const object of state.objects) {
      if (object.type === "platform") considerSurface(platformBounds(object).top, object.id, object);
    }
    if (!landing) {
      state.feetY = endY;
      state.velocityY = velocity + state.jump.gravity * remaining;
      return;
    }
    remaining = Math.max(0, remaining - landing.time);
    state.feetY = landing.top;
    state.velocityY = 0;
    state.supportId = landing.id;
    state.airJumpsRemaining = getCharacter(state.characterId).airJumps;
    state.airAction = null;
    state.jumpOriginY = landing.top;
    state.landingUntil = state.animationTime - remaining + CHARACTER_SET.landingSeconds;
  }
}

function characterBob(state) {
  return state.supportId === "ground" ? Math.abs(Math.sin(state.animationTime * Math.PI * 6)) * 4 : 0;
}

function shadowY(state) {
  let surface = GROUND_Y;
  for (const object of state.objects) {
    if (object.type !== "platform" || !overlapsPlatform(object)) continue;
    const top = platformBounds(object).top;
    if (top >= state.feetY - PHYSICS_EPSILON) surface = Math.min(surface, top);
  }
  return surface;
}

function characterCenter(state) {
  return { x: CHARACTER_X, y: state.feetY - 43 - characterBob(state) };
}

function touchesObject(state, object) {
  const character = characterCenter(state);
  const ground = GROUND_Y;
  if (object.type === "star") {
    const radius = COLLISION.characterRadius + COLLISION.starHitRadius;
    return Math.hypot(character.x - object.x, character.y - (ground - 43 - (object.height ?? 0))) <= radius;
  }
  if (object.type === "wall") {
    const bounds = wallBounds(object);
    const closestX = Math.max(bounds.left, Math.min(character.x, bounds.right));
    const closestY = Math.max(bounds.top, Math.min(character.y, bounds.bottom));
    return Math.hypot(character.x - closestX, character.y - closestY) <= COLLISION.characterRadius;
  }
  if (object.type !== "obstacle") return false;
  const scale = OBSTACLE_IMAGE.width / 80;
  return COLLISION.obstacleRegions.some(region => {
    const closestX = Math.max(object.x + region.left * scale,
      Math.min(character.x, object.x + region.right * scale));
    const closestY = Math.max(ground + region.top * scale,
      Math.min(character.y, ground + region.bottom * scale));
    return Math.hypot(character.x - closestX, character.y - closestY) <= COLLISION.characterRadius;
  });
}

function progressPercent(state) {
  if (state.distance >= state.goalDistance) return 100;
  return Math.min(99, Math.max(0, Math.floor(state.distance / state.goalDistance * 100 + 1e-9)));
}

function goalX(state) {
  return CHARACTER_X + state.goalDistance - state.distance;
}

function updateRunner(state, seconds) {
  if (state.mode !== "running" || !Number.isFinite(seconds) || seconds < 0) return;
  let remaining = seconds;
  // 同じサブステップの衝突を先に処理し、最終衝突ではスター・ゴールより優先する。
  do {
    const step = Math.min(SIMULATION_STEP, remaining, Math.max(0, state.goalDistance - state.distance) / state.speed);
    state.distance += state.speed * step;
    state.animationTime += step;
    state.elapsed += step;
    if (state.goalDistance - state.distance < 1e-9) state.distance = state.goalDistance;
    for (const object of state.objects) object.x -= state.speed * step;
    while (state.nextSpawn < state.course.length && state.course[state.nextSpawn].at * SCROLL_SPEED <= state.distance + 1e-9) {
      const entry = state.course[state.nextSpawn];
      const spawnDistance = entry.at * SCROLL_SPEED;
      state.objects.push({ ...entry, spawnDistance, id: state.nextSpawn++,
        x: SPAWN_X - Math.max(0, state.distance - spawnDistance) });
    }
    advanceMotion(state, step);
    // 実時間ではなく、走行した時間だけ保護を消費する。再開入力だけでは減らない。
    const invincible = state.invincibleRemaining > PHYSICS_EPSILON;
    state.invincibleRemaining = Math.max(0, state.invincibleRemaining - step);
    state.hitFeedbackRemaining = Math.max(0, state.hitFeedbackRemaining - step);
    if (state.hitFeedbackRemaining <= PHYSICS_EPSILON) state.hitPoint = null;
    state.objects = state.objects.filter(object => object.x +
      objectHalfWidth(object) >= 0);
    if (!invincible && state.objects.some(object =>
      (object.type === "obstacle" || object.type === "wall") && touchesObject(state, object))) {
      state.lives = Math.max(0, state.lives - 1);
      if (state.lives === 0) {
        state.mode = "finished";
        state.reason = "collision";
        return;
      }
      // 同じプレイ・サブステップを継続する。位置・ジャンプ・足場・得点は戻さない。
      // この接触の直後から保護し、残りのサブステップでも多重減算を防ぐ。
      state.invincibleRemaining = RESPAWN_INVINCIBLE_SECONDS;
      state.hitFeedbackRemaining = HIT_FEEDBACK_SECONDS;
      const center = characterCenter(state);
      // 接触時の地点を記録。描画だけで使い、衝突・足場・ジャンプには戻さない。
      state.hitPoint = { x: center.x + COLLISION.characterRadius, y: center.y,
        distance: state.distance };
    }
    state.objects = state.objects.filter(object => {
      if (object.type === "star" && touchesObject(state, object)) {
        state.collectedStarIds.push(object.id);
        state.score += 10;
        return false; // 取得済みスターは削除し、二重に加点しない。
      }
      return true;
    });
    // 残機があれば、保護中のスター取得もゴールも通常どおり扱う。
    if (state.distance >= state.goalDistance) {
      state.mode = "finished";
      state.reason = "clear";
      break;
    }
    remaining -= step;
  } while (remaining > 1e-9);
}

function resumeRunner(state) {
  if (state.mode !== "paused") return false;
  state.reason = null;
  state.mode = "running";
  return true;
}

function startJump(state) {
  if (state.mode !== "running") return false;
  if (state.supportId === null) {
    if (state.airJumpsRemaining <= 0) return false;
    state.airJumpsRemaining--;
  }
  state.jumpOriginY = state.feetY;
  state.velocityY = -state.jump.initialVelocity;
  state.supportId = null;
  state.airAction = "jump";
  state.landingUntil = 0;
  return true;
}

function characterPose(state) {
  if (state.mode !== "running") return "idle";
  if (state.supportId === null) {
    if (state.airAction === "jump" && Math.abs(state.velocityY) <= state.jump.gravity * CHARACTER_SET.apexHalfWindow + 1e-9)
      return "jump_top";
    return state.velocityY < 0 ? "jump_up" : "jump_down";
  }
  if (state.animationTime < state.landingUntil - 1e-9) return "land";
  const frame = Math.floor((state.animationTime + 1e-9) / ANIMATION_SETS[state.characterId].runFrameSeconds) % 4 + 1;
  return `run_${frame}`;
}

function drawBackground(context, state) {
  const sky = context.createLinearGradient(0, 0, 0, WORLD.height);
  sky.addColorStop(0, "#ccebea");
  sky.addColorStop(1, "#f4f5cf");
  context.fillStyle = sky;
  context.fillRect(0, 0, WORLD.width, WORLD.height);

  context.fillStyle = "#fff5b5";
  context.beginPath();
  context.arc(786, 86, 43, 0, Math.PI * 2);
  context.fill();

  // 両端の高さを合わせた丘を横に敷き、遠景はゆっくり流す。
  for (const [speed, color, near] of [[0.18, "#accfb4", false], [0.35, "#80b994", true]]) {
    const offset = (state.distance * speed) % WORLD.width;
    for (let x = -offset; x < WORLD.width; x += WORLD.width) {
      context.save();
      context.translate(x, 0);
      context.fillStyle = color;
      context.beginPath();
      if (near) {
        context.moveTo(0, 252);
        context.bezierCurveTo(260, 152, 440, 286, 620, 208);
        context.bezierCurveTo(780, 146, 860, 188, 960, 252);
      } else {
        context.moveTo(0, 220);
        context.bezierCurveTo(180, 80, 290, 160, 440, 216);
        context.bezierCurveTo(620, 82, 750, 150, 960, 220);
      }
      context.lineTo(WORLD.width, WORLD.height);
      context.lineTo(0, WORLD.height);
      context.closePath();
      context.fill();
      context.restore();
    }
  }
}

function drawGround(context, state) {
  context.fillStyle = "#edd4a5";
  context.fillRect(0, GROUND_Y, WORLD.width, WORLD.height - GROUND_Y);
  context.fillStyle = "#fae7bd";
  context.fillRect(0, GROUND_Y, WORLD.width, 7);
  context.fillStyle = "#a77d50";
  context.fillRect(0, WORLD.height - 7, WORLD.width, 7);
  context.fillStyle = "#d5b987";
  for (let x = 36 - state.distance % 108; x < WORLD.width; x += 108) {
    context.fillRect(x, GROUND_Y + 35, 30, 5);
  }
}

// 読み込み中・失敗時にも表示とプレイを継続できる仮キャラクター。
function drawFallbackCharacter(context, state) {
  const x = CHARACTER_X;
  const ground = state.feetY;
  const stride = state.supportId === null ? 0 : Math.sin(state.animationTime * Math.PI * 6);
  const bob = characterBob(state);
  context.fillStyle = "#705c4930";
  context.beginPath();
  context.ellipse(x, shadowY(state), 38, 9, 0, 0, Math.PI * 2);
  context.fill();

  context.fillStyle = "#344e47";
  context.fillRect(x - 22, ground - 14 + stride * 5, 17, 12);
  context.fillRect(x + 8, ground - 14 - stride * 5, 17, 12);
  context.fillStyle = "#e99b45";
  context.beginPath();
  context.arc(x, ground - 43 - bob, 36, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#fff2cf";
  context.beginPath();
  context.ellipse(x + 9, ground - 38 - bob, 24, 23, 0, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#344e47";
  context.beginPath();
  context.arc(x + 12, ground - 49 - bob, 4, 0, Math.PI * 2);
  context.arc(x + 27, ground - 49 - bob, 4, 0, Math.PI * 2);
  context.fill();
}

function drawCharacter(context, state, characterImages) {
  const definition = getCharacter(state.characterId);
  const pose = characterPose(state);
  const set = ANIMATION_SETS[state.characterId];
  const images = characterImages[state.characterId];
  const selectedImage = images?.[pose];
  if (loadedImage(selectedImage)) images.last = {image: selectedImage, feetRatio: set.frames[pose].feetRatio};
  const available = loadedImage(selectedImage) ? images.last :
    loadedImage(images?.last?.image) ? images.last :
    loadedImage(images?.idle) ? {image: images.idle, feetRatio: set.frames.idle.feetRatio} :
    {image: images?.fallback, feetRatio: definition.image.feetRatio};
  const characterImage = available.image;
  if (!loadedImage(characterImage)) {
    context.fillStyle = "#344e47";
    context.font = "16px sans-serif";
    context.textAlign = "center";
    context.fillText(definition.name, CHARACTER_X, state.feetY - 35);
    context.textAlign = "start";
    return;
  }
  const feetRatio = available.feetRatio;
  const scale = set.maxSize / Math.max(characterImage.naturalWidth, characterImage.naturalHeight);
  const width = characterImage.naturalWidth * scale;
  const height = characterImage.naturalHeight * scale;
  const bob = set.bob === false ? 0 : characterBob(state);
  context.fillStyle = "#705c4930";
  context.beginPath();
  context.ellipse(CHARACTER_X, shadowY(state), 38, 9, 0, 0, Math.PI * 2);
  context.fill();
  context.drawImage(characterImage, CHARACTER_X - width / 2,
    state.feetY - height * feetRatio - bob, width, height);
}

function drawGoal(context, state) {
  const x = goalX(state);
  if (x < -80 || x > WORLD.width + 80) return;
  const top = GROUND_Y - 156;
  context.fillStyle = "#fffdf3";
  context.fillRect(x - 3, GROUND_Y, 6, WORLD.height - GROUND_Y);
  context.fillStyle = "#35594b";
  context.fillRect(x - 3, top, 6, GROUND_Y - top);
  for (let row = 0; row < 4; row++) for (let column = 0; column < 6; column++) {
    context.fillStyle = (row + column) % 2 ? "#35594b" : "#fffdf3";
    context.fillRect(x + 3 + column * 10, top + row * 10, 10, 10);
  }
  context.font = "bold 24px sans-serif";
  context.fillStyle = "#263f3b";
  context.fillText("GOAL", x + 8, top - 12);
}

function drawObstacle(context, object, obstacleImage) {
  const { width, height, feetRatio } = OBSTACLE_IMAGE;
  if (obstacleImage?.complete && obstacleImage.naturalWidth && obstacleImage.naturalHeight) {
    context.drawImage(obstacleImage, object.x - width / 2,
      GROUND_Y - height * feetRatio, width, height);
    return;
  }
  // 読み込み中・404でも、同じ大きさのトゲ岩を図形で示してプレイを続ける。
  const outline = [[-.5, 0], [-.46, -.33], [-.32, -.5], [-.32, -.78],
    [-.18, -.62], [-.11, -.6], [0, -1], [.14, -.58], [.28, -.78],
    [.34, -.48], [.47, -.29], [.5, 0]];
  context.beginPath();
  outline.forEach(([x, y], index) => {
    const pointX = object.x + x * width, pointY = GROUND_Y + y * height;
    if (index === 0) context.moveTo(pointX, pointY);
    else context.lineTo(pointX, pointY);
  });
  context.closePath();
  context.fillStyle = "#514650";
  context.fill();
  context.strokeStyle = "#ff4048";
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(object.x - width * .2, GROUND_Y - height * .4);
  context.lineTo(object.x - width * .05, GROUND_Y - height * .22);
  context.lineTo(object.x + width * .15, GROUND_Y - height * .34);
  context.stroke();
}

function drawPlatform(context, object) {
  const { left, top, width, thickness } = platformBounds(object);
  context.fillStyle = "#79c9d4";
  context.fillRect(left, top, width, thickness);
  context.fillStyle = "#d9f6b0";
  context.fillRect(left, top, width, Math.min(6, thickness));
  context.strokeStyle = "#397b85";
  context.lineWidth = 2;
  context.strokeRect(left + 1, top + 1, width - 2, thickness - 2);
}

function drawWall(context, object) {
  const { left, top, width, height } = wallBounds(object);
  context.fillStyle = "#936247";
  context.fillRect(left, top, width, height);
  // 目地も斜線も実体の内側に収める。画像の読み込みには依存しない。
  context.save();
  context.beginPath();
  context.rect(left, top, width, height);
  context.clip();
  context.strokeStyle = "#e8ba85";
  context.lineWidth = 2;
  for (let y = top + 30, row = 0; y < GROUND_Y; y += 30, row++) {
    context.beginPath();
    context.moveTo(left, y);
    context.lineTo(left + width, y);
    const seam = left + width * (row % 2 ? .35 : .65);
    context.moveTo(seam, y - 30);
    context.lineTo(seam, y);
    context.stroke();
  }
  context.strokeStyle = "#ffe099";
  context.lineWidth = 4;
  context.beginPath();
  context.moveTo(left + width * .25, top + 12);
  context.lineTo(left + width * .75, top + 26);
  context.moveTo(left + width * .25, top + 26);
  context.lineTo(left + width * .75, top + 40);
  context.stroke();
  context.restore();
  context.strokeStyle = "#573c32";
  context.lineWidth = 2;
  context.strokeRect(left + 1, top + 1, width - 2, height - 2);
}

function drawObjects(context, state, obstacleImage) {
  for (const object of state.objects) {
    const radius = objectHalfWidth(object);
    if (object.x + radius < 0 || object.x - radius > WORLD.width) continue;
    const ground = GROUND_Y;
    if (object.type === "obstacle") {
      drawObstacle(context, object, obstacleImage);
    } else if (object.type === "wall") {
      drawWall(context, object);
    } else if (object.type === "platform") {
      drawPlatform(context, object);
    } else if (object.type === "star") {
      context.beginPath();
      for (let point = 0; point < 10; point++) {
        const angle = -Math.PI / 2 + point * Math.PI / 5;
        const length = point % 2 ? COLLISION.starRadius * 0.48 : COLLISION.starRadius;
        const x = object.x + Math.cos(angle) * length;
        const y = ground - 43 - (object.height ?? 0) + Math.sin(angle) * length;
        if (point === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.closePath();
      context.fillStyle = "#ffdf59";
      context.fill();
      context.strokeStyle = "#a96b16";
      context.lineWidth = 2;
      context.stroke();
    }
  }
}

function renderScene(context, canvas, state, characterImages, obstacleImage) {
  // width/heightの変更でリセットされた変換も毎回復元する。
  context.setTransform(canvas.width / WORLD.width, 0, 0, canvas.height / WORLD.height, 0, 0);
  drawBackground(context, state);
  drawGround(context, state);
  drawObjects(context, state, obstacleImage);
  drawGoal(context, state);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hitProgress = 1 - state.hitFeedbackRemaining / HIT_FEEDBACK_SECONDS;
  const offset = state.hitFeedbackRemaining > PHYSICS_EPSILON && !reducedMotion ?
    -36 * Math.sin(Math.PI * Math.max(0, hitProgress)) : 0;
  context.save();
  context.translate(offset, 0);
  drawCharacter(context, state, characterImages);
  if (state.invincibleRemaining > PHYSICS_EPSILON) {
    // 点滅させず静かなシールドで示す（動きを減らす設定でも同じ表示）。
    const center = characterCenter(state);
    context.beginPath();
    context.arc(center.x, center.y, 58, 0, Math.PI * 2);
    context.fillStyle = "#d9faff44";
    context.fill();
    context.strokeStyle = "#287da4";
    context.lineWidth = 4;
    context.stroke();
  }
  context.restore();
  if (state.hitPoint && state.hitFeedbackRemaining > PHYSICS_EPSILON) {
    const point = state.hitPoint;
    const x = point.x - (state.distance - point.distance);
    const radius = reducedMotion ? 22 : 16 + 16 * hitProgress;
    context.save();
    context.strokeStyle = "#bd5425";
    context.lineWidth = 5;
    context.beginPath();
    context.arc(x, point.y, radius, 0, Math.PI * 2);
    for (let i = 0; i < 6; i++) {
      const angle = i * Math.PI / 3;
      context.moveTo(x + Math.cos(angle) * (radius + 5), point.y + Math.sin(angle) * (radius + 5));
      context.lineTo(x + Math.cos(angle) * (radius + 14), point.y + Math.sin(angle) * (radius + 14));
    }
    context.stroke();
    context.restore();
  }
}

function resizeCanvas(canvas, stage, viewport) {
  const scale = Math.min(viewport.clientWidth / WORLD.width, viewport.clientHeight / WORLD.height, 1);
  if (scale <= 0) return false;
  const width = WORLD.width * scale;
  const height = WORLD.height * scale;
  stage.style.width = `${width}px`;
  stage.style.height = `${height}px`;

  const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), MAX_DPR);
  const pixelWidth = Math.max(1, Math.round(width * dpr));
  const pixelHeight = Math.max(1, Math.round(height * dpr));
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  return true;
}

function initializeRunner(session = null) {
  const canvas = document.getElementById("runner-canvas");
  const stage = document.getElementById("runner-stage");
  const viewport = document.getElementById("runner-viewport");
  const status = document.getElementById("runner-status");
  const toggle = document.getElementById("runner-toggle");
  const jumpButton = document.getElementById("runner-jump");
  const modeLabel = document.getElementById("runner-mode");
  const scoreLabel = document.getElementById("runner-score");
  const progressLabel = document.getElementById("runner-progress");
  const livesLabel = document.getElementById("runner-lives");
  const heartsLabel = document.getElementById("runner-hearts");
  const result = document.getElementById("runner-result");
  const preview = document.getElementById("runner-preview");
  const stageSelect = document.getElementById("runner-stage-select");
  const stageDetails = document.getElementById("runner-stage-details");
  const characterSelect = document.getElementById("runner-character-select");
  const characterDetails = document.getElementById("runner-character-details");
  const characterIcon = document.getElementById("runner-character-image");
  const isStagePreview = !session && STAGE_PREVIEW_ENABLED &&
    new URLSearchParams(window.location.search).get("stagePreview") === "1";
  if(session){document.querySelector('.runner-app').classList.add('runner-app-formal');status.setAttribute('aria-live','polite');document.querySelector('.runner-footer').append(status);}
  let context;
  try {
    context = canvas.getContext("2d", { alpha: false });
  } catch {
    context = null;
  }
  if (!context) {
    stage.hidden = true;
    toggle.disabled = true;
    if (jumpButton) jumpButton.disabled = true;
    modeLabel.textContent = "表示できません";
    status.textContent = "ゲーム画面を表示できません。Canvas 2Dに対応したSafariなどで開き直してください。";
    return;
  }

  let state = session ? session.view.state : isStagePreview ? createRunnerState(STAGES[0]) : createRunnerState();
  let controlBusy=false, stopped=false;
  function syncSession(){if(session)state=session.view.state;}
  function saveFailure(){syncSession();updateControls();requestRedraw();}
  function describeStage(definition) {
    const count = type => definition.course.filter(entry => entry.type === type).length;
    return `${definition.stageId} ${definition.name} ｜ 難易度 ${definition.difficulty} ｜ ` +
      `約${Math.ceil(definition.goalDistance / state.speed)}秒 ｜ ` +
      `トゲ岩 ${count("obstacle")}個・足場 ${count("platform")}個・壁 ${count("wall")}個`;
  }
  if (isStagePreview) {
    for (const definition of STAGES) {
      const option = document.createElement("option");
      option.value = definition.stageId;
      option.textContent = describeStage(definition);
      stageSelect.append(option);
    }
    stageSelect.value = state.stageId;
    stageDetails.textContent = describeStage(STAGES[0]);
    for (const definition of CHARACTERS) {
      const option = document.createElement("option");
      option.value = definition.characterId;
      option.textContent = definition.name;
      characterSelect.append(option);
    }
    characterSelect.value = state.characterId;
    preview.hidden = false;
    document.querySelector(".runner-app").classList.add("runner-app-preview");
  }
  const characterImages = Object.create(null);
  const obstacleImage = new Image();
  let active = !document.hidden;
  let pendingFrame = null;
  let previousTimestamp = null;
  let sizeDirty = true;

  function updateCharacterDetails() {
    const definition = getCharacter(state.characterId);
    characterDetails.textContent = describeCharacter(definition);
    const iconURL = new URL(definition.image.src, import.meta.url).href;
    if(characterIcon.src !== iconURL)characterIcon.src = iconURL;
    characterIcon.alt = definition.name;
    // 読み込み失敗でも名前・能力と操作はそのまま使える。
    characterIcon.onerror = () => { characterIcon.hidden = true; };
    characterIcon.onload = () => { characterIcon.hidden = false; };
    loadCharacterImages(characterImages, state.characterId, requestRedraw);
    canvas.setAttribute("aria-label", `地面を走る${definition.name}とトゲ岩、乗れる足場、スター、ゴールの旗。` +
      "走行中にタップするとジャンプします。旗のラインを通過するとクリアです。");
    for (const option of stageSelect.options) {
      option.textContent = describeStage(STAGES.find(definition => definition.stageId === option.value));
    }
    stageDetails.textContent = describeStage(STAGES.find(definition => definition.stageId === state.stageId));
  }

  function updatePreviewCards() {
    if (!isStagePreview) return;
    const items=selectionItems(STAGES,CHARACTERS,STAGES.map(s=>s.stageId),true);
    for(const [kind,select] of [["stage",stageSelect],["character",characterSelect]]) {
      renderSelectionCards(document.getElementById(`runner-${kind}-cards`),items[kind==="stage"?"stages":"characters"],select.value,select.disabled,id=>{
        select.value=id; select.dispatchEvent(new Event("change"));
      });
    }
  }
  function updateControls() {
    if (isStagePreview) {
      stageSelect.disabled = !active || (state.mode !== "ready" && state.mode !== "finished");
      characterSelect.disabled = stageSelect.disabled;
      stageSelect.value = state.stageId; characterSelect.value = state.characterId;
      updatePreviewCards();
    }
    const text = { ready: "ゲーム開始", running: "一時停止", paused: "再開", finished: "もう一度" }[state.mode];
    if (toggle.textContent !== text) toggle.textContent = text;
    if(session) {
      toggle.disabled=controlBusy||(!!session.view.error&&!!session.view.savedPlay)||(state.mode==='finished'&&(session.view.dirty||!session.view.result));
      if(state.mode==='finished')toggle.textContent='再挑戦';
      if(session.view.error&&session.view.savedPlay) {toggle.disabled=controlBusy;toggle.textContent='最後の保存から再開（無料）';}
    }
    const jumpDisabled = !active || state.mode !== "running";
    if (jumpButton && jumpButton.disabled !== jumpDisabled) jumpButton.disabled = jumpDisabled;
    const mode = { ready: "開始前", running: "走行中", paused: "一時停止中", finished: "終了" }[state.mode];
    if (modeLabel.textContent !== mode) modeLabel.textContent = mode;
    if (scoreLabel.textContent !== String(state.score)) scoreLabel.textContent = state.score;
    const hearts = "♥".repeat(state.lives) + "♡".repeat(state.initialLives - state.lives);
    const livesDescription = `ハートはあと${state.lives}個（全部で${state.initialLives}個）`;
    if (heartsLabel.textContent !== hearts) heartsLabel.textContent = hearts;
    if (livesLabel.getAttribute("aria-label") !== livesDescription) livesLabel.setAttribute("aria-label", livesDescription);
    const progress = String(progressPercent(state));
    if (progressLabel.textContent !== progress) progressLabel.textContent = progress;
    const hideResult = state.mode !== "finished";
    const resetResult = hideResult && !result.hidden;
    if (result.hidden !== hideResult) result.hidden = hideResult;
    document.getElementById('runner-formal-result').hidden=!session||hideResult;
    if (state.mode === "finished") {
      document.getElementById("runner-result-title").textContent = state.reason === "clear" ? "クリア！" : "ゲームオーバー";
      document.getElementById("runner-result-message").textContent = state.reason === "clear" ?
        "ゴールまで走りきったよ！" : "トゲ岩にぶつかったよ。もう一度挑戦しよう！";
      document.getElementById("runner-result-score").textContent = state.score;
      document.getElementById("runner-result-progress").textContent = progress;
      result.dataset.reason=state.reason;
      if(session){
        const view=session.view,r=view.result;
        const confirmed=r&&!view.dirty&&!view.error&&view.savedPlay?.status==='finished';
        document.getElementById('runner-result-title').textContent=confirmed?(r.play.result.reason==='clear'?'クリア！':'ゲームオーバー'):'結果を保存中…';
        document.getElementById('runner-result-message').textContent=confirmed?'保存しました。下のボタンで再挑戦！':view.error?'保存できませんでした。追加コインなしで最後の保存から再開できます。':'保存が終わるまで待ってね。';
        if(view.error)document.getElementById('runner-result-title').textContent='まだ保存できていません';
        document.getElementById('runner-result-score').textContent=confirmed?r.play.score:state.score;
        document.getElementById('runner-result-record').textContent=confirmed?(r.stageRecord||r.characterRecord||''):'';
        document.getElementById('runner-result-unlock').textContent=confirmed&&r.unlocked.length?`${r.unlocked.join('・')} が遊べるようになったよ！`:'';
      }
    } else if (resetResult) {
      document.getElementById("runner-result-title").textContent = "";
      document.getElementById("runner-result-message").textContent = "";
      document.getElementById("runner-result-score").textContent = "0";
      document.getElementById("runner-result-progress").textContent = "0";
    }
  }

  function redraw(timestamp) {
    pendingFrame = null;
    if (!active || document.hidden) {
      suspendRendering();
      return;
    }
    if (sizeDirty) {
      if (!resizeCanvas(canvas, stage, viewport)) {
        previousTimestamp = null;
        return;
      }
      sizeDirty = false;
    }
    if (state.mode === "running") {
      const seconds = previousTimestamp === null ? 0 :
        Math.min(Math.max((timestamp - previousTimestamp) / 1000, 0), MAX_FRAME_SECONDS);
      if(session) {
        // advanceは同期的にモデルを進め、保存だけ非同期。フレームの待機キューは作らない。
        session.advance(seconds).then(()=>{if(state.mode!=='running')requestRedraw();}).catch(saveFailure);
        syncSession();
      } else updateRunner(state, seconds);
      previousTimestamp = state.mode === "running" ? timestamp : null;
      updateControls();
    }
    if(session){syncSession();updateControls();}
    renderScene(context, canvas, state, characterImages, obstacleImage);
    if(session) {
      const view=session.view;
      status.hidden=false;
      status.textContent=view.message||(view.error?'保存に失敗しました。'+view.error:'');
      status.hidden=!status.textContent;
      status.style.position='static';
    } else status.hidden = true;
    if (state.mode === "running") requestRedraw();
  }

  // 通常描画・リサイズ・走行が共通の1枠を使い、ループを二重起動しない。
  function requestRedraw() {
    if (!stopped && active && pendingFrame === null) pendingFrame = requestAnimationFrame(redraw);
  }

  function pauseRunning() {
    if(session&&!stopped){session.pause().catch(saveFailure);syncSession();}
    if (state.mode === "running") state.mode = "paused";
    previousTimestamp = null;
    if (pendingFrame !== null) cancelAnimationFrame(pendingFrame);
    pendingFrame = null;
    updateControls();
  }

  function suspendRendering() {
    active = false;
    pauseRunning();
  }

  function resumeRendering() {
    // 復帰は画面だけを戻す。走行はユーザーの「再開」を待つ。
    pauseRunning();
    active = !document.hidden;
    updateControls();
    sizeDirty = true;
    requestRedraw();
  }

  function resizeAndRedraw() {
    sizeDirty = true;
    requestRedraw();
  }

  function pauseForResize() {
    pauseRunning();
    resizeAndRedraw();
  }

  stageSelect?.addEventListener("change", () => {
    const selected = STAGES.find(definition => definition.stageId === stageSelect.value);
    if (!isStagePreview || !active || document.hidden ||
        (state.mode !== "ready" && state.mode !== "finished") || !selected) {
      stageSelect.value = state.stageId ?? "";
      return;
    }
    if (pendingFrame !== null) cancelAnimationFrame(pendingFrame);
    pendingFrame = null;
    previousTimestamp = null;
    state = createRunnerState(selected, state.characterId);
    stageDetails.textContent = describeStage(selected);
    updateControls();
    requestRedraw();
  });

  characterSelect?.addEventListener("change", () => {
    const selected = CHARACTERS.find(definition => definition.characterId === characterSelect.value);
    if (!isStagePreview || !active || document.hidden ||
        (state.mode !== "ready" && state.mode !== "finished") || !selected) {
      characterSelect.value = state.characterId;
      return;
    }
    if (pendingFrame !== null) cancelAnimationFrame(pendingFrame);
    pendingFrame = null;
    previousTimestamp = null;
    state = createRunnerState(state, selected.characterId);
    updateCharacterDetails();
    updateControls();
    requestRedraw();
  });

  toggle.addEventListener("click", async () => {
    if (!active || document.hidden || controlBusy) return;
    if(session) {
      controlBusy=true;
      try {
        if(state.mode==='running')await session.pause();
        else await session.resume();
      } catch {saveFailure();}
      finally {controlBusy=false;syncSession();previousTimestamp=null;updateControls();requestRedraw();}
      return;
    }
    if (state.mode === "running") {
      pauseRunning();
      // 走行位置を進めず、停止中のidleを1回だけ表示する。
      if (sizeDirty) requestRedraw();
      else renderScene(context, canvas, state, characterImages, obstacleImage);
    } else {
      if (state.mode === "finished") state = createRunnerState(state);
      if (state.mode === "ready") state.mode = "running";
      else resumeRunner(state);
      previousTimestamp = null;
      updateControls();
      requestRedraw();
    }
  });
  function requestJump() {
    if (!active || document.hidden || state.mode !== "running") return;
    if(session){session.jump().catch(saveFailure);syncSession();requestRedraw();}
    else startJump(state);
  }
  // 既存のclickを維持。タップ・マウス・キーボードを二重登録しない。
  // 古いHTMLが残ってボタンがない場合にも、Canvas操作は維持する。
  jumpButton?.addEventListener("pointerdown", event=>{
    if(event.isPrimary&&event.button===0){event.preventDefault();requestJump();}
  });
  jumpButton?.addEventListener("click", event=>{if(event.detail===0)requestJump();});
  canvas.addEventListener("pointerdown", event => {
    if (!active || document.hidden || !event.isPrimary || event.button !== 0 || state.mode !== "running") return;
    event.preventDefault();
    requestJump();
  });

  window.addEventListener("resize", pauseForResize);
  window.addEventListener("orientationchange", pauseForResize);
  window.visualViewport?.addEventListener("resize", pauseForResize);
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(resizeAndRedraw);
    observer.observe(viewport);
  }
  window.addEventListener("pagehide", suspendRendering);
  window.addEventListener("pageshow", resumeRendering);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) suspendRendering();
    else resumeRendering();
  });
  // 画像を待ってゲームを止めない。復帰・静止中も必要な1フレームだけ更新する。
  loadCharacterImages(characterImages, state.characterId, requestRedraw);
  if (isStagePreview || session) updateCharacterDetails();
  obstacleImage.onload = requestRedraw;
  obstacleImage.onerror = requestRedraw;
  obstacleImage.src = new URL(OBSTACLE_IMAGE.src, import.meta.url).href;
  if(session)window.refreshFormalRunner=()=>{syncSession();updateCharacterDetails();updateControls();requestRedraw();};
  if(session)window.stopFormalRunner=()=>{
    stopped=true;active=false;
    if(pendingFrame!==null)cancelAnimationFrame(pendingFrame);
  };
  toggle.disabled = false;
  updateControls();
  requestRedraw();
}

if (typeof document !== "undefined" && document.getElementById("runner-canvas")) {
  // embeddedは無料エンジンを止める指示のみ。正式な権限は親の検証済みセッション。
  if(new URLSearchParams(location.search).get('embedded')==='1') {
    let mounted=false;
    window.mountFormalRunner=session=>{
      if(mounted||window.parent===window)return;
      mounted=true;initializeRunner(session);
    };
  } else initializeRunner();
}

// snapshot v2: 定義は再生成し、実行中に変化する値は丸めず保持する。
const SNAPSHOT_KEYS = ['distance','elapsed','lives','score','invincibleRemaining',
  'feetY','velocityY','supportId','jumpOriginY','airAction','airJumpsRemaining',
  'animationTime','landingUntil','hitFeedbackRemaining','hitPoint','nextSpawn',
  'objects','collectedStarIds','mode','reason'];
function snapshotRunner(state) {
  return structuredClone({version:2,...Object.fromEntries(SNAPSHOT_KEYS.map(k=>[k,state[k]]))});
}
function restoreRunner(play) {
  const s=play.snapshot;
  if(play.stageVersion!==1 || s?.version!==2) throw new Error('この途中記録は現在の版では正確に再開できません。購入記録は保持されています。');
  const stage=STAGES.find(s=>s.stageId===play.stageId);
  const state=createRunnerState(stage,play.characterId);
  if(!s || Object.keys(s).length!==SNAPSHOT_KEYS.length+1 || !SNAPSHOT_KEYS.every(k=>Object.hasOwn(s,k)))throw new Error('途中状態の項目が不正です。');
  const finite=['distance','elapsed','lives','score','invincibleRemaining','feetY','velocityY',
    'jumpOriginY','airJumpsRemaining','animationTime','landingUntil','hitFeedbackRemaining','nextSpawn'];
  if(!finite.every(k=>Number.isFinite(s[k])&&Math.abs(s[k])<=1000000) ||
    s.distance<0||s.distance>state.goalDistance||s.elapsed<0||s.animationTime<0||
    !Number.isInteger(s.lives)||s.lives<0||s.lives>state.initialLives||
    !Number.isInteger(s.airJumpsRemaining)||s.airJumpsRemaining<0||s.airJumpsRemaining>getCharacter(play.characterId).airJumps||
    s.invincibleRemaining<0||s.invincibleRemaining>1||s.hitFeedbackRemaining<0||s.hitFeedbackRemaining>HIT_FEEDBACK_SECONDS||
    ![null,'jump','fall'].includes(s.airAction)|| !['ready','paused','running','finished'].includes(s.mode)||
    (s.mode==='finished' ? !((s.reason==='clear'&&s.distance===state.goalDistance&&s.lives>0)||(s.reason==='collision'&&s.lives===0)) : s.reason!==null||s.lives<1||s.distance>=state.goalDistance))throw new Error('途中状態の値が不正です。');
  const next=state.course.filter(e=>e.at*SCROLL_SPEED<=s.distance+1e-9).length;
  if(s.nextSpawn!==next||!Array.isArray(s.collectedStarIds)||new Set(s.collectedStarIds).size!==s.collectedStarIds.length||
    !s.collectedStarIds.every(id=>Number.isInteger(id)&&id>=0&&id<next&&state.course[id].type==='star')||
    s.score!==s.collectedStarIds.length*10||s.score!==play.score||s.score>100)throw new Error('スター記録が不正です。');
  const expected=state.course.slice(0,next).map((e,id)=>({...e,spawnDistance:e.at*SCROLL_SPEED,id,
    x:SPAWN_X-Math.max(0,s.distance-e.at*SCROLL_SPEED)})).filter(o=>o.x+objectHalfWidth(o)>=0&&!s.collectedStarIds.includes(o.id));
  if(!Array.isArray(s.objects)||s.objects.length!==expected.length||!s.objects.every((o,i)=>{
    const e=expected[i];return Object.keys(o).length===Object.keys(e).length&&Object.keys(e).every(k=>k==='x'?Math.abs(o.x-e.x)<1e-6:o[k]===e[k]);
  }))throw new Error('コース状態が不正です。');
  if(s.hitPoint!==null && (!s.hitPoint||Object.keys(s.hitPoint).sort().join(',')!=='distance,x,y'||!Object.values(s.hitPoint).every(Number.isFinite)))throw new Error('衝撃状態が不正です。');
  if(s.supportId!==null && s.supportId!=='ground' && !s.objects.some(o=>o.id===s.supportId&&o.type==='platform'&&overlapsPlatform(o)&&Math.abs(platformBounds(o).top-s.feetY)<1e-6))throw new Error('足場状態が不正です。');
  if(s.supportId==='ground'&&(s.feetY!==GROUND_Y||s.velocityY!==0))throw new Error('接地状態が不正です。');
  Object.assign(state,structuredClone(s));delete state.version;
  if(state.mode!=='finished')state.mode='paused';
  return state;
}
export {snapshotRunner,restoreRunner,STAGES};

// コースとゲーム状態はDOMから独立。配置の差し替えや決定的なルール検証に使う。
export { ANIMATION_SETS, loadCharacterImages, drawCharacter, describeCharacter, selectionItems, renderSelectionCards, CHARACTERS, getCharacter, COURSE, COLLISION, CHARACTER_X, SPAWN_X, CHARACTER_IMAGE, CHARACTER_SET, OBSTACLE_IMAGE, PLATFORM, GROUND_Y, JUMP, COURSE_LENGTH, SCROLL_SPEED,
  createRunnerState, updateRunner, resumeRunner, startJump, progressPercent, goalX, characterCenter, characterPose,
  platformBounds, wallBounds, characterBob, shadowY };
