"""Original, resolution-independent 24-unit line icons for Windows."""
from functools import lru_cache
from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "excel": '<rect x="4" y="3" width="16" height="18" rx="3"/><path d="M4 9h16M4 15h16M10 9v12"/>',
    "open": '<path d="M3 19V7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v1M3 19l3-8h16l-3 8z"/>',
    "apply": '<path d="M9 8H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-4M10 3h11v11M21 3L10 14"/>',
    "refresh": '<path d="M20 8a8 8 0 1 0 0 8M20 3v5h-5"/>',
    "trash": '<path d="M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7M14 10v7"/>',
    "collapse": '<path d="M9 5l7 7-7 7"/>',
    "add": '<path d="M12 5v14M5 12h14"/>',
    "copy": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
    "paste": '<path d="M8 5H5v16h14V5h-3"/><rect x="8" y="3" width="8" height="5" rx="2"/>',
    "network": '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="12" r="3"/><circle cx="6" cy="18" r="3"/><path d="M9 7l6 4M9 17l6-4M6 9v6"/>',
}


@lru_cache(maxsize=100)
def symbol(name, color="#475569"):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</g></svg>'
    renderer=QSvgRenderer(QByteArray(svg.encode()))
    icon=QIcon()
    for size in (16,20,24,32,48,64):
        pix=QPixmap(size,size);pix.fill(Qt.transparent);p=QPainter(pix);renderer.render(p);p.end();icon.addPixmap(pix)
    return icon
