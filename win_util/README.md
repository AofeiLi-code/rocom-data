# win-util

Windows UI 自动化工具，提供图像识别、鼠标键盘控制、OCR 等功能。

## 安装

```bash
# 开发模式安装（推荐，可实时修改代码）
pip install -e /path/to/win_util

# 或从目录安装
cd /path/to/win_util
pip install .
```

## 依赖

- numpy >= 1.26.0
- Pillow >= 10.0.0
- pywin32 >= 300
- mss >= 10.0.0
- opencv-python >= 4.8.0
- aircv >= 1.4.0
- easyocr >= 1.7.0
- loguru >= 0.7.0

## 核心功能

### WinController

整合图像识别、键盘鼠标控制、OCR 的统一控制器：

```python
from win_util import WinController

# 初始化（传入窗口句柄）
controller = WinController(hwnd=window_hwnd)

# 找图并点击
controller.find_and_click("button.png")

# 等待图片出现
controller.wait_for_image("loading.png", timeout=10)

# OCR 识别文字
text = controller.ocr_text(image)

# 键盘按键
controller.press_key('A')
```

### 独立组件

```python
from win_util import ImageFinder, KeyboardController, MouseController, CommonOcr

# 图像查找
finder = ImageFinder(hwnd=window_hwnd)
pos = finder.bg_find_pic_by_cache("target.png", similarity=0.8)

# 鼠标控制
mouse = MouseController(hwnd=window_hwnd)
mouse.bg_left_click(100, 200)

# 键盘控制
keyboard = KeyboardController(window_hwnd)
keyboard.bg_press_key('Enter')

# OCR
ocr = CommonOcr()
result = ocr.ocr(image)
```
