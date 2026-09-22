# Three.js × Blender 声学吉他

用 **Blender（Python 脚本程序化建模）** 生成一把完整民谣吉他，导出 `guitar.glb`，
再用 **Three.js** 渲染并弹奏（Web Audio Karplus-Strong 物理弦合成）。

![stack](https://img.shields.io/badge/three.js-r180-blue) ![blender](https://img.shields.io/badge/blender-5.2-orange)

## 快速开始

```bash
npm install
npm run dev        # http://localhost:5173
```

仓库已包含导出好的 `public/guitar.glb`。如需重新生成模型（需要安装 Blender 5.x，
且 `blender` 需在 PATH 中，否则把 `npm run model` 里的 `blender` 换成完整路径）：

```bash
npm run model                                    # 仅导出 GLB
blender -b --factory-startup -P blender/make_guitar.py -- --glb public/guitar.glb --render preview.png
```

## 操作方式

| 操作 | 说明 |
| --- | --- |
| 点击 / 划过琴弦 | 拨动对应琴弦（按住拖过多根 = 扫弦） |
| `1`–`6` 或 `A S D F G H` | 拨第 6→1 弦 |
| `↑` `↓` / 方向键 | 切换按弦品位（0–14 品） |
| `Space` | 扫弦 |
| `R` 复位 / `M` 静音 | |
| 拖动空白处 / 滚轮 | 旋转视角 / 缩放 |

## 结构

```
threejs-guitar/
├── blender/make_guitar.py   # Blender 无头建模：琴身挖腔、音孔、琴颈、品丝、
│                            # 调弦钮、琴弦、程序化木纹 → Cycles 烘焙贴图 → GLB
├── public/guitar.glb        # 导出的模型（含烘焙贴图）
├── src/
│   ├── config.js            # 与 Blender 脚本共享的几何/乐理常量
│   ├── audio.js             # Karplus-Strong 拨弦合成（分数延迟 + 激励梳状滤波）
│   └── main.js              # 场景、拾取、琴弦分割几何与振动动画
└── index.html
```

### 实现要点

- **建模**：琴身由轮廓多边形挤出 + 双 boolean（内腔 / 音孔）+ 倒角；Chaikin 平滑轮廓；
  各部件按真实尺寸（弦长 648mm、14 品接柄、0.048m 音孔）。
- **贴图**：木纹为 Wave/Noise 程序化节点，用 Cycles `DIFFUSE/COLOR` 烘焙成图片后接回
  Base Color，随 GLB 一起导出（glTF 不支持 Blender 程序化节点）。
- **可弹奏**：琴弦射线拾取（隐形碰撞柱）+ 键盘映射；音频为逐弦缓存的
  Karplus-Strong 缓冲，按品位实时合成频率。
- **振动动画**：加载后把 GLB 里的琴弦替换为分段圆柱，每帧按
  `sin(πu)·cos(2πft)·e^(-λt)` 位移顶点（局部 X/Y 双向），并随能量衰减发光。
