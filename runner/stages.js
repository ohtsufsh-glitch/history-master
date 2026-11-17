// Issue #84 第1段階。座標・攻略入力の設計値は docs/RUNNER_DIFFICULTY_DESIGN.md。
// atは旧200px/s基準の右端出現秒を維持。中心通過距離X = at * 200 + 822。
// 足場と壁のwidth/height、スターheightは論理px。旧通常コースは全版を維持。
const LEGACY_STAGES = Object.freeze([
  {
    stageId: "S01", name: "はじめての草原", difficulty: 1,
    goalDistance: 4000,
    course: [
      { at: 1.09, type: "star", height: 0 },
      { at: 2.29, type: "star", height: 0 },
      { at: 2.99, type: "star", height: 0 },
      { at: 4.89, type: "obstacle" },
      { at: 4.89, type: "star", height: 120 },
      { at: 6.29, type: "star", height: 0 },
      { at: 7.19, type: "star", height: 0 },
      { at: 8.09, type: "star", height: 0 },
      { at: 10.89, type: "obstacle" },
      { at: 10.89, type: "star", height: 120 },
      { at: 12.29, type: "star", height: 0 },
      { at: 13.39, type: "star", height: 0 },
    ],
  },
  {
    stageId: "S02", name: "トゲ岩の道", difficulty: 2,
    goalDistance: 4800,
    course: [
      { at: 1.29, type: "star", height: 0 },
      { at: 2.49, type: "star", height: 0 },
      { at: 3.89, type: "obstacle" },
      { at: 3.89, type: "star", height: 120 },
      { at: 5.89, type: "star", height: 0 },
      { at: 6.99, type: "star", height: 0 },
      { at: 8.89, type: "obstacle" },
      { at: 8.89, type: "star", height: 120 },
      { at: 10.19, type: "obstacle" },
      { at: 10.19, type: "star", height: 120 },
      { at: 11.89, type: "star", height: 0 },
      { at: 13.89, type: "obstacle" },
      { at: 13.89, type: "star", height: 120 },
      { at: 17.39, type: "star", height: 0 },
    ],
  },
  {
    stageId: "S03", name: "スターへの挑戦", difficulty: 3,
    goalDistance: 5600,
    course: [
      { at: 1.49, type: "star", height: 0 },
      { at: 3.89, type: "obstacle" },
      { at: 3.89, type: "star", height: 120 },
      { at: 5.99, type: "star", height: 0 },
      { at: 8.89, type: "platform", width: 360, height: 90 },
      { at: 8.89, type: "star", height: 90 },
      { at: 9.94, type: "obstacle" },
      { at: 10.19, type: "star", height: 200 },
      { at: 10.44, type: "obstacle" },
      { at: 12.39, type: "star", height: 0 },
      { at: 15.89, type: "obstacle" },
      { at: 15.89, type: "star", height: 120 },
      { at: 18.89, type: "obstacle" },
      { at: 18.89, type: "star", height: 120 },
      { at: 20.49, type: "star", height: 0 },
      { at: 21.99, type: "star", height: 0 },
    ],
  },
  {
    stageId: "S04", name: "空中の足場", difficulty: 4,
    goalDistance: 6400,
    course: [
      { at: 1.39, type: "star", height: 0 },
      { at: 3.89, type: "obstacle" },
      { at: 3.89, type: "star", height: 120 },
      { at: 5.89, type: "star", height: 0 },
      { at: 9.89, type: "platform", width: 360, height: 100 },
      { at: 9.89, type: "star", height: 100 },
      { at: 11.09, type: "wall", width: 40, height: 180 },
      { at: 11.09, type: "star", height: 210 },
      { at: 13.89, type: "star", height: 0 },
      { at: 17.39, type: "platform", width: 190, height: 90 },
      { at: 17.39, type: "star", height: 90 },
      { at: 20.89, type: "obstacle" },
      { at: 20.89, type: "star", height: 120 },
      { at: 23.89, type: "obstacle" },
      { at: 23.89, type: "star", height: 120 },
      { at: 26.19, type: "star", height: 0 },
    ],
  },
  {
    stageId: "S05", name: "トゲ岩と足場", difficulty: 5,
    goalDistance: 7200,
    course: [
      { at: 1.39, type: "star", height: 0 },
      { at: 3.89, type: "obstacle" },
      { at: 3.89, type: "star", height: 120 },
      { at: 5.19, type: "obstacle" },
      { at: 5.19, type: "star", height: 120 },
      { at: 10.89, type: "platform", width: 360, height: 90 },
      { at: 10.89, type: "star", height: 90 },
      { at: 11.94, type: "obstacle" },
      { at: 12.19, type: "star", height: 200 },
      { at: 12.44, type: "obstacle" },
      { at: 18.89, type: "platform", width: 360, height: 100 },
      { at: 18.89, type: "star", height: 100 },
      { at: 20.09, type: "wall", width: 40, height: 180 },
      { at: 20.09, type: "star", height: 210 },
      { at: 22.89, type: "star", height: 0 },
      { at: 25.89, type: "obstacle" },
      { at: 25.89, type: "star", height: 120 },
      { at: 28.39, type: "platform", width: 190, height: 100 },
      { at: 28.39, type: "star", height: 100 },
    ],
  },
  {
    stageId: "S06", name: "マスターコース", difficulty: 6,
    goalDistance: 8000,
    course: [
      { at: 1.39, type: "star", height: 0 },
      { at: 3.89, type: "obstacle" },
      { at: 3.89, type: "star", height: 120 },
      { at: 5.19, type: "obstacle" },
      { at: 5.19, type: "star", height: 120 },
      { at: 9.39, type: "platform", width: 360, height: 90 },
      { at: 9.39, type: "star", height: 90 },
      { at: 10.44, type: "obstacle" },
      { at: 10.69, type: "star", height: 200 },
      { at: 10.94, type: "obstacle" },
      { at: 15.39, type: "platform", width: 360, height: 100 },
      { at: 15.39, type: "star", height: 100 },
      { at: 16.59, type: "wall", width: 40, height: 180 },
      { at: 16.59, type: "star", height: 210 },
      { at: 20.89, type: "platform", width: 260, height: 80 },
      { at: 22.39, type: "platform", width: 320, height: 140 },
      { at: 22.39, type: "star", height: 140 },
      { at: 23.59, type: "wall", width: 40, height: 220 },
      { at: 23.59, type: "star", height: 250 },
      { at: 28.89, type: "obstacle" },
      { at: 30.19, type: "obstacle" },
      { at: 33.39, type: "star", height: 0 },
    ],
  },
].map(stage => Object.freeze({ ...stage,
  course: Object.freeze(stage.course.map(entry => Object.freeze(entry))),
})));

// 版1は購入済みプレイの正本。距離・イベント・配列順を編集しない。
// 版2のXはキャラ中心の通過距離。旧at形式に変換し既存の出現・着地を再利用する。
const at = (x, type, dimensions = {}) => ({ at: (x - 822) / 200, type, ...dimensions });
const VERSION2_STAGES = [
  {
    ...LEGACY_STAGES[1], stageVersion: 2, goalDistance: 5000,
    course: [
      at(1080, "star", {height: 0}), at(1320, "star", {height: 0}),
      at(1600, "obstacle"), at(1600, "star", {height: 120}),
      at(2050, "star", {height: 0}),
      at(2800, "platform", {width: 600, height: 90}),
      at(2540, "star", {height: 90}), at(2800, "star", {height: 90}),
      at(2810, "wall", {width: 340, height: 80}),
      at(3040, "star", {height: 90}), at(3400, "star", {height: 0}),
      at(3800, "obstacle"), at(3800, "star", {height: 120}),
      at(4500, "star", {height: 0}),
    ],
  },
  {
    ...LEGACY_STAGES[2], stageVersion: 2, goalDistance: 6000,
    holes: [{start: 2300, end: 2420}, {start: 4500, end: 4630}],
    course: [
      at(1120, "star", {height: 0}),
      at(1600, "obstacle"), at(1600, "star", {height: 120}),
      at(2020, "star", {height: 0}), at(2360, "star", {height: 120}),
      at(3330, "platform", {width: 260, height: 90}),
      at(3330, "star", {height: 90}),
      at(3540, "wall", {width: 520, height: 80}),
      at(3720, "platform", {width: 300, height: 110}),
      at(3630, "star", {height: 110}), at(3850, "star", {height: 110}),
      at(4560, "star", {height: 120}),
      at(5000, "obstacle"), at(5000, "star", {height: 120}),
      at(5500, "star", {height: 0}),
    ],
  },
  {
    ...LEGACY_STAGES[3], stageVersion: 2, goalDistance: 7000,
    // 鳥は固定高度。可変状態を持たず、旧snapshotのobjectsへ型を追加しない。
    birds: [2880, 3260, 3640].map(x => ({x, height: 143})),
    course: [
      at(1000, "star", {height: 0}),
      at(1600, "obstacle"), at(1600, "star", {height: 120}),
      at(2050, "star", {height: 0}),
      at(3220, "platform", {width: 1440, height: 100}),
      at(2580, "star", {height: 100}),
      at(3260, "wall", {width: 1240, height: 90}),
      at(2880, "star", {height: 220}), at(3260, "star", {height: 220}),
      at(3640, "star", {height: 220}), at(4450, "star", {height: 0}),
      at(5000, "obstacle"), at(5000, "star", {height: 120}),
      at(6500, "star", {height: 0}),
    ],
  },
].map(stage => Object.freeze({...stage,
  ...(stage.birds ? {birds: Object.freeze(stage.birds.map(bird => Object.freeze(bird)))} : {}),
  holes: Object.freeze((stage.holes ?? []).map(hole => Object.freeze(hole))),
  course: Object.freeze(stage.course.slice().sort((a, b) => a.at - b.at).map(entry => Object.freeze(entry))),
}));

// 版1・2・3は購入済みプレイの正本。以降も編集しない。
const VERSION3_STAGES = [
  {
    ...LEGACY_STAGES[1], stageVersion: 3, goalDistance: 5000,
    course: [
      at(900, "obstacle"), at(900, "star", {height: 120}),
      at(1320, "star", {height: 0}),
      at(1600, "obstacle"), at(1600, "star", {height: 120}),
      at(2050, "star", {height: 0}),
      at(2800, "platform", {width: 600, height: 90}),
      at(2540, "star", {height: 90}),
      at(2810, "wall", {width: 340, height: 80}),
      at(2840, "wall", {width: 40, height: 170}),
      at(2840, "star", {height: 210}), at(3040, "star", {height: 90}),
      at(3500, "star", {height: 0}),
      at(3800, "obstacle"), at(3800, "star", {height: 120}),
      at(4600, "obstacle"), at(4600, "star", {height: 120}),
    ],
  },
  {
    ...VERSION2_STAGES[1], stageVersion: 3, holeFailure: "fatal",
    holes: [...VERSION2_STAGES[1].holes, {start: 5400, end: 5520}],
    course: [
      at(970, "platform", {width: 540, height: 80}),
      at(1100, "wall", {width: 320, height: 70}), at(1000, "star", {height: 80}),
      ...VERSION2_STAGES[1].course.filter(e => e.type !== "star" || ![1120, 5500].some(x => Math.abs(e.at * 200 + 822 - x) < 1e-6)),
      at(5460, "star", {height: 120}),
    ],
  },
  {
    ...VERSION2_STAGES[2], stageVersion: 3,
    // 世界速度40px/sで左へ飛ぶ。しば犬との遭遇Xは2880/3260/3640。
    birds: [3456, 3912, 4368].map(x => ({x, height: 143, speed: 40})),
    course: [
      at(900, "obstacle"), at(900, "star", {height: 120}),
      ...VERSION2_STAGES[2].course
        .filter(e => e.type !== "star" || ![1000, 2050, 4450, 6500].some(x => Math.abs(e.at * 200 + 822 - x) < 1e-6))
        .map(e => Math.abs(e.at * 200 + 822 - 5000) < 1e-6 ? {...e, at: at(4600, e.type).at} : e),
      at(5810, "platform", {width: 620, height: 90}),
      at(5480, "star", {height: 90}),
      at(5780, "wall", {width: 320, height: 80}),
      at(5800, "wall", {width: 40, height: 170}), at(5800, "star", {height: 210}),
      at(6600, "obstacle"), at(6600, "star", {height: 120}),
    ],
  },
].map(stage => Object.freeze({...stage,
  ...(stage.birds ? {birds: Object.freeze(stage.birds.map(bird => Object.freeze(bird)))} : {}),
  holes: Object.freeze((stage.holes ?? []).map(hole => Object.freeze(hole))),
  course: Object.freeze(stage.course.slice().sort((a, b) => a.at - b.at).map(entry => Object.freeze(entry))),
}));

// Issue #85 高密度版。以前の定義は購入済みプレイのため上で固定する。
// しば犬の通常ジャンプ(200px/s, 高さ120, 0.9秒)で測定。設計・入力幅は
// docs/RUNNER_DENSITY_85.md。補助関数はこの版の静的な定義生成だけに使う。
const rocks = xs => xs.map(x => at(x, "obstacle"));
const platform = (x, width, height) => at(x, "platform", {width, height});
const wall = (start, end, height) => at((start + end) / 2, "wall", {width: end - start, height});
const stars = points => points.map(([x, height]) => at(x, "star", {height}));
const incoming = (encounter, height) => ({x: encounter * 1.6, height, speed: 120});
// 地上壁→足場への着地→上の壁へ再ジャンプ。壁同士の実体は重ねない。
const wallDeck = start => [platform(start + 280, 560, 90),
  wall(start + 100, start + 300, 80), wall(start + 320, start + 360, 170)];
// 長い地上壁は鳥の下を走る抜け道を防ぐ。鳥同士は1.2秒ずつ離す。
const birdDeck = start => [platform(start + 500, 1000, 100), wall(start + 100, start + 950, 90)];
const DENSE_STAGES = [
  {
    ...LEGACY_STAGES[0], stageVersion: 2,
    course: [...rocks([800, 1200, 1600, 2100, 2700, 3300]),
      ...stars([[340,0],[580,0],[800,120],[1200,120],[1600,120],[2100,120],
        [2450,0],[2700,120],[3300,120],[3700,0]])],
  },
  {
    ...LEGACY_STAGES[1], stageVersion: 4, goalDistance: 5000,
    course: [...rocks([420,640,860,1080,1300,1520,2540,2760,2980,3200,4220,4440,4660,4880]),
      ...wallDeck(1760), ...wallDeck(3440),
      ...stars([[420,120],[860,120],[1300,120],[1820,90],[2100,210],
        [2760,120],[3200,120],[3500,90],[3780,210],[4660,120]])],
  },
  {
    ...LEGACY_STAGES[2], stageVersion: 4, goalDistance: 6000, holeFailure: "fatal",
    holes: [420,640,860,1080,1300,1520,2800,3020,3240,3460,3680,3900].map(start => ({start,end:start+100})),
    course: [...rocks([1800,4160,5140,5380,5620,5860]),
      platform(2200,160,90), platform(2470,160,110), wall(2180,2550,80),
      platform(4500,160,90), platform(4770,160,110), wall(4480,4850,80),
      ...stars([[470,120],[910,120],[1350,120],[1800,120],[2200,90],
        [2470,110],[3070,120],[3730,120],[4770,110],[5620,120]])],
  },
  {
    ...LEGACY_STAGES[3], stageVersion: 4, goalDistance: 7000,
    birds: [2180,2420,2660,4940,5180,5420].map(x => incoming(x,143)),
    course: [...rocks([420,630,840,1050,1260,1470,1680,3180,3390,3600,3810,4020,4230,4440,5880,6090,6300,6510,6720,6930]),
      ...birdDeck(1900), ...birdDeck(4660),
      ...stars([[420,120],[1260,120],[2180,220],[2420,220],[2660,220],
        [3810,120],[4940,220],[5180,220],[5420,220],[6510,120]])],
  },
  {
    ...LEGACY_STAGES[4], stageVersion: 2,
    birds: [incoming(1400,133)],
    course: [...rocks([420,680,940,2200,2550,2900,3250,3600,3950,4300,4650,5000,5350,5700,6050,6400]),
      platform(1300,90,90), platform(1500,90,110), platform(1730,90,90), wall(1280,1860,80),
      ...stars([[420,120],[940,120],[1300,90],[1500,110],[1730,90],
        [2550,120],[3600,120],[4650,120],[5700,120],[6400,120]])],
  },
  {
    ...LEGACY_STAGES[5], stageVersion: 2,
    birds: [incoming(1400,133),incoming(1840,123)],
    course: [...rocks([420,660,900,2360,2620,2880,3140,3400,3660,3920,4180,4440,4700,4960,5220,5480,5740,6000,6260,6520,6780]),
      platform(1300,90,90), platform(1500,90,110), platform(1740,90,80), platform(1950,90,105), wall(1280,2080,70),
      ...stars([[420,120],[900,120],[1300,90],[1500,110],[1740,80],[1950,105],
        [3140,120],[4440,120],[5740,120],[6780,120]])],
  },
].map(stage => Object.freeze({...stage,
  holes: Object.freeze((stage.holes ?? []).map(hole => Object.freeze(hole))),
  birds: Object.freeze((stage.birds ?? []).map(bird => Object.freeze(bird))),
  course: Object.freeze(stage.course.slice().sort((a,b) => a.at-b.at).map(entry => Object.freeze(entry))),
}));

// Issue #85 高所・上下分岐版。旧定義には触れず、新規購入だけに適用する。
// 高度は地面からの論理px、phaseはラジアン、periodはゲーム内秒。
const spike = (x, height, amplitude, period, phase = 0) => ({x, height, amplitude, period, phase});
const VERTICAL_STAGES = [
  {
    ...DENSE_STAGES[3], stageVersion: 5,
    birds: [...[2180,2420,2660].map(x => incoming(x,143)), incoming(3620,193),
      ...[5180,5420,5660].map(x => incoming(x,143)), incoming(6660,70)],
    spikes: [spike(3050,90,48,2.4,.4), spike(3980,145,60,2.8,1.2)],
    course: [...rocks([420,630,840,1050,1260,1470,1680,4380,4660,6240,6920]),
      ...birdDeck(1900),
      platform(3240,220,80), platform(3460,220,150), platform(3680,260,150),
      platform(3960,220,80), ...birdDeck(4900),
      ...stars([[420,120],[1260,120],[2180,220],[2660,220],[3240,80],
        [3620,270],[3960,80],[5420,220],[6240,120],[6660,120]])],
  },
  {
    ...DENSE_STAGES[4], stageVersion: 3,
    birds: [incoming(1400,133), incoming(3100,243),
      ...[4140,4380,4620].map((x,i) => incoming(x, i===0?143:i===1?235:240)),
      ...[5100,5340,5580,5820,6060,6300,6540].map((x,i) => incoming(x,143+(i%2)*8))],
    spikes: [spike(1080,150,40,2.6,.2), spike(3260,270,55,2.8,3.59),
      spike(4660,50,25,2.4,2), spike(6880,105,55,2.6,.5)],
    course: [...rocks([420,680,940,2200,4660,7120]),
      // PR #131の短い3足場を維持。
      platform(1300,90,90), platform(1500,90,110), platform(1730,90,90), wall(1280,1860,80),
      platform(2460,220,80), platform(2680,220,150), platform(2920,300,200),
      platform(3260,220,140), platform(3500,220,70),
      // 跳ばずに地上を選べる分岐。上にのみ鳥がいる。
      platform(3940,240,80), platform(4180,280,150), platform(4460,280,150), platform(4700,200,80),
      platform(5200,800,100), platform(6000,800,100), platform(6700,600,100),
      wall(4900,5600,90), wall(5600,6300,90), wall(6300,6950,90),
      ...stars([[420,120],[940,120],[1300,90],[1730,90],[2460,80],
        [3100,320],[3500,70],[4780,80],[5580,220],[6540,220]])],
  },
  {
    ...DENSE_STAGES[5], stageVersion: 3,
    birds: [incoming(1400,133), incoming(1840,123), incoming(3400,253),
      ...[4520,4570,4620,4670].map((x,i) => incoming(x,i%2?280:193)),
      ...[5780,6020,6260,6500,6740,6980,7220,7460,7700].map((x,i) => incoming(x,143+(i%3)*5))],
    spikes: [spike(1080,100,45,2.4,.4), spike(3520,120,40,2.6,1.5),
      spike(3980,190,45,2.8,.8), spike(5300,50,25,2.4,2), spike(7900,100,50,2.6,.5)],
    // 鳥シルエットと警戒色を分岐手前から表示。物理や保存には関与しない。
    routeWarnings: [{start:4100,end:5160,height:150}],
    course: [...rocks([420,660,900,2360,5260]),
      // PR #131の短い4足場を維持。
      platform(1300,90,90), platform(1500,90,110), platform(1740,90,80), platform(1950,90,105), wall(1280,2080,70),
      platform(2600,220,80), platform(2820,220,140), platform(3040,220,185), platform(3280,300,210),
      platform(3620,240,140), platform(3860,220,70),
      platform(4240,240,80), platform(4460,240,150), platform(4840,640,150), platform(5260,240,80),
      platform(5800,800,100), platform(6600,800,100), platform(7450,900,100),
      wall(5500,6300,90), wall(6300,7100,90), wall(7100,7850,90),
      ...stars([[420,120],[900,120],[1300,90],[1740,80],[2600,80],
        [3400,330],[3860,70],[5360,80],[6260,220],[7460,220]])],
  },
].map(stage => Object.freeze({...stage,
  spikes: Object.freeze(stage.spikes.map(s => Object.freeze(s))),
  routeWarnings: Object.freeze((stage.routeWarnings ?? []).map(r => Object.freeze(r))),
  birds: Object.freeze(stage.birds.map(b => Object.freeze(b))),
  course: Object.freeze(stage.course.sort((a,b) => a.at-b.at).map(e => Object.freeze(e))),
}));

// Issue #85 後半の配置改善。公開済み版3を保持し、新規購入だけ版4へ。
const VARIED_STAGES = [
  {
    ...VERTICAL_STAGES[1], stageVersion: 4,
    birds: [...VERTICAL_STAGES[1].birds.slice(0,5),
      ...[[5100,143],[5400,280],[5770,203],[6020,300],[6250,123],[6760,163],[6950,310]]
        .map(([x,height]) => incoming(x,height))],
    spikes: [...VERTICAL_STAGES[1].spikes.slice(0,3),spike(6440,80,35,2.6,.5)],
    course: [...VERTICAL_STAGES[1].course.filter(e => e.at*200+822 < 4800),
      platform(5130,660,100), platform(5670,420,160), platform(6150,500,80), platform(6700,600,120),
      wall(4900,5460,90), wall(5530,5880,150), wall(5880,6400,70), wall(6470,6950,110),
      ...rocks([7120]),...stars([[5580,220],[6760,240]])],
  },
  {
    ...VERTICAL_STAGES[2], stageVersion: 4,
    birds: [...VERTICAL_STAGES[2].birds.slice(0,7),
      ...[[5780,143],[6070,290],[6500,193],[6680,310],[6850,113],[7160,270],[7420,153],[7650,300],[7830,153]]
        .map(([x,height]) => incoming(x,height))],
    spikes: [...VERTICAL_STAGES[2].spikes.slice(0,4),spike(7100,80,35,2.8,.4),spike(7900,50,25,2.6,.5)],
    course: [...VERTICAL_STAGES[2].course.filter(e => e.at*200+822 < 5400),
      platform(5800,800,100), platform(6385,430,150), platform(6830,380,70),
      platform(7270,460,110),platform(7700,400,110),
      wall(5500,6200,90),wall(6200,6600,140),wall(6600,7040,60),wall(7040,7850,100),
      ...stars([[6500,270],[7420,230]])],
  },
].map(stage => Object.freeze({...stage,
  birds: Object.freeze(stage.birds.map(b => Object.freeze(b))),
  spikes: Object.freeze(stage.spikes.map(b => Object.freeze(b))),
  course: Object.freeze(stage.course.sort((a,b) => a.at-b.at).map(e => Object.freeze(e))),
}));

// Issue #85: 高所登りと最終連続足場。購入済み版1〜4は変更しない。
const ASCENT_STAGES = [
  {
    ...VARIED_STAGES[0], stageVersion: 5, holeFailure: "fatal",
    holes: [{start:2500,end:3600}],
    spikes: [...VARIED_STAGES[0].spikes, spike(2590,115,35,2.7,0), spike(3080,230,35,2.3,0)],
  },
  {
    ...VARIED_STAGES[1], stageVersion: 5, holeFailure: "fatal",
    holes: [{start:2640,end:3960},{start:5480,end:7780}],
    birds: [...VARIED_STAGES[1].birds.slice(0,7),
      ...[[5500,340],[5700,143],[5840,320],[6040,193],[6180,240],[6380,113],
        [6520,310],[6720,183],[6860,250],[7060,123],[7200,300],[7400,173],[7540,240],[7740,113]]
        .map(([x,h])=>incoming(x,h))],
    spikes: [...VARIED_STAGES[1].spikes.slice(0,4), spike(2740,115,35,2.5,0), spike(3140,220,35,2.9,0),
      spike(5660,135,25,2.4,.6), spike(6000,150,25,2.5,.3), spike(6340,105,30,2.7,1.2),
      spike(6720,175,25,2.9,1.7), spike(7400,165,25,3.1,2)],
    course: [...VARIED_STAGES[1].course.filter(e=>e.at*200+822<5400),
      ...[[5500,100],[5840,150],[6180,70],[6520,140],[6860,80],[7200,130],[7540,70]]
        .map(([x,h])=>platform(x,220,h)),
      ...stars([[6180,70],[7540,70]])],
  },
].map(stage=>Object.freeze({...stage,
  holes:Object.freeze(stage.holes.map(h=>Object.freeze(h))),
  birds:Object.freeze(stage.birds.map(b=>Object.freeze(b))),
  spikes:Object.freeze(stage.spikes.map(s=>Object.freeze(s))),
  course:Object.freeze(stage.course.slice().sort((a,b)=>a.at-b.at).map(e=>Object.freeze(e))),
}));

// 選択・新規購入は最新版。再開は必ず(ID, 版)で引く。未知版の推測は禁止。
const STAGES = Object.freeze(LEGACY_STAGES.map(stage =>
  ASCENT_STAGES.find(current => current.stageId === stage.stageId) ??
  VARIED_STAGES.find(current => current.stageId === stage.stageId) ??
  VERTICAL_STAGES.find(current => current.stageId === stage.stageId) ??
  DENSE_STAGES.find(current => current.stageId === stage.stageId) ?? stage));
function getStage(stageId, stageVersion) {
  return [...LEGACY_STAGES, ...VERSION2_STAGES, ...VERSION3_STAGES, ...DENSE_STAGES, ...VERTICAL_STAGES, ...VARIED_STAGES, ...ASCENT_STAGES].find(stage =>
    stage.stageId === stageId && (stage.stageVersion ?? 1) === stageVersion);
}
export { STAGES, LEGACY_STAGES, getStage };
