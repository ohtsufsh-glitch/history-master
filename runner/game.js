import { describeCharacter, selectionItems, renderSelectionCards } from "./selection.js?v=1.7.55";
import { STAGES, getStage } from "./stages.js?v=1.7.55";
import { CHARACTERS, getCharacter } from "./characters.js?v=1.7.55";

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
const OBSTACLE_IMAGE = Object.freeze({ src: "./assets/spike-rock.webp?v=1.7.53", width: OBSTACLE_WIDTH,
  height: OBSTACLE_WIDTH * 466 / 640, feetRatio: 464 / 466 });
const PLATFORM = Object.freeze({ width: 190, thickness: 32, height: 80, footHalfWidth: 20 });
const BIRD_RADIUS = 28; // 輪郭を含む円。描画と当たり判定で共有。
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
  const state = { stageId: stage.stageId ?? null, stageVersion: stage.stageVersion ?? 1,
    holes: (stage.holes ?? []).map(hole => ({...hole})),
    holeFailure: stage.holeFailure ?? "recover",
    crumbling: stage.crumbling ?? [],
    spikes: (stage.spikes ?? []).map(spike => ({...spike})),
    routeWarnings: (stage.routeWarnings ?? []).map(route => ({...route})),
    birds: (stage.birds ?? []).map(bird => ({...bird})), goalDistance: stage.goalDistance,
    characterId: character.characterId, speed: character.speed, jump: character.jump,
    initialLives: character.initialLives, airJumpsRemaining: character.airJumps,
    hitFeedbackRemaining: 0, hitPoint: null,
    mode: "ready", lives: character.initialLives, invincibleRemaining: 0, distance: 0, animationTime: 0,
    feetY: GROUND_Y, velocityY: 0, supportId: "ground", jumpOriginY: GROUND_Y, airAction: null,
    landingUntil: 0,
    collectedStarIds: [], elapsed: 0, score: 0, reason: null, objects: [], nextSpawn: 0,
    course: stage.course.map(entry => ({ ...entry })).sort((a, b) => a.at - b.at) };
  // 開始画面内にある早期イベントも、購入直後から通常のsnapshot v2として保存する。
  // 旧コースには負のatがなく、旧版の初期snapshotは変化しない。
  state.nextSpawn = state.course.filter(entry => entry.at * SCROLL_SPEED <= 0).length;
  state.objects = courseObjectsAt(state, 0, state.nextSpawn);
  return state;
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

// 穴はキャラの足元中心（通過距離）で判定。描画にも同じ開始・終了座標を使う。
function groundHoleAt(state, distance = state.distance) {
  return state.holes.find(hole => distance >= hole.start - PHYSICS_EPSILON &&
    distance < hole.end - PHYSICS_EPSILON);
}

function advanceMotion(state, seconds) {
  let remaining = seconds;
  // objectsはサブステップ終了位置。途中の接地・端離脱時刻へXを戻して判定する。
  while (remaining > PHYSICS_EPSILON) {
    if (state.supportId === "ground") {
      state.feetY = GROUND_Y;
      state.velocityY = 0;
      const startDistance = state.distance - state.speed * remaining;
      const hole = groundHoleAt(state, startDistance) ?? state.holes.find(hole =>
        hole.start > startDistance && hole.start <= state.distance + PHYSICS_EPSILON);
      if (!hole) return;
      const untilEdge = Math.max(0, (hole.start - startDistance) / state.speed);
      remaining = Math.max(0, remaining - untilEdge);
      state.supportId = null;
      state.airAction = "fall";
      state.jumpOriginY = GROUND_Y;
    }
    if (state.supportId !== null) {
      const platform = state.objects.find(object => object.type === "platform" && object.id === state.supportId);
      if (platform && overlapsPlatform(platform, platform.x + state.speed * remaining)) {
        const bounds = platformBounds(platform);
        state.feetY = bounds.top;
        const untilEdge = (bounds.right + state.speed * remaining -
          (CHARACTER_X - PLATFORM.footHalfWidth)) / state.speed;
        const crumble = state.crumbling.find(p => p.id === platform.id);
        // landingUntilは接地中に上書きされない着地アニメの終了時刻。
        // サブステップ途中の崩壊時刻で支持を切り、残り時間は自由落下する。
        const untilCollapse = crumble ? state.landingUntil - CHARACTER_SET.landingSeconds +
          crumble.seconds - (state.animationTime - remaining) : Infinity;
        const untilRelease = Math.min(untilEdge, untilCollapse);
        if (untilRelease > remaining + PHYSICS_EPSILON) return;
        if (untilCollapse <= untilEdge + PHYSICS_EPSILON) {
          // 不在そのものが永続状態。再生成せず保存し、描画と着地判定の両方から除く。
          state.objects = state.objects.filter(o => o.id !== platform.id);
        }
        remaining = Math.max(0, remaining - Math.max(0, untilRelease));
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
      const distance = state.distance - state.speed * (remaining - time);
      if (id === "ground" && groundHoleAt(state, distance)) return;
      if (platform) {
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

// speed欠損は旧静止鳥。定義ごとの世界速度(40/120)と既存elapsedだけから再生成する。
function birdCenter(state, bird) {
  return {x: CHARACTER_X + bird.x - state.distance - (bird.speed ?? 0) * state.elapsed, y: GROUND_Y - bird.height};
}

// 位置は定義とelapsedだけから再計算。描画・衝突・再開で同じ関数を使う。
const SPIKE_RADIUS = 26;
function spikeCenter(state, spike) {
  return {x: CHARACTER_X + spike.x - state.distance,
    y: GROUND_Y - spike.height - spike.amplitude * Math.sin(2 * Math.PI * state.elapsed / spike.period + spike.phase)};
}
function touchesSpike(state, spike) {
  const a = characterCenter(state), b = spikeCenter(state, spike);
  return Math.hypot(a.x-b.x,a.y-b.y) <= COLLISION.characterRadius + SPIKE_RADIUS;
}

function touchesBird(state, bird) {
  const center = birdCenter(state, bird), character = characterCenter(state);
  return Math.hypot(character.x - center.x, character.y - center.y) <=
    COLLISION.characterRadius + BIRD_RADIUS;
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

function courseObjectsAt(state, distance, nextSpawn, collectedStarIds = state.collectedStarIds) {
  return state.course.slice(0, nextSpawn).map((entry, id) => ({...entry,
    spawnDistance: entry.at * SCROLL_SPEED, id,
    x: SPAWN_X - Math.max(0, distance - entry.at * SCROLL_SPEED),
  })).filter(object => object.x + objectHalfWidth(object) >= 0 && !collectedStarIds.includes(object.id));
}

function recoverFromHole(state) {
  // 無敵でも落下は防げない。画面外まで落ちたら1機だけ消費する。
  state.lives = Math.max(0, state.lives - 1);
  if (state.lives === 0) {
    state.mode = "finished";
    state.reason = "collision"; // 保存済みの終了形式（gameover）を維持。
    return;
  }
  // 後方への巻き戻しはしない。穴の直後へ移し、次の入力まで安全な地面を確保。
  let safeDistance = state.distance;
  for (const hole of state.holes) {
    if (safeDistance >= hole.start && safeDistance < hole.end + 60) safeDistance = hole.end + 60;
  }
  state.distance = safeDistance;
  state.nextSpawn = state.course.filter(entry => entry.at * SCROLL_SPEED <= safeDistance + 1e-9).length;
  state.objects = courseObjectsAt(state, safeDistance, state.nextSpawn);
  state.feetY = GROUND_Y;
  state.velocityY = 0;
  state.supportId = "ground";
  state.jumpOriginY = GROUND_Y;
  state.airAction = null;
  state.airJumpsRemaining = getCharacter(state.characterId).airJumps;
  state.invincibleRemaining = RESPAWN_INVINCIBLE_SECONDS;
  state.hitFeedbackRemaining = HIT_FEEDBACK_SECONDS;
  state.hitPoint = {...characterCenter(state), distance: state.distance};
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
    let invincible = state.invincibleRemaining > PHYSICS_EPSILON;
    state.invincibleRemaining = Math.max(0, state.invincibleRemaining - step);
    state.hitFeedbackRemaining = Math.max(0, state.hitFeedbackRemaining - step);
    if (state.hitFeedbackRemaining <= PHYSICS_EPSILON) state.hitPoint = null;
    state.objects = state.objects.filter(object => object.x +
      objectHalfWidth(object) >= 0);
    // 足が地面より下へ落ちると、通常のジャンプ・着地では復帰できない。
    // 穴の上空を正常に飛び越える間はfeetY<=GROUND_Yなので終了しない。
    if (state.holeFailure === "fatal" && state.feetY > GROUND_Y + PHYSICS_EPSILON) {
      state.lives = 0;
      state.mode = "finished";
      state.reason = "collision";
      return; // 終了したサブステップではスターもゴールも処理しない。
    }
    if (state.feetY >= WORLD.height + 100) {
      recoverFromHole(state);
      if (state.mode === "finished") return;
      invincible = true;
    }
    if (!invincible && (state.objects.some(object =>
      (object.type === "obstacle" || object.type === "wall") && touchesObject(state, object)) ||
      state.birds.some(bird => touchesBird(state, bird)) ||
      state.spikes.some(spike => touchesSpike(state, spike)))) {
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
  context.save();
  context.beginPath();
  let left = 0;
  for (const hole of state.holes) {
    const start = Math.max(0, Math.min(WORLD.width, CHARACTER_X + hole.start - state.distance));
    const end = Math.max(0, Math.min(WORLD.width, CHARACTER_X + hole.end - state.distance));
    context.rect(left, GROUND_Y, start - left, WORLD.height - GROUND_Y);
    left = end;
  }
  context.rect(left, GROUND_Y, WORLD.width - left, WORLD.height - GROUND_Y);
  context.clip();
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
  context.restore();
  for (const hole of state.holes) {
    const start = CHARACTER_X + hole.start - state.distance;
    const end = CHARACTER_X + hole.end - state.distance;
    if (end < 0 || start > WORLD.width) continue;
    context.fillStyle = "#354c62";
    context.fillRect(start, GROUND_Y, end - start, WORLD.height - GROUND_Y);
    context.fillStyle = "#213245";
    context.fillRect(start + 6, GROUND_Y + 20, end - start - 12, WORLD.height - GROUND_Y - 20);
    // 明るい崖の縁と手前の注意模様。穴の内側を足場に見せない。
    context.fillStyle = "#936247";
    context.fillRect(start - 6, GROUND_Y, 6, WORLD.height - GROUND_Y);
    context.fillRect(end, GROUND_Y, 6, WORLD.height - GROUND_Y);
    context.fillStyle = "#e7aa3c";
    for (const edge of [start - 36, end + 8]) {
      context.fillRect(edge, GROUND_Y - 6, 28, 6);
      context.fillStyle = "#694e35";
      context.fillRect(edge + 6, GROUND_Y - 6, 5, 6);
      context.fillRect(edge + 18, GROUND_Y - 6, 5, 6);
      context.fillStyle = "#e7aa3c";
    }
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
  // 読み込み中・404も、赤い鋭角トゲと大きな亀裂で危険を示す。
  // 640×466の素材座標で描き、画像と同じ矩形・足元基準へ変換する。
  context.save();
  context.translate(object.x - width / 2, GROUND_Y - height * feetRatio);
  context.scale(width / 640, height / 466);
  const polygon = (points, color) => {
    context.beginPath();
    points.forEach(([x, y], i) => i ? context.lineTo(x, y) : context.moveTo(x, y));
    context.closePath();
    context.fillStyle = color;
    context.fill();
  };
  // 太い暗色の輪郭。中央・左右の細い判定矩形もこの実体の内側。
  polygon([[1,432],[26,353],[45,274],[89,190],[170,160],[226,157],
    [284,35],[303,8],[320,3],[337,8],[356,35],[414,157],[472,160],
    [552,190],[595,274],[614,353],[638,432],[617,453],[560,464],
    [80,464],[23,453]], "#211c23");
  polygon([[82,263],[85,148],[94,109],[112,100],[135,109],[204,183],
    [220,230],[190,271],[117,281]], "#211c24");
  polygon([[420,230],[436,183],[505,109],[528,100],[546,109],[555,148],
    [558,263],[523,281],[450,271]], "#211c24");
  polygon([[38,356],[57,278],[100,204],[176,177],[232,173],[408,173],
    [464,177],[540,204],[583,278],[602,356],[555,340],[469,375],
    [323,416],[174,375],[85,340]], "#45434f");
  polygon([[38,404],[92,360],[160,390],[179,443],[70,443],[24,427]], "#45434f");
  polygon([[461,443],[480,390],[548,360],[602,404],[616,427],[570,443]], "#45434f");
  // 輪郭より内側に赤い三角を置く。色に頼らず、尖った面でも識別できる。
  for (const points of [
    [[320,17],[235,194],[268,217],[366,217],[400,194]],
    [[118,115],[92,251],[118,266],[181,251],[204,221]],
    [[522,115],[435,221],[459,251],[522,266],[548,251]],
  ]) polygon(points, "#ff2418");
  for (const points of [
    [[320,25],[248,191],[303,145]],
    [[118,121],[101,249],[136,202]],
    [[522,121],[443,232],[497,202]],
  ]) polygon(points, "#ff9b22");
  polygon([[150,290],[193,284],[211,307],[311,259],[256,317],
    [270,332],[221,350],[169,388],[157,371],[185,330]], "#ff302b");
  polygon([[306,436],[346,375],[408,351],[394,318],[485,275],
    [517,283],[440,329],[458,356],[373,390]], "#ff302b");
  context.restore();
}

function drawBird(context, state, bird) {
  const {x, y} = birdCenter(state, bird);
  if (x + BIRD_RADIUS < 0 || x - BIRD_RADIUS > WORLD.width) return;
  context.save();
  // 丸い赤い小鳥。輪郭の外端までが衝突円、羽・くちばしもその内側に描く。
  context.fillStyle = "#e64b65";
  context.strokeStyle = "#652c48";
  context.lineWidth = 4;
  context.beginPath();
  context.arc(x, y, BIRD_RADIUS - 2, 0, Math.PI * 2);
  context.fill(); context.stroke();
  context.clip(); // 羽ばたき中も実体が衝突円の外へはみ出さない。
  if ((bird.speed ?? 0) > 0) {
    // 左端のくちばし・左を見る目・後方の羽で進行方向を示す。版2の正面顔は維持。
    context.fillStyle = "#fff2ce";
    context.beginPath(); context.ellipse(x - 3, y + 10, 15, 12, 0, 0, Math.PI * 2); context.fill();
    const wing = Math.sin(state.animationTime * Math.PI * 6) * 4;
    context.fillStyle = "#9b294f";
    context.beginPath(); context.ellipse(x + 10, y + wing, 12, 7, -.35, 0, Math.PI * 2); context.fill();
    context.fillStyle = "#fff";
    context.beginPath(); context.arc(x - 10, y - 8, 8, 0, Math.PI * 2); context.fill();
    context.fillStyle = "#302638";
    context.beginPath(); context.arc(x - 14, y - 8, 4, 0, Math.PI * 2); context.fill();
    context.strokeStyle = "#652c48"; context.lineWidth = 3;
    context.beginPath(); context.moveTo(x - 18, y - 20); context.lineTo(x - 4, y - 15); context.stroke();
    context.fillStyle = "#ffbb38";
    context.beginPath(); context.moveTo(x - 25, y + 1); context.lineTo(x - 13, y - 3);
    context.lineTo(x - 13, y + 8); context.closePath(); context.fill();
    context.restore();
    return;
  }
  context.fillStyle = "#fff2ce";
  context.beginPath(); context.ellipse(x - 1, y + 10, 15, 12, 0, 0, Math.PI * 2); context.fill();
  // 羽ばたきはゲーム内時間だけで変化。高度と衝突円は動かない。
  const wing = Math.sin(state.animationTime * Math.PI * 6) * 4;
  context.fillStyle = "#9b294f";
  for (const side of [-1, 1]) {
    context.beginPath(); context.ellipse(x + side * 19, y + wing, 5, 11, side * .4, 0, Math.PI * 2); context.fill();
  }
  context.fillStyle = "#fff";
  for (const side of [-1, 1]) {
    context.beginPath(); context.arc(x + side * 8, y - 8, 6, 0, Math.PI * 2); context.fill();
  }
  context.fillStyle = "#302638";
  for (const side of [-1, 1]) {
    context.beginPath(); context.arc(x + side * 8 - 1, y - 7, 3, 0, Math.PI * 2); context.fill();
  }
  context.strokeStyle = "#652c48";
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(x - 14, y - 18); context.lineTo(x - 4, y - 14);
  context.moveTo(x + 14, y - 18); context.lineTo(x + 4, y - 14); context.stroke();
  context.fillStyle = "#ffbb38";
  context.beginPath(); context.moveTo(x - 6, y); context.lineTo(x + 6, y);
  context.lineTo(x, y + 7); context.closePath(); context.fill();
  context.restore();
}

function drawSpike(context, state, spike) {
  const {x,y} = spikeCenter(state, spike);
  if(x + SPIKE_RADIUS < 0 || x - SPIKE_RADIUS > WORLD.width) return;
  context.save();
  // 最大半径26のトゲ球。先端・輪郭を衝突円内に収める。
  context.fillStyle = "#ba4663"; context.strokeStyle = "#61243e"; context.lineWidth = 2;
  context.beginPath();
  for(let i=0;i<24;i++){
    const angle=i*Math.PI/12, r=i%2?17:SPIKE_RADIUS-1;
    const px=x+Math.cos(angle)*r, py=y+Math.sin(angle)*r;
    if(i===0)context.moveTo(px,py);else context.lineTo(px,py);
  }
  context.closePath();context.fill();context.stroke();
  context.fillStyle="#ffd8e0";context.beginPath();context.arc(x-5,y-5,5,0,Math.PI*2);context.fill();
  context.restore();
}
function drawRouteWarnings(context, state) {
  for(const route of state.routeWarnings){
    const x=CHARACTER_X+route.start-state.distance, end=CHARACTER_X+route.end-state.distance;
    context.save();context.fillStyle="rgba(168,62,87,.12)";
    context.fillRect(x,GROUND_Y-route.height-120,end-x,120);
    // 進路を選ぶ前に読める、上空の群れのシルエット。
    context.strokeStyle="#844d66";context.lineWidth=4;
    for(let i=0;i<4;i++){
      const bx=x+60+i*60, by=GROUND_Y-route.height-85-(i%2)*15;
      context.beginPath();context.moveTo(bx-12,by);context.quadraticCurveTo(bx-6,by-10,bx,by);
      context.quadraticCurveTo(bx+6,by-10,bx+12,by);context.stroke();
    }context.restore();
  }
}

function crumbleProgress(state, object) {
  const crumble = state.crumbling.find(p => p.id === object.id);
  if (!crumble) return null;
  return state.supportId === object.id ? Math.max(0, Math.min(1,
    (state.animationTime - state.landingUntil + CHARACTER_SET.landingSeconds) / crumble.seconds)) : 0;
}

function drawPlatform(context, object, state) {
  const { left, top, width, thickness } = platformBounds(object);
  const progress = crumbleProgress(state, object);
  context.fillStyle = progress === null ? "#79c9d4" : progress > .65 ? "#ed9962" : "#e4bc85";
  context.fillRect(left, top, width, thickness);
  context.fillStyle = progress === null ? "#d9f6b0" : "#fff1c1";
  context.fillRect(left, top, width, Math.min(6, thickness));
  context.strokeStyle = progress === null ? "#397b85" : "#65402c";
  context.lineWidth = 2;
  context.strokeRect(left + 1, top + 1, width - 2, thickness - 2);
  if (progress !== null) {
    context.lineWidth = state.supportId === object.id ? 4 : 3;
    for (let x = left + 20; x < left + width - 10; x += 44) {
      context.beginPath();
      context.moveTo(x, top + 4);
      context.lineTo(x - 7, top + 13);
      context.lineTo(x + 4, top + 19);
      context.lineTo(x - 5 - progress * 9, top + thickness - 3);
      if (state.supportId === object.id) {
        context.moveTo(x + 4, top + 19);
        context.lineTo(x + 15 + progress * 12, top + 10);
      }
      context.stroke();
    }
  }
}

function drawWall(context, object) {
  const { left, top, width, height } = wallBounds(object);
  // 全面が危険な電撃ブロック。放電も輪郭も既存の判定矩形内に収める。
  context.save();
  context.translate(left, top);
  context.beginPath();
  context.rect(0, 0, width, height);
  context.clip();
  const unit = Math.min(width, height);
  const rim = Math.min(10, unit * .14);
  const stripe = Math.min(18, unit * .26);
  context.fillStyle = "#ffd84a";
  context.fillRect(0, 0, width, height);
  context.fillStyle = "#202337";
  for (let x = -height; x < width; x += stripe * 2) {
    context.beginPath();
    context.moveTo(x, 0); context.lineTo(x + stripe, 0);
    context.lineTo(x + stripe + height, height); context.lineTo(x + height, height);
    context.closePath(); context.fill();
  }
  context.fillStyle = "#292b50";
  context.fillRect(rim, rim, width - rim * 2, height - rim * 2);

  // 小さな壁でも読める大きな稲妻。縦横を別々に合わせ、細長い壁にも対応。
  const boltWidth = Math.min(width * .57, height * .65);
  const boltHeight = Math.min(height * .66, width * 1.35);
  // 画面より長い壁も、見えている区間に危険マークが残る間隔で繰り返す。
  const bolts = Math.max(1, Math.floor(width / Math.max(120, height * 1.5)));
  for (let i = 0; i < bolts; i++) {
    context.save();
    context.translate(width * (i + .5) / bolts - boltWidth / 2, (height - boltHeight) / 2);
    context.scale(boltWidth, boltHeight);
    context.fillStyle = "#ffe15a";
    context.beginPath();
    context.moveTo(.55, 0); context.lineTo(0, .57); context.lineTo(.42, .57);
    context.lineTo(.26, 1); context.lineTo(1, .36); context.lineTo(.58, .36);
    context.lineTo(.82, 0); context.closePath(); context.fill();
    context.restore();
  }

  // 上面・両側面・底面に静止した太い放電。時間依存や点滅は加えない。
  const inset = rim * .38, amplitude = rim * .65;
  context.beginPath();
  for (const [x, y, dx, dy, length] of [
    [inset, inset, 1, 0, width - inset * 2],
    [width - inset, inset, 0, 1, height - inset * 2],
    [width - inset, height - inset, -1, 0, width - inset * 2],
    [inset, height - inset, 0, -1, height - inset * 2]
  ]) {
    const steps = Math.max(4, Math.round(length / (unit * .25)));
    context.moveTo(x, y);
    for (let i = 1; i <= steps; i++) {
      const along = length * i / steps, zig = i < steps && i % 2 ? amplitude : 0;
      context.lineTo(x + dx * along - dy * zig, y + dy * along + dx * zig);
    }
  }
  context.strokeStyle = "#359cdb"; context.lineWidth = Math.min(6, unit * .09);
  context.lineJoin = "round"; context.stroke();
  context.strokeStyle = "#dcfcff"; context.lineWidth = Math.min(3, unit * .045);
  context.stroke();
  context.restore();
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
      drawPlatform(context, object, state);
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
  drawRouteWarnings(context, state);
  drawObjects(context, state, obstacleImage);
  for (const spike of state.spikes) drawSpike(context, state, spike);
  for (const bird of state.birds) drawBird(context, state, bird);
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

// 終了理由は既存のcollisionのまま。表示専用の判別でsnapshot/DBへ追加しない。
function isFatalHoleFall(state) {
  return state.mode === "finished" && state.reason === "collision" &&
    state.holeFailure === "fatal" && state.feetY > GROUND_Y + PHYSICS_EPSILON;
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
  const retireButton = document.getElementById("runner-retire");
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
  // この画面で観測した終了遷移だけ再生する。保存済み終了状態では再生しない。
  let observedMode=state.mode, fall=null, fallTimestamp=null;
  function observeFall() {
    if(observedMode==='running' && isFatalHoleFall(state)) {
      fall={feetY:state.feetY,velocityY:Math.max(0,state.velocityY)};
      fallTimestamp=null;
      session?.setPresentationBusy?.(true);
    }
    if(state.mode!=='finished')fall=null;
    observedMode=state.mode;
  }
  function displayState() {
    return fall ? {...state,mode:'running',feetY:fall.feetY,velocityY:fall.velocityY,
      supportId:null,airAction:'fall',hitFeedbackRemaining:0,invincibleRemaining:0} : state;
  }
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
    observeFall();
    if (isStagePreview) {
      stageSelect.disabled = !!fall || !active || (state.mode !== "ready" && state.mode !== "finished");
      characterSelect.disabled = stageSelect.disabled;
      stageSelect.value = state.stageId; characterSelect.value = state.characterId;
      updatePreviewCards();
    }
    const text = { ready: "ゲーム開始", running: "一時停止", paused: "再開", finished: "もう一度" }[state.mode];
    if (toggle.textContent !== text) toggle.textContent = text;
    toggle.disabled=!active||controlBusy;
    if(session) {
      toggle.disabled=controlBusy||(!!session.view.error&&!!session.view.savedPlay)||(state.mode==='finished'&&(session.view.dirty||!session.view.result));
      if(state.mode==='finished')toggle.textContent='再挑戦';
      if(session.view.error&&session.view.savedPlay) {toggle.disabled=controlBusy;toggle.textContent='最後の保存から再開（無料）';}
    }
    const retireView=session?.view;
    retireButton.hidden=!retireView?.savedPlay||retireView.savedPlay.status!=='active'||!['running','paused'].includes(state.mode);
    retireButton.disabled=!active||controlBusy||!!fall||!!retireView?.error||!!retireView?.confirmingRetire;
    if(retireView?.confirmingRetire)toggle.disabled=true;
    if(fall) {
      toggle.disabled=true;
      toggle.textContent='落下中…';
    }
    const jumpDisabled = !active || state.mode !== "running";
    if (jumpButton && jumpButton.disabled !== jumpDisabled) jumpButton.disabled = jumpDisabled;
    const mode = fall ? "落下中" : { ready: "開始前", running: "走行中", paused: "一時停止中", finished: "終了" }[state.mode];
    if (modeLabel.textContent !== mode) modeLabel.textContent = mode;
    if (scoreLabel.textContent !== String(state.score)) scoreLabel.textContent = state.score;
    const hearts = "♥".repeat(state.lives) + "♡".repeat(state.initialLives - state.lives);
    const livesDescription = `ハートはあと${state.lives}個（全部で${state.initialLives}個）`;
    if (heartsLabel.textContent !== hearts) heartsLabel.textContent = hearts;
    if (livesLabel.getAttribute("aria-label") !== livesDescription) livesLabel.setAttribute("aria-label", livesDescription);
    const progress = String(progressPercent(state));
    if (progressLabel.textContent !== progress) progressLabel.textContent = progress;
    const hideResult = state.mode !== "finished" || !!fall;
    const resetResult = hideResult && !result.hidden;
    if (result.hidden !== hideResult) result.hidden = hideResult;
    document.getElementById('runner-formal-result').hidden=!session||hideResult;
    if (!hideResult) {
      document.getElementById("runner-result-title").textContent = state.reason === "clear" ? "クリア！" : "ゲームオーバー";
      document.getElementById("runner-result-message").textContent = state.reason === "clear" ?
        "ゴールまで走りきったよ！" : isFatalHoleFall(state) ? "穴に落ちてしまった！もう一度挑戦しよう！" : "トゲ岩にぶつかったよ。もう一度挑戦しよう！";
      document.getElementById("runner-result-score").textContent = state.score;
      document.getElementById("runner-result-progress").textContent = progress;
      result.dataset.reason=state.reason;
      if(session){
        const view=session.view,r=view.result;
        const confirmed=r&&!view.dirty&&!view.error&&view.savedPlay?.status==='finished';
        document.getElementById('runner-result-title').textContent=confirmed?(r.play.result.reason==='retire'?'リタイアしました':r.play.result.reason==='clear'?'クリア！':'ゲームオーバー'):'結果を保存中…';
        document.getElementById('runner-result-message').textContent=confirmed?(r.play.result.reason==='retire'?'途中の得点は最高記録にはなりません。ステージやキャラクターを選び直せます。':isFatalHoleFall(state)?'穴に落ちてしまった！もう一度挑戦しよう！':'保存しました。下のボタンで再挑戦！'):view.error?'保存できませんでした。追加コインなしで最後の保存から再開できます。':'保存が終わるまで待ってね。';
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
    if(fall) {
      const dt=fallTimestamp===null?0:Math.min(Math.max((timestamp-fallTimestamp)/1000,0),MAX_FRAME_SECONDS);
      fall.feetY+=fall.velocityY*dt+state.jump.gravity*dt*dt/2;
      fall.velocityY+=state.jump.gravity*dt;
      fallTimestamp=timestamp;
      // 画像は最大100px。透明余白・画像失敗時の文字を含め上端が消えるまで待つ。
      if(fall.feetY-ANIMATION_SETS[state.characterId].maxSize>=WORLD.height) {
        fall=null;fallTimestamp=null;session?.setPresentationBusy?.(false);updateControls();
      }
    }
    // 消失後も物理モデルの足元へ戻して描かない。
    const painted=displayState();
    renderScene(context, canvas, isFatalHoleFall(state)&&!fall ? {...painted,feetY:WORLD.height+100} : painted, characterImages, obstacleImage);
    if(session) {
      const view=session.view;
      status.hidden=false;
      status.textContent=view.message||(view.error?'保存に失敗しました。'+view.error:'');
      status.hidden=!status.textContent;
      status.style.position='static';
    } else status.hidden = true;
    if (state.mode === "running" || fall) requestRedraw();
  }

  // 通常描画・リサイズ・走行が共通の1枠を使い、ループを二重起動しない。
  function requestRedraw() {
    if (!stopped && active && pendingFrame === null) pendingFrame = requestAnimationFrame(redraw);
  }

  function pauseRunning() {
    if(session&&!stopped){session.pause().catch(saveFailure);syncSession();}
    if (state.mode === "running") state.mode = "paused";
    previousTimestamp = null;
    fallTimestamp = null;
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
    if (!isStagePreview || !active || document.hidden || fall ||
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
    if (!isStagePreview || !active || document.hidden || fall ||
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

  retireButton.addEventListener('click',()=>{
    if(!session||retireButton.disabled||stopped)return;
    try {session.beginRetire();}catch{saveFailure();}
    syncSession();previousTimestamp=null;updateControls();requestRedraw();
  });
  toggle.addEventListener("click", async () => {
    if (!active || document.hidden || controlBusy || fall) return;
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
  const stage=getStage(play.stageId,play.stageVersion);
  if(!stage || s?.version!==2) throw new Error('この途中記録は現在の版では正確に再開できません。購入記録は保持されています。');
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
    (s.mode==='finished' ? !((s.reason==='clear'&&s.distance===state.goalDistance&&s.lives>0)||(s.reason==='collision'&&s.lives===0)||(s.reason==='retire'&&s.lives>0&&s.distance<state.goalDistance)) : s.reason!==null||s.lives<1||s.distance>=state.goalDistance))throw new Error('途中状態の値が不正です。');
  const next=state.course.filter(e=>e.at*SCROLL_SPEED<=s.distance+1e-9).length;
  if(s.nextSpawn!==next||!Array.isArray(s.collectedStarIds)||new Set(s.collectedStarIds).size!==s.collectedStarIds.length||
    !s.collectedStarIds.every(id=>Number.isInteger(id)&&id>=0&&id<next&&state.course[id].type==='star')||
    s.score!==s.collectedStarIds.length*10||s.score!==play.score||s.score>100)throw new Error('スター記録が不正です。');
  // 版7だけ崩れる足場の不在を認める。通常足場・他object・旧版は従来どおり完全一致。
  const presentIds=new Set(Array.isArray(s.objects)?s.objects.map(o=>o?.id):[]);
  const expected=courseObjectsAt(state,s.distance,next,s.collectedStarIds).filter(o=> {
    const crumble=state.crumbling.find(p=>p.id===o.id);
    // 最も早い水平接触から必要秒数が経つ前の消失も拒否する。
    return presentIds.has(o.id)||!crumble||
      platformBounds(o).left+state.speed*crumble.seconds>CHARACTER_X+PLATFORM.footHalfWidth+1e-6;
  });
  if(!Array.isArray(s.objects)||s.objects.length!==expected.length||!s.objects.every((o,i)=>{
    const e=expected[i];return Object.keys(o).length===Object.keys(e).length&&Object.keys(e).every(k=>k==='x'?Math.abs(o.x-e.x)<1e-6:o[k]===e[k]);
  }))throw new Error('コース状態が不正です。');
  if(s.hitPoint!==null && (!s.hitPoint||Object.keys(s.hitPoint).sort().join(',')!=='distance,x,y'||!Object.values(s.hitPoint).every(Number.isFinite)))throw new Error('衝撃状態が不正です。');
  if(s.supportId!==null && s.supportId!=='ground' && !s.objects.some(o=>o.id===s.supportId&&o.type==='platform'&&overlapsPlatform(o)&&Math.abs(platformBounds(o).top-s.feetY)<1e-6))throw new Error('足場状態が不正です。');
  if(s.supportId==='ground'&&(s.feetY!==GROUND_Y||s.velocityY!==0||groundHoleAt(state,s.distance)))throw new Error('接地状態が不正です。');
  const crumble=state.crumbling.find(p=>p.id===s.supportId);
  if(crumble && (s.landingUntil<CHARACTER_SET.landingSeconds ||
    s.landingUntil-CHARACTER_SET.landingSeconds>s.animationTime+PHYSICS_EPSILON ||
    s.animationTime-s.landingUntil+CHARACTER_SET.landingSeconds>=crumble.seconds+PHYSICS_EPSILON))throw new Error('崩れる足場の接地時刻が不正です。');
  Object.assign(state,structuredClone(s));delete state.version;
  if(state.mode!=='finished')state.mode='paused';
  return state;
}
export {snapshotRunner,restoreRunner,STAGES,getStage};

// コースとゲーム状態はDOMから独立。配置の差し替えや決定的なルール検証に使う。
export { ANIMATION_SETS, loadCharacterImages, drawCharacter, describeCharacter, selectionItems, renderSelectionCards, CHARACTERS, getCharacter, COURSE, COLLISION, CHARACTER_X, SPAWN_X, CHARACTER_IMAGE, CHARACTER_SET, OBSTACLE_IMAGE, PLATFORM, GROUND_Y, JUMP, COURSE_LENGTH, SCROLL_SPEED,
  createRunnerState, updateRunner, resumeRunner, startJump, progressPercent, goalX, characterCenter, characterPose,
  spikeCenter, touchesSpike, SPIKE_RADIUS, drawSpike, drawBird, drawRouteWarnings, platformBounds, wallBounds, birdCenter, touchesBird, BIRD_RADIUS, characterBob, shadowY, crumbleProgress, drawPlatform };
