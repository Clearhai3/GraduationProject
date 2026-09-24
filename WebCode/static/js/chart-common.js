// 图表公共皮肤 (大屏 + 单图页共用)
// ECharts 是 JS，读不到 CSS 变量 —— 只能现场冲 CSS 里"取"一次"
const CSSVar = (name, fallback) =>
    getComputedStyle(document.documentElement)
        .getPropertyValue(name).trim() || fallback;

const INK       = CSSVar('--text',      '#1f2328');
const MUTED     = CSSVar('--muted',     '#6b7280');
const AXIS      = CSSVar('--axis',      '#9ca3af');
const BAR_INK   = CSSVar('--chart-ink', '#272727');
const AXIS_W    = 1.5;
const RAMP_FROM = '#e2e2e2';    // 最浅
const RAMP_TO   = '#4a4a4a';    // 最深

// 灰阶生成器: 给两个端点和档数，自动插值出中间色
const grayRamp = (n, from = RAMP_FROM, to = RAMP_TO) => {
    if (n <= 1) return [to];
    const hex = (h) => parseInt(h, 16);
    const rgb = (h) => [hex(h.slice(1, 3)), hex(h.slice(3, 5)), hex(h.slice(5, 7))];
    const [r1, g1, b1] = rgb(from);
    const [r2, g2, b2] = rgb(to);
    return Array.from({ length: n }, (_, i) => {
        const t = i / (n - 1);      // 0 -> 1 均匀取 n 个点
        const mix = (a, b) => Math.round(a + (b - a) * t);
        return `rgb(${mix(r1, r2)}, ${mix(g1, g2)}, ${mix(b1, b2)})`;
    });
};

// 字号随卡片大小缩放: 基准 容器 344px -> 字号 10px; 限制在 8~12
const fontFor = (w) => Math.max(8, Math.min(12, Math.round(w / 34.4)));

// * 参数化: 传谁的数组就调谁; 宽度从第一个图自己的容器上量
function rescaleFonts(charts) {
    if (!charts.length) return;
    const w = charts[0].getDom().getBoundingClientRect().width;
    const fs = fontFor(w);
    charts.forEach(c => {
        const opt = c.getOption();
        const patch = {
            textStyle: { 
                fontSize: fs
            },
            series: [{
                label: { 
                    fontSize: fs 
                }
            }],
        };
        if (opt.xAxis && opt.xAxis.length) {
            patch.xAxis = { axisLabel: { fontSize: fs } };
            patch.yAxis = { axisLabel: { fontSize: fs } };
        }
        c.setOption(patch);
    });
}

// 每个setOption 前面加 ...BASE，就是"套上皮肤"
const BASE = {
    animationDuration: 400,
    animationEasing: 'cubicOut',
    textStyle: {
        color: MUTED,
        fontSize: 10
    },
    tooltip: {
        backgroundColor: CSSVar('--bg', '#ffffff'),
        borderColor: CSSVar('--border', '#e5e7eb'),
        textStyle: { 
            color: INK, 
            fontSize: 13 
        },
        confine: true
    }
};

// 大数字缩写成"万"
const WAN = (v) => v >= 10000 ? (v / 10000).toFixed(1) + '万' : v;

// 数值轴 (y 轴或横向图的 x 轴) ： L 型灰轴，不要刻度、不要网格线
const VALUE_AXIS = {
    type: 'value',
    axisLine: { 
        show: true, 
        lineStyle: { 
            color: AXIS,
            width: AXIS_W 
        } 
    },
    axisTick: { 
        show: false 
    },
    axisLabel: { 
        color: MUTED,
        formatter: WAN 
    },
    splitLine: { 
        show: false 
    },
};

// 类目轴 (动漫名/评分档)
const CAT_AXIS = {
    type: 'category',
    axisLine: { 
        show: true, 
        lineStyle: { 
            color: AXIS, 
            width: AXIS_W 
        } 
    },
    axisTick: {
        show: false
    },
    axisLabel: {
        color: MUTED
    },
    splitLine: {
        show: false
    },
};

// 柱子: 统一中性黑、圆角、不描边
const BAR = {
    type: 'bar',
    itemStyle: {
        color: BAR_INK,
        borderRadius: [4, 4, 0, 0]
    },
    label: {
        show: true,
        position: 'top',
        color: MUTED,
        fontSize: 10,
        formatter: (p) => WAN(p.value)
    }
};

// 横条图专用: 柱子向右长，数字要贴右边 (不是 top)
const HBAR = {
    ...BAR,
    label: {
        ...BAR.label,
        position: 'right'
    }
};