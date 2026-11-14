// すべての描画はこの論理座標で行い、CSS表示サイズ・実ピクセル数と分離する。
const WORLD = Object.freeze({ width: 960, height: 540 });
const MAX_DPR = 2; // 最大1920×1080（RGBAで約8MiB）。表示を拡大しすぎない。
const LANES = Object.freeze([
  { top: 230, height: 112 },
  { top: 374, height: 112 },
]);

function drawBackground(context) {
  const sky = context.createLinearGradient(0, 0, 0, WORLD.height);
  sky.addColorStop(0, "#ccebea");
  sky.addColorStop(1, "#f4f5cf");
  context.fillStyle = sky;
  context.fillRect(0, 0, WORLD.width, WORLD.height);

  context.fillStyle = "#fff5b5";
  context.beginPath();
  context.arc(786, 86, 43, 0, Math.PI * 2);
  context.fill();

  context.fillStyle = "#accfb4";
  context.beginPath();
  context.moveTo(0, 220);
  context.bezierCurveTo(180, 80, 290, 160, 440, 216);
  context.bezierCurveTo(620, 82, 750, 150, 960, 198);
  context.lineTo(960, 540);
  context.lineTo(0, 540);
  context.closePath();
  context.fill();

  context.fillStyle = "#80b994";
  context.beginPath();
  context.moveTo(0, 252);
  context.bezierCurveTo(260, 152, 440, 286, 620, 208);
  context.bezierCurveTo(780, 146, 860, 188, 960, 224);
  context.lineTo(960, 540);
  context.lineTo(0, 540);
  context.closePath();
  context.fill();
}

function drawLanes(context) {
  for (const lane of LANES) {
    context.fillStyle = "#edd4a5";
    context.fillRect(0, lane.top, WORLD.width, lane.height);
    context.fillStyle = "#fae7bd";
    context.fillRect(0, lane.top, WORLD.width, 7);
    context.fillStyle = "#a77d50";
    context.fillRect(0, lane.top + lane.height - 7, WORLD.width, 7);
    context.fillStyle = "#d5b987";
    for (let x = 36; x < WORLD.width; x += 108) {
      context.fillRect(x, lane.top + lane.height - 29, 30, 5);
    }
  }

  context.save();
  context.strokeStyle = "#f4f4ce";
  context.lineWidth = 3;
  context.setLineDash([12, 12]);
  context.beginPath();
  context.moveTo(0, 358);
  context.lineTo(WORLD.width, 358);
  context.stroke();
  context.restore();
}

// 後からキャラクター画像の描画に差し替えるため、背景・レーンと分離。
function drawCharacter(context) {
  const x = 186;
  const ground = LANES[1].top + LANES[1].height - 16;
  context.fillStyle = "#705c4930";
  context.beginPath();
  context.ellipse(x, ground, 38, 9, 0, 0, Math.PI * 2);
  context.fill();

  context.fillStyle = "#344e47";
  context.fillRect(x - 22, ground - 14, 17, 12);
  context.fillRect(x + 8, ground - 14, 17, 12);
  context.fillStyle = "#e99b45";
  context.beginPath();
  context.arc(x, ground - 43, 36, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#fff2cf";
  context.beginPath();
  context.ellipse(x + 9, ground - 38, 24, 23, 0, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = "#344e47";
  context.beginPath();
  context.arc(x + 12, ground - 49, 4, 0, Math.PI * 2);
  context.arc(x + 27, ground - 49, 4, 0, Math.PI * 2);
  context.fill();
}

function renderScene(context, canvas) {
  // width/heightの変更でリセットされた変換も毎回復元する。
  context.setTransform(canvas.width / WORLD.width, 0, 0, canvas.height / WORLD.height, 0, 0);
  drawBackground(context);
  drawLanes(context);
  drawCharacter(context);
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
  let context;
  try {
    context = canvas.getContext("2d", { alpha: false });
  } catch {
    context = null;
  }
  if (!context) {
    stage.hidden = true;
    status.textContent = "ゲーム画面を表示できません。Canvas 2Dに対応したSafariなどで開き直してください。";
    return;
  }

  let active = !document.hidden;
  let pendingFrame = null;

  function redraw() {
    pendingFrame = null;
    if (!active || !resizeCanvas(canvas, stage, viewport)) return;
    renderScene(context, canvas);
    status.hidden = true;
  }

  // イベントが続いた場合だけ1フレームにまとめる。継続するゲームループはない。
  function requestRedraw() {
    if (active && pendingFrame === null) pendingFrame = requestAnimationFrame(redraw);
  }

  function suspendRendering() {
    active = false;
    if (pendingFrame !== null) cancelAnimationFrame(pendingFrame);
    pendingFrame = null;
  }

  function resumeRendering() {
    active = !document.hidden;
    requestRedraw();
  }

  window.addEventListener("resize", requestRedraw);
  window.addEventListener("orientationchange", requestRedraw);
  window.visualViewport?.addEventListener("resize", requestRedraw);
  if (typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(requestRedraw);
    observer.observe(viewport);
  }
  window.addEventListener("pagehide", suspendRendering);
  window.addEventListener("pageshow", resumeRendering);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) suspendRendering();
    else resumeRendering();
  });
  requestRedraw();
}

initializeRunner();
