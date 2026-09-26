// 整页 Ctrl + 滚轮缩放。
// 引擎 = CSS zoom 
// 全站所有页面共用，由 base.html

(function () {
    // 档位: 固定几级，且必须精确包含
    const LEVELS = [0.5, 0.67, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2];
    const KEY = 'pageZoom';
    const BASE_COLS = 4;    // [data-zoom-fit] 网格在 100% 时的列数

    let k = 1;          // 当前倍数, 1 = 原始
    let lastWheel = 0;  // 触控板捏合会瞬间连发十几个 wheel
    let btn = null;     // 还原按钮 (DOM 齐了才有)

    // 把倍数写进 CSS 变量。样式表负责应用:
    //  #page-zoom          -> zoom
    //  [data-zoom-fit]     -> 列数 = 100%时的列数 / 倍数
    // 原理: 内容宽 / 列数 = 卡片宽；倍数变大 -> 列数按反比减少，卡片才真的占更大地方
    function applyVars() {
        const root = document.documentElement.style;
        root.setProperty('--page-zoom', String(k));
        root.setProperty('--zoom-cols', String(Math.max(1, Math.round(BASE_COLS / k))));
    }

    // 立即执行: 此刻 <head> 刚解析，body 一个字都没渲染 —— 页面第一帧就是缩好的
    const saved = parseFloat(sessionStorage.getItem(KEY));
    if (saved && Math.abs(saved - 1) > 1e-6) {
        k = Math.max(LEVELS[0], Math.max(LEVELS[LEVELS.length - 1], saved));
    }
    applyVars();

    // 唯一的写入口。给了 anchor = 鼠标锚点 (放大用); 不给 = 按比例滚动 (缩小用)
    function setZoom(next, anchor) {
        if (Math.abs(next - k) < 1e-9) return;

        const k1 = k;       // 旧倍数，换算要用
        const S1 = window.scrollY;  // 旧滚动位置 (视觉像素)
        const oldMax = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);

        // 放大: 先记住鼠标底下是谁、它此刻在哪 (必须抢在改 zoom 之前抓)
        let hit = null, fracY = 0;
        if (anchor) {
            hit = document.elementFromPoint(anchor.x, anchor.y);
            // 抓到 body/html 说明鼠标在空白处，锚点没意义，退回按比例
            if (hit === document.body || hit === document.documentElement) hit = null;
            if (hit) {
                const r1 = hit.getBoundingClientRect();
                // rect 是"局部像素", 鼠标是"视觉像素": 视口在局部空间里只有 innerHeight/k 高
                fracY = (anchor.y / k1 - r1.top) / r1.height;

            }
        }

        // 改倍数
        k = next;
        applyVars();
        void document.documentElement.offsetHeight;     // 逼浏览器立刻重排，下面量到的才是新尺寸

        if (hit) {
            // 让鼠标底下那一点缩放后仍停在鼠标底下 (实测 8 个档位)
            const r2 = hit.getBoundingClientRect();
            window.scrollTo(
                window.scrollX,
                Math.max(0, Math.round(
                    r2.top * k + S1 + fracY * r2.height * k - anchor.y
                ))
            );
        } else {
            // 缩小: 不跟鼠标，按比例滚动 (滚了多深，缩放后还还停在同样的相对深度)
            const newMax = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
            window.scrollTo(0, Math.round((S1 / oldMax) * newMax));
        }

        if (btn) btn.classList.toggle('on', k !==1);
        sessionStorage.setItem(KEY, String(k));
        window.dispatchEvent(new Event('resize'));
        window.dispatchEvent(new Event('pagezoom'));
    }

    // 档位步进: 返回上一档 / 下一档
    function step(dir) {
        let i = 0, best = Infinity;
        for (let j = 0; j < LEVELS.length; j++) {
            const d = Math.abs(LEVELS[j] - k);
            if (d < best) {
                best = d;
                i = j;
            }
        }
        return LEVELS[Math.max(0, Math.min(LEVELS.length - 1, i + dir))];
    }

    // Ctrl + 滚轮
    window.addEventListener('wheel', function (e) {
        if (!e.ctrlKey) return;     // 没按 Crtl -> 页面照常滚，完全不管
        e.preventDefault();         // 挡掉浏览器自带的缩放
        if (e.timeStamp - lastWheel < 80) return;   // 限流: 嫌手感慢就把 80 调小
        lastWheel = e.timeStamp;
        const up = e.deltaY < 0;    // 上滚 = 放大
        setZoom(step(up ? 1 : -1), up ? { x: e.clientX, y: e.clientY} : null);
    }, { passive: false });

    // 事件挂在 DOM 齐了之后 —— 此时才找得到按钮
    document.addEventListener('DOMContentLoaded', function () {
        btn = document.getElementById('page-zoom-reset');
        if (!btn) return;
        if (k !== 1) btn.classList.add('on');
        btn.addEventListener('click', function () {
            setZoom(1, null);
        });
    });

})();