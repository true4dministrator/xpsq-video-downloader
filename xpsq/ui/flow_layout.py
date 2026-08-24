"""FlowLayout：控件放不下时自动折行，窗口拉小内容不截断。

基于 Qt 官方 FlowLayout 示例改写，用 QLayoutItem.sizeHint() + minimumSize() 双保险判断换行，
并为每个子项保留 buffer 防文字贴边重叠。
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, hspacing: int = 12, vspacing: int = 10):
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self._hspace = hspacing
        self._vspace = vspacing

    def addItem(self, item) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:  # noqa: N802
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _item_w(self, item) -> int:
        """子项实际占据宽度：取 sizeHint 与 minimumSize 较大者 + buffer 防止文字贴边。"""
        return max(item.sizeHint().width(), item.minimumSize().width()) + 2

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x, y = m.left(), m.top() + rect.y()
        row_h = 0
        right = rect.right() - m.right()
        for it in self._items:
            w = self._item_w(it)
            # 当前 x 加上本项宽度若超出右边界且不是行首 → 换行
            if x + w > right and x > m.left() + rect.x():
                x = m.left() + rect.x()
                y += row_h + self._vspace
                row_h = 0
            if not test_only:
                # 给子项高度用 sizeHint 的高度（widget 自己画，宽度严格按 _item_w 留够）
                it.setGeometry(QRect(QPoint(x, y), QSize(w - 2, it.sizeHint().height())))
            x += w + self._hspace
            row_h = max(row_h, it.sizeHint().height())
        return y + row_h + m.bottom() - rect.y()
