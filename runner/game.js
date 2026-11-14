// すべての描画はこの論理座標で行い、CSS表示サイズ・実ピクセル数と分離する。
const WORLD = Object.freeze({ width: 960, height: 540 });
const MAX_DPR = 2; // 最大1920×1080（RGBAで約8MiB）。表示を拡大しすぎない。
const SCROLL_SPEED = 200; // 論理座標 px/秒。
const LANE_SWITCH_SECONDS = 0.2;
const MAX_FRAME_SECONDS = 0.05; // 長い処理停止後の急な飛びを防ぐ。
const LANES = Object.freeze([
  { top: 230, height: 112 },
  { top: 374, height: 112 },
]);

function laneGround(index) {
  return LANES[index].top + LANES[index].height - 16;
}

function createRunnerState() {
  return { mode: "ready", distance: 0, animationTime: 0,
    targetLane: 1, ground: laneGround(1), transition: null };
}

function updateRunner(state, seconds) {
  state.distance += SCROLL_SPEED * seconds;
  state.animationTime += seconds;
  if (!state.transition) return;
  const transition = state.transition;
  transition.elapsed = Math.min(transition.elapsed + seconds, LANE_SWITCH_SECONDS);
  const progress = transition.elapsed / LANE_SWITCH_SECONDS;
  const eased = progress * progress * (3 - 2 * progress);
  state.ground = transition.from + (transition.to - transition.from) * eased;
  if (progress === 1) state.transition = null;
}

function switchLane(state) {
  if (state.mode !== "running") return;
  state.targetLane = 1 - state.targetLane;
  // 連打時も表示中の座標から補間し直す。座標をレーン端へ飛ばさない。
  state.transition = { from: state.ground, to: laneGround(state.targetLane), elapsed: 0 };
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

function drawLanes(context, state) {
  for (const lane of LANES) {
    context.fillStyle = "#edd4a5";
    context.fillRect(0, lane.top, WORLD.width, lane.height);
    context.fillStyle = "#fae7bd";
    context.fillRect(0, lane.top, WORLD.width, 7);
    context.fillStyle = "#a77d50";
    context.fillRect(0, lane.top + lane.height - 7, WORLD.width, 7);
    context.fillStyle = "#d5b987";
    for (let x = 36 - state.distance % 108; x < WORLD.width; x += 108) {
      context.fillRect(x, lane.top + lane.height - 29, 30, 5);
    }
  }

  context.save();
  context.strokeStyle = "#f4f4ce";
  context.lineWidth = 3;
  context.setLineDash([12, 12]);
  context.lineDashOffset = state.distance % 24;
  context.beginPath();
  context.moveTo(0, 358);
  context.lineTo(WORLD.width, 358);
  context.stroke();
  context.restore();
}

// 後からキャラクター画像の描画に差し替えるため、背景・レーンと分離。
function drawCharacter(context, state) {
  const x = 186;
  const ground = state.ground;
  const stride = Math.sin(state.animationTime * Math.PI * 6);
  const bob = Math.abs(stride) * 4;
  context.fillStyle = "#705c4930";
  context.beginPath();
  context.ellipse(x, ground, 38, 9, 0, 0, Math.PI * 2);
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

function renderScene(context, canvas, state) {
  // width/heightの変更でリセットされた変換も毎回復元する。
  context.setTransform(canvas.width / WORLD.width, 0, 0, canvas.height / WORLD.height, 0, 0);
  drawBackground(context, state);
  drawLanes(context, state);
  drawCharacter(context, state);
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
  const modeLabel = document.getElementById("runner-mode");
  let context;
  try {
    context = canvas.getContext("2d", { alpha: false });
  } catch {
    context = null;
  }
  if (!context) {
    stage.hidden = true;
    toggle.disabled = true;
    modeLabel.textContent = "表示できません";
    status.textContent = "ゲーム画面を表示できません。Canvas 2Dに対応したSafariなどで開き直してください。";
    return;
  }

  const state = createRunnerState();
  let active = !document.hidden;
  let pendingFrame = null;
  let previousTimestamp = null;
  let sizeDirty = true;

  function updateControls() {
    toggle.textContent = { ready: "ゲーム開始", running: "一時停止", paused: "再開" }[state.mode];
    modeLabel.textContent = { ready: "開始前", running: "走行中", paused: "一時停止中" }[state.mode];
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
      previousTimestamp = timestamp;
    }
    renderScene(context, canvas, state);
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
      state.mode = "running";
      previousTimestamp = null;
      updateControls();
      requestRedraw();
    }
  });
  canvas.addEventListener("pointerdown", event => {
    if (!active || document.hidden || !event.isPrimary || event.button !== 0 || state.mode !== "running") return;
    event.preventDefault();
    switchLane(state);
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
  toggle.disabled = false;
  updateControls();
  requestRedraw();
}

initializeRunner();
