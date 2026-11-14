// すべての描画はこの論理座標で行い、CSS表示サイズ・実ピクセル数と分離する。
const WORLD = Object.freeze({ width: 960, height: 540 });
const MAX_DPR = 2; // 最大1920×1080（RGBAで約8MiB）。表示を拡大しすぎない。
const SCROLL_SPEED = 200; // 論理座標 px/秒。
const JUMP_HEIGHT = 120;
const JUMP_DURATION = 0.9;
const JUMP = Object.freeze({ height: JUMP_HEIGHT, duration: JUMP_DURATION,
  initialVelocity: 4 * JUMP_HEIGHT / JUMP_DURATION,
  gravity: 8 * JUMP_HEIGHT / (JUMP_DURATION * JUMP_DURATION) });
const MAX_FRAME_SECONDS = 0.05; // 長い処理停止後の急な飛びを防ぐ。
const COURSE_LENGTH = 6400; // スタートからゴールまでの走行距離（論理px）。
const SIMULATION_STEP = 1 / 120;
const CHARACTER_X = 186;
const GROUND_Y = 470;
const CHARACTER_IMAGE = Object.freeze({ src: "../assets/plush/shiba.webp", maxSize: 100,
  feetRatio: 465 / 512 }); // 既存画像の透明余白を含む、足元の基準位置。
const SPAWN_X = WORLD.width + 48;
const COLLISION = Object.freeze({ characterRadius: 28, obstacleWidth: 52,
  obstacleHeight: 64, obstacleInset: 6, starRadius: 20, starHitRadius: 18 });
// 時刻は右端での出現時刻。heightはスターの地上基準位置からの上昇量。
// 木箱の初接触は約5.37秒後、以後3秒間隔。滞空0.9秒の後に着地猶予を残す。
const COURSE = Object.freeze([
  { at: 0.25, type: "star", height: 0 },
  ...Array.from({ length: 8 }, (_, index) => [
    { at: 1.5 + index * 3, type: "obstacle" },
    { at: 1.5 + index * 3, type: "star", height: JUMP.height },
  ]).flat(),
  { at: 24.25, type: "star", height: 0 },
].map(entry => Object.freeze(entry)));

function createRunnerState(course = COURSE) {
  return { mode: "ready", distance: 0, animationTime: 0,
    ground: GROUND_Y, jumping: false, jumpElapsed: 0, jumpOffset: 0, jumpVelocity: 0,
    elapsed: 0, score: 0, reason: null, objects: [], nextSpawn: 0,
    course: course.map(entry => ({ ...entry })).sort((a, b) => a.at - b.at) };
}

function advanceMotion(state, seconds) {
  state.distance += SCROLL_SPEED * seconds;
  state.animationTime += seconds;
  if (!state.jumping) return;
  state.jumpElapsed = Math.min(state.jumpElapsed + seconds, JUMP.duration);
  if (JUMP.duration - state.jumpElapsed < 1e-9) {
    // 着地は丸め誤差を残さず、次のタップで再び跳べる状態に戻す。
    state.jumping = false;
    state.jumpElapsed = 0;
    state.jumpOffset = 0;
    state.jumpVelocity = 0;
    state.ground = GROUND_Y;
    return;
  }
  const time = state.jumpElapsed;
  // 解析式なので、更新回数に依存せず上昇は減速、下降は加速する。
  state.jumpOffset = Math.max(0, JUMP.initialVelocity * time - JUMP.gravity * time * time / 2);
  state.jumpVelocity = JUMP.initialVelocity - JUMP.gravity * time;
  state.ground = GROUND_Y - state.jumpOffset;
}

function characterCenter(state) {
  const bob = state.jumping ? 0 : Math.abs(Math.sin(state.animationTime * Math.PI * 6)) * 4;
  return { x: CHARACTER_X, y: state.ground - 43 - bob };
}

function touchesObject(state, object) {
  const character = characterCenter(state);
  const ground = GROUND_Y;
  if (object.type === "star") {
    const radius = COLLISION.characterRadius + COLLISION.starHitRadius;
    return Math.hypot(character.x - object.x, character.y - (ground - 43 - (object.height ?? 0))) <= radius;
  }
  const inset = COLLISION.obstacleInset;
  const halfWidth = COLLISION.obstacleWidth / 2 - inset;
  const closestX = Math.max(object.x - halfWidth, Math.min(character.x, object.x + halfWidth));
  const closestY = Math.max(ground - COLLISION.obstacleHeight + inset,
    Math.min(character.y, ground - inset));
  return Math.hypot(character.x - closestX, character.y - closestY) <= COLLISION.characterRadius;
}

function progressPercent(state) {
  if (state.distance >= COURSE_LENGTH) return 100;
  return Math.min(99, Math.max(0, Math.floor(state.distance / COURSE_LENGTH * 100 + 1e-9)));
}

function goalX(state) {
  return CHARACTER_X + COURSE_LENGTH - state.distance;
}

function updateRunner(state, seconds) {
  if (state.mode !== "running" || !Number.isFinite(seconds) || seconds < 0) return;
  let remaining = seconds;
  let gained = 0;
  // 同じ更新内に接触があれば、新たなスターの加点より障害物を優先する。
  do {
    const step = Math.min(SIMULATION_STEP, remaining, Math.max(0, COURSE_LENGTH - state.distance) / SCROLL_SPEED);
    advanceMotion(state, step);
    state.elapsed += step;
    if (COURSE_LENGTH - state.distance < 1e-9) state.distance = COURSE_LENGTH;
    for (const object of state.objects) object.x -= SCROLL_SPEED * step;
    while (state.nextSpawn < state.course.length && state.course[state.nextSpawn].at <= state.elapsed + 1e-9) {
      const entry = state.course[state.nextSpawn];
      state.objects.push({ ...entry, id: state.nextSpawn++,
        x: SPAWN_X - SCROLL_SPEED * Math.max(0, state.elapsed - entry.at) });
    }
    state.objects = state.objects.filter(object => object.x +
      (object.type === "star" ? COLLISION.starRadius : COLLISION.obstacleWidth / 2) >= 0);
    if (state.objects.some(object => object.type === "obstacle" && touchesObject(state, object))) {
      state.mode = "finished";
      state.reason = "collision";
      return;
    }
    state.objects = state.objects.filter(object => {
      if (object.type === "star" && touchesObject(state, object)) {
        gained += 10;
        return false; // 取得済みスターは削除し、二重に加点しない。
      }
      return true;
    });
    // 同じ更新でゴールラインを越えても、直前の障害物判定を優先する。
    if (state.distance >= COURSE_LENGTH) {
      state.mode = "finished";
      state.reason = "clear";
      break;
    }
    remaining -= step;
  } while (remaining > 1e-9);
  state.score += gained;
}

function startJump(state) {
  if (state.mode !== "running" || state.jumping) return false;
  state.jumping = true;
  state.jumpElapsed = 0;
  state.jumpVelocity = JUMP.initialVelocity;
  return true;
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
  const ground = state.ground;
  const stride = state.jumping ? 0 : Math.sin(state.animationTime * Math.PI * 6);
  const bob = Math.abs(stride) * 4;
  context.fillStyle = "#705c4930";
  context.beginPath();
  context.ellipse(x, GROUND_Y, 38, 9, 0, 0, Math.PI * 2);
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

function drawCharacter(context, state, characterImage) {
  if (!characterImage?.complete || !characterImage.naturalWidth || !characterImage.naturalHeight) {
    drawFallbackCharacter(context, state);
    return;
  }
  const scale = CHARACTER_IMAGE.maxSize / Math.max(characterImage.naturalWidth, characterImage.naturalHeight);
  const width = characterImage.naturalWidth * scale;
  const height = characterImage.naturalHeight * scale;
  const bob = state.jumping ? 0 : Math.abs(Math.sin(state.animationTime * Math.PI * 6)) * 4;
  context.fillStyle = "#705c4930";
  context.beginPath();
  context.ellipse(CHARACTER_X, GROUND_Y, 38, 9, 0, 0, Math.PI * 2);
  context.fill();
  context.drawImage(characterImage, CHARACTER_X - width / 2,
    state.ground - height * CHARACTER_IMAGE.feetRatio - bob, width, height);
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

function drawObjects(context, state) {
  for (const object of state.objects) {
    const radius = object.type === "star" ? COLLISION.starRadius : COLLISION.obstacleWidth / 2;
    if (object.x + radius < 0 || object.x - radius > WORLD.width) continue;
    const ground = GROUND_Y;
    if (object.type === "obstacle") {
      const left = object.x - COLLISION.obstacleWidth / 2;
      const top = ground - COLLISION.obstacleHeight;
      context.fillStyle = "#b98045";
      context.fillRect(left, top, COLLISION.obstacleWidth, COLLISION.obstacleHeight);
      context.fillStyle = "#e7b77a";
      context.fillRect(left, top, COLLISION.obstacleWidth, 8);
      context.strokeStyle = "#725033";
      context.lineWidth = 2;
      context.strokeRect(left + 1, top + 1, COLLISION.obstacleWidth - 2, COLLISION.obstacleHeight - 2);
      context.beginPath();
      context.moveTo(left + 7, top + 13);
      context.lineTo(left + COLLISION.obstacleWidth - 7, ground - 7);
      context.moveTo(left + COLLISION.obstacleWidth - 7, top + 13);
      context.lineTo(left + 7, ground - 7);
      context.stroke();
    } else {
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

function renderScene(context, canvas, state, characterImage) {
  // width/heightの変更でリセットされた変換も毎回復元する。
  context.setTransform(canvas.width / WORLD.width, 0, 0, canvas.height / WORLD.height, 0, 0);
  drawBackground(context, state);
  drawGround(context, state);
  drawObjects(context, state);
  drawGoal(context, state);
  drawCharacter(context, state, characterImage);
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

function initializeRunner() {
  const canvas = document.getElementById("runner-canvas");
  const stage = document.getElementById("runner-stage");
  const viewport = document.getElementById("runner-viewport");
  const status = document.getElementById("runner-status");
  const toggle = document.getElementById("runner-toggle");
  const jumpButton = document.getElementById("runner-jump");
  const modeLabel = document.getElementById("runner-mode");
  const scoreLabel = document.getElementById("runner-score");
  const progressLabel = document.getElementById("runner-progress");
  const result = document.getElementById("runner-result");
  let context;
  try {
    context = canvas.getContext("2d", { alpha: false });
  } catch {
    context = null;
  }
  if (!context) {
    stage.hidden = true;
    toggle.disabled = true;
    document.getElementById("runner-jump").disabled = true;
    modeLabel.textContent = "表示できません";
    status.textContent = "ゲーム画面を表示できません。Canvas 2Dに対応したSafariなどで開き直してください。";
    return;
  }

  let state = createRunnerState();
  const characterImage = new Image();
  let active = !document.hidden;
  let pendingFrame = null;
  let previousTimestamp = null;
  let sizeDirty = true;

  function updateControls() {
    const text = { ready: "ゲーム開始", running: "一時停止", paused: "再開", finished: "もう一度" }[state.mode];
    if (toggle.textContent !== text) toggle.textContent = text;
    jumpButton.disabled = !active || state.mode !== "running";
    const mode = { ready: "開始前", running: "走行中", paused: "一時停止中", finished: "終了" }[state.mode];
    if (modeLabel.textContent !== mode) modeLabel.textContent = mode;
    if (scoreLabel.textContent !== String(state.score)) scoreLabel.textContent = state.score;
    const progress = String(progressPercent(state));
    if (progressLabel.textContent !== progress) progressLabel.textContent = progress;
    const hideResult = state.mode !== "finished";
    if (result.hidden !== hideResult) result.hidden = hideResult;
    if (state.mode === "finished") {
      document.getElementById("runner-result-title").textContent = state.reason === "clear" ? "クリア！" : "ゲームオーバー";
      document.getElementById("runner-result-message").textContent = state.reason === "clear" ?
        "ゴールまで走りきったよ！" : "木箱にぶつかったよ。もう一度挑戦しよう！";
      document.getElementById("runner-result-score").textContent = state.score;
      document.getElementById("runner-result-progress").textContent = progress;
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
      updateRunner(state, seconds);
      previousTimestamp = state.mode === "running" ? timestamp : null;
      updateControls();
    }
    renderScene(context, canvas, state, characterImage);
    status.hidden = true;
    if (state.mode === "running") requestRedraw();
  }

  // 通常描画・リサイズ・走行が共通の1枠を使い、ループを二重起動しない。
  function requestRedraw() {
    if (active && pendingFrame === null) pendingFrame = requestAnimationFrame(redraw);
  }

  function pauseRunning() {
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
    sizeDirty = true;
    requestRedraw();
  }

  function resizeAndRedraw() {
    sizeDirty = true;
    requestRedraw();
  }

  toggle.addEventListener("click", () => {
    if (!active || document.hidden) return;
    if (state.mode === "running") {
      pauseRunning();
      if (sizeDirty) requestRedraw();
    } else {
      if (state.mode === "finished") state = createRunnerState();
      state.mode = "running";
      previousTimestamp = null;
      updateControls();
      requestRedraw();
    }
  });
  // タップとキーボード操作のどちらでも同じジャンプ処理を利用する。
  jumpButton.addEventListener("click", () => {
    if (!active || document.hidden || state.mode !== "running") return;
    startJump(state);
  });
  canvas.addEventListener("pointerdown", event => {
    if (!active || document.hidden || !event.isPrimary || event.button !== 0 || state.mode !== "running") return;
    event.preventDefault();
    startJump(state);
  });

  window.addEventListener("resize", resizeAndRedraw);
  window.addEventListener("orientationchange", resizeAndRedraw);
  window.visualViewport?.addEventListener("resize", resizeAndRedraw);
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
  characterImage.onload = requestRedraw;
  characterImage.onerror = requestRedraw;
  characterImage.src = new URL(CHARACTER_IMAGE.src, import.meta.url).href;
  toggle.disabled = false;
  updateControls();
  requestRedraw();
}

initializeRunner();

// コースとゲーム状態はDOMから独立。配置の差し替えや決定的なルール検証に使う。
export { COURSE, COLLISION, CHARACTER_X, CHARACTER_IMAGE, GROUND_Y, JUMP, COURSE_LENGTH, SCROLL_SPEED,
  createRunnerState, updateRunner, startJump, progressPercent, goalX, characterCenter };
