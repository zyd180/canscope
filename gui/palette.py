"""配色方案:信号 20 色调色板 + ECU 节点哈希定色(与 Web 版一致)。"""

# 信号曲线调色板(20 色,按未占用顺序分配)
PALETTE = [
    "#4da3ff", "#ffb84d", "#5ad47a", "#ff6b6b", "#c77dff",
    "#4dd6c8", "#f472b6", "#a3e635", "#fb923c", "#60a5fa",
    "#fda4af", "#93c5fd", "#c4b5fd", "#86efac", "#fcd34d",
    "#7dd3fc", "#f0abfc", "#bef264", "#fdba74", "#a5b4fc",
]

# ECU 节点色(前 10 与信号板相同)
NODE_COLORS = PALETTE[:10]


def node_color(name: str) -> str:
    """ECU 名 → 稳定颜色(哈希保证同一节点恒定同色)。"""
    h = 0
    for ch in name or "?":
        h = (h * 31 + ord(ch)) % len(NODE_COLORS)
    return NODE_COLORS[h]


def alloc_color(used_colors) -> str:
    """从调色板取第一个未占用的颜色;全占用时循环取。"""
    used = set(used_colors or [])
    for c in PALETTE:
        if c not in used:
            return c
    n = len(list(used))
    return PALETTE[n % len(PALETTE)]
