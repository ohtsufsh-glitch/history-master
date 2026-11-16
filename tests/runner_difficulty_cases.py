"""Issue #84 設計表の独立した期待座標と操作。配信データから解を作らない。"""

# Xは中心通過距離、P/Wは (X, 幅, 高さ)、starsは (X, 高さ)。
DESIGN = {
    'S01': dict(length=4000, rocks=[1800, 3000], platforms=[], walls=[],
        stars=[(1040,0),(1280,0),(1420,0),(1800,120),(2080,0),(2260,0),(2440,0),
               (3000,120),(3280,0),(3500,0)], single=[1800,3000], fixed=[]),
    'S02': dict(length=4800, rocks=[1600,2600,2860,3600], platforms=[], walls=[],
        stars=[(1080,0),(1320,0),(1600,120),(2000,0),(2220,0),(2600,120),
               (2860,120),(3200,0),(3600,120),(4300,0)],
        single=[1600,2600,2860,3600], fixed=[]),
    'S03': dict(length=5600, rocks=[1600,2810,2910,4000,4600],
        platforms=[(2600,360,90)], walls=[],
        stars=[(1120,0),(1600,120),(2020,0),(2600,90),(2860,200),(3300,0),
               (4000,120),(4600,120),(4920,0),(5220,0)],
        single=[1600,4000,4600], fixed=[2420,2775]),
    'S04': dict(length=6400, rocks=[1600,5000,5600],
        platforms=[(2800,360,100),(4300,190,90)], walls=[(3040,40,180)],
        stars=[(1100,0),(1600,120),(2000,0),(2800,100),(3040,210),(3600,0),
               (4300,90),(5000,120),(5600,120),(6060,0)],
        single=[1600,5000,5600], fixed=[2620,2948,4120]),
    'S05': dict(length=7200, rocks=[1600,1860,3210,3310,6000],
        platforms=[(3000,360,90),(4600,360,100),(6500,190,100)], walls=[(4840,40,180)],
        stars=[(1100,0),(1600,120),(1860,120),(3000,90),(3260,200),(4600,100),
               (4840,210),(5400,0),(6000,120),(6500,100)],
        single=[1600,1860,6000], fixed=[2820,3175,4420,4748,6320]),
    'S06': dict(length=8000, rocks=[1600,1860,2910,3010,6600,6860],
        platforms=[(2700,360,90),(3900,360,100),(5000,260,80),(5300,320,140)],
        walls=[(4140,40,180),(5540,40,220)],
        stars=[(1100,0),(1600,120),(1860,120),(2700,90),(2960,200),(3900,100),
               (4140,210),(5300,140),(5540,250),(7500,0)],
        single=[1600,1860,6600,6860], fixed=[2520,2875,3720,4048,4820,5070,5448]),
}

EXPECTED_NAMES = dict(zip(DESIGN, ['はじめての草原','トゲ岩の道','スターへの挑戦',
                                  '空中の足場','トゲ岩と足場','マスターコース']))

# 従来テスト向けの200px/s中心到達秒。新たなサイズ・星座標はDESIGNで照合。
EXPECTED = {key: dict(length=s['length'], rocks=[x/200 for x in s['rocks']],
    platforms=[p[0]/200 for p in s['platforms']], upper=[p[0]/200 for p in s['platforms']],
    ground=[x/200 for x,h in s['stars'] if h == 0]) for key,s in DESIGN.items()}


def character_inputs(stage_id, speed=200, duration=.90, perfect=True):
    s = DESIGN[stage_id]
    fixed = s['fixed']
    # 任意の高所スター足場を省略したクリアルートも別に検証する。
    if not perfect and stage_id in ('S04', 'S05'):
        fixed = fixed[:-1]
    return sorted([x/speed-duration/2 for x in s['single']] + [x/speed for x in fixed])


SOLUTIONS = {key: {path: character_inputs(key, perfect=path == 'perfect')
                   for path in ('clear','perfect')} for key in DESIGN}
